"""Observation Store"""
import sqlite3
import json
from datetime import datetime, timedelta
from typing import List, Optional
from pathlib import Path

from core import Observation, ObservationSource
from .base_store import BaseStore


class ObservationStore(BaseStore):
    _instance: Optional["ObservationStore"] = None

    def __init__(self, db_path: str):
        super().__init__(db_path, "observations", Observation)

    @classmethod
    def get(cls, db_path: str) -> "ObservationStore":
        if not hasattr(cls, "_instance") or cls._instance is None:
            cls._instance = cls(db_path)
        return cls._instance

    def _ensure_table(self) -> None:
        conn = self._connect()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS observations (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                url TEXT,
                raw_content TEXT,
                title TEXT,
                timestamp TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                tags TEXT DEFAULT '[]',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_obs_source ON observations(source)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_obs_timestamp ON observations(timestamp)")
        conn.commit()
        conn.close()

    def _row_to_entity(self, row: sqlite3.Row) -> Observation:
        return Observation(
            id=row["id"],
            source=ObservationSource(row["source"]),
            url=row["url"],
            raw_content=row["raw_content"] or "",
            title=row["title"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            tags=json.loads(row["tags"]) if row["tags"] else [],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def _entity_to_row(self, entity: Observation) -> dict:
        return {
            "id": entity.id,
            "source": entity.source.value,
            "url": entity.url,
            "raw_content": entity.raw_content,
            "title": entity.title,
            "timestamp": entity.timestamp.isoformat(),
            "metadata": json.dumps(entity.metadata, ensure_ascii=False),
            "tags": json.dumps(entity.tags, ensure_ascii=False),
            "created_at": entity.created_at.isoformat(),
        }

    def list_by_source(self, source: ObservationSource, limit: int = 100) -> List[Observation]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM observations WHERE source = ? ORDER BY timestamp DESC LIMIT ?",
                (source.value, limit),
            ).fetchall()
            return [self._row_to_entity(r) for r in rows]
        finally:
            conn.close()

    def get_recent(self, days: int = 7) -> List[Observation]:
        conn = self._connect()
        try:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            rows = conn.execute(
                "SELECT * FROM observations WHERE timestamp >= ? ORDER BY timestamp DESC",
                (cutoff,),
            ).fetchall()
            return [self._row_to_entity(r) for r in rows]
        finally:
            conn.close()
