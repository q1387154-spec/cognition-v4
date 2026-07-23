"""Prediction Engine — Belief → Prediction"""
from datetime import datetime
from typing import List, Dict, Any, Optional
from core import Prediction, PredictionStatus, HorizonLabel, Scenario
from config import ConfigHorizonLabel, days_to_horizon_label
from .base_engine import BaseEngine


class PredictionEngine(BaseEngine):
    """Prediction Engine：Belief + Evidence → Prediction（含概率分布）。"""

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        输入 context：
          - belief: Belief
          - bound_evidence: List[Evidence]
          - horizon_days: int（可选）
          - target: str（可选）

        输出 context 新增：
          - prediction: Prediction
        """
        self.info("Prediction Engine 开始运行")
        belief = context.get("belief")
        bound_evidence = context.get("bound_evidence", [])
        horizon_days = context.get("horizon_days", 90)
        target = context.get("target", belief.subject if belief else "unknown")
        # 从 context 取当前价格，用于 base_value 计算
        self._current_price = context.get("current_price", None)

        if not belief:
            self.warning("无 Belief 输入，跳过")
            context["prediction"] = None
            return context

        # 生成场景
        scenarios = self._generate_scenarios(belief, bound_evidence)

        # 计算期望值
        expected_value = self._compute_expected_value(scenarios)

        # 推断 horizon_label
        horizon_label = days_to_horizon_label(horizon_days)

        # 推断 catalyst（从 Evidence 语义提取）
        catalyst = self._infer_catalyst(bound_evidence)

        # 计算 effective_score
        calibrated_accuracy = context.get("calibrated_accuracy", 0.5)
        effective_score = belief.confidence * calibrated_accuracy

        prediction = Prediction(
            id=Prediction.generate_id(target, belief.id, str(datetime.now())),
            target=target,
            belief_id=belief.id,
            probability_distribution={s.name: s.probability for s in scenarios},
            scenarios=scenarios,
            expected_value=expected_value,
            confidence=belief.confidence,
            horizon_days=horizon_days,
            horizon_label=horizon_label,
            catalyst=catalyst,
            regime=context.get("regime", "neutral"),
            effective_score=effective_score,
            bound_evidence_ids=[e.id for e in bound_evidence],
            status=PredictionStatus.ACTIVE,
            metadata={"base_value": self._current_price or 1.0},
        )

        context["prediction"] = prediction
        self.info(f"Prediction Engine 完成: {target}, {len(scenarios)} scenarios")
        return context

    def _generate_scenarios(self, belief, evidence) -> List[Scenario]:
        """生成基准/乐观/悲观三场景。"""
        base_prob = belief.probability
        # 优先级: context 传来的 current_price → belief.metadata.base_value → 1.0
        base_value = self._current_price or belief.metadata.get("base_value", 1.0)

        # 基准场景
        base = Scenario(
            name="基准",
            probability=0.60,
            assumptions=["无超预期因素", "趋势延续"],
            target_value=base_value,
            expected_return=base_value,
        )

        # 乐观场景
        optimistic = Scenario(
            name="乐观",
            probability=0.25,
            assumptions=["超预期表现", "催化剂兑现"],
            target_value=base_value * 1.15,
            expected_return=base_value * 1.15,
        )

        # 悲观场景
        pessimistic = Scenario(
            name="悲观",
            probability=0.15,
            assumptions=["低于预期", "风险暴露"],
            target_value=base_value * 0.85,
            expected_return=base_value * 0.85,
        )

        return [base, optimistic, pessimistic]

    def _compute_expected_value(self, scenarios: List[Scenario]) -> Optional[float]:
        """期望值 = Σ(scenario_prob × target_value)。"""
        total = 0.0
        for s in scenarios:
            if s.target_value is not None:
                total += s.probability * s.target_value
        return round(total, 4)

    def _infer_catalyst(self, evidence) -> Optional[str]:
        """从 Evidence 推断催化剂。"""
        if not evidence:
            return None
        catalyst_keywords = {
            "发布": "新产品发布",
            "签约": "重大订单",
            "合作": "战略合作",
            "量产": "产能爬坡",
            "降价": "价格竞争",
            "涨价": "提价",
        }
        for e in evidence:
            for kw, cat in catalyst_keywords.items():
                if kw in e.content:
                    return cat
        return None
