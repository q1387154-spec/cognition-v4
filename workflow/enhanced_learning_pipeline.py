"""Enhanced Learning Pipeline — 完整学习闭环"""
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from engines import (
    LearningEngine,
    CounterfactualEngine,
    FeatureLearningEngine,
    WeightLearningEngine,
)
from memory import (
    BeliefStore,
    PredictionStore,
    OutcomeStore,
    LearningStore,
)

logger = logging.getLogger("cognition-v4")


class EnhancedLearningPipeline:
    """
    增强学习管道：

    Prediction + Outcome
        ↓
    CounterfactualEngine（反事实分析）
        ↓
    FeatureLearningEngine（特征重要性）
        ↓
    WeightLearningEngine（维度权重）
        ↓
    LearningEngine（生成 Learning Entity）
        ↓
    Belief 校准
        ↓
    CausalGraph 更新（Phase 4）

    Learning 是真正的闭环——系统因此变聪明。
    """

    def __init__(self, db_path: str):
        self.db_path = db_path

        self.belief_store = BeliefStore.get(db_path)
        self.pred_store = PredictionStore.get(db_path)
        self.outcome_store = OutcomeStore.get(db_path)
        self.learning_store = LearningStore.get(db_path)

        self.counterfactual_engine = CounterfactualEngine("counterfactual_engine")
        self.feature_engine = FeatureLearningEngine("feature_learning_engine")
        self.weight_engine = WeightLearningEngine("weight_learning_engine")
        self.learning_engine = LearningEngine("learning_engine")

    def run(
        self,
        outcome: "Outcome",
        prediction: "Prediction",
        belief: "Belief",
        features: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        增强学习管道。

        Args:
            outcome: Outcome（实际结果）
            prediction: Prediction（原始预测）
            belief: Belief（原始信念）
            features: 该 prediction 使用的 feature 列表

        Returns:
            包含 counterfactuals / feature_ranking / weight_updates / learning 的 dict
        """
        logger.info(
            f"=== Enhanced Learning Pipeline === "
            f"outcome={outcome.id[:8]} pred={prediction.id[:8]} "
            f"error={outcome.prediction_error:.3f} type={outcome.error_type.value}"
        )

        context = {
            "outcome": outcome,
            "prediction": prediction,
            "belief": belief,
            "features": features or [],
            "timestamp": datetime.now(),
        }

        try:
            # Step 1: Counterfactual Analysis
            context = self.counterfactual_engine.run(context)
            counterfactuals = context.get("counterfactuals", [])
            logger.info(f"  Counterfactuals: {len(counterfactuals)} 个")

            # Step 2: Feature Learning
            context["domain"] = "investment"
            context = self.feature_engine.run(context)
            feature_ranking = context.get("feature_ranking", [])
            logger.info(f"  Feature Ranking: top={feature_ranking[0]['feature'] if feature_ranking else 'N/A'}")

            # Step 3: Weight Learning
            context = self.weight_engine.run(context)
            weight_updates = context.get("weight_updates", {})
            dimension_accuracy = context.get("dimension_accuracy", {})
            logger.info(f"  Weight Updates: {len(weight_updates)} 个")

            # Step 4: Learning Entity（整合所有结果）
            context["counterfactuals"] = [cf.scenario for cf in counterfactuals]
            context["feature_ranking"] = feature_ranking
            context["weight_updates"] = weight_updates
            context["dimension_accuracy"] = dimension_accuracy
            context = self.learning_engine.run(context)
            learning = context.get("learning")

            if learning:
                self.learning_store.insert(learning)
                logger.info(f"  Learning Entity: {learning.id[:8]} type={learning.learning_type.value}")

            # Step 5: Belief 校准
            belief_adjustment = context.get("belief_adjustment", 0.0)
            self._calibrate_belief(belief, belief_adjustment)

            # Step 6: 更新 Prediction 状态
            self.pred_store.mark_realized(prediction.id)

            result = {
                "status": "success",
                "counterfactuals": counterfactuals,
                "feature_ranking": feature_ranking,
                "weight_updates": weight_updates,
                "dimension_accuracy": dimension_accuracy,
                "learning": learning,
                "belief_adjustment": belief_adjustment,
            }

            logger.info(
                f"  ✅ Learning 完成: adj={belief_adjustment:+.3f} "
                f"top_feature={feature_ranking[0]['feature'] if feature_ranking else 'N/A'}"
            )
            return result

        except Exception as e:
            logger.error(f"Enhanced Learning Pipeline 异常: {e}", exc_info=True)
            return {
                "status": "failed",
                "error": str(e),
                "counterfactuals": context.get("counterfactuals", []),
                "feature_ranking": context.get("feature_ranking", []),
                "weight_updates": context.get("weight_updates", {}),
                "learning": None,
                "belief_adjustment": 0.0,
            }

    def _calibrate_belief(self, belief, adjustment: float):
        """校准 Belief 置信度。"""
        try:
            import uuid
            self.belief_store.archive_previous(belief.id)
            new_belief = belief.__class__(
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
            logger.warning(f"Belief 校准失败: {e}")
