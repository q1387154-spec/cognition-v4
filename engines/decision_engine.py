"""Decision Engine — 决策信号 + 仓位"""
from typing import Dict, Any

from config import DECISION_THRESHOLDS
from .base_engine import BaseEngine


class DecisionEngine(BaseEngine):
    """
    Decision Engine：胜率 + 盈亏比决策。

    输入：Prediction（概率分布）+ WorldModel 输出 + 估值
    输出：Decision（信号 + 理由 + 仓位）
    """

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        输入 context：
          - prediction: Prediction
          - world_view: dict（可选）
          - valuation: dict（可选）
          - signal: dict（可选，来自 WorldModel）

        输出 context 新增：
          - decision: Decision
        """
        self.info("Decision Engine 开始运行")

        prediction = context.get("prediction")
        valuation = context.get("valuation", {})
        world_signal = context.get("signal", {})

        if not prediction:
            context["decision"] = None
            return context

        # 决定信号
        signal_label = world_signal.get("label") or self._derive_signal(prediction)
        expected_return = (
            world_signal.get("expected_return_pct")
            or valuation.get("expected_return_pct")
            or self._derive_return(prediction)
        )

        # 凯利公式计算仓位
        win_rate = self._derive_win_rate(prediction)
        kelly_fraction = self._kelly_fraction(win_rate, expected_return)

        decision = Decision(
            entity=prediction.target,
            signal=signal_label,
            expected_return_pct=expected_return,
            kelly_fraction=round(kelly_fraction, 3),
            confidence=prediction.confidence,
            horizon_days=prediction.horizon_days,
            reason=self._build_reason(prediction, valuation, world_signal),
            regime=world_signal.get("regime_adjustment", "neutral"),
        )

        context["decision"] = decision
        self.info(f"Decision Engine 完成: {decision}")
        return context

    def _derive_signal(self, prediction) -> str:
        """从 Prediction 推断信号。"""
        prob = prediction.confidence
        if prob >= DECISION_THRESHOLDS["strong_buy"]:
            return "强烈买入"
        elif prob >= DECISION_THRESHOLDS["buy"]:
            return "买入"
        elif prob >= DECISION_THRESHOLDS["hold"]:
            return "持有"
        elif prob >= DECISION_THRESHOLDS["sell"]:
            return "卖出"
        else:
            return "强烈卖出"

    def _derive_return(self, prediction) -> float:
        """从 Prediction 推断预期收益率。"""
        if prediction.expected_value and prediction.expected_value != 1.0:
            return round((prediction.expected_value - 1.0) * 100, 2)
        # 简化：从 effective_score 推断
        return round((prediction.effective_score - 0.5) * 100, 2)

    def _derive_win_rate(self, prediction) -> float:
        """推断胜率。"""
        # 乐观场景概率 = 基准 + 乐观
        base_prob = 0.0
        for s in prediction.scenarios:
            if s.name in ("基准", "乐观"):
                base_prob += s.probability
        return min(base_prob, 0.95)

    def _kelly_fraction(self, win_rate: float, expected_return_pct: float) -> float:
        """
        凯利公式：f* = (b × p - q) / b

        其中：
          p = 胜率
          q = 1 - p
          b = 盈亏比（预期收益 / 最大亏损）
        """
        if expected_return_pct >= 0:
            b = expected_return_pct / 10.0  # 假设最大亏损10%
        else:
            b = 10.0 / abs(expected_return_pct)  # 亏损情况

        p = win_rate
        q = 1 - p
        f_star = (b * p - q) / b

        # 限制在 [0, 0.25]（保守）
        return max(0.0, min(0.25, f_star))

    def _build_reason(self, prediction, valuation, world_signal) -> str:
        """构建决策理由。"""
        reasons = []
        if valuation:
            reasons.append(valuation.get("valuation_basis", ""))
        if world_signal:
            reasons.append(f"宏观{world_signal.get('regime_adjustment', '')}")
        if prediction.bound_evidence_ids:
            reasons.append(f"基于{len(prediction.bound_evidence_ids)}条证据")
        return "；".join(filter(None, reasons)) or "无特定理由"


from dataclasses import dataclass


@dataclass
class Decision:
    """决策信号。"""
    entity: str
    signal: str
    expected_return_pct: float
    kelly_fraction: float        # 凯利仓位比例
    confidence: float
    horizon_days: int
    reason: str
    regime: str

    def __str__(self):
        return (
            f"{self.entity}: {self.signal} "
            f"(预期{self.expected_return_pct:+.1f}%, "
            f"仓位{self.kelly_fraction:.0%}, "
            f"置信度{self.confidence:.0%}, "
            f"理由:{self.reason})"
        )
