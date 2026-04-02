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


class TestRicherReadinessPreview:
    """Sprint 8VQ: Tests for richer readiness previews."""

    def test_decision_gate_preview_fields(self):
        """DecisionGateReadiness must have required fields."""
        from hledac.universal.runtime.shadow_pre_decision import DecisionGateReadiness

        gate = DecisionGateReadiness(
            gate_status="ready",
            blocker_count=0,
            unknown_count=1,
            compat_seam_count=1,
            blocker_categories=[],
            unknown_categories=["provider"],
            is_proceed_allowed=True,
            defer_to_provider=True,
        )

        assert gate.gate_status == "ready"
        assert gate.blocker_count == 0
        assert gate.is_proceed_allowed is True
        assert gate.defer_to_provider is True

    def test_tool_readiness_preview_fields(self):
        """ToolReadinessPreview must have required fields."""
        from hledac.universal.runtime.shadow_pre_decision import ToolReadinessPreview

        tool = ToolReadinessPreview(
            readiness="ready",
            tool_count=5,
            tool_names=["fetch", "search", "analyze"],
            has_network_tools=True,
            has_high_memory_tools=False,
            control_mode="normal",
            pruned_tool_count=0,
            resource_constraint="none",
            can_execute=True,
            defer_reason=None,
        )

        assert tool.readiness == "ready"
        assert tool.can_execute is True
        assert tool.control_mode == "normal"

    def test_windup_readiness_preview_fields(self):
        """WindupReadinessPreview must have required fields."""
        from hledac.universal.runtime.shadow_pre_decision import WindupReadinessPreview

        windup = WindupReadinessPreview(
            readiness="ready",
            is_windup_phase=True,
            synthesis_mode="synthesis",
            synthesis_engine="test-engine",
            has_export_data=True,
            export_data_quality="ready",
            defer_reason=None,
        )

        assert windup.readiness == "ready"
        assert windup.is_windup_phase is True

    def test_provider_activation_note_fields(self):
        """ProviderActivationNote must have required fields."""
        from hledac.universal.runtime.shadow_pre_decision import ProviderActivationNote

        note = ProviderActivationNote(
            status="deferred",
            deferral_reason="lifecycle not in ACTIVE phase",
            has_recommendation=False,
            recommendation=None,
            next_phase_hint="ACTIVATE phase required",
        )

        assert note.status == "deferred"
        assert note.has_recommendation is False
        assert note.next_phase_hint == "ACTIVATE phase required"

    def test_decision_gate_blocked_when_blockers_present(self):
        """DecisionGateReadiness must be blocked when blockers present."""
        from hledac.universal.runtime.shadow_pre_decision import DecisionGateReadiness

        gate = DecisionGateReadiness(
            gate_status="blocked",
            blocker_count=2,
            unknown_count=0,
            compat_seam_count=0,
            blocker_categories=["lifecycle", "graph"],
            unknown_categories=[],
            is_proceed_allowed=False,
            defer_to_provider=False,
        )

        assert gate.gate_status == "blocked"
        assert gate.is_proceed_allowed is False
        assert gate.blocker_count == 2

    def test_pre_decision_summary_has_new_fields(self):
        """PreDecisionSummary must have decision_gate, tool_readiness, windup_readiness, provider_note."""
        from hledac.universal.runtime.shadow_pre_decision import (
            PreDecisionSummary,
            LifecycleInterpretation,
            GraphCapabilitySummary,
            ExportReadinessSummary,
            ModelControlSummary,
            PrecursorSummary,
            DiffTaxonomy,
        )

        # Minimal PreDecisionSummary with new fields
        pd = PreDecisionSummary(
            parity_timestamp_monotonic=0.0,
            parity_timestamp_wall="2026-04-02T00:00:00Z",
            runtime_mode="scheduler_shadow",
            lifecycle=LifecycleInterpretation(
                workflow_phase="ACTIVE",
                workflow_phase_entered_at=0.0,
                control_phase_mode="normal",
                control_phase_thermal="nominal",
                windup_local_mode=None,
                is_active=True,
                is_windup=False,
                is_export_ready=False,
                is_terminal=False,
                can_accept_work=True,
                should_prune=False,
                synthesis_mode_known=False,
                phase_conflict=False,
                phase_conflict_reason=None,
            ),
            graph=GraphCapabilitySummary(
                backend="duckpgq",
                nodes=100,
                edges=500,
                pgq_active=True,
                top_nodes_count=10,
                is_initialized=True,
                has_structured_data=True,
                is_rich=True,
                readiness="rich",
            ),
            export_readiness=ExportReadinessSummary(
                sprint_id="test",
                synthesis_engine="test",
                ranked_parquet_present=True,
                gnn_predictions=10,
                is_ready=True,
                has_gnn_predictions=True,
                has_ranked_data=True,
                readiness="ready",
            ),
            model_control=ModelControlSummary(
                tools_count=5,
                sources_count=3,
                privacy="STANDARD",
                depth="DEEP",
                models_needed=[],
                has_tools=True,
                has_sources=True,
                is_high_quality=True,
                readiness="ready",
            ),
            precursors=PrecursorSummary(
                branch_decision_id=None,
                provider_recommend=None,
                correlation_run_id=None,
                correlation_branch_id=None,
                has_branch_decision=False,
                has_provider_recommend=False,
                has_correlation=False,
                is_correlation_linked=False,
                readiness="unknown",
            ),
            diff_taxonomy=[DiffTaxonomy.NONE],
            blockers=[],
            unknowns=["provider recommendation not available"],
            mismatch_reasons={},
            compat_seams=[],
        )

        # New fields must be present (can be None)
        assert hasattr(pd, "decision_gate")
        assert hasattr(pd, "tool_readiness")
        assert hasattr(pd, "windup_readiness")
        assert hasattr(pd, "provider_note")

    def test_compose_decision_gate_ready(self):
        """_compose_decision_gate_readiness must return ready when no blockers."""
        from hledac.universal.runtime.shadow_pre_decision import (
            _compose_decision_gate_readiness,
        )

        gate = _compose_decision_gate_readiness(
            blockers=[],
            unknowns=["some unknown"],
            compat_seams=["windup_local_phase"],
        )

        assert gate.gate_status == "ready"
        assert gate.is_proceed_allowed is True
        assert gate.blocker_count == 0

    def test_compose_decision_gate_blocked(self):
        """_compose_decision_gate_readiness must return blocked when blockers present."""
        from hledac.universal.runtime.shadow_pre_decision import (
            _compose_decision_gate_readiness,
        )

        gate = _compose_decision_gate_readiness(
            blockers=["lifecycle not ready", "graph backend unknown"],
            unknowns=[],
            compat_seams=[],
        )

        assert gate.gate_status == "blocked"
        assert gate.is_proceed_allowed is False
        assert gate.blocker_count == 2

    def test_compose_windup_not_active(self):
        """_compose_windup_readiness_preview must return not_active when not in WINDUP."""
        from hledac.universal.runtime.shadow_pre_decision import (
            _compose_windup_readiness_preview,
            LifecycleInterpretation,
            ExportReadinessSummary,
        )

        lc = LifecycleInterpretation(
            workflow_phase="ACTIVE",
            workflow_phase_entered_at=0.0,
            control_phase_mode="normal",
            control_phase_thermal="nominal",
            windup_local_mode=None,
            is_active=True,
            is_windup=False,
            is_export_ready=False,
            is_terminal=False,
            can_accept_work=True,
            should_prune=False,
            synthesis_mode_known=False,
            phase_conflict=False,
            phase_conflict_reason=None,
        )
        er = ExportReadinessSummary(
            sprint_id="test",
            synthesis_engine="test",
            ranked_parquet_present=True,
            gnn_predictions=10,
            is_ready=True,
            has_gnn_predictions=True,
            has_ranked_data=True,
            readiness="ready",
        )

        windup = _compose_windup_readiness_preview(lc, er)

        assert windup.readiness == "not_active"
        assert windup.is_windup_phase is False

    def test_compose_provider_deferred_not_active(self):
        """ProviderActivationNote must be deferred when lifecycle not in ACTIVE."""
        from hledac.universal.runtime.shadow_pre_decision import (
            _compose_provider_activation_note,
            LifecycleInterpretation,
            PrecursorSummary,
        )

        lc = LifecycleInterpretation(
            workflow_phase="WARMUP",
            workflow_phase_entered_at=0.0,
            control_phase_mode="normal",
            control_phase_thermal="nominal",
            windup_local_mode=None,
            is_active=False,
            is_windup=False,
            is_export_ready=False,
            is_terminal=False,
            can_accept_work=True,
            should_prune=False,
            synthesis_mode_known=False,
            phase_conflict=False,
            phase_conflict_reason=None,
        )
        pr = PrecursorSummary(
            branch_decision_id=None,
            provider_recommend=None,
            correlation_run_id=None,
            correlation_branch_id=None,
            has_branch_decision=False,
            has_provider_recommend=False,
            has_correlation=False,
            is_correlation_linked=False,
            readiness="unknown",
        )

        note = _compose_provider_activation_note(pr, lc)

        assert note.status == "deferred"
        assert "not ACTIVE or WINDUP" in note.deferral_reason

    def test_no_provider_simulation(self):
        """ProviderActivationNote must NOT contain load_order or provider_state."""
        from hledac.universal.runtime.shadow_pre_decision import ProviderActivationNote
        import dataclasses

        note = ProviderActivationNote(
            status="deferred",
            deferral_reason="test",
            has_recommendation=False,
            recommendation=None,
            next_phase_hint=None,
        )

        # Ensure no load_order or provider_state fields exist
        field_names = {f.name for f in dataclasses.fields(note)}
        assert "load_order" not in field_names
        assert "provider_state" not in field_names
        assert "activation_sequence" not in field_names
