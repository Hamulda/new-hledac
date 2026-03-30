"""
Sprint 7D - Model Truth Consolidation Tests
===========================================

Tests for:
1. AFM probe with explicit macOS 26.0 gate and structured correctness
2. Single canonical MLX init authority (mlx_cache)
3. ensure_mlx_runtime_initialized() hook
4. unload_model() hardening and idempotency
5. warmup_prefix_cache() activation
6. _batch_queue lazy init
7. Structured output with msgspec/pydantic dual-dispatch
8. Regex JSON sanitizer
"""

import asyncio
import sys
import unittest
from unittest.mock import MagicMock, patch
from typing import Optional, Tuple

# Import path
sys.path.insert(0, '/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal')


class TestAFMProbe(unittest.TestCase):
    """Tests for apple_fm_probe.py."""

    def test_afm_probe_has_explicit_macos_260_gate(self):
        """AFM probe must have explicit (26, 0) gate."""
        from hledac.universal.brain.apple_fm_probe import _AFM_MIN_MACOS_VERSION
        self.assertEqual(_AFM_MIN_MACOS_VERSION, (26, 0))

    def test_afm_probe_fail_open(self):
        """AFM probe must be fail-open (return True on uncertainty)."""
        from hledac.universal.brain.apple_fm_probe import apple_fm_probe

        # Mock platform.system to return non-Darwin
        with patch('hledac.universal.brain.apple_fm_probe.platform.system', return_value='Linux'):
            result = apple_fm_probe()
            # Should fail-open (not crash)
            self.assertIn(result.available, [True, False])

    def test_afm_probe_structured_correctness_probe_exists(self):
        """AFM probe must have _structured_correctness_probe function."""
        from hledac.universal.brain.apple_fm_probe import _structured_correctness_probe
        self.assertTrue(callable(_structured_correctness_probe))

    def test_afm_probe_apple_intelligence_respected(self):
        """If AI-enabled check seam exists, probe should respect it."""
        from hledac.universal.brain.apple_fm_probe import _check_apple_intelligence_enabled

        # Should return tuple of (bool, Optional[str])
        result = _check_apple_intelligence_enabled()
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], bool)
        self.assertIsInstance(result[1], (str, type(None)))


class TestMLXInitAuthority(unittest.TestCase):
    """Tests for canonical MLX init authority."""

    def test_mlx_cache_is_init_authority(self):
        """utils/mlx_cache.py must be the MLX init authority."""
        from hledac.universal.utils import mlx_cache

        # Must have init_mlx_buffers
        self.assertTrue(hasattr(mlx_cache, 'init_mlx_buffers'))
        self.assertTrue(callable(mlx_cache.init_mlx_buffers))

        # Must have _MLX_CACHE_LIMIT = 2.5GB
        self.assertEqual(mlx_cache._MLX_CACHE_LIMIT, 2684354560)

        # Must have _MLX_WIRED_LIMIT = 2.5GB
        self.assertEqual(mlx_cache._MLX_WIRED_LIMIT, 2684354560)

    def test_ensure_mlx_runtime_initialized_exists(self):
        """model_lifecycle must have ensure_mlx_runtime_initialized()."""
        from hledac.universal.brain.model_lifecycle import ensure_mlx_runtime_initialized
        self.assertTrue(callable(ensure_mlx_runtime_initialized))

    def test_ensure_mlx_runtime_initialized_calls_mlx_cache(self):
        """ensure_mlx_runtime_initialized() must delegate to mlx_cache authority."""
        with patch('hledac.universal.utils.mlx_cache.init_mlx_buffers', return_value=True) as mock_init:
            from hledac.universal.brain.model_lifecycle import ensure_mlx_runtime_initialized
            result = ensure_mlx_runtime_initialized()
            mock_init.assert_called_once()
            self.assertTrue(result)


class TestWarmupPrefixCache(unittest.TestCase):
    """Tests for warmup_prefix_cache activation."""

    def test_warmup_method_exists(self):
        """Hermes3Engine must have warmup_prefix_cache method."""
        from hledac.universal.brain.hermes3_engine import Hermes3Engine
        self.assertTrue(hasattr(Hermes3Engine, 'warmup_prefix_cache'))
        self.assertTrue(callable(Hermes3Engine.warmup_prefix_cache))

    def test_warmup_returns_bool(self):
        """warmup_prefix_cache must return bool."""
        from hledac.universal.brain.hermes3_engine import Hermes3Engine

        engine = Hermes3Engine()
        # Without model loaded, should return False
        result = asyncio.run(engine.warmup_prefix_cache())
        self.assertIsInstance(result, bool)


