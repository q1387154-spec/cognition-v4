"""Observation Entity — 原始信息摄入（永不修改）"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum


class ObservationSource(str, Enum):
    NEWS = "news"
    ANNOUNCEMENT = "announcement"
    FINANCIAL_REPORT = "financial_report"
    RESEARCH_REPORT = "research_report"
    MARKET_DATA = "market_data"
    POLICY = "policy"
    SOCIAL_MEDIA = "social_media"
    WEBSITE = "website"
    OTHER = "other"


@dataclass
class Observation:
    """原始信息摄入。Immutable——永远不修改。"""

    id: str
    source: ObservationSource
    raw_content: str = ""
    title: Optional[str] = None
    url: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    def fingerprint(self) -> str:
        import hashlib, json
        content = json.dumps(self.__dict__, sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    @classmethod
    def generate_id(cls, *parts: str) -> str:
        import hashlib
        raw = '|'.join(str(p) for p in parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
