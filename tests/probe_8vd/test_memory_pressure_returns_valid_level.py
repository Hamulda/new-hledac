"""Test memory pressure level returns valid value."""
import pathlib
import sys

_universal = pathlib.Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_universal))

from resource_allocator import get_memory_pressure_level


def test_memory_pressure_level():
    """get_memory_pressure_level returns normal/warn/critical."""
    level = get_memory_pressure_level()
    assert level in ("normal", "warn", "critical"), f"Unexpected: {level}"


if __name__ == "__main__":
    test_memory_pressure_level()
    print("test_memory_pressure_returns_valid_level: PASSED")
