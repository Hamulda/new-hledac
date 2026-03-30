"""
Probe tests for thermal.py helper.
"""

import platform
import pytest


class TestThermalHelper:
    """Test thermal helper fail-open and API."""

    def test_get_thermal_state_returns_tuple(self):
        """get_thermal_state should return (int, str)."""
        from hledac.universal.utils.thermal import get_thermal_state

        result = get_thermal_state()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], int)
        assert isinstance(result[1], str)

    def test_get_thermal_state_level_bounds(self):
        """Thermal level should be 0-3."""
        from hledac.universal.utils.thermal import get_thermal_state

        level, name = get_thermal_state()
        assert 0 <= level <= 3, f"Thermal level {level} out of bounds"
        assert name in ("nominal", "fair", "serious", "critical", "unknown")

    def test_get_thermal_state_str(self):
        """get_thermal_state_str should return string."""
        from hledac.universal.utils.thermal import get_thermal_state_str

        result = get_thermal_state_str()
        assert isinstance(result, str)

    def test_is_thermal_critical(self):
        """is_thermal_critical should return bool."""
        from hledac.universal.utils.thermal import is_thermal_critical

        result = is_thermal_critical()
        assert isinstance(result, bool)

    def test_format_thermal_snapshot(self):
        """format_thermal_snapshot should return dict with keys."""
        from hledac.universal.utils.thermal import format_thermal_snapshot

        snap = format_thermal_snapshot()
        assert isinstance(snap, dict)
        assert "platform" in snap
        assert "level" in snap
        assert "name" in snap
        assert "is_critical" in snap

    def test_fail_open_on_non_darwin(self):
        """On non-macOS, should return nominal/fail-open."""
        from hledac.universal.utils.thermal import get_thermal_state

        if platform.system() != "Darwin":
            level, name = get_thermal_state()
            assert level == 0
            assert name == "nominal"

    def test_thermal_levels_mapping(self):
        """Thermal levels should map correctly."""
        from hledac.universal.utils.thermal import _THERMAL_LEVELS

        assert _THERMAL_LEVELS[0] == "nominal"
        assert _THERMAL_LEVELS[1] == "fair"
        assert _THERMAL_LEVELS[2] == "serious"
        assert _THERMAL_LEVELS[3] == "critical"
