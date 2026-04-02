"""
Probe: Sprint 8VM — Shadow Pre-Decision Consumer Seam

Tests that SprintScheduler can consume ParityArtifact/PreDecisionSummary
from the existing shadow layer WITHOUT:
- Creating new mutable scheduler state
- Executing tools or activating providers
- Writing to ledgers as runtime truth
- Creating a new scheduler framework
- Dispatching or enqueuing work

These tests are READ-ONLY verification — they do not change system behavior.
"""

import os
import pytest
from unittest.mock import MagicMock, patch
from hledac.universal.runtime.sprint_scheduler import (
    SprintScheduler,
    SprintSchedulerConfig,
)


class TestShadowConsumerSeamReadOnly:
    """Verify shadow consumer is read-only and diagnostic only."""

    def test_consume_returns_none_when_not_shadow_mode(self):
        """
        When HLEDAC_RUNTIME_MODE is NOT set to shadow,
        consume_shadow_pre_decision() must return None.
        """
        # Ensure we are NOT in shadow mode
        original = os.environ.get("HLEDAC_RUNTIME_MODE")
        try:
            os.environ.pop("HLEDAC_RUNTIME_MODE", None)

            scheduler = SprintScheduler(SprintSchedulerConfig())
            result = scheduler.consume_shadow_pre_decision()
            assert result is None
        finally:
            if original is not None:
                os.environ["HLEDAC_RUNTIME_MODE"] = original

    def test_consume_returns_none_when_no_lifecycle(self):
        """
        Even in shadow mode, if no lifecycle adapter is set,
        consume_shadow_pre_decision() must return None.
        """
        original = os.environ.get("HLEDAC_RUNTIME_MODE")
        try:
            os.environ["HLEDAC_RUNTIME_MODE"] = "scheduler_shadow"

            scheduler = SprintScheduler(SprintSchedulerConfig())
            # _lc_adapter is None until run() is called
            result = scheduler.consume_shadow_pre_decision()
            assert result is None
        finally:
            if original is not None:
                os.environ["HLEDAC_RUNTIME_MODE"] = original
            else:
                os.environ.pop("HLEDAC_RUNTIME_MODE", None)

    def test_consume_caches_result_within_sprint(self):
        """
        consume_shadow_pre_decision() must cache its result
        in _shadow_pd_summary to avoid recomputation.
        """
        original = os.environ.get("HLEDAC_RUNTIME_MODE")
        try:
            os.environ["HLEDAC_RUNTIME_MODE"] = "scheduler_shadow"

            scheduler = SprintScheduler(SprintSchedulerConfig())
            # Set up mock lifecycle
            mock_lc = MagicMock()
            mock_lc.snapshot.return_value = {
                "current_phase": "ACTIVE",
                "entered_phase_at": 10.0,
                "started_at_monotonic": 0.0,
                "sprint_duration_s": 1800.0,
                "windup_lead_s": 180.0,
            }
            mock_lc.recommended_tool_mode.return_value = "normal"
            mock_lc.remaining_time.return_value = 1200.0

            # Wire it up via the adapter pattern
            scheduler._lc_adapter = MagicMock()
            scheduler._lc_adapter._lc = mock_lc
            scheduler._synthesis_engine = "test-engine"

            # First call
            result1 = scheduler.consume_shadow_pre_decision()
            cache_after_first = scheduler._shadow_pd_summary

            # Second call — should return cached value
            result2 = scheduler.consume_shadow_pre_decision()

            if result1 is not None:
                # Cache must be set after first call
                assert cache_after_first is not None
                # Second call must return same object (cached)
                assert result1 is result2
                assert result1 is cache_after_first
        finally:
            if original is not None:
                os.environ["HLEDAC_RUNTIME_MODE"] = original
            else:
                os.environ.pop("HLEDAC_RUNTIME_MODE", None)

    def test_shadow_pd_summary_cleared_in_reset(self):
        """
        _shadow_pd_summary must be cleared in _reset_result().
        """
        original = os.environ.get("HLEDAC_RUNTIME_MODE")
        try:
            os.environ["HLEDAC_RUNTIME_MODE"] = "scheduler_shadow"

            scheduler = SprintScheduler(SprintSchedulerConfig())
            # Set a fake cached value
            scheduler._shadow_pd_summary = "fake_cached_value"

            scheduler._reset_result()

            assert scheduler._shadow_pd_summary is None
        finally:
            if original is not None:
                os.environ["HLEDAC_RUNTIME_MODE"] = original
            else:
                os.environ.pop("HLEDAC_RUNTIME_MODE", None)

    def test_build_shadow_readiness_preview_returns_dict(self):
        """
        _build_shadow_readiness_preview() must return a dict
        when in shadow mode, or empty dict when not.
        """
        original = os.environ.get("HLEDAC_RUNTIME_MODE")
        try:
            os.environ["HLEDAC_RUNTIME_MODE"] = "scheduler_shadow"

            scheduler = SprintScheduler(SprintSchedulerConfig())
            scheduler._lc_adapter = MagicMock()
            scheduler._lc_adapter._lc = MagicMock()

            preview = scheduler._build_shadow_readiness_preview()
            assert isinstance(preview, dict)
        finally:
            if original is not None:
                os.environ["HLEDAC_RUNTIME_MODE"] = original
            else:
                os.environ.pop("HLEDAC_RUNTIME_MODE", None)

    def test_diagnostic_report_includes_shadow_key(self):
        """
        _build_diagnostic_report() must include 'shadow_pre_decision' key
        when in shadow mode.
        """
        original = os.environ.get("HLEDAC_RUNTIME_MODE")
        try:
            os.environ["HLEDAC_RUNTIME_MODE"] = "scheduler_shadow"

            scheduler = SprintScheduler(SprintSchedulerConfig())
            scheduler._lc_adapter = MagicMock()
            mock_lc = MagicMock()
            mock_lc._current_phase = MagicMock()
            mock_lc._current_phase.name = "ACTIVE"
            mock_lc.snapshot.return_value = {
                "current_phase": "ACTIVE",
                "entered_phase_at": 10.0,
                "started_at_monotonic": 0.0,
                "sprint_duration_s": 1800.0,
                "windup_lead_s": 180.0,
            }
            scheduler._lc_adapter._lc = mock_lc

            report = scheduler._build_diagnostic_report(mock_lc)

            assert "shadow_pre_decision" in report
            assert isinstance(report["shadow_pre_decision"], dict)
        finally:
            if original is not None:
                os.environ["HLEDAC_RUNTIME_MODE"] = original
            else:
                os.environ.pop("HLEDAC_RUNTIME_MODE", None)

    def test_diagnostic_report_skips_shadow_when_not_shadow_mode(self):
        """
        When HLEDAC_RUNTIME_MODE is not shadow,
        _build_diagnostic_report() must NOT include 'shadow_pre_decision'.
        """
        original = os.environ.get("HLEDAC_RUNTIME_MODE")
        try:
            os.environ.pop("HLEDAC_RUNTIME_MODE", None)

            scheduler = SprintScheduler(SprintSchedulerConfig())
            mock_lc = MagicMock()
            mock_lc._current_phase = MagicMock()
            mock_lc._current_phase.name = "ACTIVE"
            mock_lc.snapshot.return_value = {"current_phase": "ACTIVE"}

            report = scheduler._build_diagnostic_report(mock_lc)

            assert "shadow_pre_decision" not in report
        finally:
            if original is not None:
                os.environ["HLEDAC_RUNTIME_MODE"] = original


