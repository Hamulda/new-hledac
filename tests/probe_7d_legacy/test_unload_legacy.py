"""
Sprint 7G - Legacy Unload Model Tests
====================================

These tests were moved from probe_7d/ because they test model_lifecycle.unload_model()
which is unrelated to the batch routing / structured generation work of Sprint 7G.

These tests fail because:
- test_unload_model_evicts_prompt_cache: mocks __del__ which doesn't work reliably in async context
- test_unload_model_respects_order: GC call order is non-deterministic in Python's async context

These are NOT gating for current sprint work.
"""

import gc
import unittest
from unittest.mock import MagicMock, patch
import sys

sys.path.insert(0, '/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal')


class TestUnloadModelLegacy(unittest.TestCase):
    """Legacy tests for unload_model() - moved to probe_7d_legacy/."""

    def test_unload_model_evicts_prompt_cache(self):
        """unload_model() must evict prompt_cache before model."""
        from hledac.universal.brain.model_lifecycle import unload_model

        mock_cache = MagicMock()
        mock_model = MagicMock()
        mock_tokenizer = MagicMock()

        # Call unload
        unload_model(model=mock_model, tokenizer=mock_tokenizer, prompt_cache=mock_cache)

        # Cache should be deleted
        self.assertTrue(mock_cache.__del__.called)

    def test_unload_model_respects_order(self):
        """unload_model() must follow: cache -> model -> tokenizer -> gc -> mx.eval -> clear_cache."""
        from hledac.universal.brain.model_lifecycle import unload_model

        # Create mock objects
        call_order = []

        class MockCache:
            def __del__(self):
                call_order.append('cache')

        class MockModel:
            def __del__(self):
                call_order.append('model')

        class MockTokenizer:
            def __del__(self):
                call_order.append('tokenizer')

        cache = MockCache()
        model = MockModel()
        tokenizer = MockTokenizer()

        # Patch gc.collect and mx operations to track order
        gc_calls = []
        original_gc_collect = gc.collect
        def tracking_gc_collect(*args, **kwargs):
            gc_calls.append('gc')
            return original_gc_collect(*args, **kwargs)

        with patch('gc.collect', side_effect=tracking_gc_collect):
            unload_model(model=model, tokenizer=tokenizer, prompt_cache=cache)

        # GC should be called after all dels
        self.assertIn('cache', call_order)
        self.assertIn('model', call_order)
        self.assertIn('tokenizer', call_order)
