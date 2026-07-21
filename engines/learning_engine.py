"""Learning Engine — Prediction + Outcome → Learning（真正的闭环）"""
from datetime import datetime
from typing import List, Dict, Any, Optional

from core import Learning, LearningType, Outcome, Prediction, Belief, CausalEdgeUpdate
from config import WEIGHT_LEARNING_RATE, BELIEF_LEARNING_RATE
from .base_engine import BaseEngine


class LearningEngine(BaseEngine):
    """Learning Engine：Prediction + Outcome → Learning（真正的学习闭环）。"""

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        输入 context：
          - outcome: Outcome
          - prediction: Prediction
          - belief: Belief
          - feature_updates: dict（可选）
          - weight_updates: dict（可选）

        输出 context 新增：
          - learning: Learning
          - weight_updates: dict
          - belief_adjustment: float
        """
        self.info("Learning Engine 开始运行")
        outcome = context.get("outcome")
        prediction = context.get("prediction")
        belief = context.get("belief")

        if not outcome or not prediction:
            self.warning("无 Outcome 或 Prediction，跳过学习")
            return context

        # 计算误差
        error_type = outcome.error_type.value
        error_magnitude = outcome.prediction_error

        # 分类误差
        learning_type = self._classify_learning_type(error_type, error_magnitude)

        # 计算 Belief 调整
        belief_adjustment = self._compute_belief_adjustment(
            error_type, error_magnitude, belief.confidence
        )

        # Weight Learning：调整各维度权重
        weight_updates = self._compute_weight_updates(error_type, error_magnitude, prediction)

        # 反事实分析
        counterfactuals = self._generate_counterfactuals(prediction, outcome)

        learning = Learning(
            id=Learning.generate_id(outcome.id, prediction.id),
            outcome_id=outcome.id,
            prediction_id=prediction.id,
            belief_id=prediction.belief_id,
            learning_type=learning_type,
            feature_updates=context.get("feature_updates", {}),
            causal_updates=[],
            weight_updates=weight_updates,
            belief_adjustment=belief_adjustment,
            accuracy_delta=-error_magnitude if error_type != "no_error" else 0.0,
            counterfactuals=counterfactuals,
        )

        context["learning"] = learning
        context["weight_updates"] = weight_updates
        context["belief_adjustment"] = belief_adjustment

        self.info(f"Learning Engine 完成: {learning_type.value}, 调整={belief_adjustment:+.3f}")
        return context

    def _classify_learning_type(self, error_type: str, magnitude: float) -> LearningType:
        if error_type in ("missing_signal", "horizon_mismatch"):
            return LearningType.FEATURE
        if error_type in ("regime_mismatch",):
            return LearningType.REGIME
        if error_type in ("overconfidence", "confirmation_bias"):
            return LearningType.BELIEF
        return LearningType.WEIGHT

    def _compute_belief_adjustment(self, error_type: str, magnitude: float, confidence: float) -> float:
        """贝叶斯信念调整。"""
        adjustments = {
            "missing_signal": -0.15,
            "confirmation_bias": -0.10,
            "overconfidence": -0.20,
            "regime_mismatch": -0.25,
            "horizon_mismatch": -0.10,
            "no_error": +0.05,
        }
        base = adjustments.get(error_type, -0.05)
        # 严重程度缩放
        severity = min(magnitude, 1.0)
        return round(base * severity, 4)

    def _compute_weight_updates(self, error_type: str, magnitude: float, prediction) -> Dict[str, float]:
        """Weight Learning：根据误差调整各维度权重。"""
        # 这是一个简化实现
        # 实际需要根据 error_type 判断哪个维度出了问题
        updates = {}
        if prediction and prediction.metadata:
            for dim, delta in prediction.metadata.get("dimension_weights", {}).items():
                # 误差大 → 该维度权重应降低（如果该维度导致了误差）
                if error_type != "no_error":
                    # 简化：全部略微降低，真实实现需要因果溯源
                    updates[dim] = delta * (1 - WEIGHT_LEARNING_RATE * magnitude)
        return updates

    def _generate_counterfactuals(self, prediction: Prediction, outcome: Outcome) -> List[str]:
        """反事实分析。"""
        counterfactuals = []

        # 如果预测偏高
        if outcome.prediction_error > 0.1:
            counterfactuals.append(
                f"如果置信度降低 {abs(outcome.prediction_error)*0.5:.0%}，"
                f"概率分布会更接近实际结果"
            )

        # 如果错过了信号
        if outcome.error_type.value == "missing_signal":
            counterfactuals.append(
                "如果有更多结构性证据覆盖该领域，"
                "该信号可能被提前捕获"
            )

        return counterfactuals
