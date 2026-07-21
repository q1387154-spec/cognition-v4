"""Horizon 配置"""
from enum import Enum


class HorizonLabel(str, Enum):
    D5 = "5d"
    D20 = "20d"
    D90 = "90d"
    D180 = "180d"
    Y1 = "1y"
    Y3 = "3y"


HORIZON_DAYS = {
    HorizonLabel.D5: 5,
    HorizonLabel.D20: 20,
    HorizonLabel.D90: 90,
    HorizonLabel.D180: 180,
    HorizonLabel.Y1: 365,
    HorizonLabel.Y3: 1095,
}

HORIZON_THRESHOLDS = {
    "immediate": (0, 5),
    "short": (5, 20),
    "medium": (20, 90),
    "long": (90, 180),
    "structural": (180, float("inf")),
}


def days_to_horizon_label(days: int) -> HorizonLabel:
    """天数 → HorizonLabel。"""
    if days <= 5:
        return HorizonLabel.D5
    elif days <= 20:
        return HorizonLabel.D20
    elif days <= 90:
        return HorizonLabel.D90
    elif days <= 180:
        return HorizonLabel.D180
    elif days <= 365:
        return HorizonLabel.Y1
    else:
        return HorizonLabel.Y3
