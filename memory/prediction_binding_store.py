"""Prediction Bindings Store — Evidence ↔ Prediction 多对多绑定（Phase 3）

实现 Phase 3 设计：每条 evidence 知道它在预测什么。

Schema:
- 一条 evidence 可以支撑多个 prediction（共享）
- 一条 prediction 由多条 evidence 支撑
- 绑定类型：direct / inferential / temporal / contradicting
- 绑定强度：0.0~1.0
"""
import json
import sqlite3
from datetime import datetime
from typing import List, Optional, Dict, Any

from .base_store import BaseStore


class PredictionBindingStore:
    """Evidence-Prediction 绑定持久化。"""

    _instance: Optional["PredictionBindingStore"] = None

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_table()

    @classmethod
    def get(cls, db_path: str) -> "PredictionBindingStore":
        if not hasattr(cls, "_instance") or cls._instance is None:
            cls._instance = cls(db_path)
        return cls._instance

    def _ensure_table(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS prediction_bindings (
                id TEXT PRIMARY KEY,
                evidence_id TEXT NOT NULL,
                prediction_id TEXT NOT NULL,
                binding_type TEXT DEFAULT 'direct',
                binding_strength REAL DEFAULT 1.0,
                binding_source TEXT DEFAULT 'auto',
                created_at TEXT NOT NULL,
                UNIQUE(evidence_id, prediction_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pb_evidence ON prediction_bindings(evidence_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pb_prediction ON prediction_bindings(prediction_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pb_type ON prediction_bindings(binding_type)")
        conn.commit()
        conn.close()

    def create(
        self,
        evidence_id: str,
        prediction_id: str,
        binding_type: str = "direct",
        binding_strength: float = 1.0,
        binding_source: str = "auto",
    ) -> Dict[str, Any]:
        """创建一条绑定。"""
        conn = sqlite3.connect(self.db_path)
        now = datetime.now().isoformat()
        binding_id = f"{evidence_id}_{prediction_id}"

        conn.execute("""
            INSERT OR IGNORE INTO prediction_bindings
            (id, evidence_id, prediction_id, binding_type, binding_strength, binding_source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            binding_id, evidence_id, prediction_id,
            binding_type, binding_strength, binding_source, now,
        ))
        conn.commit()
        conn.close()

        return {
            "id": binding_id,
            "evidence_id": evidence_id,
            "prediction_id": prediction_id,
            "binding_type": binding_type,
            "binding_strength": binding_strength,
        }

    def get_evidence_for_prediction(self, prediction_id: str) -> List[Dict]:
        """获取某 prediction 的所有 evidence 绑定。"""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("""
            SELECT evidence_id, binding_type, binding_strength, binding_source, created_at
            FROM prediction_bindings
            WHERE prediction_id = ?
            ORDER BY binding_strength DESC
        """, (prediction_id,)).fetchall()
        conn.close()
        return [
            {"evidence_id": r[0], "type": r[1], "strength": r[2],
             "source": r[3], "created_at": r[4]}
            for r in rows
        ]

    def get_predictions_for_evidence(self, evidence_id: str) -> List[Dict]:
        """获取某 evidence 支撑的所有 predictions。"""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("""
            SELECT prediction_id, binding_type, binding_strength, created_at
            FROM prediction_bindings
            WHERE evidence_id = ?
            ORDER BY binding_strength DESC
        """, (evidence_id,)).fetchall()
        conn.close()
        return [
            {"prediction_id": r[0], "type": r[1], "strength": r[2],
             "created_at": r[3]}
            for r in rows
        ]

    def auto_bind(
        self,
        evidence_id: str,
        prediction_id: str,
        evidence_type: str,
        horizon_label: str,
    ) -> Optional[Dict]:
        """自动根据规则创建绑定（无 LLM 时使用）。

        规则：
        - quantitative → direct（直接定量支撑）
        - qualitative → inferential（推断性）
        - categorical → contradicting（矛盾支撑）
        """
        type_map = {
            "quantitative": "direct",
            "qualitative": "inferential",
            "categorical": "contradicting",
        }
        strength_map = {
            "direct": 0.9,
            "inferential": 0.6,
            "contradicting": 0.7,
        }
        binding_type = type_map.get(evidence_type, "temporal")
        strength = strength_map.get(binding_type, 0.5)

        return self.create(
            evidence_id=evidence_id,
            prediction_id=prediction_id,
            binding_type=binding_type,
            binding_strength=strength,
            binding_source="rule_auto",
        )

    def count(self) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute("SELECT count(*) FROM prediction_bindings").fetchone()[0]
        finally:
            conn.close()