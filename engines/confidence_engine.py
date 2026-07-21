"""Confidence Engine — 置信度校准（避免过度自信/过度保守）"""
from typing import Dict, Any, List, Optional
from datetime import datetime

from .base_engine import BaseEngine


class ConfidenceEngine(BaseEngine):
    """
    Confidence Engine：置信度校准。

    避免两种错误：
    1. 过度自信：高置信度 + 低 accuracy
    2. 过度保守：低置信度 + 实际预测准确

    方法：
    - 历史 accuracy 回测
    - 校准曲线（reliability diagram）
    - Bayesian 置信区间
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("confidence_engine", config)
        # 每个 domain 的校准参数
        self.calibration_cache: Dict[str, List[dict]] = {}  # domain → [(confidence, accuracy), ...]

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        输入 context：
          - predictions: List[Prediction]
          - outcomes: List[Outcome]（已有结果的 Prediction+Outcome 对）
          - domain: str（可选，默认 "investment"）

        输出 context 新增：
          - calibrated_confidence: float
          - calibration_report: dict
        """
        self.info("Confidence Engine 开始运行")

        predictions = context.get("predictions", [])
        outcomes = context.get("outcomes", [])
        domain = context.get("domain", "investment")

        if not predictions and not outcomes:
            self.info("无数据，返回默认置信度 0.5")
            context["calibrated_confidence"] = 0.5
            context["calibration_report"] = {"status": "no_data", "confidence": 0.5}
            return context

        # 计算校准置信度
        calibrated = self._calibrate(predictions, outcomes, domain)

        context["calibrated_confidence"] = calibrated["confidence"]
        context["calibration_report"] = calibrated["report"]

        self.info(f"Confidence Engine 完成: calibrated={calibrated['confidence']:.3f}, "
                   f"accuracy={calibrated['report'].get('historical_accuracy', 'N/A')}")
        return context

    def _calibrate(
        self,
        predictions: List,
        outcomes: List,
        domain: str,
    ) -> Dict[str, Any]:
        """基于历史 accuracy 校准置信度。"""
        # 如果有 outcomes，计算历史 accuracy
        if outcomes:
            historical_accuracy = self._compute_historical_accuracy(outcomes)
            self._update_cache(domain, predictions, outcomes)

        # 从缓存获取校准数据
        cache = self.calibration_cache.get(domain, [])
        if len(cache) < 3:
            return {
                "confidence": 0.5,
                "report": {
                    "status": "insufficient_data",
                    "cache_size": len(cache),
                    "historical_accuracy": None,
                    "bias": "unknown",
                }
            }

        # 计算校准后的置信度
        avg_confidence = sum(p.confidence for p in predictions) / len(predictions) if predictions else 0.5
        avg_accuracy = sum(c["accuracy"] for c in cache) / len(cache) if cache else 0.5

        # 校准公式：adjusted_confidence = α × accuracy + (1-α) × raw_confidence
        # α 根据历史数据调整：如果过度自信 α 高，如果过度保守 α 低
        alpha = self._compute_alpha(cache, avg_confidence)

        calibrated = alpha * avg_accuracy + (1 - alpha) * avg_confidence
        calibrated = max(0.1, min(0.95, calibrated))  # 限制范围

        # 判断偏差类型
        bias = self._detect_bias(cache)

        return {
            "confidence": round(calibrated, 4),
            "report": {
                "status": "calibrated",
                "cache_size": len(cache),
                "historical_accuracy": round(avg_accuracy, 4),
                "raw_confidence": round(avg_confidence, 4),
                "calibrated_confidence": round(calibrated, 4),
                "alpha": round(alpha, 4),
                "bias": bias,
                "n_predictions": len(predictions),
                "n_outcomes": len(outcomes),
            }
        }

    def _compute_historical_accuracy(self, outcomes: List) -> float:
        """计算历史 accuracy（1 - prediction_error 均值）。"""
        if not outcomes:
            return 0.5
        avg_error = sum(o.prediction_error for o in outcomes) / len(outcomes)
        return max(0.0, min(1.0, 1.0 - avg_error))

    def _update_cache(self, domain: str, predictions: List, outcomes: List):
        """更新校准缓存。"""
        if domain not in self.calibration_cache:
            self.calibration_cache[domain] = []

        # 匹配 prediction 和 outcome
        pred_map = {p.id: p for p in predictions}
        for outcome in outcomes:
            if outcome.prediction_id in pred_map:
                pred = pred_map[outcome.prediction_id]
                accuracy = max(0.0, 1.0 - outcome.prediction_error)
                self.calibration_cache[domain].append({
                    "confidence": pred.confidence,
                    "accuracy": accuracy,
                    "timestamp": datetime.now().isoformat(),
                })

        # 缓存上限 100 条
        if len(self.calibration_cache[domain]) > 100:
            self.calibration_cache[domain] = self.calibration_cache[domain][-100:]

    def _compute_alpha(self, cache: List[dict], raw_confidence: float) -> float:
        """计算校准系数 α。"""
        if len(cache) < 3:
            return 0.3  # 数据少时保守

        avg_confidence = sum(c["confidence"] for c in cache) / len(cache)
        avg_accuracy = sum(c["accuracy"] for c in cache) / len(cache)

        # 如果过度自信（confidence > accuracy）：α 提高，降低置信度
        # 如果过度保守（confidence < accuracy）：α 降低，提高置信度
        bias = avg_confidence - avg_accuracy

        if bias > 0.1:  # 过度自信
            alpha = 0.4
        elif bias < -0.1:  # 过度保守
            alpha = 0.2
        else:
            alpha = 0.3

        return alpha

    def _detect_bias(self, cache: List[dict]) -> str:
        """检测偏差类型。"""
        if len(cache) < 3:
            return "unknown"
        avg_confidence = sum(c["confidence"] for c in cache) / len(cache)
        avg_accuracy = sum(c["accuracy"] for c in cache) / len(cache)
        bias = avg_confidence - avg_accuracy
        if bias > 0.1:
            return "overconfident"
        elif bias < -0.1:
            return "underconfident"
        return "well_calibrated"
