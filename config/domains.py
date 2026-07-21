"""Domain 配置"""
from enum import Enum


class Domain(str, Enum):
    INVESTMENT = "investment"
    INDUSTRY = "industry"
    MACRO = "macro"
    COMPANY = "company"
    POLICY = "policy"
    OTHER = "other"


# 投资领域子维度（用于 Weight Learning）
INVESTMENT_DIMENSIONS = {
    "growth": {
        "label": "成长",
        "weight": 0.15,
        "description": "收入/利润增速",
    },
    "value": {
        "label": "估值",
        "weight": 0.15,
        "description": "PE/PB/PS",
    },
    "quality": {
        "label": "质量",
        "weight": 0.15,
        "description": "ROE/毛利率/现金流",
    },
    "momentum": {
        "label": "动量",
        "weight": 0.15,
        "description": "趋势/成交量",
    },
    "macro": {
        "label": "宏观",
        "weight": 0.10,
        "description": "利率/汇率/政策",
    },
    "industry": {
        "label": "产业",
        "weight": 0.10,
        "description": "竞争格局/技术路线",
    },
    "management": {
        "label": "管理层",
        "weight": 0.10,
        "description": "战略/执行力",
    },
    "technical": {
        "label": "技术",
        "weight": 0.10,
        "description": "技术面/图形",
    },
}

# 所有维度权重之和 = 1.0
assert abs(sum(d["weight"] for d in INVESTMENT_DIMENSIONS.values()) - 1.0) < 0.001


# Learning Rate 配置
LEARNING_RATE = 0.05          # 全局学习率
WEIGHT_LEARNING_RATE = 0.02    # 权重更新学习率（更保守）
BELIEF_LEARNING_RATE = 0.05   # Belief 更新学习率

# 置信度衰减
CONFIDENCE_DECAY_RATE = 0.01   # 每天衰减 1%
CONFIDENCE_HALFLIFE_DAYS = 70  # 约 70 天减半
