"""
Sprint 6B: UMA Budget Thresholds Tests
======================================

Tests for updated memory thresholds:
- WARN: 6.0 GB
- CRITICAL: 6.5 GB
- EMERGENCY: 7.0 GB
"""

import unittest
from unittest.mock import patch


class TestUMABudgetThresholds(unittest.TestCase):
    """Tests for updated UMA threshold values."""

    def test_threshold_values(self):
        """Test threshold constants are 6.0/6.5/7.0 GB."""
        from hledac.universal.utils import uma_budget

        self.assertEqual(uma_budget._WARN_THRESHOLD_MB, 6_144)  # 6.0 GB
        self.assertEqual(uma_budget._CRITICAL_THRESHOLD_MB, 6_656)  # 6.5 GB
        self.assertEqual(uma_budget._EMERGENCY_THRESHOLD_MB, 7_168)  # 7.0 GB

    def test_pressure_level_emergency(self):
        """Test get_uma_pressure_level returns 'emergency' at 7.0+ GB."""
        from hledac.universal.utils import uma_budget

        with patch.object(uma_budget, 'get_uma_usage_mb', return_value=7200):
            pct, level = uma_budget.get_uma_pressure_level()
            self.assertEqual(level, "emergency")

    def test_pressure_level_critical(self):
        """Test get_uma_pressure_level returns 'critical' at 6.5+ GB."""
        from hledac.universal.utils import uma_budget

        with patch.object(uma_budget, 'get_uma_usage_mb', return_value=6700):
            pct, level = uma_budget.get_uma_pressure_level()
            self.assertEqual(level, "critical")

    def test_pressure_level_warn(self):
        """Test get_uma_pressure_level returns 'warn' at 6.0+ GB."""
        from hledac.universal.utils import uma_budget

        with patch.object(uma_budget, 'get_uma_usage_mb', return_value=6200):
            pct, level = uma_budget.get_uma_pressure_level()
            self.assertEqual(level, "warn")

    def test_pressure_level_normal(self):
        """Test get_uma_pressure_level returns 'normal' below 6.0 GB."""
        from hledac.universal.utils import uma_budget

        with patch.object(uma_budget, 'get_uma_usage_mb', return_value=5000):
            pct, level = uma_budget.get_uma_pressure_level()
            self.assertEqual(level, "normal")

    def test_is_uma_warn_includes_emergency(self):
        """Test is_uma_warn returns True for emergency level."""
        from hledac.universal.utils import uma_budget

        with patch.object(uma_budget, 'get_uma_usage_mb', return_value=7200):
            self.assertTrue(uma_budget.is_uma_warn())

    def test_is_uma_critical_includes_emergency(self):
        """Test is_uma_critical returns True for emergency level."""
        from hledac.universal.utils import uma_budget

        with patch.object(uma_budget, 'get_uma_usage_mb', return_value=7200):
            self.assertTrue(uma_budget.is_uma_critical())

    def test_is_uma_emergency(self):
        """Test is_uma_emergency returns True only at emergency level."""
        from hledac.universal.utils import uma_budget

        with patch.object(uma_budget, 'get_uma_usage_mb', return_value=7200):
            self.assertTrue(uma_budget.is_uma_emergency())

        with patch.object(uma_budget, 'get_uma_usage_mb', return_value=6700):
            self.assertFalse(uma_budget.is_uma_emergency())

    def test_snapshot_includes_emergency_threshold(self):
        """Test get_uma_snapshot includes emergency_threshold_mb."""
        from hledac.universal.utils import uma_budget

        with patch.object(uma_budget, 'get_system_memory_mb', return_value=(8192, 5000, 3192)):
            with patch.object(uma_budget, 'get_mlx_memory_mb', return_value=(0, 0, 0)):
                snapshot = uma_budget.get_uma_snapshot()
                self.assertIn("emergency_threshold_mb", snapshot)
                self.assertEqual(snapshot["emergency_threshold_mb"], 7_168)
                self.assertIn("is_emergency", snapshot)
                self.assertFalse(snapshot["is_emergency"])


class TestUMABudgetAPI(unittest.TestCase):
    """Tests for UMA budget API exports."""

    def test_is_uma_emergency_exported(self):
        """Test is_uma_emergency is in __all__."""
        from hledac.universal.utils import uma_budget
        self.assertIn("is_uma_emergency", uma_budget.__all__)


if __name__ == "__main__":
    unittest.main()
