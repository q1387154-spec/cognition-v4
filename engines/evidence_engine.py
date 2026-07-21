"""Evidence Engine — Observation → Evidence（规则 + LLM 双模式）"""
import re
from datetime import datetime
from typing import List, Dict, Any, Optional

from core import Evidence, EvidenceType, NoveltyLevel, HorizonType
from .base_engine import BaseEngine


class EvidenceEngine(BaseEngine):
    """
    Evidence Engine：Observation → Evidence（语义提炼）。

    Phase 1：规则提取（无需 LLM）
    Phase 2：LLM 语义提取（更准确）
    """

    def __init__(self, llm_client=None, config: Optional[Dict[str, Any]] = None):
        super().__init__("evidence_engine", config)
        self.llm_client = llm_client

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        输入 context：
          - observations: List[Observation]
          - use_llm: bool（可选，默认 False）

        输出 context 新增：
          - evidence_list: List[Evidence]
          - evidence_count: int
        """
        self.info("Evidence Engine 开始运行")
        observations = context.get("observations", [])
        use_llm = context.get("use_llm", False)

        if not observations:
            self.info("无 Observation 输入，跳过")
            context["evidence_list"] = []
            return context

        evidence_list = []
        for obs in observations:
            if use_llm and self.llm_client:
                ev = self._extract_with_llm(obs)
            else:
                ev = self._extract_with_rules(obs)
            if ev:
                evidence_list.extend(ev if isinstance(ev, list) else [ev])

        context["evidence_list"] = evidence_list
        context["evidence_count"] = len(evidence_list)
        self.info(f"Evidence Engine 完成: {len(evidence_list)} 条 Evidence (mode={'LLM' if use_llm else 'rules'})")
        return context

    def _extract_with_llm(self, observation) -> List[Evidence]:
        """LLM 语义提取（更准确）。"""
        if not self.llm_client:
            return self._extract_with_rules(observation)

        try:
            from models.llm import extract_evidence_schema
            result = extract_evidence_schema(
                observation_content=observation.raw_content,
                observation_title=observation.title or "",
            )
            if "error" in result:
                self.warning(f"LLM 调用失败: {result['error']}，降级到规则")
                return self._extract_with_rules(observation)

            evidence_list = []
            for ev_data in result.get("evidence", []):
                evidence_id = Evidence.generate_id(
                    observation.id,
                    ev_data.get("content", "")[:50],
                )
                ev = Evidence(
                    id=evidence_id,
                    observation_ids=[observation.id],
                    content=ev_data.get("content", ""),
                    type=EvidenceType(ev_data.get("type", "qualitative")),
                    confidence=float(ev_data.get("confidence", 0.5)),
                    novelty=NoveltyLevel(ev_data.get("novelty", "medium")),
                    horizon=HorizonType(ev_data.get("horizon", "medium")),
                    importance=float(ev_data.get("importance", 0.5)),
                    domain="investment",
                    metadata={
                        "llm_extracted": True,
                        "binding_type": result.get("binding_type"),
                        "regime": result.get("regime"),
                    },
                )
                evidence_list.append(ev)

            return evidence_list

        except Exception as e:
            self.warning(f"LLM 提取异常: {e}，降级到规则")
            return self._extract_with_rules(observation)

    def _extract_with_rules(self, observation) -> List[Evidence]:
        """Phase 1 规则提取（无需 LLM）。"""
        content = observation.raw_content
        evidence_list = []

        # ---- 定量 Pattern ----
        patterns = [
            # (regex, label, type, importance)
            (r"增长[了]?(\d+\.?\d*)%", "增长", "quantitative", 0.7),
            (r"同比增长[了]?(\d+\.?\d*)%", "同比增长", "quantitative", 0.7),
            (r"毛利率[为]?(\d+\.?\d*)%", "毛利率", "quantitative", 0.8),
            (r"净利润[为]?(\d+\.?\d*)[亿万元]?", "净利润", "quantitative", 0.8),
            (r"市场份额[达到]?(\d+\.?\d*)%", "市场份额", "quantitative", 0.6),
            (r"研发投入[为]?(\d+\.?\d*)[亿万元]?", "研发投入", "quantitative", 0.5),
            (r"营收[为]?(\d+\.?\d*)[亿万元]?", "营收", "quantitative", 0.7),
            (r"销量[为]?(\d+\.?\d*)[万辆台]?", "销量", "quantitative", 0.7),
            (r"市占率[为]?(\d+\.?\d*)%", "市占率", "quantitative", 0.7),
            (r"产能[为]?(\d+\.?\d*)[亿万台]?", "产能", "quantitative", 0.5),
        ]

        for pattern, label, ev_type, importance in patterns:
            match = re.search(pattern, content)
            if match:
                number = match.group(1) if match.lastindex else ""
                content_str = f"{label} {number}"
                ev_id = Evidence.generate_id(observation.id, content_str[:50])
                ev = Evidence(
                    id=ev_id,
                    observation_ids=[observation.id],
                    content=content_str,
                    type=EvidenceType(ev_type),
                    confidence=0.6,
                    novelty=NoveltyLevel("medium"),
                    horizon=HorizonType("medium"),
                    importance=importance,
                    domain="investment",
                    summary=f"从{observation.title or observation.source.value}提取",
                )
                evidence_list.append(ev)
                break  # 每个 Observation 只提取1条定量证据

        # ---- 定性 Pattern ----
        if not evidence_list:
            qualitative_map = [
                ("推出", "新产品发布"),
                ("合作", "战略合作"),
                ("签约", "重大订单"),
                ("获奖", "行业认可"),
                ("扩建", "产能扩张"),
                ("降价", "价格调整"),
                ("涨价", "价格调整"),
                ("突破", "技术突破"),
                ("领先", "行业领先"),
                ("首家", "先发优势"),
            ]
            for keyword, label in qualitative_map:
                if keyword in content:
                    ev_id = Evidence.generate_id(observation.id, label)
                    ev = Evidence(
                        id=ev_id,
                        observation_ids=[observation.id],
                        content=label,
                        type=EvidenceType.QUALITATIVE,
                        confidence=0.5,
                        novelty=NoveltyLevel("medium"),
                        horizon=HorizonType("short"),
                        importance=0.5,
                        domain="investment",
                        summary=f"从{observation.title or observation.source.value}提取",
                    )
                    evidence_list.append(ev)
                    break

        # ---- 矛盾 Pattern（categorical）----
        # 用于触发 Belief Engine 的矛盾证据分支，避免后验冲 1.0
        negative_map = [
            ("下滑", "业绩下滑"),
            ("亏损", "业绩亏损"),
            ("下降", "指标下降"),
            ("风险", "风险信号"),
            ("质疑", "市场质疑"),
            ("违规", "合规风险"),
            ("减持", "股东减持"),
            ("业绩不及预期", "业绩不及预期"),
            ("营收下降", "营收下降"),
            ("销量下滑", "销量下滑"),
        ]
        for keyword, label in negative_map:
            if keyword in content:
                ev_id = Evidence.generate_id(observation.id, f"neg_{label}")
                ev = Evidence(
                    id=ev_id,
                    observation_ids=[observation.id],
                    content=label,
                    type=EvidenceType.CATEGORICAL,
                    confidence=0.6,  # 矛盾证据略高置信度
                    novelty=NoveltyLevel("medium"),
                    horizon=HorizonType("short"),
                    importance=0.6,
                    domain="investment",
                    summary=f"从{observation.title or observation.source.value}提取的矛盾信号",
                )
                evidence_list.append(ev)
                break

        return evidence_list
