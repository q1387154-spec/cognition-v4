"""Outcome Store"""
import json
import sqlite3
from datetime import datetime
from typing import List, Optional

from core import Outcome, ErrorType
from .base_store import BaseStore


class OutcomeStore(BaseStore):
    _instance: Optional["OutcomeStore"] = None

    def __init__(self, db_path: str):
        super().__init__(db_path, "outcomes", Outcome)

    @classmethod
    def get(cls, db_path: str) -> "OutcomeStore":
        if not hasattr(cls, "_instance") or cls._instance is None:
            cls._instance = cls(db_path)
        return cls._instance

    def _ensure_table(self) -> None:
        conn = self._connect()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS outcomes (
                id TEXT PRIMARY KEY,
                prediction_id TEXT NOT NULL,
                actual_value REAL NOT NULL,
                actual_result TEXT NOT NULL,
                prediction_error REAL NOT NULL,
                error_type TEXT DEFAULT 'no_error',
                reason TEXT,
                realized_at TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY (prediction_id) REFERENCES predictions(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_out_pred ON outcomes(prediction_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_out_type ON outcomes(error_type)")
        conn.commit()
        conn.close()

    def _row_to_entity(self, row: sqlite3.Row) -> Outcome:
        return Outcome(
            id=row["id"],
            prediction_id=row["prediction_id"],
            actual_value=row["actual_value"],
            actual_result=row["actual_result"],
            prediction_error=row["prediction_error"],
            error_type=ErrorType(row["error_type"]),
            reason=row["reason"],
            realized_at=datetime.fromisoformat(row["realized_at"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def _entity_to_row(self, entity: Outcome) -> dict:
        return {
            "id": entity.id,
            "prediction_id": entity.prediction_id,
            "actual_value": entity.actual_value,
            "actual_result": entity.actual_result,
            "prediction_error": entity.prediction_error,
            "error_type": entity.error_type.value,
            "reason": entity.reason,
            "realized_at": entity.realized_at.isoformat(),
            "metadata": json.dumps(entity.metadata),
            "created_at": entity.created_at.isoformat(),
        }

    def list_by_error_type(self, error_type: ErrorType) -> List[Outcome]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM outcomes WHERE error_type=? ORDER BY realized_at DESC",
                (error_type.value,),
            ).fetchall()
            return [self._row_to_entity(r) for r in rows]
        finally:
            conn.close()

    def get_latest(self, limit: int = 10) -> List[Outcome]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM outcomes ORDER BY realized_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [self._row_to_entity(r) for r in rows]
        finally:
            conn.close()
