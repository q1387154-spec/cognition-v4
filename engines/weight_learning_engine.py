"""Weight Learning Engine — 维度权重动态调整"""
from typing import List, Dict, Any
from datetime import datetime

from config import WEIGHT_LEARNING_RATE, INVESTMENT_DIMENSIONS
from .base_engine import BaseEngine


class WeightLearningEngine(BaseEngine):
    """
    Weight Learning Engine：维度权重动态调整。

    核心问题："哪个维度预测率最高/最低？"

    方法：
    1. 每次 Outcome 到达，根据 error_type 判断哪个维度出了问题
    2. 更新该维度的 accuracy 历史
    3. 用历史数据计算新的权重
    4. 权重调整限制：单次 ±5%，总和恒为 1.0

    维度权重（investment）：
    growth / value / quality / momentum / macro / industry / management / technical
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("weight_learning_engine", config)
        # accuracy_history[domain][dimension] = [accuracy1, accuracy2, ...]
        self.accuracy_history: Dict[str, Dict[str, List[float]]] = {}
        self._init_dimensions()

    def _init_dimensions(self):
        """初始化维度权重。"""
        for domain in ["investment"]:
            if domain not in self.accuracy_history:
                self.accuracy_history[domain] = {}
            for dim_name in INVESTMENT_DIMENSIONS.keys():
                if dim_name not in self.accuracy_history[domain]:
                    self.accuracy_history[domain][dim_name] = []

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        输入 context：
          - outcome: Outcome
          - prediction: Prediction
          - domain: str（可选，默认 investment）

        输出 context 新增：
          - weight_updates: Dict[str, float]  # dimension → new_weight
          - dimension_accuracy: Dict[str, float]  # dimension → avg_accuracy
        """
        self.info("Weight Learning Engine 开始运行")

        outcome = context.get("outcome")
        prediction = context.get("prediction")
        domain = context.get("domain", "investment")

        if not outcome:
            context["weight_updates"] = {}
            context["dimension_accuracy"] = {}
            return context

        # 计算 accuracy
        accuracy = max(0.0, 1.0 - outcome.prediction_error)

        # 根据 error_type 分配到维度
        affected_dimensions = self._get_affected_dimensions(outcome.error_type.value)

        # 更新历史
        for dim in affected_dimensions:
            if domain not in self.accuracy_history:
                self.accuracy_history[domain] = {}
            if dim not in self.accuracy_history[domain]:
                self.accuracy_history[domain][dim] = []
            self.accuracy_history[domain][dim].append(accuracy)
            # 保留最近 50 条
            if len(self.accuracy_history[domain][dim]) > 50:
                self.accuracy_history[domain][dim] = self.accuracy_history[domain][dim][-50:]

        # 计算新的维度权重
        weight_updates = self._compute_weights(domain)
        dimension_accuracy = self._get_dimension_accuracy(domain)

        context["weight_updates"] = weight_updates
        context["dimension_accuracy"] = dimension_accuracy

        self.info(f"Weight Learning 完成: {len(weight_updates)} 个维度更新")
        return context

    def _get_affected_dimensions(self, error_type: str) -> List[str]:
        """根据 error_type 判断影响哪些维度。"""
        mapping = {
            "overconfidence": ["growth", "value", "quality"],
            "confirmation_bias": ["quality", "management"],
            "missing_signal": ["industry", "macro", "growth"],
            "regime_mismatch": ["macro", "industry", "momentum"],
            "horizon_mismatch": ["momentum", "technical"],
            "no_error": ["growth", "value"],
        }
        return mapping.get(error_type, ["growth", "value"])

    def _compute_weights(self, domain: str) -> Dict[str, float]:
        """
        计算新的维度权重。

        逻辑：
        - 精度高的维度 ↑ 权重
        - 精度低的维度 ↓ 权重
        - 总和 = 1.0
        """
        if domain not in self.accuracy_history:
            return {}

        dim_acc = {}
        for dim, history in self.accuracy_history[domain].items():
            if history:
                dim_acc[dim] = sum(history) / len(history)
            else:
                dim_acc[dim] = 0.5

        if not dim_acc:
            return {}

        # 用 softmax 归一化权重
        import math
        # INVESTMENT_DIMENSIONS keys are dimension names: growth/value/quality/momentum/macro/industry/management/technical
        dim_names = list(INVESTMENT_DIMENSIONS.keys())
        acc_values = [dim_acc.get(d, 0.5) for d in dim_names]
        exp_values = [math.exp(a * 2) for a in acc_values]  # 放大差异
        total = sum(exp_values)
        softmax_weights = [e / total for e in exp_values]

        new_weights = {
            dim_names[i]: round(softmax_weights[i], 4)
            for i in range(len(dim_names))
        }

        return new_weights

    def _get_dimension_accuracy(self, domain: str) -> Dict[str, float]:
        """获取各维度当前精度。"""
        result = {}
        if domain in self.accuracy_history:
            for dim, history in self.accuracy_history[domain].items():
                if history:
                    result[dim] = round(sum(history) / len(history), 4)
                else:
                    result[dim] = 0.5
        return result
