"""Feature Learning Engine — 特征重要性追踪"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from collections import defaultdict

from .base_engine import BaseEngine


class FeatureLearningEngine(BaseEngine):
    """
    Feature Learning Engine：特征重要性追踪。

    核心问题："哪些Feature最影响预测精度？"

    方法：
    1. 每次 Outcome 到达时，记录 (feature → error_delta)
    2. 维护每个 domain 的 feature importance 排名
    3. 误差大时，该 prediction 使用的 feature 重要性降低
    4. 输出：feature_ranking（按 domain）
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("feature_learning_engine", config)
        # feature_importance[domain][feature] = (total_score, count)
        self.feature_importance: Dict[str, Dict[str, List[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        # 每个 feature 的精度记录
        self.feature_accuracy: Dict[str, Dict[str, List[float]]] = defaultdict(
            lambda: defaultdict(list)
        )

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        输入 context：
          - outcome: Outcome
          - prediction: Prediction
          - features: List[str]（该 prediction 使用的 feature 列表）
          - domain: str

        输出 context 新增：
          - feature_ranking: List[dict]  # [{feature, importance, accuracy, count}, ...]
        """
        self.info("Feature Learning Engine 开始运行")

        outcome = context.get("outcome")
        prediction = context.get("prediction")
        features = context.get("features", [])
        domain = context.get("domain", "investment")

        if not outcome or not features:
            # 无数据时返回空排名（而非默认排名）
            context["feature_ranking"] = []
            return context

        # 计算每个 feature 的精度
        accuracy = max(0.0, 1.0 - outcome.prediction_error)

        for feature in features:
            self.feature_accuracy[domain][feature].append(accuracy)
            self.feature_importance[domain][feature].append(
                accuracy if outcome.prediction_error < 0.2 else -outcome.prediction_error
            )

        # 生成排名
        ranking = self._compute_ranking(domain)

        context["feature_ranking"] = ranking
        context["feature_count"] = len(ranking)

        self.info(f"Feature Learning 完成: {len(ranking)} features, top={ranking[0]['feature'] if ranking else 'N/A'}")
        return context

    def _compute_ranking(self, domain: str) -> List[Dict[str, Any]]:
        """计算 feature 排名。"""
        features = self.feature_importance.get(domain, {})
        if not features:
            return []

        ranking = []
        for feature, scores in features.items():
            if not scores:
                continue
            acc_list = self.feature_accuracy[domain][feature]
            avg_accuracy = sum(acc_list) / len(acc_list) if acc_list else 0.5
            avg_score = sum(scores) / len(scores)
            ranking.append({
                "feature": feature,
                "importance": round(avg_score, 4),
                "avg_accuracy": round(avg_accuracy, 4),
                "count": len(scores),
            })

        # 按 importance 降序
        ranking.sort(key=lambda x: x["importance"], reverse=True)
        return ranking

    def _get_default_ranking(self, domain: str) -> List[Dict[str, Any]]:
        """默认 feature 排名（无历史数据时）。"""
        defaults = {
            "investment": [
                {"feature": "growth", "label": "成长", "default_importance": 0.15},
                {"feature": "value", "label": "估值", "default_importance": 0.15},
                {"feature": "quality", "label": "质量", "default_importance": 0.15},
                {"feature": "momentum", "label": "动量", "default_importance": 0.15},
                {"feature": "macro", "label": "宏观", "default_importance": 0.10},
                {"feature": "industry", "label": "产业", "default_importance": 0.10},
                {"feature": "management", "label": "管理层", "default_importance": 0.10},
                {"feature": "technical", "label": "技术", "default_importance": 0.10},
            ]
        }
        items = defaults.get(domain, defaults["investment"])
        return [
            {"feature": d["feature"], "importance": d["default_importance"],
             "avg_accuracy": 0.5, "count": 0, "label": d["label"]}
            for d in items
        ]

    def get_top_features(self, domain: str = "investment", top_n: int = 3) -> List[str]:
        """获取 top N 最重要的 feature。"""
        ranking = self._compute_ranking(domain)
        return [r["feature"] for r in ranking[:top_n]]

    def get_bottom_features(self, domain: str = "investment", bottom_n: int = 2) -> List[str]:
        """获取 bottom N（应降低权重的）feature。"""
        ranking = self._compute_ranking(domain)
        return [r["feature"] for r in ranking[-bottom_n:]] if len(ranking) >= bottom_n else []
