"""pytest fixtures for cognition-v4 tests."""
import pytest
from memory import reset_all_stores


@pytest.fixture(autouse=True)
def reset_stores_between_tests():
    """在每个测试前重置所有 Store 单例，避免跨测试污染。"""
    reset_all_stores()
    yield
