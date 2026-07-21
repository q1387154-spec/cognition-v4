"""Causal Graph Store — 因果图谱持久化（节点/边分别表）"""
import json
import sqlite3
from datetime import datetime
from typing import List, Optional, Dict, Set, Tuple

from .base_store import BaseStore


class CausalGraph:
    """内存因果图谱。"""

    def __init__(self):
        self.nodes: Dict[str, dict] = {}   # node_id → {type, label, metadata}
        self.edges: Dict[str, List[dict]] = {}  # from_node → [{to, weight, type}]
        self.edge_set: Set[Tuple[str, str]] = set()

    def add_node(self, node_id: str, node_type: str, label: str = "", metadata: dict = None):
        self.nodes[node_id] = {
            "type": node_type, "label": label, "metadata": metadata or {}
        }
        if node_id not in self.edges:
            self.edges[node_id] = []

    def add_edge(self, from_node: str, to_node: str, weight: float = 1.0, edge_type: str = "causes"):
        if from_node not in self.nodes:
            self.add_node(from_node, "unknown")
        if to_node not in self.nodes:
            self.add_node(to_node, "unknown")
        if (from_node, to_node) not in self.edge_set:
            self.edges.setdefault(from_node, []).append({"to": to_node, "weight": weight, "type": edge_type})
            self.edge_set.add((from_node, to_node))

    def get_downstream(self, node_id: str, depth: int = 3) -> List[str]:
        """获取下游节点（用于传导分析）。"""
        result = []
        queue = [(node_id, 0)]
        visited = {node_id}
        while queue:
            cur, d = queue.pop(0)
            if d >= depth:
                continue
            for edge in self.edges.get(cur, []):
                nxt = edge["to"]
                if nxt not in visited:
                    visited.add(nxt)
                    result.append(nxt)
                    queue.append((nxt, d + 1))
        return result

    def get_upstream(self, node_id: str, depth: int = 3) -> List[str]:
        """获取上游节点。"""
        visited = {node_id}
        result = []
        queue = [(node_id, 0)]
        while queue:
            cur, d = queue.pop(0)
            if d >= depth:
                continue
            for from_node, edges in self.edges.items():
                for edge in edges:
                    if edge["to"] == cur and from_node not in visited:
                        visited.add(from_node)
                        result.append(from_node)
                        queue.append((from_node, d + 1))
        return result

    def update_edge_weight(self, from_node: str, to_node: str, new_weight: float):
        for edge in self.edges.get(from_node, []):
            if edge["to"] == to_node:
                edge["weight"] = new_weight

    def to_dict(self) -> dict:
        return {"nodes": self.nodes, "edges": self.edges}

    @classmethod
    def from_dict(cls, data: dict) -> "CausalGraph":
        g = cls()
        g.nodes = data.get("nodes", {})
        g.edges = data.get("edges", {})
        g.edge_set = {
            (f, e["to"]) for f, edges in g.edges.items() for e in edges
        }
        return g


class CausalGraphStore:
    """因果图谱持久化（节点/边分离为独立表）。"""

    _instance: Optional["CausalGraphStore"] = None

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_table()

    @classmethod
    def get(cls, db_path: str) -> "CausalGraphStore":
        if not hasattr(cls, "_instance") or cls._instance is None:
            cls._instance = cls(db_path)
        return cls._instance

    def _ensure_table(self) -> None:
        conn = sqlite3.connect(self.db_path)
        # 节点表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS causal_nodes (
                id TEXT PRIMARY KEY,
                node_type TEXT NOT NULL,
                label TEXT,
                metadata TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        # 边表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS causal_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_node TEXT NOT NULL,
                to_node TEXT NOT NULL,
                weight REAL DEFAULT 1.0,
                edge_type TEXT DEFAULT 'causes',
                created_at TEXT NOT NULL,
                UNIQUE(from_node, to_node)
            )
        """)
        # 索引
        conn.execute("CREATE INDEX IF NOT EXISTS idx_causal_edges_from ON causal_edges(from_node)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_causal_edges_to ON causal_edges(to_node)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_causal_nodes_type ON causal_nodes(node_type)")
        conn.commit()
        conn.close()

    def save(self, graph: CausalGraph) -> None:
        """保存图谱到节点/边表（增量更新）。"""
        conn = sqlite3.connect(self.db_path)
        now = datetime.now().isoformat()
        try:
            # 1. 写入节点（upsert）
            for node_id, info in graph.nodes.items():
                conn.execute("""
                    INSERT INTO causal_nodes (id, node_type, label, metadata, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        node_type=excluded.node_type,
                        label=excluded.label,
                        metadata=excluded.metadata,
                        updated_at=excluded.updated_at
                """, (
                    node_id, info.get("type", "unknown"),
                    info.get("label", ""),
                    json.dumps(info.get("metadata", {}), ensure_ascii=False),
                    now, now,
                ))
            # 2. 写入边
            for from_node, edges in graph.edges.items():
                for edge in edges:
                    conn.execute("""
                        INSERT INTO causal_edges (from_node, to_node, weight, edge_type, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(from_node, to_node) DO UPDATE SET
                            weight=excluded.weight,
                            edge_type=excluded.edge_type
                    """, (
                        from_node, edge["to"],
                        edge.get("weight", 1.0),
                        edge.get("type", "causes"),
                        now,
                    ))
            # 3. 向后兼容：同步更新旧的 causal_graph 整表
            data = json.dumps(graph.to_dict(), ensure_ascii=False)
            conn.execute("DELETE FROM causal_graph")
            conn.execute(
                "INSERT INTO causal_graph (graph_data, updated_at) VALUES (?, ?)",
                (data, now),
            )
            conn.commit()
        finally:
            conn.close()

    def load(self) -> CausalGraph:
        """从节点/边表加载图谱（重启恢复）。"""
        conn = sqlite3.connect(self.db_path)
        graph = CausalGraph()
        # 加载节点
        for row in conn.execute("SELECT id, node_type, label, metadata FROM causal_nodes").fetchall():
            node_id, ntype, label, metadata = row
            graph.nodes[node_id] = {
                "type": ntype,
                "label": label or "",
                "metadata": json.loads(metadata) if metadata else {},
            }
            graph.edges.setdefault(node_id, [])
        # 加载边
        for row in conn.execute("SELECT from_node, to_node, weight, edge_type FROM causal_edges").fetchall():
            from_node, to_node, weight, edge_type = row
            graph.edges[from_node].append({
                "to": to_node, "weight": weight, "type": edge_type
            })
            graph.edge_set.add((from_node, to_node))
        conn.close()
        return graph

    def count_nodes(self) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute("SELECT count(*) FROM causal_nodes").fetchone()[0]
        finally:
            conn.close()

    def count_edges(self) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute("SELECT count(*) FROM causal_edges").fetchone()[0]
        finally:
            conn.close()