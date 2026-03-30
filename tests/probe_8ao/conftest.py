"""
conftest for probe_8ao — mock ahocorasick before any test imports
the pattern_matcher → live_feed_pipeline chain.
"""
import sys
from unittest.mock import MagicMock

# Pre-empt ahocorasick import so tests that transitively import
# live_feed_pipeline → pattern_matcher don't crash on missing native ext
sys.modules.setdefault("ahocorasick", MagicMock(__name__="ahocorasick"))
