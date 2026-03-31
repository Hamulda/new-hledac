"""Test backpressure reduces concurrency under memory pressure."""
import pathlib
import sys

_universal = pathlib.Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_universal))

from unittest.mock import patch
from resource_allocator import get_recommended_concurrency


def test_backpressure_concurrency():
    """Under warn level, fetch concurrency drops to 8."""
    with patch("resource_allocator.get_memory_pressure_level", return_value="warn"):
        limits = get_recommended_concurrency()
        assert limits["fetch"] == 8, f"Expected fetch=8, got {limits['fetch']}"
        assert limits["ml_jobs"] == 0, f"Expected ml_jobs=0, got {limits['ml_jobs']}"


if __name__ == "__main__":
    test_backpressure_concurrency()
    print("test_backpressure_reduces_concurrency: PASSED")
