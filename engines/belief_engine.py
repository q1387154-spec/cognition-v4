"""Belief Engine — Evidence → Belief 更新（贝叶斯）"""
from datetime import datetime
from typing import List, Dict, Any, Optional
import math

from core import Belief, BeliefStatus, Evidence
from .base_engine import BaseEngine


class BeliefEngine(BaseEngine):
    """Belief Engine：Evidence → Belief 更新（贝叶斯更新 + 置信度衰减）。"""

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        输入 context：
          - evidence: List[Evidence]
          - subject: str（信念主体）
          - existing_belief: Belief（可选，已有 Belief）

        输出 context 新增：
          - belief: Belief
        """
        self.info("Belief Engine 开始运行")
        evidence = context.get("evidence", [])
        subject = context.get("subject", "unknown")
        existing_belief = context.get("existing_belief")

        # 如果有已有 Belief，先衰减其置信度
        if existing_belief:
            existing_belief = self._apply_decay(existing_belief)
            # 贝叶斯更新
            new_belief = self._bayesian_update(existing_belief, evidence, subject)
        else:
            # 无已有 Belief，直接从 Evidence 创建
            new_belief = self._create_from_evidence(evidence, subject)

        context["belief"] = new_belief
        self.info(f"Belief Engine 完成: {subject}, 概率={new_belief.probability:.2f}, 置信度={new_belief.confidence:.2f}")
        return context

    def _apply_decay(self, belief: Belief) -> Belief:
        """置信度时间衰减。"""
        now = datetime.now()
        days_elapsed = (now - belief.update_time).days
        if days_elapsed <= 0:
            return belief

        decayed_confidence = belief.decay_confidence(days_elapsed)
        belief.confidence = max(0.0, decayed_confidence)
        return belief

    def _bayesian_update(self, old_belief: Belief, evidence: List[Evidence], subject: str) -> Belief:
        """
        贝叶斯更新（防止概率冲1.0的修复版）：
        - prior 接近1.0时（DB残留值），先 cap 到0.95，防止 log(1.0)=∞
        - 矛盾证据为空时，默认 P(E|¬H)=0.5，避免全支持→后验=1.0
        - 后验概率用 sigmoid(logit) 域平滑更新
        - 置信度上限 0.92，防止全自信
        """
        # 【修复】prior 接近1.0时 cap，避免 logit 爆炸
        prior = old_belief.probability
        if prior >= 0.98:
            prior = 0.95  # 从 DB 读取的残留值，防止 log(1.0)=∞
        # 分类支持/矛盾证据
        support_evidence = [e for e in evidence if e.type.value in ("quantitative", "qualitative")]
        contradict_evidence = [e for e in evidence if e.type.value == "categorical"]

        # 计算似然（支持证据平均 confidence）
        if support_evidence:
            p_e_given_h = sum(e.confidence * e.importance for e in support_evidence) / len(support_evidence)
        else:
            p_e_given_h = 0.0

        # 【修复】矛盾证据为空时默认0.5，避免后验直接=1.0
        if contradict_evidence:
            p_e_given_not_h = sum(e.confidence * e.importance for e in contradict_evidence) / len(contradict_evidence)
        else:
            p_e_given_not_h = 0.5  # 默认50%，保留不确定性

        p_e = p_e_given_h * prior + p_e_given_not_h * (1 - prior)

        if p_e > 0:
            posterior = (p_e_given_h * prior) / p_e
        else:
            posterior = prior

        # 【修复】用 logit 域平滑更新，防止概率冲到1.0
        old_logit = math.log(max(prior, 1e-6) / max(1 - prior, 1e-6))
        evidence_strength = p_e_given_h * len(support_evidence) * 0.3
        if contradict_evidence:
            evidence_strength -= p_e_given_not_h * len(contradict_evidence) * 0.5
        new_logit = old_logit + evidence_strength
        posterior = 1 / (1 + math.exp(-new_logit))

        # 置信度：证据越多越自信，上限0.92
        n_evidence = len(support_evidence) + len(contradict_evidence)
        confidence_boost = min(0.08 * n_evidence, 0.25)
        new_confidence = min(old_belief.confidence + confidence_boost, 0.92)

        return Belief(
            id=Belief.generate_id(subject, str(datetime.now())),
            subject=subject,
            probability=round(posterior, 4),
            confidence=round(new_confidence, 4),
            support_evidence_ids=[e.id for e in support_evidence],
            contradict_evidence_ids=[e.id for e in contradict_evidence],
            update_time=datetime.now(),
            decay_rate=old_belief.decay_rate,
            version=old_belief.version + 1,
            status=BeliefStatus.ACTIVE,
            previous_version_id=old_belief.id,
            domain=old_belief.domain,
            horizon=old_belief.horizon,
        )

    def _create_from_evidence(self, evidence: List[Evidence], subject: str) -> Belief:
        """从零创建 Belief。"""
        if not evidence:
            return Belief(
                id=Belief.generate_id(subject, "init"),
                subject=subject,
                probability=0.5,
                confidence=0.3,
                support_evidence_ids=[],
                version=1,
                status=BeliefStatus.ACTIVE,
            )

        # 基于 Evidence 计算初始概率
        avg_confidence = sum(e.confidence * e.importance for e in evidence) / len(evidence)
        # 【修复】初始概率上限0.85，防止新 Belief 一开始就过度自信
        probability = min(max(avg_confidence, 0.3), 0.85)

        # 置信度：初始上限0.7
        confidence = min(0.3 + 0.05 * len(evidence), 0.7)

        return Belief(
            id=Belief.generate_id(subject, str(datetime.now())),
            subject=subject,
            probability=round(probability, 4),
            confidence=round(confidence, 4),
            support_evidence_ids=[e.id for e in evidence],
            contradict_evidence_ids=[],
            update_time=datetime.now(),
            version=1,
            status=BeliefStatus.ACTIVE,
        )
