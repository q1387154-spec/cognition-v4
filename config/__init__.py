"""Config — 领域/Horizon/引擎配置"""
from .domains import (
    Domain,
    INVESTMENT_DIMENSIONS,
    LEARNING_RATE,
    WEIGHT_LEARNING_RATE,
    BELIEF_LEARNING_RATE,
    CONFIDENCE_DECAY_RATE,
    CONFIDENCE_HALFLIFE_DAYS,
)
from .horizons import (
    HorizonLabel as ConfigHorizonLabel,
    HORIZON_DAYS,
    HORIZON_THRESHOLDS,
    days_to_horizon_label,
)
from .engines import (
    EngineName,
    ENGINE_PIPELINE_ORDER,
    GAP_CONFIDENCE_THRESHOLD,
    GAP_HORIZON_WARNING_DAYS,
    PREDICTABILITY_LOW,
    PREDICTABILITY_HIGH,
    DECISION_THRESHOLDS,
)

__all__ = [
    "Domain",
    "INVESTMENT_DIMENSIONS",
    "LEARNING_RATE",
    "WEIGHT_LEARNING_RATE",
    "BELIEF_LEARNING_RATE",
    "CONFIDENCE_DECAY_RATE",
    "CONFIDENCE_HALFLIFE_DAYS",
    "ConfigHorizonLabel",
    "HORIZON_DAYS",
    "HORIZON_THRESHOLDS",
    "days_to_horizon_label",
    "EngineName",
    "ENGINE_PIPELINE_ORDER",
    "GAP_CONFIDENCE_THRESHOLD",
    "GAP_HORIZON_WARNING_DAYS",
    "PREDICTABILITY_LOW",
    "PREDICTABILITY_HIGH",
    "DECISION_THRESHOLDS",
]
