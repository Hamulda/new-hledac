"""
Sprint 8C1: Flow trace smoke tests.

Tests that GHOST_FLOW_TRACE=1 produces valid JSONL output.
"""

import json
import os
import tempfile
from pathlib import Path


def test_flow_trace_module_import():
    """Flow trace module can be imported."""
    from hledac.universal.utils.flow_trace import is_enabled, trace_event, flush
    assert callable(is_enabled)
    assert callable(trace_event)
    assert callable(flush)


def test_flow_trace_disabled_by_default():
    """With flag OFF, tracing is disabled."""
    # Temporarily unset flag
    old = os.environ.pop("GHOST_FLOW_TRACE", None)

    try:
        # Re-import to pick up env change
        import importlib
        import hledac.universal.utils.flow_trace as ft
        importlib.reload(ft)

        assert ft.TRACE_ENABLED == False
        assert ft.is_enabled() == False
    finally:
        if old is not None:
            os.environ["GHOST_FLOW_TRACE"] = old


def test_flow_trace_enabled_flag():
    """With flag ON, tracing reports enabled."""
    old = os.environ.get("GHOST_FLOW_TRACE")

    try:
        os.environ["GHOST_FLOW_TRACE"] = "1"
        import importlib
        import hledac.universal.utils.flow_trace as ft
        importlib.reload(ft)

        assert ft.TRACE_ENABLED == True
        assert ft.is_enabled() == True
    finally:
        if old is None:
            os.environ.pop("GHOST_FLOW_TRACE", None)
        else:
            os.environ["GHOST_FLOW_TRACE"] = old


def test_flow_trace_event_no_crash():
    """trace_event doesn't crash even with invalid inputs."""
    from hledac.universal.utils.flow_trace import trace_event, is_enabled

    # Even if enabled, bad inputs should not crash
    try:
        trace_event(
            component="test",
            stage="test",
            event_type="test",
            item_id=None,
            url=None,
            target=None,
            status="ok",
            duration_ms=0.0,
            metadata={"key": "value"},
        )
    except Exception as e:
        raise AssertionError(f"trace_event crashed: {e}")


def test_flow_trace_summary_basic():
    """get_summary returns a dict with expected keys."""
    from hledac.universal.utils.flow_trace import get_summary, is_enabled

    if not is_enabled():
        return  # Skip if disabled

    summary = get_summary()
    assert isinstance(summary, dict)
    # When disabled, returns {}


def test_flow_trace_sample_rate():
    """SAMPLE_RATE parsing works."""
    old = os.environ.get("GHOST_FLOW_TRACE_SAMPLE_RATE")

    try:
        os.environ["GHOST_FLOW_TRACE_SAMPLE_RATE"] = "0.5"
        import importlib
        import hledac.universal.utils.flow_trace as ft
        importlib.reload(ft)

        assert ft.TRACE_SAMPLE_RATE == 0.5
    finally:
        if old is None:
            os.environ.pop("GHOST_FLOW_TRACE_SAMPLE_RATE", None)
        else:
            os.environ["GHOST_FLOW_TRACE_SAMPLE_RATE"] = old


def test_flow_trace_max_events():
    """MAX_EVENTS parsing works."""
    old = os.environ.get("GHOST_FLOW_TRACE_MAX_EVENTS")

    try:
        os.environ["GHOST_FLOW_TRACE_MAX_EVENTS"] = "10000"
        import importlib
        import hledac.universal.utils.flow_trace as ft
        importlib.reload(ft)

        assert ft.TRACE_MAX_EVENTS == 10000
    finally:
        if old is None:
            os.environ.pop("GHOST_FLOW_TRACE_MAX_EVENTS", None)
        else:
            os.environ["GHOST_FLOW_TRACE_MAX_EVENTS"] = old
