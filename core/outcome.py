"""Outcome Entity — 实际结果与误差"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
import hashlib
import json


class ErrorType(str, Enum):
    MISSING_SIGNAL = "missing_signal"
    CONFIRMATION_BIAS = "confirmation_bias"
    OVERCONFIDENCE = "overconfidence"
    REGIME_MISMATCH = "regime_mismatch"
    HORIZON_MISMATCH = "horizon_mismatch"
    NO_ERROR = "no_error"
    REASONABLE = "reasonable"


@dataclass
class Outcome:
    """实际结果。Immutable。"""

    id: str
    prediction_id: str
    actual_value: float
    actual_result: str
    prediction_error: float
    error_type: ErrorType = ErrorType.NO_ERROR
    reason: Optional[str] = None
    realized_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    @classmethod
    def generate_id(cls, *parts: str) -> str:
        raw = '|'.join(str(p) for p in parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
