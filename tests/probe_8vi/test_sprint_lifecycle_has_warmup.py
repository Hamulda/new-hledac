"""
Sprint 8VI §E: run_warmup() import and signature test.
"""
import pytest

def test_sprint_lifecycle_has_warmup():
    """runtime/sprint_lifecycle must have run_warmup exported."""
    from runtime.sprint_lifecycle import run_warmup
    assert callable(run_warmup)
