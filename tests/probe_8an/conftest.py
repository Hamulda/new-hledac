"""
conftest for probe_8an — Pattern-backed feed pipeline tests.

ENV BLOCKER: live_feed_pipeline imports pattern_matcher which requires pyahocorasick.
Use importorskip to ensure collection succeeds when the C extension is not installed.
"""
import pytest

# ENV BLOCKER: skip entire conftest if ahocorasick not available
pytest.importorskip("ahocorasick", reason="ENV BLOCKER: pyahocorasick not installed")
