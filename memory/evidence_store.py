"""Evidence Store"""
import json
import sqlite3
from datetime import datetime
from typing import List, Optional

from core import Evidence, EvidenceType, NoveltyLevel, HorizonType
from .base_store import BaseStore


class EvidenceStore(BaseStore):
    _instance: Optional["EvidenceStore"] = None

    def __init__(self, db_path: str):
        super().__init__(db_path, "evidence", Evidence)

    @classmethod
    def get(cls, db_path: str) -> "EvidenceStore":
        if not hasattr(cls, "_instance") or cls._instance is None:
            cls._instance = cls(db_path)
        return cls._instance

    def _ensure_table(self) -> None:
        conn = self._connect()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS evidence (
                id TEXT PRIMARY KEY,
                observation_ids TEXT NOT NULL,
                content TEXT NOT NULL,
                type TEXT NOT NULL,
                confidence REAL NOT NULL,
                novelty TEXT NOT NULL,
                horizon TEXT NOT NULL,
                importance REAL NOT NULL,
                domain TEXT DEFAULT 'investment',
                summary TEXT,
                binding_id TEXT,
                tags TEXT DEFAULT '[]',
                metadata TEXT DEFAULT '{}',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ev_domain ON evidence(domain)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ev_horizon ON evidence(horizon)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ev_binding ON evidence(binding_id)")
        conn.commit()
        conn.close()

    def _row_to_entity(self, row: sqlite3.Row) -> Evidence:
        return Evidence(
            id=row["id"],
            observation_ids=json.loads(row["observation_ids"]),
            content=row["content"],
            type=EvidenceType(row["type"]),
            confidence=row["confidence"],
            novelty=NoveltyLevel(row["novelty"]),
            horizon=HorizonType(row["horizon"]),
            importance=row["importance"],
            domain=row["domain"],
            summary=row["summary"],
            binding_id=row["binding_id"],
            tags=json.loads(row["tags"]) if row["tags"] else [],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def _entity_to_row(self, entity: Evidence) -> dict:
        return {
            "id": entity.id,
            "observation_ids": json.dumps(entity.observation_ids, ensure_ascii=False),
            "content": entity.content,
            "type": entity.type.value,
            "confidence": entity.confidence,
            "novelty": entity.novelty.value,
            "horizon": entity.horizon.value,
            "importance": entity.importance,
            "domain": entity.domain,
            "summary": entity.summary,
            "binding_id": entity.binding_id,
            "tags": json.dumps(entity.tags, ensure_ascii=False),
            "metadata": json.dumps(entity.metadata, ensure_ascii=False),
            "created_at": entity.created_at.isoformat(),
        }

    def list_by_domain(self, domain: str, limit: int = 100) -> List[Evidence]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM evidence WHERE domain = ? ORDER BY created_at DESC LIMIT ?",
                (domain, limit),
            ).fetchall()
            return [self._row_to_entity(r) for r in rows]
        finally:
            conn.close()

    def list_by_binding(self, binding_id: str) -> List[Evidence]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM evidence WHERE binding_id = ? ORDER BY created_at",
                (binding_id,),
            ).fetchall()
            return [self._row_to_entity(r) for r in rows]
        finally:
            conn.close()

    def list_unbound(self, limit: int = 100) -> List[Evidence]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM evidence WHERE binding_id IS NULL ORDER BY importance DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [self._row_to_entity(r) for r in rows]
        finally:
            conn.close()
