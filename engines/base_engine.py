"""Base Engine — 所有引擎的基类"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger("cognition-v4")


class BaseEngine(ABC):
    """所有 Engine 的抽象基类。"""

    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        self.name = name
        self.config = config or {}

    @abstractmethod
    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行引擎逻辑。

        Args:
            context: 管道上下文，包含输入数据和中间结果

        Returns:
            更新后的 context（Engine 不修改输入，只输出结果）
        """
        raise NotImplementedError

    def log(self, level: str, msg: str, **kwargs):
        getattr(logger, level)(f"[{self.name}] {msg}", **kwargs)

    def info(self, msg: str, **kwargs):
        self.log("info", msg, **kwargs)

    def warning(self, msg: str, **kwargs):
        self.log("warning", msg, **kwargs)

    def error(self, msg: str, **kwargs):
        self.log("error", msg, **kwargs)


class EngineRegistry:
    """引擎注册表。"""

    _engines: Dict[str, BaseEngine] = {}

    @classmethod
    def register(cls, name: str, engine: BaseEngine):
        cls._engines[name] = engine

    @classmethod
    def get(cls, name: str) -> Optional[BaseEngine]:
        return cls._engines.get(name)

    @classmethod
    def list_all(cls) -> Dict[str, BaseEngine]:
        return dict(cls._engines)
