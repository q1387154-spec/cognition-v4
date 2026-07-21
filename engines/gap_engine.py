"""Gap Engine — Information Gap 检测"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional

from config import GAP_CONFIDENCE_THRESHOLD, GAP_HORIZON_WARNING_DAYS
from .base_engine import BaseEngine


class GapType(str, Enum):
    LOW_CONFIDENCE = "low_confidence"
    MISSING_EVIDENCE = "missing_evidence"
    HORIZON_EXPIRING = "horizon_expiring"
    CONTRADICTING_EVIDENCE = "contradicting_evidence"
    REGIME_CHANGE = "regime_change"


@dataclass
class Gap:
    """Gap Entity。"""
    belief_id: str
    subject: str
    gap_type: GapType
    severity: int              # 1-3，3最严重
    description: str
    missing_evidence_types: List[str] = field(default_factory=list)
    suggested_actions: List[str] = field(default_factory=list)
    detected_at: datetime = field(default_factory=datetime.now)


class GapEngine(BaseEngine):
    """
    Gap Engine：检测 Information Gap，触发 Deep Research。
    """

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.info("Gap Engine 开始运行")

        beliefs = context.get("beliefs", [])
        belief_store = context.get("belief_store")
        evidence_list = context.get("evidence_list", [])

        if not beliefs and belief_store:
            beliefs = belief_store.get_active()

        gaps = []
        for belief in beliefs:
            gap = self._detect_gap(belief, evidence_list)
            if gap:
                gaps.append(gap)

        research_needed = [g for g in gaps if g.severity >= 2]

        context["gaps"] = gaps
        context["gap_count"] = len(gaps)
        context["research_needed"] = research_needed

        self.info(f"Gap Engine 完成: {len(gaps)} Gaps, {len(research_needed)} 需Deep Research")
        return context

    def _detect_gap(self, belief, evidence_list: List) -> Optional[Gap]:
        """检测单个 Belief 的 Gap。"""
        gaps_found = []

        # Gap 1: 置信度低于阈值
        if belief.confidence < GAP_CONFIDENCE_THRESHOLD:
            severity = 1 if belief.confidence > 0.3 else 3
            gaps_found.append(Gap(
                belief_id=belief.id,
                subject=belief.subject,
                gap_type=GapType.LOW_CONFIDENCE,
                severity=severity,
                description=f"置信度 {belief.confidence:.2f} < 阈值 {GAP_CONFIDENCE_THRESHOLD}",
                missing_evidence_types=["量化数据", "权威来源"],
                suggested_actions=["深度研究", "专家咨询"],
            ))

        # Gap 2: 无支持 Evidence
        if not belief.support_evidence_ids:
            gaps_found.append(Gap(
                belief_id=belief.id,
                subject=belief.subject,
                gap_type=GapType.MISSING_EVIDENCE,
                severity=2,
                description="无支持 Evidence",
                missing_evidence_types=["相关事实", "数据支撑"],
                suggested_actions=["信息收集", "原始数据获取"],
            ))

        # Gap 3: Horizon 即将到期
        if hasattr(belief, "horizon"):
            horizon_days_map = {"short": 20, "medium": 90, "long": 180, "structural": 365}
            horizon_days = horizon_days_map.get(belief.horizon, 90)
            days_elapsed = (datetime.now() - belief.update_time).days
            if days_elapsed >= horizon_days - GAP_HORIZON_WARNING_DAYS:
                gaps_found.append(Gap(
                    belief_id=belief.id,
                    subject=belief.subject,
                    gap_type=GapType.HORIZON_EXPIRING,
                    severity=2,
                    description=f"Horizon 即将到期（已过 {days_elapsed}/{horizon_days} 天）",
                    missing_evidence_types=["最新数据", "更新信息"],
                    suggested_actions=["信息更新", "重新评估"],
                ))

        # Gap 4: 矛盾 Evidence 多于支持
        if len(belief.contradict_evidence_ids) > len(belief.support_evidence_ids):
            gaps_found.append(Gap(
                belief_id=belief.id,
                subject=belief.subject,
                gap_type=GapType.CONTRADICTING_EVIDENCE,
                severity=2,
                description="矛盾 Evidence 多于支持 Evidence",
                missing_evidence_types=["中立来源", "第三方验证"],
                suggested_actions=["矛盾分析", "来源核查"],
            ))

        if gaps_found:
            return max(gaps_found, key=lambda g: g.severity)
        return None
