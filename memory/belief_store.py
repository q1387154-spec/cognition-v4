"""Belief Store"""
import json
import sqlite3
from datetime import datetime
from typing import List, Optional

from core import Belief, BeliefStatus
from .base_store import BaseStore


class BeliefStore(BaseStore):
    _instance: Optional["BeliefStore"] = None

    def __init__(self, db_path: str):
        super().__init__(db_path, "beliefs", Belief)

    @classmethod
    def get(cls, db_path: str) -> "BeliefStore":
        if not hasattr(cls, "_instance") or cls._instance is None:
            cls._instance = cls(db_path)
        return cls._instance

    def get_by_id(self, id: str) -> Optional[Belief]:
        """根据 ID 获取单个 Belief。"""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM beliefs WHERE id=? LIMIT 1", (id,)
            ).fetchone()
            if row:
                return self._row_to_entity(row)
            return None
        finally:
            conn.close()

    def _ensure_table(self) -> None:
        conn = self._connect()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS beliefs (
                id TEXT PRIMARY KEY,
                subject TEXT NOT NULL,
                probability REAL NOT NULL,
                confidence REAL NOT NULL,
                support_evidence_ids TEXT DEFAULT '[]',
                contradict_evidence_ids TEXT DEFAULT '[]',
                update_time TEXT NOT NULL,
                decay_rate REAL DEFAULT 0.01,
                version INTEGER DEFAULT 1,
                status TEXT DEFAULT 'active',
                previous_version_id TEXT,
                domain TEXT DEFAULT 'investment',
                horizon TEXT DEFAULT 'medium',
                metadata TEXT DEFAULT '{}',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_belief_subject ON beliefs(subject)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_belief_status ON beliefs(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_belief_domain ON beliefs(domain)")
        conn.commit()
        conn.close()

    def _row_to_entity(self, row: sqlite3.Row) -> Belief:
        return Belief(
            id=row["id"],
            subject=row["subject"],
            probability=row["probability"],
            confidence=row["confidence"],
            support_evidence_ids=json.loads(row["support_evidence_ids"]),
            contradict_evidence_ids=json.loads(row["contradict_evidence_ids"]),
            update_time=datetime.fromisoformat(row["update_time"]),
            decay_rate=row["decay_rate"],
            version=row["version"],
            status=BeliefStatus(row["status"]),
            previous_version_id=row["previous_version_id"],
            domain=row["domain"],
            horizon=row["horizon"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def _entity_to_row(self, entity: Belief) -> dict:
        return {
            "id": entity.id,
            "subject": entity.subject,
            "probability": entity.probability,
            "confidence": entity.confidence,
            "support_evidence_ids": json.dumps(entity.support_evidence_ids),
            "contradict_evidence_ids": json.dumps(entity.contradict_evidence_ids),
            "update_time": entity.update_time.isoformat(),
            "decay_rate": entity.decay_rate,
            "version": entity.version,
            "status": entity.status.value,
            "previous_version_id": entity.previous_version_id,
            "domain": entity.domain,
            "horizon": entity.horizon,
            "metadata": json.dumps(entity.metadata),
            "created_at": entity.created_at.isoformat(),
        }

    def get_active(self, subject: Optional[str] = None) -> List[Belief]:
        conn = self._connect()
        try:
            if subject:
                rows = conn.execute(
                    "SELECT * FROM beliefs WHERE status='active' AND subject=? ORDER BY update_time DESC",
                    (subject,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM beliefs WHERE status='active' ORDER BY update_time DESC"
                ).fetchall()
            return [self._row_to_entity(r) for r in rows]
        finally:
            conn.close()

    def archive_previous(self, id: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE beliefs SET status='inactive' WHERE id=? AND status='active'",
                (id,),
            )
            conn.commit()
        finally:
            conn.close()
