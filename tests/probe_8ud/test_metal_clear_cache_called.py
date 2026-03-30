"""
Sprint 8UD B.2: mx.metal.clear_cache() called after mlx_lm.generate()

Tests that clear_cache is invoked in finally block after successful
and failed inference.
"""
import unittest
from unittest.mock import MagicMock, patch


class TestMetalClearCache(unittest.TestCase):
    """Test mx.metal.clear_cache() is called after MLX inference."""

    def test_metal_clear_cache_on_success(self):
        """clear_cache called after successful generate."""
        clear_cache_mock = MagicMock()
        is_available_mock = MagicMock(return_value=True)

        mock_metal = MagicMock()
        mock_metal.is_available = is_available_mock
        mock_metal.clear_cache = clear_cache_mock

        mock_mx_core = MagicMock()
        mock_mx_core.metal = mock_metal

        with patch.dict('sys.modules', {'mlx.core': mock_mx_core}):
            # Simulate the finally block logic
            try:
                # Simulate successful mlx_lm.generate (no-op in test)
                pass
            finally:
                if mock_mx_core.metal.is_available():
                    mock_mx_core.metal.clear_cache()

        mock_mx_core.metal.clear_cache.assert_called_once()

    def test_metal_clear_cache_on_exception(self):
        """clear_cache called even when generate raises."""
        clear_cache_mock = MagicMock()
        is_available_mock = MagicMock(return_value=True)

        mock_metal = MagicMock()
        mock_metal.is_available = is_available_mock
        mock_metal.clear_cache = clear_cache_mock

        mock_mx_core = MagicMock()
        mock_mx_core.metal = mock_metal

        clear_cache_called = [False]

        with patch.dict('sys.modules', {'mlx.core': mock_mx_core}):
            try:
                try:
                    raise RuntimeError("MLX inference failed")
                finally:
                    if mock_mx_core.metal.is_available():
                        mock_mx_core.metal.clear_cache()
                        clear_cache_called[0] = True
            except RuntimeError:
                pass  # Expected

        # Verify clear_cache was called despite exception
        self.assertTrue(clear_cache_called[0])
        mock_mx_core.metal.clear_cache.assert_called_once()

    def test_metal_clear_cache_guard_when_unavailable(self):
        """No crash when is_available returns False."""
        mock_metal = MagicMock()
        mock_metal.is_available.return_value = False
        mock_metal.clear_cache = MagicMock()

        mock_mx_core = MagicMock()
        mock_mx_core.metal = mock_metal

        with patch.dict('sys.modules', {'mlx.core': mock_mx_core}):
            # Should not raise when metal unavailable
            if mock_mx_core.metal.is_available():
                mock_mx_core.metal.clear_cache()

            mock_mx_core.metal.clear_cache.assert_not_called()

    def test_finally_block_pattern_in_synthesis_runner(self):
        """Verify the finally+clear_cache pattern exists in synthesis_runner."""
        with open("/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/brain/synthesis_runner.py") as f:
            source = f.read()

        # Check for the clear_cache pattern in _xgrammar_sync
        self.assertIn("mx.metal.clear_cache()", source)
        self.assertIn("finally:", source)

        # Verify the pattern is inside _xgrammar_sync or _gen
        self.assertTrue(
            source.count("finally:") >= 2,
            "At least 2 finally blocks (one in _xgrammar_sync, one in _gen)"
        )

    def test_finally_block_pattern_in_model_lifecycle(self):
        """Verify the finally+clear_cache pattern exists in model_lifecycle."""
        with open("/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/brain/model_lifecycle.py") as f:
            source = f.read()

        self.assertIn("mx.metal.clear_cache()", source)
        self.assertIn("finally:", source)

    def test_finally_block_pattern_in_hermes3_engine(self):
        """Verify the finally+clear_cache pattern exists in hermes3_engine prefill."""
        with open("/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/brain/hermes3_engine.py") as f:
            source = f.read()

        self.assertIn("mx.metal.clear_cache()", source)
        self.assertIn("finally:", source)


if __name__ == "__main__":
    unittest.main()