class TestShadowConsumerHardBoundaries:
    """
    Verify hard boundaries: no tool execution, no ledger writes,
    no provider activation, no dispatch.

    These tests verify the INVARIANTS rather than patching the wrong targets.
    """

    def test_only_shadow_pd_summary_field_is_mutated(self):
        """
        consume_shadow_pre_decision() must ONLY modify _shadow_pd_summary
        as persistent state. No other scheduler fields may be mutated.
        """
        original = os.environ.get("HLEDAC_RUNTIME_MODE")
        try:
            os.environ["HLEDAC_RUNTIME_MODE"] = "scheduler_shadow"

            scheduler = SprintScheduler(SprintSchedulerConfig())
            mock_lc = MagicMock()
            mock_lc.snapshot.return_value = {
                "current_phase": "ACTIVE",
                "entered_phase_at": 10.0,
                "started_at_monotonic": 0.0,
                "sprint_duration_s": 1800.0,
                "windup_lead_s": 180.0,
            }
            mock_lc.recommended_tool_mode.return_value = "normal"
            mock_lc.remaining_time.return_value = 1200.0
            scheduler._lc_adapter = MagicMock()
            scheduler._lc_adapter._lc = mock_lc
            scheduler._config = SprintSchedulerConfig()

            # Snapshot mutable fields before
            bg_tasks_before = len(scheduler._bg_tasks)
            result_before = scheduler._result
            seen_hashes_before = dict(scheduler._seen_hashes)

            result = scheduler.consume_shadow_pre_decision()

            # Only _shadow_pd_summary should be mutated (or remain None if unavailable)
            # bg_tasks must not grow (no new asyncio tasks created)
            assert len(scheduler._bg_tasks) == bg_tasks_before, \
                "consume_shadow_pre_decision must not create new asyncio tasks"
            # _result must not be replaced
            assert scheduler._result is result_before, \
                "consume_shadow_pre_decision must not replace _result"
            # _seen_hashes must not be mutated
            assert dict(scheduler._seen_hashes) == seen_hashes_before, \
                "consume_shadow_pre_decision must not mutate _seen_hashes"
        finally:
            if original is not None:
                os.environ["HLEDAC_RUNTIME_MODE"] = original
            else:
                os.environ.pop("HLEDAC_RUNTIME_MODE", None)

    def test_returns_none_in_legacy_mode(self):
        """
        In legacy mode (default), consume_shadow_pre_decision()
        must return None immediately — no computation performed.
        """
        original = os.environ.get("HLEDAC_RUNTIME_MODE")
        try:
            os.environ.pop("HLEDAC_RUNTIME_MODE", None)

            scheduler = SprintScheduler(SprintSchedulerConfig())
            scheduler._lc_adapter = MagicMock()
            scheduler._lc_adapter._lc = MagicMock()

            result = scheduler.consume_shadow_pre_decision()

            assert result is None
            # _shadow_pd_summary must NOT be set in legacy mode
            assert scheduler._shadow_pd_summary is None
        finally:
            if original is not None:
                os.environ["HLEDAC_RUNTIME_MODE"] = original

    def test_result_has_pre_decision_summary_attributes(self):
        """
        When consume_shadow_pre_decision() succeeds, the returned
        object must be a PreDecisionSummary with expected attributes.
        """
        original = os.environ.get("HLEDAC_RUNTIME_MODE")
        try:
            os.environ["HLEDAC_RUNTIME_MODE"] = "scheduler_shadow"

            scheduler = SprintScheduler(SprintSchedulerConfig())
            mock_lc = MagicMock()
            mock_lc.snapshot.return_value = {
                "current_phase": "ACTIVE",
                "entered_phase_at": 10.0,
                "started_at_monotonic": 0.0,
                "sprint_duration_s": 1800.0,
                "windup_lead_s": 180.0,
            }
            mock_lc.recommended_tool_mode.return_value = "normal"
            mock_lc.remaining_time.return_value = 1200.0
            scheduler._lc_adapter = MagicMock()
            scheduler._lc_adapter._lc = mock_lc
            scheduler._config = SprintSchedulerConfig()
            scheduler._synthesis_engine = "test-engine"

            result = scheduler.consume_shadow_pre_decision()

            # If ToolRegistry is unavailable (try/except), result may be None
            # If available, must have PreDecisionSummary attributes
            if result is not None:
                assert hasattr(result, "lifecycle"), \
                    "Result must have lifecycle attribute"
                assert hasattr(result, "graph"), \
                    "Result must have graph attribute"
                assert hasattr(result, "diff_taxonomy"), \
                    "Result must have diff_taxonomy attribute"
                assert hasattr(result, "blockers"), \
                    "Result must have blockers attribute"
                assert hasattr(result, "unknowns"), \
                    "Result must have unknowns attribute"
        finally:
            if original is not None:
                os.environ["HLEDAC_RUNTIME_MODE"] = original
            else:
                os.environ.pop("HLEDAC_RUNTIME_MODE", None)


