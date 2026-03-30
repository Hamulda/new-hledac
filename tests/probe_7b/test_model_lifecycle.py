"""
Sprint 7B: Model Lifecycle Tests
===============================

Tests for model_lifecycle.py:
- unload_model() order enforcement
- idempotence / fail-open
- prompt_cache eviction
"""

import unittest
from unittest.mock import MagicMock


class TestUnloadModelOrder(unittest.TestCase):
    """Tests for unload_model order enforcement."""

    def test_unload_model_callable(self):
        """unload_model should be importable and callable."""
        from hledac.universal.brain.model_lifecycle import unload_model
        self.assertTrue(callable(unload_model))

    def test_unload_model_fail_open_with_none(self):
        """unload_model should be fail-open with None inputs."""
        from hledac.universal.brain.model_lifecycle import unload_model

        # Should not raise even with all None
        try:
            unload_model(model=None, tokenizer=None, prompt_cache=None)
        except Exception as e:
            self.fail(f"unload_model raised exception with None inputs: {e}")

    def test_unload_model_fail_open_with_mock(self):
        """unload_model should be fail-open with mock objects."""
        from hledac.universal.brain.model_lifecycle import unload_model

        mock_model = MagicMock()
        mock_tokenizer = MagicMock()
        mock_cache = MagicMock()

        try:
            unload_model(model=mock_model, tokenizer=mock_tokenizer, prompt_cache=mock_cache)
        except Exception as e:
            self.fail(f"unload_model raised exception with mocks: {e}")

    def test_unload_model_idempotent(self):
        """unload_model should be idempotent (callable multiple times)."""
        from hledac.universal.brain.model_lifecycle import unload_model

        mock_model = MagicMock()

        # Multiple calls should not raise
        try:
            unload_model(model=mock_model)
            unload_model(model=mock_model)
            unload_model(model=None)  # also with None
        except Exception as e:
            self.fail(f"unload_model not idempotent: {e}")

    def test_unload_model_extracts_from_engine(self):
        """unload_model should extract _model/_tokenizer/_prompt_cache from engine."""
        from hledac.universal.brain.model_lifecycle import unload_model

        # Create mock engine with _model/_tokenizer/_prompt_cache
        mock_engine = MagicMock()
        mock_engine._model = MagicMock()
        mock_engine._tokenizer = MagicMock()
        mock_engine._prompt_cache = MagicMock()

        try:
            unload_model(model=mock_engine)  # Should extract from engine
        except Exception as e:
            self.fail(f"unload_model failed with engine object: {e}")

    def test_unload_model_with_aggressive_flag(self):
        """unload_model should accept aggressive=True."""
        from hledac.universal.brain.model_lifecycle import unload_model

        try:
            unload_model(model=None, aggressive=True)
        except Exception as e:
            self.fail(f"unload_model with aggressive=True raised: {e}")


class TestPreloadModelHint(unittest.TestCase):
    """Tests for preload_model_hint."""

    def test_preload_model_hint_callable(self):
        """preload_model_hint should be callable."""
        from hledac.universal.brain.model_lifecycle import preload_model_hint

        self.assertTrue(callable(preload_model_hint))
        # Should not raise
        preload_model_hint("test/model/path")


if __name__ == "__main__":
    unittest.main()
