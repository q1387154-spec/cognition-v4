"""Base Store — 所有 Store 的基类"""
import sqlite3
from pathlib import Path
from typing import List, Optional, Type, TypeVar, Any
from datetime import datetime
import json

T = TypeVar("T")


class BaseStore:
    """SQLite 持久化基类。"""

    _instances: dict = {}

    @classmethod
    def _reset_singleton(cls):
        """Reset singleton cache (for testing)."""
        cls._instances.clear()

    def __init__(self, db_path: str, table_name: str, entity_class: Type[T]):
        self.db_path = db_path
        self.table_name = table_name
        self.entity_class = entity_class
        self._ensure_table()

    def _ensure_table(self) -> None:
        """子类实现：创建表（如不存在）。"""
        raise NotImplementedError

    def _row_to_entity(self, row: sqlite3.Row) -> T:
        """子类实现：sqlite3.Row → Entity。"""
        raise NotImplementedError

    def _entity_to_row(self, entity: T) -> dict:
        """Entity → dict（用于 INSERT/UPDATE）。"""
        raise NotImplementedError

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn

    # ---- CRUD ----

    def insert(self, entity: T) -> T:
        conn = self._connect()
        try:
            row = self._entity_to_row(entity)
            cols = ", ".join(row.keys())
            placeholders = ", ".join([f":{k}" for k in row.keys()])
            conn.execute(
                f"INSERT INTO {self.table_name} ({cols}) VALUES ({placeholders})",
                row,
            )
            conn.commit()
            return entity
        finally:
            conn.close()

    def get_by_id(self, id: str) -> Optional[T]:
        conn = self._connect()
        try:
            row = conn.execute(
                f"SELECT * FROM {self.table_name} WHERE id = ?", (id,)
            ).fetchone()
            return self._row_to_entity(row) if row else None
        finally:
            conn.close()

    def list_all(self, limit: int = 1000) -> List[T]:
        conn = self._connect()
        try:
            rows = conn.execute(
                f"SELECT * FROM {self.table_name} ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [self._row_to_entity(r) for r in rows]
        finally:
            conn.close()

    def update(self, entity: T) -> T:
        conn = self._connect()
        try:
            row = self._entity_to_row(entity)
            sets = ", ".join([f"{k} = :{k}" for k in row.keys() if k != "id"])
            conn.execute(
                f"UPDATE {self.table_name} SET {sets} WHERE id = :id",
                row,
            )
            conn.commit()
            return entity
        finally:
            conn.close()

    def delete(self, id: str) -> None:
        conn = self._connect()
        try:
            conn.execute(f"DELETE FROM {self.table_name} WHERE id = ?", (id,))
            conn.commit()
        finally:
            conn.close()

    def count(self) -> int:
        conn = self._connect()
        try:
            return conn.execute(
                f"SELECT COUNT(*) FROM {self.table_name}"
            ).fetchone()[0]
        finally:
            conn.close()
