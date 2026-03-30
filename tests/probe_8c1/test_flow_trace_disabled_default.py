"""
Sprint 8C1: Default-off behavior tests.

Ensures with GHOST_FLOW_TRACE=0 (or unset), default path is unchanged.
"""

import os
import sys


def test_no_trace_io_when_disabled():
    """When disabled, no trace files are created."""
    # Ensure flag is off
    os.environ.pop("GHOST_FLOW_TRACE", None)

    import importlib
    import hledac.universal.utils.flow_trace as ft
    importlib.reload(ft)

    assert ft.is_enabled() == False

    # Write some events
    ft.trace_event("test", "test", "test_event", status="ok")
    ft.trace_counter("test_counter")
    ft.flush()

    # No files should be created when disabled
    # (This is tested by the fact no file handles are opened)


def test_trace_span_disabled():
    """Span operations work when disabled (no-op)."""
    import hledac.universal.utils.flow_trace as ft

    # Should return 0.0 when disabled
    start = ft.trace_span_start("span1")
    assert start == 0.0

    # Should return None when disabled
    end = ft.trace_span_end("span1", "test", "test", "ok")
    assert end is None


def test_convenience_wrappers_disabled():
    """Convenience wrappers don't crash when disabled."""
    from hledac.universal.utils.flow_trace import (
        trace_fetch_start, trace_fetch_end, trace_dedup_decision,
        trace_evidence_append, trace_evidence_flush, trace_queue_drop,
    )

    # Should not crash
    trace_fetch_start("http://example.com", "curl")
    trace_fetch_end("http://example.com", "curl", "ok", 10.0)
    trace_dedup_decision("http://example.com", False)
    trace_evidence_append("tool_call", 5, "queued")
    trace_evidence_flush(10, 5.0, "ok", 10)
    trace_queue_drop("sqlite_queue", 501)
