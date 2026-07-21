"""Learning Pipeline — 学习主管道"""
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from engines import LearningEngine
from core import Outcome, Belief, Prediction
from memory import (
    BeliefStore,
    PredictionStore,
    OutcomeStore,
    LearningStore,
)

logger = logging.getLogger("cognition-v4")


class LearningPipeline:
    """
    学习主管道：

    Prediction + Outcome → Learning → Belief 校准 → Weight 更新

    Learning 是真正的闭环——系统因此变聪明。
    """

    def __init__(self, db_path: str):
        self.db_path = db_path

        self.belief_store = BeliefStore.get(db_path)
        self.pred_store = PredictionStore.get(db_path)
        self.outcome_store = OutcomeStore.get(db_path)
        self.learning_store = LearningStore.get(db_path)

        self.learning_engine = LearningEngine("learning_engine")

    def run(
        self,
        outcome: Outcome,
        prediction: Prediction,
        belief: Belief,
    ) -> Dict[str, Any]:
        """
        运行学习管道。

        Args:
            outcome: Outcome（实际结果）
            prediction: Prediction（原始预测）
            belief: Belief（原始信念）

        Returns:
            {
                "learning": Learning,
                "weight_updates": dict,
                "belief_adjustment": float,
                "status": "success" | "failed",
            }
        """
        logger.info(f"=== Learning Pipeline 开始 | outcome={outcome.id} | prediction={prediction.id} ===")

        context: Dict[str, Any] = {
            "outcome": outcome,
            "prediction": prediction,
            "belief": belief,
            "timestamp": datetime.now(),
        }

        try:
            # Step 1: Learning Engine
            context = self.learning_engine.run(context)
            learning = context.get("learning")

            if learning:
                # 持久化 Learning
                self.learning_store.insert(learning)

                # Step 2: 校准 Belief
                self._calibrate_belief(belief, context["belief_adjustment"])

                # Step 3: 更新 Prediction 状态
                self.pred_store.mark_realized(prediction.id)

                logger.info(f"✅ Learning 完成: {learning.id}, 调整={context['belief_adjustment']:+.3f}")

            return {
                "learning": learning,
                "weight_updates": context.get("weight_updates", {}),
                "belief_adjustment": context.get("belief_adjustment", 0.0),
                "status": "success" if learning else "failed",
            }

        except Exception as e:
            logger.error(f"Learning Pipeline 异常: {e}", exc_info=True)
            return {
                "learning": None,
                "weight_updates": {},
                "belief_adjustment": 0.0,
                "status": "failed",
                "error": str(e),
            }

    def _calibrate_belief(self, belief: Belief, adjustment: float):
        """校准 Belief 置信度。"""
        try:
            from core import Belief
            import uuid
            # 归档旧版本
            self.belief_store.archive_previous(belief.id)

            # 创建新版本（用新ID）
            new_belief = Belief(
                id=str(uuid.uuid4())[:16],
                subject=belief.subject,
                probability=belief.probability,
                confidence=max(0.0, min(1.0, belief.confidence + adjustment)),
                support_evidence_ids=belief.support_evidence_ids,
                contradict_evidence_ids=belief.contradict_evidence_ids,
                update_time=datetime.now(),
                decay_rate=belief.decay_rate,
                version=belief.version + 1,
                status=belief.status,
                previous_version_id=belief.id,
                domain=belief.domain,
                horizon=belief.horizon,
                metadata=belief.metadata,
            )
            self.belief_store.insert(new_belief)
        except Exception as e:
            self.warning(f"Belief 校准失败: {e}")

    def process_due_predictions(self) -> Dict[str, Any]:
        """
        处理所有已到期 Prediction。

        Cron 调用：每日检查已到期 Prediction，
        触发 Outcome + Learning 流程。
        """
        due_predictions = self.pred_store.list_due()
        logger.info(f"发现 {len(due_predictions)} 个到期 Prediction")

        results = []
        for pred in due_predictions:
            # 实际应用中这里会从数据源获取 actual_value
            # 目前仅记录，不自动创建 Outcome
            results.append({
                "prediction_id": pred.id,
                "target": pred.target,
                "status": "awaiting_outcome",
            })

        return {
            "due_count": len(due_predictions),
            "predictions": results,
        }
