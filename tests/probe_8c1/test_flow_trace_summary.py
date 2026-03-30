"""
Sprint 8C1: Trace summary aggregation tests.

Tests that the trace summary correctly aggregates events.
"""

import json
import os
import tempfile
from pathlib import Path


def _enable_and_reload():
    """Enable tracing and reload module."""
    os.environ["GHOST_FLOW_TRACE"] = "1"
    import importlib
    import hledac.universal.utils.flow_trace as ft
    importlib.reload(ft)
    ft.set_run_id("test_run_8c1")
    return ft


def _disable_and_reload():
    """Disable tracing and reload module."""
    os.environ.pop("GHOST_FLOW_TRACE", None)
    import importlib
    import hledac.universal.utils.flow_trace as ft
    importlib.reload(ft)
    return ft


def test_summary_has_expected_fields():
    """Summary dict contains expected aggregation fields."""
    ft = _enable_and_reload()

    # Emit some events
    ft.trace_event("fetch_coordinator", "fetch", "fetch_start", status="ok")
    ft.trace_event("fetch_coordinator", "fetch", "fetch_end", status="ok", duration_ms=50.0)
    ft.trace_counter("fetch_total")
    ft.flush()

    summary = ft.get_summary()
    assert "run_id" in summary
    assert "event_count" in summary
    assert "counters" in summary

    _disable_and_reload()


def test_summary_counters():
    """Counters are correctly accumulated."""
    ft = _enable_and_reload()

    ft.trace_counter("test_counter", 1)
    ft.trace_counter("test_counter", 2)
    ft.trace_counter("another_counter", 5)
    ft.flush()

    summary = ft.get_summary()
    assert summary["counters"].get("test_counter", 0) == 3
    assert summary["counters"].get("another_counter", 0) == 5

    _disable_and_reload()


def test_summary_event_count_incremented():
    """Event count increments on trace calls."""
    ft = _enable_and_reload()

    initial = ft.get_summary().get("event_count", 0)
    ft.trace_event("test", "test", "test1", status="ok")
    ft.trace_event("test", "test", "test2", status="ok")
    ft.flush()

    summary = ft.get_summary()
    assert summary["event_count"] >= initial + 2

    _disable_and_reload()
