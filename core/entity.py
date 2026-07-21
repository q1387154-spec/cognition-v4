"""Base Entity — 所有 Entity 的基类（Mixin）"""
from datetime import datetime
from typing import Any, Dict
import hashlib
import json


class BaseMixin:
    """混入类——提供通用方法，不影响 dataclass 字段定义。"""

    @property
    def created_at(self) -> datetime:
        """子类必须实现。"""
        raise NotImplementedError

    def to_dict(self) -> Dict[str, Any]:
        """序列化。"""
        result = {}
        for k, v in self.__dict__.items():
            if isinstance(v, datetime):
                result[k] = v.isoformat()
            elif not k.startswith('_'):
                result[k] = v
        return result

    def fingerprint(self) -> str:
        """内容指纹（用于去重）。"""
        content = json.dumps(self.to_dict(), sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    @classmethod
    def generate_id(cls, *parts: str) -> str:
        """生成确定性 ID。"""
        raw = '|'.join(str(p) for p in parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
