"""
conftest for probe_8bd — env blocker helper for ahocorasick.
Uses module-level import guard so pytest.skip is raised as SKIP, not collection ERROR.
"""
import pytest

# ENV BLOCKER: ahocorasick C extension is not installed.
# Tests that transitively import pattern_matcher → live_feed_pipeline chain
# will be skipped rather than causing collection errors.
ahocorasick = pytest.importorskip("ahocorasick", reason="ENV BLOCKER: ahocorasick C extension not available")
