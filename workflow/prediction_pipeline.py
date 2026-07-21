"""Prediction Pipeline — 预测主管道"""
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from engines import (
    ObservationEngine,
    EvidenceEngine,
    BeliefEngine,
    PredictionEngine,
)
from memory import (
    ObservationStore,
    EvidenceStore,
    BeliefStore,
    PredictionStore,
    CausalGraphStore,
)

logger = logging.getLogger("cognition-v4")


class PredictionPipeline:
    """
    预测主管道：

    Observation → Evidence → Belief → Prediction

    Engine 负责流程，LLM 只是工具。
    """

    def __init__(self, db_path: str):
        self.db_path = db_path

        # 初始化 Store
        self.obs_store = ObservationStore.get(db_path)
        self.ev_store = EvidenceStore.get(db_path)
        self.belief_store = BeliefStore.get(db_path)
        self.pred_store = PredictionStore.get(db_path)

        # 初始化 Engine
        self.obs_engine = ObservationEngine("observation_engine")
        self.ev_engine = EvidenceEngine("evidence_engine")
        self.belief_engine = BeliefEngine("belief_engine")
        self.pred_engine = PredictionEngine("prediction_engine")

    def run(
        self,
        sources: Optional[List[dict]] = None,
        wiki_dir: Optional[str] = None,
        subject: Optional[str] = None,
        horizon_days: int = 90,
    ) -> Dict[str, Any]:
        """
        运行预测管道。

        Args:
            sources: 原始信息列表（可选）
            wiki_dir: Wiki 目录（自动摄取 Observation）
            subject: 信念主体（如 "赛力斯毛利率"）
            horizon_days: 预测期限

        Returns:
            {
                "observations": List[Observation],
                "evidence_list": List[Evidence],
                "belief": Belief,
                "prediction": Prediction,
                "status": "success" | "partial" | "failed",
            }
        """
        logger.info(f"=== Prediction Pipeline 开始 | subject={subject} | horizon={horizon_days}d ===")

        context: Dict[str, Any] = {
            "sources": sources or [],
            "wiki_dir": wiki_dir,
            "subject": subject,
            "horizon_days": horizon_days,
            "timestamp": datetime.now(),
        }

        try:
            # Step 1: Observation Engine
            context = self.obs_engine.run(context)
            observations = context.get("observations", [])

            # 持久化 Observation
            for obs in observations:
                try:
                    self.obs_store.insert(obs)
                except Exception:
                    pass  # 去重失败（已有 ID）

            # Step 2: Evidence Engine
            context = self.ev_engine.run(context)
            evidence_list = context.get("evidence_list", [])

            # 持久化 Evidence
            for ev in evidence_list:
                try:
                    self.ev_store.insert(ev)
                except Exception:
                    pass

            # Step 3: Belief Engine
            if evidence_list:
                # 获取已有 Belief
                existing_belief = None
                if subject:
                    beliefs = self.belief_store.get_active(subject=subject)
                    existing_belief = beliefs[0] if beliefs else None

                context["evidence"] = evidence_list
                context["existing_belief"] = existing_belief
                context = self.belief_engine.run(context)

                belief = context.get("belief")
                if belief:
                    # 归档旧版本
                    if existing_belief:
                        self.belief_store.archive_previous(existing_belief.id)
                    # 持久化
                    self.belief_store.insert(belief)

            # Step 4: Prediction Engine
            if evidence_list:
                context["bound_evidence"] = evidence_list
                context = self.pred_engine.run(context)
                prediction = context.get("prediction")

                if prediction:
                    # 持久化
                    self.pred_store.insert(prediction)
                    logger.info(f"✅ Prediction 创建成功: {prediction.id}")

            # 返回结果
            return {
                "observations": observations,
                "evidence_list": evidence_list,
                "belief": context.get("belief"),
                "prediction": context.get("prediction"),
                "status": "success" if context.get("prediction") else "partial",
            }

        except Exception as e:
            logger.error(f"Prediction Pipeline 异常: {e}", exc_info=True)
            return {
                "observations": context.get("observations", []),
                "evidence_list": context.get("evidence_list", []),
                "belief": context.get("belief"),
                "prediction": None,
                "status": "failed",
                "error": str(e),
            }
