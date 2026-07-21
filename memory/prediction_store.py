"""Prediction Store"""
import json
import sqlite3
from datetime import datetime
from typing import List, Optional

from core import Prediction, PredictionStatus, HorizonLabel, Scenario
from config import ConfigHorizonLabel, days_to_horizon_label
from .base_store import BaseStore


class PredictionStore(BaseStore):
    _instance: Optional["PredictionStore"] = None

    def __init__(self, db_path: str):
        super().__init__(db_path, "predictions", Prediction)

    @classmethod
    def get(cls, db_path: str) -> "PredictionStore":
        if not hasattr(cls, "_instance") or cls._instance is None:
            cls._instance = cls(db_path)
        return cls._instance

    def _ensure_table(self) -> None:
        conn = self._connect()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id TEXT PRIMARY KEY,
                target TEXT NOT NULL,
                belief_id TEXT NOT NULL,
                probability_distribution TEXT DEFAULT '{}',
                scenarios TEXT DEFAULT '[]',
                expected_value REAL,
                confidence REAL DEFAULT 0.5,
                horizon_days INTEGER DEFAULT 90,
                horizon_label TEXT DEFAULT '90d',
                catalyst TEXT,
                regime TEXT DEFAULT 'neutral',
                effective_score REAL DEFAULT 0.5,
                expected_return REAL,
                max_drawdown REAL,
                created_at TEXT NOT NULL,
                bound_evidence_ids TEXT DEFAULT '[]',
                status TEXT DEFAULT 'active',
                metadata TEXT DEFAULT '{}',
                FOREIGN KEY (belief_id) REFERENCES beliefs(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pred_belief ON predictions(belief_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pred_status ON predictions(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pred_target ON predictions(target)")
        conn.commit()
        conn.close()

    def _row_to_entity(self, row: sqlite3.Row) -> Prediction:
        scenarios = [
            Scenario(**s) for s in json.loads(row["scenarios"]) if isinstance(s, dict)
        ]
        return Prediction(
            id=row["id"],
            target=row["target"],
            belief_id=row["belief_id"],
            probability_distribution=json.loads(row["probability_distribution"]),
            scenarios=scenarios,
            expected_value=row["expected_value"],
            confidence=row["confidence"],
            horizon_days=row["horizon_days"],
            horizon_label=HorizonLabel(row["horizon_label"]),
            catalyst=row["catalyst"],
            regime=row["regime"],
            effective_score=row["effective_score"],
            expected_return=row["expected_return"],
            max_drawdown=row["max_drawdown"],
            created_at=datetime.fromisoformat(row["created_at"]),
            bound_evidence_ids=json.loads(row["bound_evidence_ids"]),
            status=PredictionStatus(row["status"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def _entity_to_row(self, entity: Prediction) -> dict:
        return {
            "id": entity.id,
            "target": entity.target,
            "belief_id": entity.belief_id,
            "probability_distribution": json.dumps(entity.probability_distribution),
            "scenarios": json.dumps([s.__dict__ for s in entity.scenarios]),
            "expected_value": entity.expected_value,
            "confidence": entity.confidence,
            "horizon_days": entity.horizon_days,
            "horizon_label": entity.horizon_label.value,
            "catalyst": entity.catalyst,
            "regime": entity.regime,
            "effective_score": entity.effective_score,
            "expected_return": entity.expected_return,
            "max_drawdown": entity.max_drawdown,
            "created_at": entity.created_at.isoformat(),
            "bound_evidence_ids": json.dumps(entity.bound_evidence_ids),
            "status": entity.status.value,
            "metadata": json.dumps(entity.metadata),
        }

    def list_active(self) -> List[Prediction]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM predictions WHERE status='active' ORDER BY created_at DESC"
            ).fetchall()
            return [self._row_to_entity(r) for r in rows]
        finally:
            conn.close()

    def list_due(self, as_of: Optional[datetime] = None) -> List[Prediction]:
        """返回已到期的 Prediction。"""
        if as_of is None:
            as_of = datetime.now()
        conn = self._connect()
        try:
            # 简化：用 created_at + horizon_days 推算
            rows = conn.execute(
                """
                SELECT * FROM predictions
                WHERE status='active'
                AND datetime(created_at, '+' || horizon_days || ' days') <= ?
                ORDER BY created_at
                """,
                (as_of.isoformat(),),
            ).fetchall()
            return [self._row_to_entity(r) for r in rows]
        finally:
            conn.close()

    def mark_realized(self, id: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE predictions SET status='realized' WHERE id=?", (id,)
            )
            conn.commit()
        finally:
            conn.close()

    def update(self, entity: Prediction) -> None:
        """更新整个 Prediction（场景重生成等场景使用）。"""
        conn = self._connect()
        try:
            row = self._entity_to_row(entity)
            conn.execute("""
                UPDATE predictions SET
                    target=?, belief_id=?, probability_distribution=?, scenarios=?,
                    expected_value=?, confidence=?, horizon_days=?, horizon_label=?,
                    catalyst=?, regime=?, effective_score=?, expected_return=?,
                    max_drawdown=?, bound_evidence_ids=?, status=?, metadata=?
                WHERE id=?
            """, (
                row["target"], row["belief_id"],
                row["probability_distribution"], row["scenarios"],
                row["expected_value"], row["confidence"],
                row["horizon_days"], row["horizon_label"],
                row["catalyst"], row["regime"],
                row["effective_score"], row["expected_return"],
                row["max_drawdown"], row["bound_evidence_ids"],
                row["status"], row["metadata"],
                row["id"],
            ))
            conn.commit()
        finally:
            conn.close()
