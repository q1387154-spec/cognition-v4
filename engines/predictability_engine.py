"""Predictability Engine — 可预测性评估（Phase 2）

职责：
- 评估某个预测目标的客观可预测性
- 综合考量：信号质量、因果清晰度、历史可重复性、噪声水平
- 输出 PredictabilityScore（0.0-1.0），< 0.3 提示谨慎依赖

输出：
- predictability_score: float (0.0~1.0)
- dimensions: dict - 各维度得分明细
- recommendation: str - 操作建议
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from .base_engine import BaseEngine


class PredictabilityEngine(BaseEngine):
    """可预测性评估引擎。"""

    def __init__(self, name: str = "predictability_engine", config: Dict[str, Any] = None):
        super().__init__(name, config)
        # 各维度权重（合计 1.0）
        self.weights = {
            "signal_quality": 0.30,    # 信号质量
            "causal_clarity": 0.20,    # 因果清晰度
            "historical_repeatability": 0.25,  # 历史可重复性
            "noise_level": 0.15,       # 噪声水平（反向）
            "horizon_feasibility": 0.10,  # 期限可行性
        }

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        输入 context：
          - target: str - 预测目标（如 "赛力斯毛利率"）
          - evidence: List[Evidence] - 当前可用证据
          - horizon_days: int - 预测期限
          - entity_accuracy: Optional[Dict] - 历史精度数据

        输出 context 新增：
          - predictability_score: float (0.0~1.0)
          - dimensions: dict - 各维度明细
          - recommendation: str
        """
        self.info("Predictability Engine 开始运行")
        target = context.get("target", "unknown")
        evidence = context.get("evidence", [])
        horizon_days = context.get("horizon_days", 90)
        entity_acc = context.get("entity_accuracy", {})

        # 各维度评估
        signal_quality = self._evaluate_signal_quality(evidence)
        causal_clarity = self._evaluate_causal_clarity(target, evidence)
        historical_repeatability = self._evaluate_historical(entity_acc)
        noise_level = self._evaluate_noise(horizon_days)
        horizon_feasibility = self._evaluate_horizon(horizon_days)

        dimensions = {
            "signal_quality": round(signal_quality, 4),
            "causal_clarity": round(causal_clarity, 4),
            "historical_repeatability": round(historical_repeatability, 4),
            "noise_level": round(noise_level, 4),
            "horizon_feasibility": round(horizon_feasibility, 4),
        }

        # 加权得分
        score = (
            signal_quality * self.weights["signal_quality"]
            + causal_clarity * self.weights["causal_clarity"]
            + historical_repeatability * self.weights["historical_repeatability"]
            + noise_level * self.weights["noise_level"]
            + horizon_feasibility * self.weights["horizon_feasibility"]
        )

        recommendation = self._build_recommendation(score, target)

        context["predictability_score"] = round(score, 4)
        context["dimensions"] = dimensions
        context["recommendation"] = recommendation

        self.info(
            f"Predictability: {target} → {score:.3f} "
            f"({signal_quality:.2f}/{causal_clarity:.2f}/{historical_repeatability:.2f})"
        )
        return context

    def _evaluate_signal_quality(self, evidence) -> float:
        """评估信号质量（基于证据）。"""
        if not evidence:
            return 0.20  # 无证据=不可预测
        n = len(evidence)
        avg_importance = sum(e.importance for e in evidence) / n
        avg_confidence = sum(e.confidence for e in evidence) / n
        # 多样性奖励：支持+矛盾同时存在 → 更高质量
        types = set(e.type.value for e in evidence)
        diversity_bonus = min(0.15, len(types) * 0.05)

        score = avg_importance * 0.5 + avg_confidence * 0.3 + diversity_bonus
        # 证据数量不足扣分
        if n < 3:
            score *= 0.7
        return min(1.0, score)

    def _evaluate_causal_clarity(self, target: str, evidence) -> float:
        """评估因果清晰度（启发式）。"""
        # 行业关键词识别
        clear_industries = ["毛利率", "净息差", "净利率", "不良率", "市占率"]
        unclear_industries = ["股价", "情绪", "政策"]

        score = 0.5
        for kw in clear_industries:
            if kw in target:
                score = 0.80
                break
        for kw in unclear_industries:
            if kw in target:
                score = 0.30
                break

        # 证据支撑则加分
        if any(e.type.value == "quantitative" for e in evidence):
            score += 0.10

        return min(1.0, score)

    def _evaluate_historical(self, entity_acc: Dict) -> float:
        """评估历史可重复性。"""
        if not entity_acc:
            return 0.40  # 无历史数据=未知
        rate = entity_acc.get("accuracy_rate", 0.0)
        verified = entity_acc.get("verified_count", 0)
        if verified < 3:
            return 0.30  # 样本不足
        return rate

    def _evaluate_noise(self, horizon_days: int) -> float:
        """评估噪声水平（短期低噪声=高得分）。"""
        if horizon_days <= 5:
            return 0.30  # 短期噪声大
        elif horizon_days <= 20:
            return 0.55
        elif horizon_days <= 90:
            return 0.75
        elif horizon_days <= 365:
            return 0.85
        else:
            return 0.90

    def _evaluate_horizon(self, horizon_days: int) -> float:
        """评估期限可行性。"""
        if horizon_days < 0:
            return 0.0
        if horizon_days <= 1095:  # 3 年内
            return 0.90
        elif horizon_days <= 1825:  # 5 年
            return 0.70
        else:
            return 0.40

    def _build_recommendation(self, score: float, target: str) -> str:
        """根据得分给出操作建议。"""
        if score >= 0.75:
            return f"✅ 高可预测性 | {target} 适合深度预测"
        elif score >= 0.5:
            return f"⚠️ 中等可预测性 | {target} 建议作为辅助参考"
        elif score >= 0.3:
            return f"⚠️ 低可预测性 | {target} 谨慎依赖，建议减少权重"
        else:
            return f"❌ 不可预测 | {target} 建议放弃该预测目标"