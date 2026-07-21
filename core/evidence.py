"""Evidence Entity — 结构化证据（从 Observation 提炼）"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
import hashlib
import json


class EvidenceType(str, Enum):
    QUANTITATIVE = "quantitative"
    QUALITATIVE = "qualitative"
    CATEGORICAL = "categorical"


class NoveltyLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class HorizonType(str, Enum):
    IMMEDIATE = "immediate"
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"
    STRUCTURAL = "structural"
    UNKNOWN = "unknown"


@dataclass
class Evidence:
    """结构化证据。从 Observation 语义提炼，永不修改。"""

    id: str
    observation_ids: List[str]
    content: str
    type: EvidenceType
    confidence: float
    novelty: NoveltyLevel
    horizon: HorizonType
    importance: float
    domain: str = "investment"
    summary: Optional[str] = None
    binding_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        result = {}
        for k, v in self.__dict__.items():
            if isinstance(v, datetime):
                result[k] = v.isoformat()
            elif not k.startswith('_'):
                result[k] = v
        return result

    def fingerprint(self) -> str:
        content = json.dumps(self.to_dict(), sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    @classmethod
    def generate_id(cls, *parts: str) -> str:
        raw = '|'.join(str(p) for p in parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
