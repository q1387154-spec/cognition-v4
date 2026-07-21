"""Belief Entity — 动态信念（含置信度衰减）"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
import hashlib
import json


class BeliefStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


@dataclass
class Belief:
    """动态信念。Immutable ID，其他字段可更新。"""

    id: str
    subject: str
    probability: float
    confidence: float
    support_evidence_ids: List[str] = field(default_factory=list)
    contradict_evidence_ids: List[str] = field(default_factory=list)
    update_time: datetime = field(default_factory=datetime.now)
    decay_rate: float = 0.01
    version: int = 1
    status: BeliefStatus = BeliefStatus.ACTIVE
    previous_version_id: Optional[str] = None
    domain: str = "investment"
    horizon: str = "medium"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def decay_confidence(self, days: float) -> float:
        return self.confidence * ((1 - self.decay_rate) ** days)

    def to_dict(self) -> Dict[str, Any]:
        result = {}
        for k, v in self.__dict__.items():
            if isinstance(v, datetime):
                result[k] = v.isoformat()
            elif not k.startswith('_'):
                result[k] = v
        return result

    @classmethod
    def generate_id(cls, *parts: str) -> str:
        raw = '|'.join(str(p) for p in parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
