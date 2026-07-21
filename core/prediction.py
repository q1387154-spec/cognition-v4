"""Prediction Entity — 结构化预测（含概率分布）"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
import hashlib
import json


class PredictionStatus(str, Enum):
    ACTIVE = "active"
    REALIZED = "realized"
    CANCELLED = "cancelled"


class HorizonLabel(str, Enum):
    D5 = "5d"
    D20 = "20d"
    D90 = "90d"
    D180 = "180d"
    Y1 = "1y"
    Y3 = "3y"


@dataclass
class Scenario:
    name: str
    probability: float
    assumptions: List[str] = field(default_factory=list)
    target_value: Optional[float] = None
    expected_return: Optional[float] = None
    max_drawdown: Optional[float] = None


@dataclass
class Prediction:
    """结构化预测。"""

    id: str
    target: str
    belief_id: str
    probability_distribution: Dict[str, float] = field(default_factory=dict)
    scenarios: List[Scenario] = field(default_factory=list)
    expected_value: Optional[float] = None
    confidence: float = 0.5
    horizon_days: int = 90
    horizon_label: HorizonLabel = HorizonLabel.D90
    catalyst: Optional[str] = None
    regime: str = "neutral"
    effective_score: float = 0.5
    expected_return: Optional[float] = None
    max_drawdown: Optional[float] = None
    created_at: datetime = field(default_factory=datetime.now)
    bound_evidence_ids: List[str] = field(default_factory=list)
    status: PredictionStatus = PredictionStatus.ACTIVE
    metadata: Dict[str, Any] = field(default_factory=dict)

    def expected_return_pct(self) -> Optional[float]:
        if self.expected_value is None:
            return None
        return round((self.expected_value - 1) * 100, 2)

    @classmethod
    def generate_id(cls, *parts: str) -> str:
        raw = '|'.join(str(p) for p in parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
