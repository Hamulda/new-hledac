"""
Sprint 6B: Apple FM Probe Tests
================================

Tests for apple_fm_probe.py:
- fail-open behavior
- macOS version gate
- correctness validation
- is_afm_available() boolean API
"""

import unittest
from unittest.mock import patch
import platform


class TestAppleFMProbe(unittest.TestCase):
    """Tests for Apple Foundation Models probe."""

    def test_probe_result_dataclass(self):
        """Test AFMProbeResult dataclass exists and works."""
        from hledac.universal.brain.apple_fm_probe import AFMProbeResult

        result = AFMProbeResult(
            available=True,
            macos_version=(26, 0),
            is_apple_silicon=True,
            apple_intelligence_enabled=True,
            correctness_valid=True,
            error=None
        )
        self.assertTrue(result.available)
        self.assertEqual(result.macos_version, (26, 0))
        self.assertTrue(result.is_apple_silicon)
        self.assertTrue(result.apple_intelligence_enabled)
        self.assertTrue(result.correctness_valid)
        self.assertIsNone(result.error)

    def test_probe_result_with_error(self):
        """Test AFMProbeResult with error."""
        from hledac.universal.brain.apple_fm_probe import AFMProbeResult

        result = AFMProbeResult(
            available=False,
            macos_version=(25, 0),
            is_apple_silicon=False,
            apple_intelligence_enabled=False,
            correctness_valid=False,
            error="Not Apple Silicon"
        )
        self.assertFalse(result.available)
        self.assertEqual(result.error, "Not Apple Silicon")

    @patch('platform.mac_ver')
    @patch('platform.system')
    @patch('platform.machine')
    def test_is_afm_available_non_darwin(self, mock_machine, mock_system, mock_mac_ver):
        """Test is_afm_available returns False on non-Darwin."""
        mock_system.return_value = "Linux"
        mock_mac_ver.return_value = ("14.0", (), "")

        from hledac.universal.brain.apple_fm_probe import is_afm_available
        self.assertFalse(is_afm_available())

    @patch('platform.mac_ver')
    @patch('platform.system')
    @patch('platform.machine')
    def test_is_afm_available_old_macos(self, mock_machine, mock_system, mock_mac_ver):
        """Test is_afm_available returns False on old macOS."""
        mock_system.return_value = "Darwin"
        mock_mac_ver.return_value = ("13.0", (), "")
        mock_machine.return_value = "arm64"

        from hledac.universal.brain.apple_fm_probe import is_afm_available
        self.assertFalse(is_afm_available())

    @patch('platform.mac_ver')
    @patch('platform.system')
    @patch('platform.machine')
    def test_is_afm_available_non_arm64(self, mock_machine, mock_system, mock_mac_ver):
        """Test is_afm_available returns False on non-ARM64."""
        mock_system.return_value = "Darwin"
        mock_mac_ver.return_value = ("14.0", (), "")
        mock_machine.return_value = "x86_64"

        from hledac.universal.brain.apple_fm_probe import is_afm_available
        self.assertFalse(is_afm_available())

    @patch('platform.mac_ver')
    @patch('platform.system')
    @patch('platform.machine')
    def test_is_afm_available_success(self, mock_machine, mock_system, mock_mac_ver):
        """Test is_afm_available returns True on valid Apple Silicon macOS 26+."""
        mock_system.return_value = "Darwin"
        mock_mac_ver.return_value = ("26.3", (), "")
        mock_machine.return_value = "arm64"

        from hledac.universal.brain.apple_fm_probe import is_afm_available
        self.assertTrue(is_afm_available())

    def test_afm_probe_full_result(self):
        """Test apple_fm_probe returns correct structure."""
        from hledac.universal.brain.apple_fm_probe import apple_fm_probe, AFMProbeResult

        result = apple_fm_probe()

        self.assertIsInstance(result, AFMProbeResult)
        self.assertIn("available", result.__dict__ or {})
        self.assertIn("macos_version", result.__dict__ or {})

    def test_nl_framework_check(self):
        """Test get_nl_framework_available is callable."""
        from hledac.universal.brain.apple_fm_probe import get_nl_framework_available

        # Just verify it's callable and returns bool
        result = get_nl_framework_available()
        self.assertIsInstance(result, bool)


class TestAFMProbeExports(unittest.TestCase):
    """Test that probe exports are available."""

    def test_exports(self):
        """Test __all__ exports."""
        from hledac.universal.brain import apple_fm_probe

        self.assertIn("apple_fm_probe", apple_fm_probe.__all__)
        self.assertIn("is_afm_available", apple_fm_probe.__all__)
        self.assertIn("AFMProbeResult", apple_fm_probe.__all__)


if __name__ == "__main__":
    unittest.main()
