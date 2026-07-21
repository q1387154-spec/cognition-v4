"""Learning Entity — 反馈学习（真正的闭环）"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any
from enum import Enum
import hashlib
import json


class LearningType(str, Enum):
    FEATURE = "feature"
    CAUSAL = "causal"
    WEIGHT = "weight"
    BELIEF = "belief"
    REGIME = "regime"


@dataclass
class CausalEdgeUpdate:
    from_node: str
    to_node: str
    old_weight: float
    new_weight: float
    confidence: float


@dataclass
class Learning:
    """学习记录。每次 Prediction → Outcome 生成一条。Immutable。"""

    id: str
    outcome_id: str
    prediction_id: str
    belief_id: str
    learning_type: LearningType
    feature_updates: Dict[str, float] = field(default_factory=dict)
    causal_updates: List[CausalEdgeUpdate] = field(default_factory=list)
    weight_updates: Dict[str, float] = field(default_factory=dict)
    belief_adjustment: float = 0.0
    accuracy_delta: float = 0.0
    regime_correction: Optional[str] = None
    counterfactuals: List[str] = field(default_factory=list)
    learned_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    @classmethod
    def generate_id(cls, *parts: str) -> str:
        import hashlib
        raw = '|'.join(str(p) for p in parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]