"""Causal Engine — 因果图谱构建引擎

职责：
- 从 Evidence 自动提取因果关系（实体 → 事件 → 影响 → 结果）
- 维护节点（节点类型：cause / event / effect / metric）
- 维护有向边（权重表示因果强度，类型表示因果方向）
- 持久化到 causal_nodes / causal_edges 表（通过 CausalGraphStore）

输出：
- graph: CausalGraph — 内存中的完整图谱
- new_nodes: List[str] — 本次新增节点
- new_edges: List[Tuple] — 本次新增边
"""
import re
from typing import List, Dict, Any, Set, Tuple
from datetime import datetime

from core import Evidence
from memory import CausalGraph, CausalGraphStore
from .base_engine import BaseEngine


class CausalEngine(BaseEngine):
    """因果图谱构建引擎。"""

    def __init__(self, name: str = "causal_engine", config: Dict[str, Any] = None):
        super().__init__(name, config)
        self.db_path = (config or {}).get("db_path", "cognition_v4.db")
        # 节点类型映射（关键词 → 节点类型）
        self.cause_keywords = {
            "政策": "macro", "央行": "macro", "利率": "macro",
            "增长": "metric", "下滑": "metric", "上升": "metric", "下降": "metric",
            "突破": "event", "发布": "event", "签约": "event",
            "涨价": "event", "降价": "event", "合作": "event",
            "减持": "event", "亏损": "metric", "盈利": "metric",
        }
        # 因果连接词（识别证据里的因果关系）
        self.causal_connectors = [
            "导致", "引发", "造成", "带动", "推动", "拖累",
            "因为", "由于", "受.*影响", "由于.*下滑",
        ]

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        输入 context：
          - evidence: List[Evidence]
          - subject: str（可选，焦点实体）
          - existing_graph: CausalGraph（可选，已有图谱）

        输出 context 新增：
          - graph: CausalGraph（更新后的图谱）
          - new_nodes: List[str]
          - new_edges: List[Tuple[str, str, str, float]]
        """
        self.info("Causal Engine 开始运行")
        evidence_list = context.get("evidence", [])
        subject = context.get("subject", "unknown")
        existing = context.get("existing_graph")

        # 加载或新建图谱
        if existing:
            graph = existing
        else:
            store = CausalGraphStore.get(self.db_path)
            graph = store.load()  # 从 DB 加载

        new_nodes = []
        new_edges = []

        for ev in evidence_list:
            nodes, edges = self._extract_causal_relations(ev, subject)
            for nid, ntype, label in nodes:
                if nid not in graph.nodes:
                    graph.add_node(nid, ntype, label)
                    new_nodes.append(nid)
            for from_node, to_node, edge_type, weight in edges:
                if (from_node, to_node) not in graph.edge_set:
                    graph.add_edge(from_node, to_node, weight, edge_type)
                    new_edges.append((from_node, to_node, edge_type, weight))

        # 持久化（如果有新内容）
        if new_nodes or new_edges:
            store = CausalGraphStore.get(self.db_path)
            store.save(graph)

        context["graph"] = graph
        context["new_nodes"] = new_nodes
        context["new_edges"] = new_edges

        self.info(
            f"Causal Engine 完成: {len(new_nodes)} 新节点, "
            f"{len(new_edges)} 新边, 图谱总计 {len(graph.nodes)} 节点 / "
            f"{sum(len(v) for v in graph.edges.values())} 边"
        )
        return context

    def _extract_causal_relations(
        self, evidence: Evidence, subject: str
    ) -> Tuple[List[Tuple[str, str, str]], List[Tuple[str, str, str, float]]]:
        """
        从单条 Evidence 提取因果节点和边。

        策略：
        - subject 是核心节点
        - evidence.content 里的关键词识别 cause/effect 节点
        - 用因果连接词推断边方向
        """
        nodes = []
        edges = []
        content = evidence.content or ""

        # 1. 主实体节点（必有）
        subj_node = (subject, "entity", subject)
        nodes.append(subj_node)

        # 2. 关键词提取节点
        for keyword, node_type in self.cause_keywords.items():
            if keyword in content:
                node_id = f"{subject}_{keyword}"
                nodes.append((node_id, node_type, keyword))
                # 关联到主体
                if keyword in ("下滑", "下降", "亏损"):
                    edge_type = "negatively_impacts"
                elif keyword in ("增长", "上升", "盈利"):
                    edge_type = "positively_impacts"
                else:
                    edge_type = "correlates_with"
                weight = evidence.importance * evidence.confidence
                edges.append((node_id, subject, edge_type, round(weight, 4)))

        # 3. 检测因果连接词（决定边方向）
        for connector in self.causal_connectors:
            if connector in content:
                # 找到匹配节点之间建立强因果边
                if len(nodes) >= 2:
                    # 简化为：第一个节点 → 主实体
                    first_node = nodes[0][0]
                    if first_node != subject:
                        edges.append((
                            first_node, subject,
                            "causes", 0.8,
                        ))

        return nodes, edges

    def query_causes(self, target_node: str, depth: int = 3) -> List[str]:
        """查询某个节点的所有上游原因（因果链）。"""
        store = CausalGraphStore.get(self.db_path)
        graph = store.load()
        return graph.get_upstream(target_node, depth)

    def query_effects(self, source_node: str, depth: int = 3) -> List[str]:
        """查询某个节点的所有下游影响。"""
        store = CausalGraphStore.get(self.db_path)
        graph = store.load()
        return graph.get_downstream(source_node, depth)