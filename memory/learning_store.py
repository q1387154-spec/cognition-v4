"""Learning Store"""
import json
import sqlite3
from datetime import datetime
from typing import List, Optional

from core import Learning, LearningType, CausalEdgeUpdate
from .base_store import BaseStore


class LearningStore(BaseStore):
    _instance: Optional["LearningStore"] = None

    def __init__(self, db_path: str):
        super().__init__(db_path, "learning", Learning)

    @classmethod
    def get(cls, db_path: str) -> "LearningStore":
        if not hasattr(cls, "_instance") or cls._instance is None:
            cls._instance = cls(db_path)
        return cls._instance

    def _ensure_table(self) -> None:
        conn = self._connect()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS learning (
                id TEXT PRIMARY KEY,
                outcome_id TEXT NOT NULL,
                prediction_id TEXT NOT NULL,
                belief_id TEXT NOT NULL,
                learning_type TEXT NOT NULL,
                feature_updates TEXT DEFAULT '{}',
                causal_updates TEXT DEFAULT '[]',
                weight_updates TEXT DEFAULT '{}',
                belief_adjustment REAL DEFAULT 0.0,
                accuracy_delta REAL DEFAULT 0.0,
                regime_correction TEXT,
                counterfactuals TEXT DEFAULT '[]',
                learned_at TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_learn_pred ON learning(prediction_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_learn_type ON learning(learning_type)")
        conn.commit()
        conn.close()

    def _row_to_entity(self, row: sqlite3.Row) -> Learning:
        causal_raw = json.loads(row["causal_updates"]) if row["causal_updates"] else []
        causal_updates = [CausalEdgeUpdate(**u) for u in causal_raw]
        return Learning(
            id=row["id"],
            outcome_id=row["outcome_id"],
            prediction_id=row["prediction_id"],
            belief_id=row["belief_id"],
            learning_type=LearningType(row["learning_type"]),
            feature_updates=json.loads(row["feature_updates"]) if row["feature_updates"] else {},
            causal_updates=causal_updates,
            weight_updates=json.loads(row["weight_updates"]) if row["weight_updates"] else {},
            belief_adjustment=row["belief_adjustment"],
            accuracy_delta=row["accuracy_delta"],
            regime_correction=row["regime_correction"],
            counterfactuals=json.loads(row["counterfactuals"]) if row["counterfactuals"] else [],
            learned_at=datetime.fromisoformat(row["learned_at"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def _entity_to_row(self, entity: Learning) -> dict:
        return {
            "id": entity.id,
            "outcome_id": entity.outcome_id,
            "prediction_id": entity.prediction_id,
            "belief_id": entity.belief_id,
            "learning_type": entity.learning_type.value,
            "feature_updates": json.dumps(entity.feature_updates),
            "causal_updates": json.dumps([u.__dict__ for u in entity.causal_updates]),
            "weight_updates": json.dumps(entity.weight_updates),
            "belief_adjustment": entity.belief_adjustment,
            "accuracy_delta": entity.accuracy_delta,
            "regime_correction": entity.regime_correction,
            "counterfactuals": json.dumps(entity.counterfactuals),
            "learned_at": entity.learned_at.isoformat(),
            "metadata": json.dumps(entity.metadata),
            "created_at": entity.created_at.isoformat(),
        }

    def list_by_type(self, learning_type: LearningType) -> List[Learning]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM learning WHERE learning_type=? ORDER BY learned_at DESC",
                (learning_type.value,),
            ).fetchall()
            return [self._row_to_entity(r) for r in rows]
        finally:
            conn.close()
