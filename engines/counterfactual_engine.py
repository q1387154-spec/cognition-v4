"""Counterfactual Engine — 反事实分析"""
from typing import List, Dict, Any, Optional
from .base_engine import BaseEngine


class CounterfactualEngine(BaseEngine):
    """
    Counterfactual Engine：反事实分析。

    核心问题："如果没有这个错误，预测会怎样？"

    方法：
    1. 给定 Prediction + Outcome + ErrorType
    2. 生成 2-3 个反事实场景
    3. 每个场景：调整某个假设，观察预期收益变化
    4. 输出：导致误差的关键因素 + 系统性改进建议
    """

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        输入 context：
          - outcome: Outcome
          - prediction: Prediction
          - belief: Belief

        输出 context 新增：
          - counterfactuals: List[Counterfactual]
        """
        self.info("Counterfactual Engine 开始运行")

        outcome = context.get("outcome")
        prediction = context.get("prediction")
        belief = context.get("belief")

        if not outcome or not prediction:
            self.info("无 Outcome/Prediction，跳过")
            context["counterfactuals"] = []
            return context

        error_type = outcome.error_type.value
        error_magnitude = outcome.prediction_error

        counterfactuals = self._generate_counterfactuals(
            prediction=prediction,
            outcome=outcome,
            error_type=error_type,
            error_magnitude=error_magnitude,
        )

        context["counterfactuals"] = counterfactuals
        context["counterfactual_count"] = len(counterfactuals)

        self.info(f"Counterfactual Engine 完成: {len(counterfactuals)} 个反事实")
        return context

    def _generate_counterfactuals(
        self, prediction, outcome, error_type: str, error_magnitude: float
    ) -> List["Counterfactual"]:
        """生成反事实场景。"""
        counterfactuals = []

        if error_type == "overconfidence":
            # 反事实：如果置信度更低
            adjusted_conf = max(prediction.confidence - 0.2, 0.3)
            adjusted_score = adjusted_conf * (1 - error_magnitude)
            counterfactuals.append(Counterfactual(
                scenario=f"置信度从 {prediction.confidence:.0%} 降至 {adjusted_conf:.0%}",
                changed_factor="confidence",
                original_value=prediction.confidence,
                adjusted_value=adjusted_conf,
                expected_improvement=error_magnitude * 0.5,
                description=f"降低置信度会使概率分布更保守，减少过度自信误差"
            ))

        if error_type == "missing_signal":
            # 反事实：如果有更多结构性证据
            counterfactuals.append(Counterfactual(
                scenario='增加【行业竞争格局】维度证据',
                changed_factor="evidence_coverage",
                original_value=outcome.prediction_error,
                adjusted_value=error_magnitude * 0.5,
                expected_improvement=error_magnitude * 0.5,
                description="覆盖不足导致对竞争格局误判，增加该维度证据可改善"
            ))

        if error_type == "regime_mismatch":
            # 反事实：如果正确识别了regime
            counterfactuals.append(Counterfactual(
                scenario="regime从'价值'修正为'AI牛市'",
                changed_factor="regime_assumption",
                original_value=prediction.regime,
                adjusted_value="AI_bull",
                expected_improvement=error_magnitude * 0.6,
                description="错误regime假设导致方向性偏差，修正后预期改善60%"
            ))

        if error_type == "horizon_mismatch":
            # 反事实：如果用了更短的horizon
            counterfactuals.append(Counterfactual(
                scenario=f"horizon从{prediction.horizon_days}d缩短为20d",
                changed_factor="horizon_days",
                original_value=prediction.horizon_days,
                adjusted_value=20,
                expected_improvement=error_magnitude * 0.4,
                description="horizon不匹配导致预测窗口错位，缩短可提高精度"
            ))

        # 如果没有任何特定类型的反事实，生成通用
        if not counterfactuals:
            counterfactuals.append(Counterfactual(
                scenario="降低置信度10%",
                changed_factor="confidence",
                original_value=prediction.confidence,
                adjusted_value=prediction.confidence * 0.9,
                expected_improvement=error_magnitude * 0.3,
                description="通用反事实：降低置信度可减少误差"
            ))

        return counterfactuals


from dataclasses import dataclass, field


@dataclass
class Counterfactual:
    """单个反事实场景。"""
    scenario: str                           # 场景描述
    changed_factor: str                     # 改变的因子
    original_value: float                  # 原始值
    adjusted_value: float                  # 调整后值
    expected_improvement: float             # 预期改善幅度
    description: str                       # 解释
