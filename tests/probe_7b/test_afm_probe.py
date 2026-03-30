"""
Sprint 7B: AFM Probe Tests
==========================

Tests for apple_fm_probe.py:
- fail-open behavior
- explicit macOS 26.0 gate
- structured correctness validation
- is_afm_available() boolean API
"""

import unittest
from unittest.mock import patch


class TestAFMProbeVersionGate(unittest.TestCase):
    """Tests for macOS 26.0 version gate."""

    @patch('platform.mac_ver')
    @patch('platform.system')
    @patch('platform.machine')
    def test_macOS_26_fails_macos_25(self, mock_machine, mock_system, mock_mac_ver):
        """macOS 25 should fail the 26.0 gate."""
        mock_system.return_value = "Darwin"
        mock_mac_ver.return_value = ("25.0", (), "")
        mock_machine.return_value = "arm64"

        from hledac.universal.brain.apple_fm_probe import apple_fm_probe, is_afm_available

        # Should be False on macOS 25
        self.assertFalse(is_afm_available())
        result = apple_fm_probe()
        self.assertFalse(result.available)
        self.assertIn("26.0", result.error)

    @patch('platform.mac_ver')
    @patch('platform.system')
    @patch('platform.machine')
    def test_macOS_26_passes_macos_26(self, mock_machine, mock_system, mock_mac_ver):
        """macOS 26 should pass the version gate."""
        mock_system.return_value = "Darwin"
        mock_mac_ver.return_value = ("26.3", (), "")
        mock_machine.return_value = "arm64"

        from hledac.universal.brain.apple_fm_probe import is_afm_available

        # Should pass version gate (correctness probe is mocked via JSON test)
        self.assertTrue(is_afm_available())


class TestAFMProbeExports(unittest.TestCase):
    """Test that probe exports are correct."""

    def test_afm_prob_result_has_new_fields(self):
        """AFMProbeResult should have apple_intelligence_enabled field."""
        from hledac.universal.brain.apple_fm_probe import AFMProbeResult

        result = AFMProbeResult(
            available=True,
            macos_version=(26, 0),
            is_apple_silicon=True,
            apple_intelligence_enabled=True,
            correctness_valid=True,
            error=None,
            details={"test": True}
        )
        self.assertTrue(result.available)
        self.assertTrue(result.apple_intelligence_enabled)
        self.assertEqual(result.macos_version, (26, 0))
        self.assertTrue(result.is_apple_silicon)
        self.assertTrue(result.correctness_valid)
        self.assertIsNone(result.error)
        self.assertTrue(result.details["test"])

    def test_is_afm_available_callable(self):
        """is_afm_available should be callable and return bool."""
        from hledac.universal.brain.apple_fm_probe import is_afm_available

        result = is_afm_available()
        self.assertIsInstance(result, bool)

    def test_apple_fm_probe_callable(self):
        """apple_fm_probe should be callable and return AFMProbeResult."""
        from hledac.universal.brain.apple_fm_probe import apple_fm_probe, AFMProbeResult

        result = apple_fm_probe()
        self.assertIsInstance(result, AFMProbeResult)


class TestStructuredCorrectnessProbe(unittest.TestCase):
    """Tests for structured correctness probe."""

    def test_structured_probe_accepts_valid_json(self):
        """Structured probe should accept valid JSON with name field."""
        from hledac.universal.brain.apple_fm_probe import _structured_correctness_probe

        valid, error = _structured_correctness_probe()
        # Should succeed (fail-open on JSON parsing)
        self.assertTrue(valid)
        self.assertIsNone(error)

    def test_afm_probe_has_details_dict(self):
        """AFMProbeResult should have details dict."""
        from hledac.universal.brain.apple_fm_probe import AFMProbeResult

        result = AFMProbeResult(
            available=False,
            macos_version=(25, 0),
            is_apple_silicon=True,
            apple_intelligence_enabled=False,
            correctness_valid=False,
            error="macOS too old",
            details={"min_version": "26.0"}
        )
        self.assertIsInstance(result.details, dict)
        self.assertEqual(result.details["min_version"], "26.0")


class TestAppleIntelligenceCheck(unittest.TestCase):
    """Tests for Apple Intelligence check seam."""

    def test_check_apple_intelligence_returns_tuple(self):
        """_check_apple_intelligence_enabled should return (bool, str|None)."""
        from hledac.universal.brain.apple_fm_probe import _check_apple_intelligence_enabled

        enabled, error = _check_apple_intelligence_enabled()
        self.assertIsInstance(enabled, bool)
        # error can be None or a string
        self.assertTrue(error is None or isinstance(error, str))


class TestFailOpenBehavior(unittest.TestCase):
    """Tests for fail-open behavior."""

    @patch('platform.mac_ver')
    @patch('platform.system')
    @patch('platform.machine')
    def test_non_darwin_returns_false(self, mock_machine, mock_system, mock_mac_ver):
        """Non-Darwin should return False (not fail-open)."""
        mock_system.return_value = "Linux"
        mock_mac_ver.return_value = ("26.0", (), "")
        mock_machine.return_value = "x86_64"

        from hledac.universal.brain.apple_fm_probe import is_afm_available

        self.assertFalse(is_afm_available())

    @patch('platform.mac_ver')
    @patch('platform.system')
    @patch('platform.machine')
    def test_non_arm64_returns_false(self, mock_machine, mock_system, mock_mac_ver):
        """Non-arm64 should return False."""
        mock_system.return_value = "Darwin"
        mock_mac_ver.return_value = ("26.0", (), "")
        mock_machine.return_value = "x86_64"

        from hledac.universal.brain.apple_fm_probe import is_afm_available

        self.assertFalse(is_afm_available())


if __name__ == "__main__":
    unittest.main()