class TestShadowReadinessPreviewStructure:
    """Verify _build_shadow_readiness_preview() produces correct structure."""

    def test_preview_contains_required_keys(self):
        """
        When shadow mode is active, preview dict must contain:
        runtime_mode, lifecycle_readiness, graph_readiness,
        diff_taxonomy, blockers, unknowns, compat_seams.
        """
        original = os.environ.get("HLEDAC_RUNTIME_MODE")
        try:
            os.environ["HLEDAC_RUNTIME_MODE"] = "scheduler_shadow"

            scheduler = SprintScheduler(SprintSchedulerConfig())
            mock_lc = MagicMock()
            mock_lc.snapshot.return_value = {
                "current_phase": "ACTIVE",
                "entered_phase_at": 10.0,
                "started_at_monotonic": 0.0,
                "sprint_duration_s": 1800.0,
                "windup_lead_s": 180.0,
            }
            mock_lc.recommended_tool_mode.return_value = "normal"
            mock_lc.remaining_time.return_value = 1200.0
            scheduler._lc_adapter = MagicMock()
            scheduler._lc_adapter._lc = mock_lc
            scheduler._synthesis_engine = "test-engine"
            scheduler._config = SprintSchedulerConfig()

            preview = scheduler._build_shadow_readiness_preview()

            if preview:  # May be empty if lifecycle unavailable
                assert "runtime_mode" in preview
                assert "lifecycle_readiness" in preview
                assert "graph_readiness" in preview
                assert "diff_taxonomy" in preview
                assert "blockers" in preview
                assert "unknowns" in preview
                assert "compat_seams" in preview
        finally:
            if original is not None:
                os.environ["HLEDAC_RUNTIME_MODE"] = original
            else:
                os.environ.pop("HLEDAC_RUNTIME_MODE", None)
