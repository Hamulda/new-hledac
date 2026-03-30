"""
Sprint 6B: QoS Constants Tests
===============================

Tests for dispatch QoS constants:
- USER_INITIATED = 0x19
- UTILITY = 0x11
- BACKGROUND = 0x09
"""

import unittest


class TestQoSConstants(unittest.TestCase):
    """Tests for thread pool QoS constants."""

    def test_qos_background_value(self):
        """Test QOS_CLASS_BACKGROUND is 0x09."""
        from hledac.universal.utils.thread_pools import _set_background

        # Read the source to verify constant value
        import inspect
        source = inspect.getsource(_set_background)

        self.assertIn("0x09", source)
        self.assertIn("QOS_CLASS_BACKGROUND", source)

    def test_qos_user_initiated_value(self):
        """Test QOS_CLASS_USER_INITIATED is 0x19."""
        from hledac.universal.utils.thread_pools import _set_user_initiated

        import inspect
        source = inspect.getsource(_set_user_initiated)

        self.assertIn("0x19", source)
        self.assertIn("QOS_CLASS_USER_INITIATED", source)

    def test_no_inference_qos(self):
        """Test that 0x21 (BACKGROUND) is not used for inference paths."""
        from hledac.universal.utils import thread_pools

        import os
        base_path = "/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal"

        # Check thread_pools source doesn't use 0x21 for inference
        source_file = thread_pools.__file__
        with open(source_file, 'r') as f:
            content = f.read()

        # 0x21 should NOT appear in context of inference
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if '0x21' in line and not line.strip().startswith('#'):
                self.fail(f"0x21 found at line {i+1}: {line.strip()}")


if __name__ == "__main__":
    unittest.main()
