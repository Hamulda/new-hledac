"""
Shared fixtures for Sprint 8BK tests.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_lifecycle():
    """Minimal mock of SprintLifecycleManager with required API."""
    lm = MagicMock()
    lm.sprint_duration_s = 1800.0
    lm.windup_lead_s = 180.0
    lm._started_at = None
    lm._current_phase = MagicMock()
    lm._current_phase.name = "BOOT"
    lm._abort_requested = False
    lm._abort_reason = ""
    lm._export_started = False
    lm._teardown_started = False

    def start(now_monotonic=None):
        lm._started_at = now_monotonic or 100.0
        lm._current_phase.name = "WARMUP"

    def tick(now_monotonic=None):
        now = now_monotonic or lm._started_at or 100.0
        if lm._started_at is None:
            return lm._current_phase
        elapsed = now - lm._started_at
        remaining = lm.sprint_duration_s - elapsed
        if remaining <= lm.windup_lead_s:
            lm._current_phase.name = "WINDUP"
        else:
            lm._current_phase.name = "ACTIVE"
        return lm._current_phase

    def should_enter_windup(now_monotonic=None):
        now = now_monotonic or lm._started_at or 100.0
        if lm._started_at is None:
            return False
        remaining = lm.sprint_duration_s - (now - lm._started_at)
        return remaining <= lm.windup_lead_s

    def is_terminal():
        return lm._teardown_started

    def request_abort(reason=""):
        lm._abort_requested = True
        lm._abort_reason = reason

    def mark_export_started(_now_monotonic=None):
        lm._export_started = True
        lm._current_phase.name = "EXPORT"

    def mark_teardown_started(_now_monotonic=None):
        lm._teardown_started = True
        lm._current_phase.name = "TEARDOWN"

    def snapshot():
        return {
            "current_phase": lm._current_phase.name,
            "abort_requested": lm._abort_requested,
        }

    def recommended_tool_mode(now_monotonic=None, thermal_state="nominal"):
        now = now_monotonic or lm._started_at or 100.0
        remaining = lm.sprint_duration_s - (now - lm._started_at) if lm._started_at else 9999.0
        if lm._abort_requested or remaining <= 30.0 or thermal_state == "critical":
            return "panic"
        if remaining <= lm.windup_lead_s or thermal_state in ("throttled", "fair"):
            return "prune"
        return "normal"

    lm.start = start
    lm.tick = tick
    lm.should_enter_windup = should_enter_windup
    lm.is_terminal = is_terminal
    lm.request_abort = request_abort
    lm.mark_export_started = mark_export_started
    lm.mark_teardown_started = mark_teardown_started
    lm.snapshot = snapshot
    lm.recommended_tool_mode = recommended_tool_mode

    return lm


@pytest.fixture
def mock_feed_result():
    """Mock FeedPipelineRunResult."""
    result = MagicMock()
    result.feed_url = "http://example.com/feed"
    result.fetched_entries = 5
    result.accepted_findings = 2
    result.stored_findings = 1
    result.patterns_configured = 10
    result.matched_patterns = 3
    result.pages = ()
    result.error = None
    return result


@pytest.fixture
def sample_sources():
    return [
        "http://feeds.example.com/news",
        "http://feeds.example.com/security",
        "http://archive.example.com/old",
    ]
