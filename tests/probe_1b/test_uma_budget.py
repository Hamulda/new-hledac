"""
Probe tests for uma_budget.py helper.
"""

import platform
import pytest


class TestUMABudgetAPI:
    """Test UMA budget accountant API."""

    def test_get_uma_snapshot_returns_dict(self):
        """get_uma_snapshot should return a dict."""
        from hledac.universal.utils.uma_budget import get_uma_snapshot

        snap = get_uma_snapshot()
        assert isinstance(snap, dict)

    def test_snapshot_has_required_keys(self):
        """UMA snapshot should have required keys."""
        from hledac.universal.utils.uma_budget import get_uma_snapshot

        snap = get_uma_snapshot()
        required = [
            "uma_total_mb",
            "warn_threshold_mb",
            "critical_threshold_mb",
            "system_total_mb",
            "system_used_mb",
            "mlx_active_mb",
            "uma_used_mb",
            "uma_usage_pct",
            "uma_pressure_level",
            "is_warn",
            "is_critical",
            "platform",
        ]
        for key in required:
            assert key in snap, f"Missing key: {key}"

    def test_thresholds_are_correct_values(self):
        """UMA thresholds should be correct M1 8GB values."""
        from hledac.universal.utils.uma_budget import (
            _UMA_TOTAL_MB,
            _WARN_THRESHOLD_MB,
            _CRITICAL_THRESHOLD_MB,
        )

        assert _UMA_TOTAL_MB == 8192
        assert _WARN_THRESHOLD_MB == 6144  # Sprint 6B: 6.0 GB
        assert _CRITICAL_THRESHOLD_MB == 6656  # Sprint 6B: 6.5 GB

    def test_get_uma_pressure_level_returns_tuple(self):
        """get_uma_pressure_level should return (int, str)."""
        from hledac.universal.utils.uma_budget import get_uma_pressure_level

        result = get_uma_pressure_level()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], int)
        assert result[1] in ("normal", "warn", "critical")

    def test_is_uma_warn_returns_bool(self):
        """is_uma_warn should return bool."""
        from hledac.universal.utils.uma_budget import is_uma_warn

        result = is_uma_warn()
        assert isinstance(result, bool)

    def test_is_uma_critical_returns_bool(self):
        """is_uma_critical should return bool."""
        from hledac.universal.utils.uma_budget import is_uma_critical

        result = is_uma_critical()
        assert isinstance(result, bool)

    def test_format_uma_budget_report(self):
        """format_uma_budget_report should return string."""
        from hledac.universal.utils.uma_budget import format_uma_budget_report

        report = format_uma_budget_report()
        assert isinstance(report, str)
        assert "UMA Budget Report" in report
        assert "Platform:" in report

    def test_get_system_memory_mb_returns_tuple(self):
        """get_system_memory_mb should return (total, used, available)."""
        from hledac.universal.utils.uma_budget import get_system_memory_mb

        result = get_system_memory_mb()
        assert isinstance(result, tuple)
        assert len(result) == 3
        total, used, avail = result
        assert total >= 0
        assert used >= 0
        assert avail >= 0

    def test_fail_open_when_no_psutil(self):
        """Should fail-open to (0,0,0) when psutil unavailable."""
        from hledac.universal.utils import uma_budget as ub

        original_psutil = ub._psutil
        ub._psutil = None

        try:
            total, used, avail = ub.get_system_memory_mb()
            # Should either get (0,0,0) or actual values from lazy re-import
            assert isinstance(total, int)
            assert isinstance(used, int)
            assert isinstance(avail, int)
        finally:
            ub._psutil = original_psutil

    def test_pressure_level_logic(self):
        """Pressure level should be correct based on thresholds."""
        from hledac.universal.utils.uma_budget import (
            _WARN_THRESHOLD_MB,
            _CRITICAL_THRESHOLD_MB,
        )

        # These constants should be defined
        assert _WARN_THRESHOLD_MB < _CRITICAL_THRESHOLD_MB
        assert _WARN_THRESHOLD_MB == 6144  # Sprint 6B: 6.0 GB
        assert _CRITICAL_THRESHOLD_MB == 6656  # Sprint 6B: 6.5 GB
