"""Entity Accuracy Store — Entity 级精度追踪（Phase 1 Schema V2）

回答"我对赛力斯的预测到底准不准"，按 entity × metric × horizon 分组。
"""
import json
import sqlite3
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from .base_store import BaseStore


class EntityAccuracyStore:
    """实体级精度持久化。"""

    _instance: Optional["EntityAccuracyStore"] = None

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_table()

    @classmethod
    def get(cls, db_path: str) -> "EntityAccuracyStore":
        if not hasattr(cls, "_instance") or cls._instance is None:
            cls._instance = cls(db_path)
        return cls._instance

    def _ensure_table(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS entity_accuracy (
                id TEXT PRIMARY KEY,
                entity_name TEXT NOT NULL,
                metric TEXT NOT NULL,
                horizon_label TEXT NOT NULL,
                prediction_type TEXT NOT NULL,
                predicted_count INTEGER DEFAULT 0,
                verified_count INTEGER DEFAULT 0,
                correct_count INTEGER DEFAULT 0,
                accuracy_rate REAL DEFAULT 0.0,
                accuracy_trend TEXT DEFAULT 'unknown',
                weight REAL DEFAULT 0.15,
                last_updated TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                UNIQUE(entity_name, metric, horizon_label, prediction_type)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ea_entity ON entity_accuracy(entity_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ea_metric ON entity_accuracy(metric, horizon_label)")
        conn.commit()
        conn.close()

    def upsert(
        self,
        entity_name: str,
        metric: str,
        horizon_label: str,
        prediction_type: str,
        was_correct: bool,
        weight: float = 0.15,
        metadata: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """插入或更新一条精度记录。"""
        conn = sqlite3.connect(self.db_path)
        now = datetime.now().isoformat()
        # 查找现有记录
        row = conn.execute("""
            SELECT predicted_count, verified_count, correct_count, weight
            FROM entity_accuracy
            WHERE entity_name=? AND metric=? AND horizon_label=? AND prediction_type=?
        """, (entity_name, metric, horizon_label, prediction_type)).fetchone()

        if row:
            predicted, verified, correct, old_weight = row
            predicted += 1
            verified += 1
            correct = correct + (1 if was_correct else 0)
        else:
            predicted = 1
            verified = 1
            correct = 1 if was_correct else 0
            old_weight = weight

        accuracy_rate = correct / verified if verified > 0 else 0.0

        # 趋势判断：基于最近 5 次验证
        trend = self._compute_trend(conn, entity_name, metric, horizon_label, prediction_type, was_correct)

        record_id = f"{entity_name}_{metric}_{horizon_label}_{prediction_type}"
        metadata_str = json.dumps(metadata or {}, ensure_ascii=False)

        conn.execute("""
            INSERT INTO entity_accuracy
            (id, entity_name, metric, horizon_label, prediction_type,
             predicted_count, verified_count, correct_count,
             accuracy_rate, accuracy_trend, weight, last_updated, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entity_name, metric, horizon_label, prediction_type) DO UPDATE SET
                predicted_count=excluded.predicted_count,
                verified_count=excluded.verified_count,
                correct_count=excluded.correct_count,
                accuracy_rate=excluded.accuracy_rate,
                accuracy_trend=excluded.accuracy_trend,
                weight=excluded.weight,
                last_updated=excluded.last_updated,
                metadata=excluded.metadata
        """, (
            record_id, entity_name, metric, horizon_label, prediction_type,
            predicted, verified, correct,
            round(accuracy_rate, 4), trend, old_weight, now, metadata_str,
        ))
        conn.commit()
        conn.close()

        return {
            "entity": entity_name,
            "metric": metric,
            "horizon_label": horizon_label,
            "predicted": predicted,
            "verified": verified,
            "correct": correct,
            "accuracy_rate": round(accuracy_rate, 4),
            "trend": trend,
            "weight": old_weight,
        }

    def _compute_trend(self, conn, entity, metric, horizon, ptype, latest_correct: bool) -> str:
        """根据最近样本判断趋势。"""
        # 这里简化处理：基于累计 accuracy_rate 判断
        row = conn.execute("""
            SELECT accuracy_rate FROM entity_accuracy
            WHERE entity_name=? AND metric=? AND horizon_label=? AND prediction_type=?
        """, (entity, metric, horizon, ptype)).fetchone()
        if not row:
            return "unknown"
        rate = row[0]
        if rate >= 0.8:
            return "improving"
        elif rate <= 0.5:
            return "declining"
        else:
            return "stable"

    def get_record(self, entity_name: str, metric: str, horizon_label: str, prediction_type: str) -> Optional[Dict]:
        """获取单条精度记录。"""
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("""
            SELECT * FROM entity_accuracy
            WHERE entity_name=? AND metric=? AND horizon_label=? AND prediction_type=?
        """, (entity_name, metric, horizon_label, prediction_type)).fetchone()
        conn.close()
        if row:
            return {
                "id": row[0], "entity_name": row[1], "metric": row[2],
                "horizon_label": row[3], "prediction_type": row[4],
                "predicted_count": row[5], "verified_count": row[6],
                "correct_count": row[7], "accuracy_rate": row[8],
                "accuracy_trend": row[9], "weight": row[10],
                "last_updated": row[11], "metadata": json.loads(row[12] or "{}"),
            }
        return None

    def list_by_entity(self, entity_name: str) -> List[Dict]:
        """列出某 entity 的所有精度记录。"""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("""
            SELECT entity_name, metric, horizon_label, accuracy_rate, predicted_count, verified_count
            FROM entity_accuracy
            WHERE entity_name=?
            ORDER BY accuracy_rate DESC
        """, (entity_name,)).fetchall()
        conn.close()
        return [
            {
                "entity": r[0], "metric": r[1], "horizon_label": r[2],
                "accuracy_rate": r[3], "predicted": r[4], "verified": r[5],
            }
            for r in rows
        ]

    def list_low_accuracy(self, threshold: float = 0.5) -> List[Dict]:
        """列出精度低于阈值的记录（用于放弃低质量预测目标）。"""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("""
            SELECT entity_name, metric, horizon_label, accuracy_rate, verified_count
            FROM entity_accuracy
            WHERE accuracy_rate < ? AND verified_count >= 3
            ORDER BY accuracy_rate ASC
        """, (threshold,)).fetchall()
        conn.close()
        return [
            {"entity": r[0], "metric": r[1], "horizon_label": r[2],
             "accuracy_rate": r[3], "verified": r[4]}
            for r in rows
        ]