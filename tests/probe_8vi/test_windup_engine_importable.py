"""
Sprint 8VI §E: run_windup() import test.
"""
import pytest

def test_windup_engine_importable():
    """runtime/windup_engine must have run_windup exported."""
    from runtime.windup_engine import run_windup
    assert callable(run_windup)
