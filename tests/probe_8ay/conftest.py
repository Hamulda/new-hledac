import pytest

pytest.importorskip("ahocorasick", reason="ENV BLOCKER: pyahocorasick not installed")