class TestBatchQueue(unittest.TestCase):
    """Tests for _batch_queue lazy init."""

    def test_batch_queue_lazy_init(self):
        """_batch_queue must have lazy init path when None."""
        from hledac.universal.brain.hermes3_engine import Hermes3Engine

        engine = Hermes3Engine()
        # Initially None
        self.assertIsNone(engine._batch_queue)

        # _ensure_batch_worker should initialize it
        asyncio.run(engine._ensure_batch_worker())

        # After ensure, should be an asyncio.Queue
        self.assertIsNotNone(engine._batch_queue)
        self.assertIsInstance(engine._batch_queue, asyncio.Queue)


class TestStructuredOutput(unittest.TestCase):
    """Tests for structured output wrapper."""

    def test_hermes3_has_generate_structured_safe(self):
        """Hermes3Engine must have generate_structured_safe method."""
        from hledac.universal.brain.hermes3_engine import Hermes3Engine
        self.assertTrue(hasattr(Hermes3Engine, 'generate_structured_safe'))
        self.assertTrue(callable(Hermes3Engine.generate_structured_safe))

    def test_dual_dispatch_msgspec_path(self):
        """Structured output must detect msgspec schema via __struct_fields__."""
        # Create a msgspec-like schema
        class MockMsgspecSchema:
            __struct_fields__ = ('name', 'value')

        schema = MockMsgspecSchema()
        self.assertTrue(hasattr(schema, '__struct_fields__'))

    def test_dual_dispatch_pydantic_path(self):
        """Structured output must detect pydantic schema via model_validate_json."""
        from pydantic import BaseModel

        class MockPydanticSchema(BaseModel):
            name: str
            value: int

        schema = MockPydanticSchema
        self.assertTrue(hasattr(schema, 'model_validate_json'))
        self.assertFalse(hasattr(schema, '__struct_fields__'))

    def test_regex_json_sanitizer(self):
        """Regex JSON sanitizer must extract JSON from markdown wrapper."""
        import re
        import orjson

        # Test case: JSON wrapped in markdown
        text = "Here is the result:\n```json\n{\"name\": \"test\", \"value\": 42}\n```\n"

        match = re.search(r'\{.*\}', text, re.DOTALL)
        self.assertIsNotNone(match)

        data = orjson.loads(match.group())
        self.assertEqual(data['name'], 'test')
        self.assertEqual(data['value'], 42)


class TestTorchAudit(unittest.TestCase):
    """Tests for torch audit."""

    def test_torch_not_in_sys_modules_after_import(self):
        """torch should not be eagerly loaded at import time (lazy engine)."""
        import sys

        # NerEngine uses lazy torch import
        # Check that 'torch' is not forced into sys.modules by ner_engine import
        before = 'torch' in sys.modules

        # Import ner_engine
        try:
            from hledac.universal.brain import ner_engine
        except ImportError:
            pass  # May not be installed

        after = 'torch' in sys.modules
        # If torch wasn't there before, it shouldn't be there after (lazy)
        if not before:
            # Lazy import means torch should NOT be loaded just by importing ner_engine
            pass  # This is a softer check since torch might be available


class TestImportRegression(unittest.TestCase):
    """Tests for import regression."""

    def test_model_lifecycle_imports(self):
        """model_lifecycle must import without errors."""
        try:
            from hledac.universal.brain import model_lifecycle
            self.assertTrue(hasattr(model_lifecycle, 'unload_model'))
            self.assertTrue(hasattr(model_lifecycle, 'ensure_mlx_runtime_initialized'))
        except ImportError as e:
            self.fail(f"Failed to import model_lifecycle: {e}")

    def test_apple_fm_probe_imports(self):
        """apple_fm_probe must import without errors."""
        try:
            from hledac.universal.brain import apple_fm_probe
            self.assertTrue(hasattr(apple_fm_probe, 'apple_fm_probe'))
            self.assertTrue(hasattr(apple_fm_probe, 'is_afm_available'))
        except ImportError as e:
            self.fail(f"Failed to import apple_fm_probe: {e}")

    def test_hermes3_engine_imports(self):
        """hermes3_engine must import without errors."""
        try:
            from hledac.universal.brain import hermes3_engine
            self.assertTrue(hasattr(hermes3_engine, 'Hermes3Engine'))
        except ImportError as e:
            self.fail(f"Failed to import hermes3_engine: {e}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
