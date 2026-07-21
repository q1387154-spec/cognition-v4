"""Engine 配置"""
from enum import Enum


class EngineName(str, Enum):
    OBSERVATION = "observation_engine"
    EVIDENCE = "evidence_engine"
    GAP = "gap_engine"
    CAUSAL = "causal_engine"
    PREDICTION = "prediction_engine"
    SCENARIO = "scenario_engine"
    DECISION = "decision_engine"
    OUTCOME = "outcome_engine"
    LEARNING = "learning_engine"
    CONFIDENCE = "confidence_engine"
    PREDICTABILITY = "predictability_engine"
    WORLD_MODEL = "world_model"


ENGINE_PIPELINE_ORDER = [
    EngineName.OBSERVATION,
    EngineName.EVIDENCE,
    EngineName.GAP,
    EngineName.CAUSAL,
    EngineName.PREDICTION,
    EngineName.SCENARIO,
    EngineName.DECISION,
    EngineName.OUTCOME,
    EngineName.LEARNING,
    # World Model 是 Phase 4
]

# Gap Engine 阈值
GAP_CONFIDENCE_THRESHOLD = 0.6    # 置信度低于此值触发 Deep Research
GAP_HORIZON_WARNING_DAYS = 7     # 到期前 N 天预警

# Predictability Engine 阈值
PREDICTABILITY_LOW = 0.3         # 低于此值提示谨慎
PREDICTABILITY_HIGH = 0.7        # 高于此值可以依赖

# Decision Engine 信号阈值
DECISION_THRESHOLDS = {
    "strong_buy": 0.75,
    "buy": 0.60,
    "hold": 0.45,
    "sell": 0.30,
    "strong_sell": 0.0,
}
