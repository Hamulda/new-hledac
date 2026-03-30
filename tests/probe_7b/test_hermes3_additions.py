"""
Sprint 7B: Hermes3 Engine Additions Tests
=======================================

Tests for hermes3_engine.py additions:
- warmup_prefix_cache seam
- generate_structured_safe wrapper
- Structured output fallback chain
"""

import unittest
from pydantic import BaseModel


class _TestSchema(BaseModel):
    name: str
    value: int = 0


class TestWarmupPrefixCache(unittest.TestCase):
    """Tests for warmup_prefix_cache seam."""

    def test_warmup_method_exists(self):
        """Hermes3Engine should have warmup_prefix_cache method."""
        from hledac.universal.brain.hermes3_engine import Hermes3Engine

        self.assertTrue(hasattr(Hermes3Engine, 'warmup_prefix_cache'))
        self.assertTrue(callable(Hermes3Engine.warmup_prefix_cache))

    def test_warmup_returns_bool(self):
        """warmup_prefix_cache should return bool."""
        import asyncio
        from hledac.universal.brain.hermes3_engine import Hermes3Engine

        engine = Hermes3Engine()
        # Without model loaded, should return False
        result = asyncio.run(engine.warmup_prefix_cache())
        self.assertIsInstance(result, bool)


class TestGenerateStructuredSafe(unittest.TestCase):
    """Tests for generate_structured_safe wrapper."""

    def test_generate_structured_safe_exists(self):
        """Hermes3Engine should have generate_structured_safe method."""
        from hledac.universal.brain.hermes3_engine import Hermes3Engine

        self.assertTrue(hasattr(Hermes3Engine, 'generate_structured_safe'))
        self.assertTrue(callable(Hermes3Engine.generate_structured_safe))

    def test_generate_structured_safe_with_mock(self):
        """generate_structured_safe should work with mock model."""
        from hledac.universal.brain.hermes3_engine import Hermes3Engine

        engine = Hermes3Engine()
        # Should return fallback when model not loaded
        result = engine.generate_structured_safe(
            prompt="test",
            response_model=_TestSchema,
            temperature=0.1,
            max_tokens=100
        )
        self.assertIsInstance(result, _TestSchema)


class TestProbeOutlinesCapability(unittest.TestCase):
    """Tests for _probe_outlines_capability."""

    def test_probe_outlines_exists(self):
        """Hermes3Engine should have _probe_outlines_capability method."""
        from hledac.universal.brain.hermes3_engine import Hermes3Engine

        self.assertTrue(hasattr(Hermes3Engine, '_probe_outlines_capability'))

    def test_probe_outlines_returns_bool(self):
        """_probe_outlines_capability should return bool."""
        from hledac.universal.brain.hermes3_engine import Hermes3Engine

        engine = Hermes3Engine()
        result = engine._probe_outlines_capability()
        self.assertIsInstance(result, bool)


class TestProbeXGrammarCapability(unittest.TestCase):
    """Tests for _probe_xgrammar_capability."""

    def test_probe_xgrammar_exists(self):
        """Hermes3Engine should have _probe_xgrammar_capability method."""
        from hledac.universal.brain.hermes3_engine import Hermes3Engine

        self.assertTrue(hasattr(Hermes3Engine, '_probe_xgrammar_capability'))

    def test_probe_xgrammar_returns_bool(self):
        """_probe_xgrammar_capability should return bool."""
        from hledac.universal.brain.hermes3_engine import Hermes3Engine

        engine = Hermes3Engine()
        result = engine._probe_xgrammar_capability()
        self.assertIsInstance(result, bool)


if __name__ == "__main__":
    unittest.main()
