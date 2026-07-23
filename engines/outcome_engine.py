"""Outcome Engine — 自动从真实数据源生成 Outcome（Phase 1）

职责：
- 自动找到到期 Prediction（horizon 已过）
- 从数据源拉取实际值（akshare/yfinance/tencent/simulated）
- 自动计算误差、分类误差类型
- 创建 Outcome Entity 并持久化

输出：
- outcomes: List[Outcome] - 本次生成的 Outcome
- updated_predictions: List[Prediction] - 已更新状态的 Prediction
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from core import Outcome, ErrorType, Prediction, PredictionStatus
from data_fetcher import DataFetcher
from .base_engine import BaseEngine


class OutcomeEngine(BaseEngine):
    """自动 Outcome 生成引擎。"""

    def __init__(self, name: str = "outcome_engine", config: Dict[str, Any] = None):
        super().__init__(name, config)
        self.data_fetcher = DataFetcher()

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        输入 context：
          - predictions: List[Prediction]（已到期的）
          - dry_run: bool（可选，默认 False）

        输出 context 新增：
          - outcomes: List[Outcome]
          - updated_predictions: List[Prediction]
        """
        self.info("Outcome Engine 开始运行")
        predictions = context.get("predictions", [])
        dry_run = context.get("dry_run", False)

        outcomes = []
        updated_predictions = []

        for pred in predictions:
            if not self._is_due(pred):
                continue

            outcome = self._generate_outcome_for(pred, dry_run)
            if outcome:
                outcomes.append(outcome)
                # 更新 prediction 状态为 realized
                if not dry_run:
                    pred.status = PredictionStatus.REALIZED
                    updated_predictions.append(pred)

        context["outcomes"] = outcomes
        context["updated_predictions"] = updated_predictions
        self.info(f"Outcome Engine 完成: {len(outcomes)} 个新 Outcome")
        return context

    def _is_due(self, prediction) -> bool:
        """检查 prediction 是否到期（基于 created_at + horizon_days）。"""
        if prediction.status != PredictionStatus.ACTIVE:
            return False
        from datetime import timedelta
        due_date = prediction.created_at + timedelta(days=prediction.horizon_days)
        return datetime.now() >= due_date

    def _generate_outcome_for(self, prediction, dry_run: bool) -> Optional[Outcome]:
        """为单个 prediction 生成 outcome。"""
        target = prediction.target

        # 1. 从数据源拉取实际值
        data = self.data_fetcher.fetch(target)
        if data is None:
            self.warning(f"无法获取 {target} 的实际值，跳过")
            return None

        # data 是 dict，提取数值字段
        actual_value = self._extract_value(data, target)
        if actual_value is None:
            self.warning(f"{target} 数据格式无法解析: {data}")
            return None

        # 2. 计算误差
        expected = prediction.expected_value or 0.5

        # 2a. 数据质量检查：如果 expected 和 actual 量级差异超过 10 倍 → 跳过
        # 修复 P2 ⑦：避免 expected=1.015 和 actual=213.77 被误判为 missing_signal
        if abs(expected) > 0.01 and abs(actual_value) > 0.01:
            scale_ratio = max(abs(expected), abs(actual_value)) / min(abs(expected), abs(actual_value))
            if scale_ratio > 10:
                self.warning(
                    f"⚠ 数据质量跳过: {target} expected={expected:.4f} "
                    f"actual={actual_value:.4f} 量级差{scale_ratio:.0f}倍 → 不生成 Outcome"
                )
                return None

        # 2b. 计算误差
        error = abs(actual_value - expected)
        relative_error = error / abs(expected) if expected else error

        # 3. 分类误差
        error_type = self._classify_error(relative_error, prediction)

        # 4. 生成 Outcome
        outcome = Outcome(
            id=Outcome.generate_id(prediction.id, str(actual_value)),
            prediction_id=prediction.id,
            actual_value=actual_value,
            actual_result=f"实际值={actual_value}, 预期={expected:.4f}",
            prediction_error=round(error, 4),
            error_type=error_type,
            reason=self._infer_reason(error_type, prediction, actual_value),
            metadata={
                "auto_generated": True,
                "expected_value": expected,
                "relative_error": round(relative_error, 4),
                "raw_data": data,
            },
        )

        if dry_run:
            self.info(f"  [DRY-RUN] {target}: exp={expected} act={actual_value} err={error:.4f}")
        return outcome

    def _extract_value(self, data: Dict, target: str) -> Optional[float]:
        """从 data dict 提取数值。"""
        if not isinstance(data, dict):
            return None
        # 优先 value 字段
        if "value" in data:
            try:
                return float(data["value"])
            except (TypeError, ValueError):
                pass
        # 尝试常见数字字段
        for key in ["price", "rate", "ratio", "metric", "amount"]:
            if key in data:
                try:
                    return float(data[key])
                except (TypeError, ValueError):
                    pass
        # 找第一个可转换为 float 的字段
        for v in data.values():
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str):
                try:
                    return float(v)
                except ValueError:
                    continue
        return None

    def _classify_error(self, relative_error: float, prediction) -> ErrorType:
        """根据相对误差分类。"""
        if relative_error < 0.05:
            return ErrorType.NO_ERROR
        elif relative_error < 0.15:
            return ErrorType.REASONABLE
        elif relative_error < 0.30:
            return ErrorType.OVERCONFIDENCE
        else:
            return ErrorType.MISSING_SIGNAL  # 误差过大=可能漏掉关键信号

    def _infer_reason(self, error_type: ErrorType, prediction, actual_value: float) -> str:
        """推断误差原因。"""
        if error_type == ErrorType.NO_ERROR:
            return "预测准确"
        elif error_type == ErrorType.REASONABLE:
            return "误差在合理范围"
        elif error_type == ErrorType.OVERCONFIDENCE:
            return "过度自信，预测置信度超出实际表现"
        elif error_type == ErrorType.MISSING_SIGNAL:
            return "可能遗漏关键信号，实际值显著偏离预期"
        elif error_type == ErrorType.REGIME_MISMATCH:
            return "市场环境判断错误"
        else:
            return f"误差类型: {error_type.value}"