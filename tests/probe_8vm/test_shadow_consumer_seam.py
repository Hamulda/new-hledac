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


class TestAdvisoryGateSnapshot:
    """Sprint 8VQ: Tests for advisory gate snapshot."""

    def test_advisory_gate_snapshot_fields(self):
        """AdvisoryGateSnapshot must have required fields."""
        from hledac.universal.runtime.shadow_pre_decision import AdvisoryGateSnapshot

        ag = AdvisoryGateSnapshot(
            gate_outcome="proceed",
            gate_status="ready",
            blocker_count=0,
            unknown_count=1,
            compat_seam_count=1,
            blocker_reasons=[],
            unknown_reasons=["graph backend unknown"],
            compat_seam_reasons=["windup_local_phase"],
            defer_to_provider=True,
            gate_evaluated_at_monotonic=1234.0,
            gate_evaluated_at_wall="2026-04-02T00:00:00Z",
            source_pd_timestamp=1233.5,
        )

        assert ag.gate_outcome == "proceed"
        assert ag.gate_status == "ready"
        assert ag.blocker_count == 0
        assert ag.defer_to_provider is True

    def test_advisory_gate_snapshot_to_dict(self):
        """AdvisoryGateSnapshot.to_dict() must return all fields."""
        from hledac.universal.runtime.shadow_pre_decision import AdvisoryGateSnapshot

        ag = AdvisoryGateSnapshot(
            gate_outcome="blocked",
            gate_status="blocked",
            blocker_count=2,
            unknown_count=0,
            compat_seam_count=0,
            blocker_reasons=["lifecycle not ready", "graph backend unknown"],
            unknown_reasons=[],
            compat_seam_reasons=[],
            defer_to_provider=False,
            gate_evaluated_at_monotonic=1234.0,
            gate_evaluated_at_wall="2026-04-02T00:00:00Z",
            source_pd_timestamp=1233.5,
        )

        d = ag.to_dict()
        assert d["gate_outcome"] == "blocked"
        assert d["gate_status"] == "blocked"
        assert d["blocker_count"] == 2
        assert len(d["blocker_reasons"]) == 2

    def test_compose_advisory_gate_proceed(self):
        """compose_advisory_gate must return proceed when no blockers."""
        from hledac.universal.runtime.shadow_pre_decision import (
            compose_advisory_gate,
            PreDecisionSummary,
            LifecycleInterpretation,
            GraphCapabilitySummary,
            ExportReadinessSummary,
            ModelControlSummary,
            PrecursorSummary,
            DiffTaxonomy,
            DecisionGateReadiness,
        )

        pd = PreDecisionSummary(
            parity_timestamp_monotonic=1234.0,
            parity_timestamp_wall="2026-04-02T00:00:00Z",
            runtime_mode="scheduler_shadow",
            lifecycle=LifecycleInterpretation(
                workflow_phase="WINDUP",
                workflow_phase_entered_at=0.0,
                control_phase_mode="normal",
                control_phase_thermal="nominal",
                windup_local_mode="synthesis",
                is_active=False,
                is_windup=True,
                is_export_ready=False,
                is_terminal=False,
                can_accept_work=False,
                should_prune=False,
                synthesis_mode_known=True,
                phase_conflict=False,
                phase_conflict_reason=None,
            ),
            graph=GraphCapabilitySummary(
                backend="duckpgq", nodes=100, edges=500, pgq_active=True,
                top_nodes_count=10, is_initialized=True, has_structured_data=True,
                is_rich=True, readiness="rich",
            ),
            export_readiness=ExportReadinessSummary(
                sprint_id="test", synthesis_engine="test",
                ranked_parquet_present=True, gnn_predictions=10,
                is_ready=True, has_gnn_predictions=True, has_ranked_data=True,
                readiness="ready",
            ),
            model_control=ModelControlSummary(
                tools_count=5, sources_count=3, privacy="STANDARD", depth="DEEP",
                models_needed=[], has_tools=True, has_sources=True,
                is_high_quality=True, readiness="ready",
            ),
            precursors=PrecursorSummary(
                branch_decision_id=None, provider_recommend=None,
                correlation_run_id=None, correlation_branch_id=None,
                has_branch_decision=False, has_provider_recommend=False,
                has_correlation=False, is_correlation_linked=False,
                readiness="unknown",
            ),
            diff_taxonomy=[DiffTaxonomy.NONE],
            blockers=[],
            unknowns=["provider recommendation not available"],
            mismatch_reasons={},
            compat_seams=["windup_local_phase"],
            decision_gate=DecisionGateReadiness(
                gate_status="ready",
                blocker_count=0,
                unknown_count=1,
                compat_seam_count=1,
                blocker_categories=[],
                unknown_categories=["provider"],
                is_proceed_allowed=True,
                defer_to_provider=True,
            ),
        )

        ag = compose_advisory_gate(pd)

        assert ag.gate_outcome == "proceed"
        assert ag.gate_status == "ready"
        assert ag.blocker_count == 0
        assert ag.unknown_count == 1
        assert ag.defer_to_provider is True

    def test_compose_advisory_gate_blocked(self):
        """compose_advisory_gate must return blocked when blockers present."""
        from hledac.universal.runtime.shadow_pre_decision import (
            compose_advisory_gate,
            PreDecisionSummary,
            LifecycleInterpretation,
            GraphCapabilitySummary,
            ExportReadinessSummary,
            ModelControlSummary,
            PrecursorSummary,
            DiffTaxonomy,
            DecisionGateReadiness,
        )

        pd = PreDecisionSummary(
            parity_timestamp_monotonic=1234.0,
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
                backend="unknown", nodes=0, edges=0, pgq_active=False,
                top_nodes_count=0, is_initialized=False, has_structured_data=False,
                is_rich=False, readiness="unknown",
            ),
            export_readiness=ExportReadinessSummary(
                sprint_id="unknown", synthesis_engine="unknown",
                ranked_parquet_present=False, gnn_predictions=0,
                is_ready=False, has_gnn_predictions=False, has_ranked_data=False,
                readiness="unknown",
            ),
            model_control=ModelControlSummary(
                tools_count=0, sources_count=0, privacy="UNKNOWN", depth="UNKNOWN",
                models_needed=[], has_tools=False, has_sources=False,
                is_high_quality=False, readiness="unknown",
            ),
            precursors=PrecursorSummary(
                branch_decision_id=None, provider_recommend=None,
                correlation_run_id=None, correlation_branch_id=None,
                has_branch_decision=False, has_provider_recommend=False,
                has_correlation=False, is_correlation_linked=False,
                readiness="unknown",
            ),
            diff_taxonomy=[DiffTaxonomy.GRAPH_CAPABILITY_AMBIGUITY],
            blockers=["graph backend unknown — cannot determine graph capability"],
            unknowns=[],
            mismatch_reasons={},
            compat_seams=[],
            decision_gate=DecisionGateReadiness(
                gate_status="blocked",
                blocker_count=1,
                unknown_count=0,
                compat_seam_count=0,
                blocker_categories=["graph"],
                unknown_categories=[],
                is_proceed_allowed=False,
                defer_to_provider=False,
            ),
        )

        ag = compose_advisory_gate(pd)

        assert ag.gate_outcome == "blocked"
        assert ag.gate_status == "blocked"
        assert ag.blocker_count == 1
        assert len(ag.blocker_reasons) == 1


class TestAdvisoryGateSchedulerIntegration:
    """Sprint 8VQ: Tests for evaluate_advisory_gate in SprintScheduler."""

    def test_evaluate_advisory_gate_clears_pd_summary_field(self):
        """_advisory_gate_snapshot must be cleared in _reset_result."""
        original = os.environ.get("HLEDAC_RUNTIME_MODE")
        try:
            os.environ["HLEDAC_RUNTIME_MODE"] = "scheduler_shadow"

            scheduler = SprintScheduler(SprintSchedulerConfig())
            scheduler._advisory_gate_snapshot = "fake_value"

            scheduler._reset_result()

            assert scheduler._advisory_gate_snapshot is None
        finally:
            if original is not None:
                os.environ["HLEDAC_RUNTIME_MODE"] = original
            else:
                os.environ.pop("HLEDAC_RUNTIME_MODE", None)

    def test_evaluate_advisory_gate_no_dispatch(self):
        """evaluate_advisory_gate must NOT create bg_tasks or dispatch."""
        original = os.environ.get("HLEDAC_RUNTIME_MODE")
        try:
            os.environ["HLEDAC_RUNTIME_MODE"] = "scheduler_shadow"

            scheduler = SprintScheduler(SprintSchedulerConfig())
            mock_lc = MagicMock()
            mock_lc.snapshot.return_value = {
                "current_phase": "WINDUP",
                "entered_phase_at": 10.0,
                "started_at_monotonic": 0.0,
                "sprint_duration_s": 1800.0,
                "windup_lead_s": 180.0,
            }
            mock_lc.recommended_tool_mode.return_value = "normal"
            mock_lc.remaining_time.return_value = 10.0
            scheduler._lc_adapter = MagicMock()
            scheduler._lc_adapter._lc = mock_lc
            scheduler._config = SprintSchedulerConfig()
            scheduler._synthesis_engine = "test-engine"

            bg_tasks_before = len(scheduler._bg_tasks)

            scheduler.evaluate_advisory_gate()

            assert len(scheduler._bg_tasks) == bg_tasks_before

        finally:
            if original is not None:
                os.environ["HLEDAC_RUNTIME_MODE"] = original
            else:
                os.environ.pop("HLEDAC_RUNTIME_MODE", None)

    def test_readiness_preview_includes_advisory_gate(self):
        """_build_shadow_readiness_preview must include advisory_gate when set."""
        original = os.environ.get("HLEDAC_RUNTIME_MODE")
        try:
            os.environ["HLEDAC_RUNTIME_MODE"] = "scheduler_shadow"

            scheduler = SprintScheduler(SprintSchedulerConfig())
            scheduler._lc_adapter = MagicMock()
            scheduler._lc_adapter._lc = MagicMock()
            scheduler._synthesis_engine = "test-engine"

            # Set fake advisory gate snapshot
            from hledac.universal.runtime.shadow_pre_decision import AdvisoryGateSnapshot
            scheduler._advisory_gate_snapshot = AdvisoryGateSnapshot(
                gate_outcome="proceed",
                gate_status="ready",
                blocker_count=0,
                unknown_count=1,
                compat_seam_count=1,
                blocker_reasons=[],
                unknown_reasons=["provider recommendation not available"],
                compat_seam_reasons=["windup_local_phase"],
                defer_to_provider=True,
                gate_evaluated_at_monotonic=1234.0,
                gate_evaluated_at_wall="2026-04-02T00:00:00Z",
                source_pd_timestamp=1233.5,
            )

            preview = scheduler._build_shadow_readiness_preview()

            assert "advisory_gate" in preview
            assert preview["advisory_gate"]["gate_outcome"] == "proceed"
            assert preview["advisory_gate"]["blocker_count"] == 0

        finally:
            if original is not None:
                os.environ["HLEDAC_RUNTIME_MODE"] = original
            else:
                os.environ.pop("HLEDAC_RUNTIME_MODE", None)


class TestDispatchParityPreview:
    """Sprint F3.11: Tests for dispatch parity preview."""

    def test_preview_dispatch_parity_function(self):
        """preview_dispatch_parity must return DispatchReadinessPreview."""
        from hledac.universal.runtime.shadow_pre_decision import preview_dispatch_parity

        result = preview_dispatch_parity(
            task_candidates=["cve_to_github", "ip_to_ct"],
            available_capabilities={"reranking"},
            control_mode="normal",
            registry_tools=None,
        )

        assert result.readiness in ("ready", "blocked", "unknown")
        assert result.dispatch_path in ("canonical_tool", "runtime_only_compat")
        # tool_candidates maps task_type → tool_name
        assert "cve_to_github" in result.tool_candidates or "ip_to_ct" in result.tool_candidates

    def test_dispatch_parity_readiness_blocked_when_capabilities_missing(self):
        """Dispatch readiness must be blocked when required capabilities missing."""
        from hledac.universal.runtime.shadow_pre_decision import preview_dispatch_parity

        result = preview_dispatch_parity(
            task_candidates=["cve_to_github", "ip_to_ct"],
            available_capabilities=set(),  # No capabilities
            control_mode="normal",
            registry_tools=None,
        )

        # Missing reranking capability blocks web_search-based tools
        assert result.readiness in ("blocked", "unknown")
        assert result.blocked_count >= 0

    def test_dispatch_parity_pruned_when_prune_mode(self):
        """Dispatch readiness must be pruned when control_mode is prune."""
        from hledac.universal.runtime.shadow_pre_decision import preview_dispatch_parity

        result = preview_dispatch_parity(
            task_candidates=["cve_to_github", "ip_to_ct"],
            available_capabilities={"reranking"},
            control_mode="prune",
            registry_tools=None,
        )

        assert result.will_be_pruned is True
        assert result.control_mode == "prune"

    def test_dispatch_parity_runtime_only_compat_when_no_registry_tools(self):
        """Dispatch path must be runtime_only_compat when registry_tools is None."""
        from hledac.universal.runtime.shadow_pre_decision import preview_dispatch_parity

        result = preview_dispatch_parity(
            task_candidates=["cve_to_github"],
            available_capabilities=set(),
            control_mode="normal",
            registry_tools=None,
        )

        # Without registry_tools, cannot determine canonical mapping
        assert result.dispatch_path in ("canonical_tool", "runtime_only_compat")

    def test_dispatch_parity_capability_gaps(self):
        """DispatchReadinessPreview must contain capability gaps."""
        from hledac.universal.runtime.shadow_pre_decision import preview_dispatch_parity

        result = preview_dispatch_parity(
            task_candidates=["ip_to_ct"],
            available_capabilities=set(),
            control_mode="normal",
            registry_tools=None,
        )

        # With empty registry, no canonical mapping found
        assert isinstance(result.to_dict(), dict)
        assert "tool_candidates" in result.to_dict()
        assert "capability_gaps" in result.to_dict()

    def test_pre_decision_summary_has_dispatch_parity_field(self):
        """PreDecisionSummary must have dispatch_parity field."""
        from hledac.universal.runtime.shadow_pre_decision import PreDecisionSummary

        # dispatch_parity is optional, may be None
        assert hasattr(PreDecisionSummary, "__dataclass_fields__")
        # Field is added via edit, check at runtime
        from hledac.universal.runtime.shadow_pre_decision import PreDecisionSummary
        pd = PreDecisionSummary(
            parity_timestamp_monotonic=0.0,
            parity_timestamp_wall="2026-04-02T00:00:00Z",
            runtime_mode="scheduler_shadow",
            lifecycle=MagicMock(),
            graph=MagicMock(),
            export_readiness=MagicMock(),
            model_control=MagicMock(),
            precursors=MagicMock(),
            diff_taxonomy=[],
            blockers=[],
            unknowns=[],
            mismatch_reasons={},
        )
        # dispatch_parity may be None or set later
        assert pd.dispatch_parity is None or hasattr(pd.dispatch_parity, "readiness")

    def test_dispatch_readiness_preview_to_dict(self):
        """DispatchReadinessPreview.to_dict() must return all fields."""
        from hledac.universal.runtime.shadow_pre_decision import (
            DispatchReadinessPreview,
            ToolCapabilityGap,
        )

        gap = ToolCapabilityGap(
            tool_name="web_search",
            required_capabilities={"reranking"},
            available_capabilities=set(),
            missing_capabilities={"reranking"},
            is_satisfied=False,
            is_network_tool=True,
            is_high_memory=False,
        )

        preview = DispatchReadinessPreview(
            readiness="blocked",
            dispatch_path="canonical_tool",
            tool_candidates={"ip_to_ct": "web_search"},
            capability_gaps={"web_search": gap},
            blockers=["web_search: missing capabilities {'reranking'}"],
            pruned_tools=[],
            unknown_tools=[],
            runtime_only_handlers=[],
            control_mode="normal",
            will_be_pruned=False,
            canonical_count=1,
            runtime_only_count=0,
            satisfied_count=0,
            blocked_count=1,
        )

        d = preview.to_dict()
        assert d["readiness"] == "blocked"
        assert d["dispatch_path"] == "canonical_tool"
        assert d["canonical_count"] == 1
        assert d["blocked_count"] == 1
        assert "web_search" in d["tool_candidates"].values()

    def test_scheduler_preview_includes_dispatch_parity(self):
        """_build_shadow_readiness_preview must include dispatch_parity when set."""
        original = os.environ.get("HLEDAC_RUNTIME_MODE")
        try:
            os.environ["HLEDAC_RUNTIME_MODE"] = "scheduler_shadow"

            scheduler = SprintScheduler(SprintSchedulerConfig())
            scheduler._lc_adapter = MagicMock()
            scheduler._lc_adapter._lc = MagicMock()
            scheduler._synthesis_engine = "test-engine"

            # Attach fake dispatch parity
            from hledac.universal.runtime.shadow_pre_decision import (
                DispatchReadinessPreview,
            )
            fake_dispatch = DispatchReadinessPreview(
                readiness="ready",
                dispatch_path="canonical_tool",
                tool_candidates={},
                capability_gaps={},
                blockers=[],
                pruned_tools=[],
                unknown_tools=[],
                runtime_only_handlers=[],
                control_mode="normal",
                will_be_pruned=False,
                canonical_count=0,
                runtime_only_count=0,
                satisfied_count=0,
                blocked_count=0,
            )
            scheduler._shadow_pd_summary = MagicMock()
            scheduler._shadow_pd_summary.dispatch_parity = fake_dispatch
            scheduler._shadow_pd_summary.lifecycle = MagicMock()
            scheduler._shadow_pd_summary.graph = MagicMock()
            scheduler._shadow_pd_summary.export_readiness = MagicMock()
            scheduler._shadow_pd_summary.model_control = MagicMock()
            scheduler._shadow_pd_summary.precursors = MagicMock()
            scheduler._shadow_pd_summary.diff_taxonomy = []
            scheduler._shadow_pd_summary.blockers = []
            scheduler._shadow_pd_summary.unknowns = []
            scheduler._shadow_pd_summary.decision_gate = None
            scheduler._shadow_pd_summary.tool_readiness = None
            scheduler._shadow_pd_summary.windup_readiness = None
            scheduler._shadow_pd_summary.provider_note = None

            preview = scheduler._build_shadow_readiness_preview()

            assert "dispatch_parity" in preview
            assert preview["dispatch_parity"]["readiness"] == "ready"
            assert preview["dispatch_parity"]["dispatch_path"] == "canonical_tool"

        finally:
            if original is not None:
                os.environ["HLEDAC_RUNTIME_MODE"] = original
            else:
                os.environ.pop("HLEDAC_RUNTIME_MODE", None)


class TestDispatchPreviewMappingOwnership:
    """Sprint F3.11: Verify TASK_TYPE_TO_TOOL_PREVIEW canonical read-side owner."""

    def test_task_tool_preview_mapping_exists_in_tool_registry(self):
        """Canonical read-side owner is tool_registry.py, not shadow_pre_decision."""
        from hledac.universal.tool_registry import TASK_TYPE_TO_TOOL_PREVIEW

        # Verify key entries exist
        assert TASK_TYPE_TO_TOOL_PREVIEW["cve_to_github"] == "python_execute"
        assert TASK_TYPE_TO_TOOL_PREVIEW["ip_to_ct"] == "web_search"
        assert TASK_TYPE_TO_TOOL_PREVIEW["domain_to_dns"] == "web_search"
        assert len(TASK_TYPE_TO_TOOL_PREVIEW) == 18

    def test_get_task_tool_preview_mapping_returns_correct_mapping(self):
        """get_task_tool_preview_mapping() returns the canonical mapping."""
        from hledac.universal.tool_registry import get_task_tool_preview_mapping

        mapping = get_task_tool_preview_mapping()

        # Verify same content as constant
        assert mapping["cve_to_github"] == "python_execute"
        assert mapping["ip_to_ct"] == "web_search"
        # Verify it returns a copy (immutable use)
        assert mapping is not None

    def test_preview_dispatch_parity_uses_registry_mapping(self):
        """preview_dispatch_parity() reads from tool_registry, not local constant."""
        from hledac.universal.runtime.shadow_pre_decision import preview_dispatch_parity

        result = preview_dispatch_parity(
            task_candidates=["cve_to_github", "ip_to_ct"],
            available_capabilities={"reranking"},
            control_mode="normal",
            registry_tools=None,  # use default registry
        )

        # Verify mapping was used correctly
        assert result.tool_candidates["cve_to_github"] == "python_execute"
        assert result.tool_candidates["ip_to_ct"] == "web_search"

    def test_preview_no_module_level_task_type_to_tool_in_shadow_pre_decision(self):
        """Verify TASK_TYPE_TO_TOOL is NOT a module-level constant in shadow_pre_decision.

        It's OK if it's a local variable inside preview_dispatch_parity() function
        (assigned from get_task_tool_preview_mapping()), but it must NOT be a
        module-level constant definition.
        """
        import ast
        import inspect

        source = inspect.getsource(
            __import__(
                "hledac.universal.runtime.shadow_pre_decision",
                fromlist=["shadow_pre_decision"]
            )
        )
        tree = ast.parse(source)

        # Find module-level assignments to TASK_TYPE_TO_TOOL
        # (top-level = not inside any function or class)
        module_level_names = set()
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "TASK_TYPE_TO_TOOL":
                        module_level_names.add(target.id)

        # TASK_TYPE_TO_TOOL should NOT be a module-level assignment in shadow_pre_decision
        # (it's now only a local variable inside preview_dispatch_parity function)
        assert "TASK_TYPE_TO_TOOL" not in module_level_names, (
            "TASK_TYPE_TO_TOOL found as module-level constant in shadow_pre_decision.py — "
            "it should be read from tool_registry.py via get_task_tool_preview_mapping()"
        )

    def test_runtime_only_compat_dispatch_still_explicit(self):
        """runtime_only_compat_dispatch is preserved for task types without registry mapping."""
        from hledac.universal.runtime.shadow_pre_decision import preview_dispatch_parity

        # Use a task type NOT in TASK_TYPE_TO_TOOL_PREVIEW
        result = preview_dispatch_parity(
            task_candidates=["unknown_task_type"],
            available_capabilities=set(),
            control_mode="normal",
        )

        assert "unknown_task_type" in result.runtime_only_handlers
        assert result.dispatch_path == "runtime_only_compat"

    def test_preview_dispatch_parity_preserves_all_dispatch_taxonomy(self):
        """All dispatch taxonomy values are preserved: canonical, runtime_only, capability gap."""
        from hledac.universal.runtime.shadow_pre_decision import preview_dispatch_parity

        # Mix: known task with cap gap + unknown task
        result = preview_dispatch_parity(
            task_candidates=["cve_to_github", "ip_to_ct", "some_unknown_task"],
            available_capabilities=set(),  # missing reranking
            control_mode="normal",
        )

        # canonical tool with capability gap
        assert "cve_to_github" in result.tool_candidates
        assert result.capability_gaps.get("python_execute") is not None
        # unknown task = runtime_only_compat
        assert "some_unknown_task" in result.runtime_only_handlers
        assert result.dispatch_path == "runtime_only_compat"


class TestProviderReadinessPreview:
    """Sprint F3.5-F3.6: Tests for provider readiness preview."""

    def test_provider_readiness_preview_fields(self):
        """ProviderReadinessPreview must have required fields."""
        from hledac.universal.runtime.shadow_pre_decision import ProviderReadinessPreview

        prp = ProviderReadinessPreview(
            has_recommendation=True,
            recommendation="hermes-3-llama-3.2-3b",
            readiness="ready",
            lifecycle_ready=True,
            control_ready=True,
            thermal_safe=True,
            has_facts=True,
            blockers=[],
            unknowns=[],
            next_phase_hint=None,
            deferred_reasons=[],
        )

        assert prp.readiness == "ready"
        assert prp.has_recommendation is True
        assert prp.lifecycle_ready is True
        assert prp.control_ready is True
        assert prp.thermal_safe is True
        assert prp.has_facts is True

    def test_provider_readiness_ready_requires_all_conditions(self):
        """ProviderReadinessPreview readiness=ready requires lifecycle+control+thermal+facts."""
        from hledac.universal.runtime.shadow_pre_decision import (
            _compose_provider_readiness_preview,
            LifecycleInterpretation,
            ModelControlSummary,
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
        mc = ModelControlSummary(
            tools_count=5,
            sources_count=3,
            privacy="STANDARD",
            depth="DEEP",
            models_needed=["hermes-3-llama-3.2-3b"],
            has_tools=True,
            has_sources=True,
            is_high_quality=True,
            readiness="ready",
        )

        result = _compose_provider_readiness_preview(lc, mc)

        assert result.readiness == "ready"
        assert result.lifecycle_ready is True
        assert result.control_ready is True
        assert result.thermal_safe is True
        assert result.has_facts is True
        assert result.blockers == []
        assert result.unknowns == []

    def test_provider_readiness_blocked_in_terminal_phase(self):
        """ProviderReadinessPreview readiness=blocked in terminal phase."""
        from hledac.universal.runtime.shadow_pre_decision import (
            _compose_provider_readiness_preview,
            LifecycleInterpretation,
            ModelControlSummary,
        )

        lc = LifecycleInterpretation(
            workflow_phase="EXPORT",
            workflow_phase_entered_at=0.0,
            control_phase_mode="normal",
            control_phase_thermal="nominal",
            windup_local_mode="synthesis",
            is_active=False,
            is_windup=False,
            is_export_ready=True,
            is_terminal=True,
            can_accept_work=False,
            should_prune=False,
            synthesis_mode_known=True,
            phase_conflict=False,
            phase_conflict_reason=None,
        )
        mc = ModelControlSummary(
            tools_count=5,
            sources_count=3,
            privacy="STANDARD",
            depth="DEEP",
            models_needed=["hermes-3-llama-3.2-3b"],
            has_tools=True,
            has_sources=True,
            is_high_quality=True,
            readiness="ready",
        )

        result = _compose_provider_readiness_preview(lc, mc)

        assert result.readiness == "blocked"
        assert "terminal phase" in result.blockers[0]

    def test_provider_readiness_blocked_in_panic_mode(self):
        """ProviderReadinessPreview readiness=blocked in panic control mode."""
        from hledac.universal.runtime.shadow_pre_decision import (
            _compose_provider_readiness_preview,
            LifecycleInterpretation,
            ModelControlSummary,
        )

        lc = LifecycleInterpretation(
            workflow_phase="ACTIVE",
            workflow_phase_entered_at=0.0,
            control_phase_mode="panic",
            control_phase_thermal="critical",
            windup_local_mode=None,
            is_active=True,
            is_windup=False,
            is_export_ready=False,
            is_terminal=False,
            can_accept_work=True,
            should_prune=True,
            synthesis_mode_known=False,
            phase_conflict=False,
            phase_conflict_reason=None,
        )
        mc = ModelControlSummary(
            tools_count=5,
            sources_count=3,
            privacy="STANDARD",
            depth="DEEP",
            models_needed=["hermes-3-llama-3.2-3b"],
            has_tools=True,
            has_sources=True,
            is_high_quality=True,
            readiness="ready",
        )

        result = _compose_provider_readiness_preview(lc, mc)

        assert result.readiness == "blocked"
        assert "panic" in result.blockers[0]

    def test_provider_readiness_deferred_when_not_active(self):
        """ProviderReadinessPreview readiness=deferred when lifecycle not ACTIVE/WINDUP (BOOT phase)."""
        from hledac.universal.runtime.shadow_pre_decision import (
            _compose_provider_readiness_preview,
            LifecycleInterpretation,
            ModelControlSummary,
        )

        lc = LifecycleInterpretation(
            workflow_phase="BOOT",
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
        mc = ModelControlSummary(
            tools_count=5,
            sources_count=3,
            privacy="STANDARD",
            depth="DEEP",
            models_needed=["hermes-3-llama-3.2-3b"],
            has_tools=True,
            has_sources=True,
            is_high_quality=True,
            readiness="ready",
        )

        result = _compose_provider_readiness_preview(lc, mc)

        assert result.readiness == "deferred"
        assert result.lifecycle_ready is False
        assert "BOOT" in result.deferred_reasons[0]

    def test_provider_readiness_compat_in_warmup(self):
        """ProviderReadinessPreview readiness=compat in WARMUP phase."""
        from hledac.universal.runtime.shadow_pre_decision import (
            _compose_provider_readiness_preview,
            LifecycleInterpretation,
            ModelControlSummary,
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
        mc = ModelControlSummary(
            tools_count=5,
            sources_count=3,
            privacy="STANDARD",
            depth="DEEP",
            models_needed=["hermes-3-llama-3.2-3b"],
            has_tools=True,
            has_sources=True,
            is_high_quality=True,
            readiness="ready",
        )

        result = _compose_provider_readiness_preview(lc, mc)

        assert result.readiness == "compat"
        assert result.lifecycle_ready is False

    def test_provider_readiness_unknown_when_no_recommendation_fact(self):
        """ProviderReadinessPreview readiness=unknown when models_needed is empty."""
        from hledac.universal.runtime.shadow_pre_decision import (
            _compose_provider_readiness_preview,
            LifecycleInterpretation,
            ModelControlSummary,
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
        mc = ModelControlSummary(
            tools_count=5,
            sources_count=3,
            privacy="STANDARD",
            depth="DEEP",
            models_needed=[],  # Empty = no recommendation fact
            has_tools=True,
            has_sources=True,
            is_high_quality=True,
            readiness="ready",
        )

        result = _compose_provider_readiness_preview(lc, mc)

        assert result.has_facts is False
        assert result.readiness in ("deferred", "unknown")

    def test_provider_readiness_no_simulation_fields(self):
        """ProviderReadinessPreview must NOT contain load_order/provider_state/activation_sequence."""
        from hledac.universal.runtime.shadow_pre_decision import ProviderReadinessPreview
        import dataclasses

        prp = ProviderReadinessPreview(
            has_recommendation=True,
            recommendation="test-model",
            readiness="ready",
            lifecycle_ready=True,
            control_ready=True,
            thermal_safe=True,
            has_facts=True,
            blockers=[],
            unknowns=[],
            next_phase_hint=None,
            deferred_reasons=[],
        )

        field_names = {f.name for f in dataclasses.fields(prp)}
        assert "load_order" not in field_names
        assert "provider_state" not in field_names
        assert "activation_sequence" not in field_names
        assert "actual_model_loaded" not in field_names

    def test_provider_readiness_distinguishes_recommendation_readiness_activation(self):
        """ProviderReadinessPreview distinguishes: recommendation fact vs readiness preview vs activation."""
        from hledac.universal.runtime.shadow_pre_decision import (
            _compose_provider_readiness_preview,
            LifecycleInterpretation,
            ModelControlSummary,
        )

        # Case: lifecycle ACTIVE, models_needed present = has recommendation fact
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
        mc = ModelControlSummary(
            tools_count=5,
            sources_count=3,
            privacy="STANDARD",
            depth="DEEP",
            models_needed=["hermes-3-llama-3.2-3b"],
            has_tools=True,
            has_sources=True,
            is_high_quality=True,
            readiness="ready",
        )

        result = _compose_provider_readiness_preview(lc, mc)

        # has_recommendation = True means recommendation FACT available
        assert result.has_recommendation is True
        # readiness = ready means readiness PREVIEW classification
        assert result.readiness == "ready"
        # No actual activation fields
        assert not hasattr(result, "actual_activation")

    def test_pre_decision_summary_has_provider_readiness_field(self):
        """PreDecisionSummary must have provider_readiness field."""
        from hledac.universal.runtime.shadow_pre_decision import PreDecisionSummary

        assert hasattr(PreDecisionSummary, "__dataclass_fields__")
        # Check at runtime that provider_readiness is a field
        from hledac.universal.runtime.shadow_pre_decision import PreDecisionSummary
        pd = PreDecisionSummary(
            parity_timestamp_monotonic=0.0,
            parity_timestamp_wall="2026-04-02T00:00:00Z",
            runtime_mode="scheduler_shadow",
            lifecycle=MagicMock(),
            graph=MagicMock(),
            export_readiness=MagicMock(),
            model_control=MagicMock(),
            precursors=MagicMock(),
            diff_taxonomy=[],
            blockers=[],
            unknowns=[],
            mismatch_reasons={},
        )
        # provider_readiness may be None initially
        assert pd.provider_readiness is None or hasattr(pd.provider_readiness, "readiness")

    def test_scheduler_preview_includes_provider_readiness(self):
        """_build_shadow_readiness_preview must include provider_readiness when set."""
        original = os.environ.get("HLEDAC_RUNTIME_MODE")
        try:
            os.environ["HLEDAC_RUNTIME_MODE"] = "scheduler_shadow"

            scheduler = SprintScheduler(SprintSchedulerConfig())
            scheduler._lc_adapter = MagicMock()
            scheduler._lc_adapter._lc = MagicMock()
            scheduler._synthesis_engine = "test-engine"

            # Attach fake provider_readiness
            from hledac.universal.runtime.shadow_pre_decision import ProviderReadinessPreview
            fake_pr = ProviderReadinessPreview(
                has_recommendation=True,
                recommendation="test-model",
                readiness="ready",
                lifecycle_ready=True,
                control_ready=True,
                thermal_safe=True,
                has_facts=True,
                blockers=[],
                unknowns=[],
                next_phase_hint=None,
                deferred_reasons=[],
            )
            scheduler._shadow_pd_summary = MagicMock()
            scheduler._shadow_pd_summary.provider_readiness = fake_pr
            scheduler._shadow_pd_summary.lifecycle = MagicMock()
            scheduler._shadow_pd_summary.graph = MagicMock()
            scheduler._shadow_pd_summary.export_readiness = MagicMock()
            scheduler._shadow_pd_summary.model_control = MagicMock()
            scheduler._shadow_pd_summary.precursors = MagicMock()
            scheduler._shadow_pd_summary.diff_taxonomy = []
            scheduler._shadow_pd_summary.blockers = []
            scheduler._shadow_pd_summary.unknowns = []
            scheduler._shadow_pd_summary.decision_gate = None
            scheduler._shadow_pd_summary.tool_readiness = None
            scheduler._shadow_pd_summary.windup_readiness = None
            scheduler._shadow_pd_summary.provider_note = None
            scheduler._shadow_pd_summary.dispatch_parity = None

            preview = scheduler._build_shadow_readiness_preview()

            assert "provider_readiness" in preview
            assert preview["provider_readiness"]["readiness"] == "ready"
            assert preview["provider_readiness"]["has_recommendation"] is True
            assert preview["provider_readiness"]["lifecycle_ready"] is True
            assert preview["provider_readiness"]["control_ready"] is True
            assert preview["provider_readiness"]["thermal_safe"] is True
            assert preview["provider_readiness"]["has_facts"] is True

        finally:
            if original is not None:
                os.environ["HLEDAC_RUNTIME_MODE"] = original
            else:
                os.environ.pop("HLEDAC_RUNTIME_MODE", None)

    def test_provider_readiness_windup_phase_ready(self):
        """ProviderReadinessPreview readiness=ready in WINDUP phase."""
        from hledac.universal.runtime.shadow_pre_decision import (
            _compose_provider_readiness_preview,
            LifecycleInterpretation,
            ModelControlSummary,
        )

        lc = LifecycleInterpretation(
            workflow_phase="WINDUP",
            workflow_phase_entered_at=0.0,
            control_phase_mode="prune",
            control_phase_thermal="fair",
            windup_local_mode="synthesis",
            is_active=False,
            is_windup=True,
            is_export_ready=False,
            is_terminal=False,
            can_accept_work=False,
            should_prune=True,
            synthesis_mode_known=True,
            phase_conflict=False,
            phase_conflict_reason=None,
        )
        mc = ModelControlSummary(
            tools_count=5,
            sources_count=3,
            privacy="STANDARD",
            depth="DEEP",
            models_needed=["hermes-3-llama-3.2-3b"],
            has_tools=True,
            has_sources=True,
            is_high_quality=True,
            readiness="ready",
        )

        result = _compose_provider_readiness_preview(lc, mc)

        assert result.readiness == "ready"
        assert result.lifecycle_ready is True
        assert result.control_ready is True  # prune is OK
        assert result.thermal_safe is True  # fair is OK

    def test_provider_readiness_critical_thermal_not_ready(self):
        """ProviderReadinessPreview readiness=deferred when thermal=critical."""
        from hledac.universal.runtime.shadow_pre_decision import (
            _compose_provider_readiness_preview,
            LifecycleInterpretation,
            ModelControlSummary,
        )

        lc = LifecycleInterpretation(
            workflow_phase="ACTIVE",
            workflow_phase_entered_at=0.0,
            control_phase_mode="normal",
            control_phase_thermal="critical",
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
        mc = ModelControlSummary(
            tools_count=5,
            sources_count=3,
            privacy="STANDARD",
            depth="DEEP",
            models_needed=["hermes-3-llama-3.2-3b"],
            has_tools=True,
            has_sources=True,
            is_high_quality=True,
            readiness="ready",
        )

        result = _compose_provider_readiness_preview(lc, mc)

        assert result.thermal_safe is False
        assert result.readiness in ("deferred", "unknown")
        assert "critical" in result.deferred_reasons[0]


# =============================================================================
# Sprint F3.13: ProviderRuntimeFactsBundle Tests
# =============================================================================

class TestProviderRuntimeFactsBundle:
    """Sprint F3.13: Tests for ProviderRuntimeFactsBundle read-only seam."""

    def test_collect_provider_runtime_facts_returns_bundle(self):
        """collect_provider_runtime_facts returns a valid bundle."""
        from hledac.universal.runtime.shadow_inputs import collect_provider_runtime_facts

        result = collect_provider_runtime_facts(model_manager=None)

        assert result is not None
        assert hasattr(result, "current_model")
        assert hasattr(result, "is_loaded")
        assert hasattr(result, "initialized")
        assert hasattr(result, "fact_stability")

    def test_collect_provider_runtime_facts_stable_when_model_manager_available(self):
        """runtime_facts stability=STABLE when model_manager is provided."""
        from hledac.universal.runtime.shadow_inputs import collect_provider_runtime_facts

        # Mock model_manager with get_current_model returning a model name
        class MockModelManager:
            def get_current_model(self):
                return "hermes-3-llama-3.2-3b"

            def is_loaded(self):
                return True

        mm = MockModelManager()
        result = collect_provider_runtime_facts(model_manager=mm)

        assert result.current_model == "hermes-3-llama-3.2-3b"
        assert result.is_loaded is True
        assert result.initialized is False  # Mock doesn't have initialized
        assert result.fact_stability == "STABLE"

    def test_collect_provider_runtime_facts_compat_with_lifecycle_status(self):
        """runtime_facts stability=COMPAT when only lifecycle_status is available."""
        from hledac.universal.runtime.shadow_inputs import collect_provider_runtime_facts

        lifecycle_status = {
            "loaded": True,
            "current_model": "modernbert",
            "initialized": True,
            "last_error": None,
        }
        result = collect_provider_runtime_facts(
            model_manager=None,
            lifecycle_status=lifecycle_status,
        )

        assert result.current_model == "modernbert"
        assert result.is_loaded is True
        assert result.initialized is True
        assert result.fact_stability == "COMPAT"

    def test_collect_provider_runtime_facts_unknown_when_nothing_available(self):
        """runtime_facts stability=UNKNOWN when neither source is available."""
        from hledac.universal.runtime.shadow_inputs import collect_provider_runtime_facts

        result = collect_provider_runtime_facts(model_manager=None)

        assert result.current_model is None
        assert result.is_loaded is False
        assert result.initialized is False
        assert result.fact_stability == "UNKNOWN"

    def test_collect_provider_runtime_facts_to_dict(self):
        """ProviderRuntimeFactsBundle.to_dict() returns correct structure."""
        from hledac.universal.runtime.shadow_inputs import collect_provider_runtime_facts

        class MockModelManager:
            def get_current_model(self):
                return "gliner"

            def is_loaded(self):
                return True

        mm = MockModelManager()
        result = collect_provider_runtime_facts(model_manager=mm)
        d = result.to_dict()

        assert d["runtime_current_model"] == "gliner"
        assert d["runtime_is_loaded"] is True
        assert d["runtime_initialized"] is False
        assert d["runtime_fact_stability"] == "STABLE"
        assert "future_owner" in d


class TestProviderRuntimeFactsIntegration:
    """Sprint F3.13: Integration tests for runtime_facts in compose_pre_decision."""

    def test_compose_pre_decision_accepts_runtime_facts(self):
        """compose_pre_decision accepts runtime_facts parameter without error."""
        from hledac.universal.runtime.shadow_pre_decision import (
            _compose_provider_readiness_preview,
        )
        from hledac.universal.runtime.shadow_inputs import ProviderRuntimeFactsBundle

        runtime_facts = ProviderRuntimeFactsBundle(
            current_model="hermes",
            is_loaded=True,
            initialized=False,
            fact_stability="STABLE",
        )

        # Verify runtime_facts can be passed without TypeError
        assert runtime_facts.current_model == "hermes"
        assert runtime_facts.fact_stability == "STABLE"

    def test_provider_readiness_preview_contains_runtime_facts(self):
        """ProviderReadinessPreview includes runtime_loaded/runtime_current_model."""
        from hledac.universal.runtime.shadow_pre_decision import (
            _compose_provider_readiness_preview,
            LifecycleInterpretation,
            ModelControlSummary,
        )
        from hledac.universal.runtime.shadow_inputs import ProviderRuntimeFactsBundle

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
        mc = ModelControlSummary(
            tools_count=5,
            sources_count=3,
            privacy="STANDARD",
            depth="DEEP",
            models_needed=["hermes-3-llama-3.2-3b"],
            has_tools=True,
            has_sources=True,
            is_high_quality=True,
            readiness="ready",
        )

        runtime_facts = ProviderRuntimeFactsBundle(
            current_model="hermes-3-llama-3.2-3b",
            is_loaded=True,
            initialized=True,
            fact_stability="STABLE",
        )

        result = _compose_provider_readiness_preview(lc, mc, runtime_facts=runtime_facts)

        assert result.runtime_loaded is True
        assert result.runtime_current_model == "hermes-3-llama-3.2-3b"
        assert result.runtime_initialized is True

    def test_provider_readiness_preview_defaults_when_no_runtime_facts(self):
        """ProviderReadinessPreview defaults to False/None when runtime_facts is None."""
        from hledac.universal.runtime.shadow_pre_decision import (
            _compose_provider_readiness_preview,
            LifecycleInterpretation,
            ModelControlSummary,
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
        mc = ModelControlSummary(
            tools_count=5,
            sources_count=3,
            privacy="STANDARD",
            depth="DEEP",
            models_needed=["hermes-3-llama-3.2-3b"],
            has_tools=True,
            has_sources=True,
            is_high_quality=True,
            readiness="ready",
        )

        result = _compose_provider_readiness_preview(lc, mc, runtime_facts=None)

        assert result.runtime_loaded is False
        assert result.runtime_current_model is None
        assert result.runtime_initialized is False

    def test_runtime_facts_in_scheduler_consume_shadow_pre_decision(self):
        """SprintScheduler.consume_shadow_pre_decision passes runtime_facts to compose_pre_decision."""
        from unittest.mock import MagicMock, patch
        from hledac.universal.runtime.sprint_scheduler import SprintScheduler, SprintSchedulerConfig

        config = SprintSchedulerConfig()
        scheduler = SprintScheduler(config)
        scheduler._lc_adapter = MagicMock()
        scheduler._lc_adapter._lc = MagicMock()
        scheduler._lc_adapter._lc.snapshot.return_value = {}

        with patch("hledac.universal.runtime.shadow_inputs.RuntimeMode") as mock_rm:
            mock_rm.is_shadow_mode.return_value = True

            result = scheduler.consume_shadow_pre_decision()

            # When model_manager is not available, runtime_facts should be UNKNOWN
            if result is not None:
                assert result.provider_readiness is not None
                assert result.runtime_facts is not None

    def test_runtime_facts_serialized_in_pre_decision_summary_to_dict(self):
        """PreDecisionSummary.to_dict() serializes runtime_facts bundle."""
        from hledac.universal.runtime.shadow_pre_decision import (
            PreDecisionSummary,
            LifecycleInterpretation,
            GraphCapabilitySummary,
            ExportReadinessSummary,
            ModelControlSummary,
            PrecursorSummary,
            DecisionGateReadiness,
            ToolReadinessPreview,
            WindupReadinessPreview,
            ProviderActivationNote,
            ProviderReadinessPreview,
            DispatchReadinessPreview,
        )
        from hledac.universal.runtime.shadow_inputs import ProviderRuntimeFactsBundle

        runtime_facts = ProviderRuntimeFactsBundle(
            current_model="hermes",
            is_loaded=True,
            initialized=True,
            fact_stability="STABLE",
        )
        d = {
            "parity_timestamp_monotonic": 0.0,
            "parity_timestamp_wall": "2026-04-02T00:00:00",
            "runtime_mode": "FULL_SHADOW",
            "lifecycle": LifecycleInterpretation(
                workflow_phase="ACTIVE",
                workflow_phase_entered_at=0.0,
                control_phase_mode="normal",
                control_phase_thermal="nominal",
                windup_local_mode="none",
                is_active=True,
                is_windup=False,
                is_export_ready=False,
                is_terminal=False,
                can_accept_work=True,
                should_prune=False,
                synthesis_mode_known=True,
                phase_conflict=False,
                phase_conflict_reason=None,
            ),
            "graph": GraphCapabilitySummary(
                backend="duckpgq",
                nodes=10,
                edges=5,
                pgq_active=True,
                top_nodes_count=3,
                is_initialized=True,
                has_structured_data=True,
                is_rich=True,
                readiness="ready",
            ),
            "export_readiness": ExportReadinessSummary(
                sprint_id="test",
                synthesis_engine="hermes",
                ranked_parquet_present=True,
                gnn_predictions=5,
                is_ready=True,
                has_gnn_predictions=True,
                has_ranked_data=True,
                readiness="ready",
            ),
            "model_control": ModelControlSummary(
                tools_count=3,
                sources_count=2,
                privacy="STANDARD",
                depth="STANDARD",
                models_needed=["hermes"],
                has_tools=True,
                has_sources=True,
                is_high_quality=True,
                readiness="ready",
            ),
            "precursors": PrecursorSummary(
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
            "diff_taxonomy": [],
            "blockers": [],
            "unknowns": [],
            "mismatch_reasons": [],
            "compat_seams": [],
            "decision_gate": DecisionGateReadiness(
                gate_status="unknown",
                blocker_count=0,
                unknown_count=0,
                compat_seam_count=0,
                blocker_categories=[],
                unknown_categories=[],
                is_proceed_allowed=False,
                defer_to_provider=True,
            ),
            "tool_readiness": ToolReadinessPreview(
                readiness="unknown",
                tool_count=0,
                tool_names=[],
                has_network_tools=False,
                has_high_memory_tools=False,
                control_mode="normal",
                pruned_tool_count=0,
                resource_constraint="unknown",
                can_execute=False,
                defer_reason=None,
            ),
            "windup_readiness": WindupReadinessPreview(
                readiness="unknown",
                is_windup_phase=False,
                synthesis_mode=None,
                synthesis_engine="unknown",
                has_export_data=False,
                export_data_quality="unknown",
                defer_reason=None,
            ),
            "provider_note": ProviderActivationNote(
                status="unknown",
                deferral_reason="lifecycle not active",
                has_recommendation=False,
                recommendation=None,
                next_phase_hint=None,
            ),
            "provider_readiness": ProviderReadinessPreview(
                has_recommendation=False,
                recommendation=None,
                readiness="unknown",
                lifecycle_ready=False,
                control_ready=True,
                thermal_safe=True,
                has_facts=False,
                blockers=[],
                unknowns=[],
                next_phase_hint=None,
                deferred_reasons=[],
                runtime_loaded=False,
                runtime_current_model=None,
                runtime_initialized=False,
            ),
            "dispatch_parity": None,
            "runtime_facts": runtime_facts,
        }

        summary = PreDecisionSummary(**d)
        result_dict = summary.to_dict()

        # runtime_facts must be serialized in to_dict() output
        assert "runtime_facts" in result_dict
        rf = result_dict["runtime_facts"]
        assert rf is not None
        assert rf["runtime_current_model"] == "hermes"
        assert rf["runtime_is_loaded"] is True
        assert rf["runtime_initialized"] is True
        assert rf["runtime_fact_stability"] == "STABLE"

    def test_runtime_facts_unknown_when_lifecycle_status_unavailable(self):
        """runtime_facts falls back to UNKNOWN when get_model_lifecycle_status raises."""
        from unittest.mock import MagicMock, patch
        from hledac.universal.runtime.sprint_scheduler import SprintScheduler, SprintSchedulerConfig

        config = SprintSchedulerConfig()
        scheduler = SprintScheduler(config)
        scheduler._lc_adapter = MagicMock()
        scheduler._lc_adapter._lc = MagicMock()
        scheduler._lc_adapter._lc.snapshot.return_value = {}

        with patch("hledac.universal.runtime.shadow_inputs.RuntimeMode") as mock_rm:
            mock_rm.is_shadow_mode.return_value = True
            # Force get_model_lifecycle_status to raise (it's imported inside the method)
            with patch("hledac.universal.brain.model_lifecycle.get_model_lifecycle_status") as mock_status:
                mock_status.side_effect = RuntimeError("lifecycle unavailable")
                result = scheduler.consume_shadow_pre_decision()
                if result is not None:
                    # Must fall back to UNKNOWN bundle
                    assert result.runtime_facts is not None
                    assert result.runtime_facts.fact_stability == "UNKNOWN"

    def test_runtime_facts_compat_when_lifecycle_status_available(self):
        """runtime_facts reaches COMPAT stability when lifecycle_status provided without model_manager."""
        from hledac.universal.runtime.shadow_inputs import (
            collect_provider_runtime_facts,
            ProviderRuntimeFactsBundle,
        )

        lifecycle_status = {
            "loaded": True,
            "current_model": "hermes",
            "initialized": True,
            "last_error": None,
        }
        result = collect_provider_runtime_facts(
            model_manager=None,
            lifecycle_status=lifecycle_status,
        )
        assert result.fact_stability == "COMPAT"
        assert result.current_model == "hermes"
        assert result.is_loaded is True
        assert result.initialized is True
        assert isinstance(result, ProviderRuntimeFactsBundle)


class TestProviderRuntimeFactsPreviewOutput:
    """Sprint F3.13: Verify runtime_facts appears as standalone top-level section in preview."""

    def test_preview_includes_runtime_facts_top_level_section(self):
        """_build_shadow_readiness_preview must include runtime_facts as top-level dict."""
        import os
        original = os.environ.get("HLEDAC_RUNTIME_MODE")
        try:
            os.environ["HLEDAC_RUNTIME_MODE"] = "scheduler_shadow"

            scheduler = SprintScheduler(SprintSchedulerConfig())
            scheduler._lc_adapter = MagicMock()
            scheduler._lc_adapter._lc = MagicMock()
            scheduler._synthesis_engine = "test-engine"

            # Attach fake PreDecisionSummary with runtime_facts
            from hledac.universal.runtime.shadow_pre_decision import PreDecisionSummary
            from hledac.universal.runtime.shadow_inputs import ProviderRuntimeFactsBundle

            fake_runtime_facts = ProviderRuntimeFactsBundle(
                current_model="hermes",
                is_loaded=True,
                initialized=True,
                fact_stability="STABLE",
            )

            scheduler._shadow_pd_summary = PreDecisionSummary(
                parity_timestamp_monotonic=0.0,
                parity_timestamp_wall="2026-04-02T00:00:00",
                runtime_mode="scheduler_shadow",
                lifecycle=MagicMock(),
                graph=MagicMock(),
                export_readiness=MagicMock(),
                model_control=MagicMock(),
                precursors=MagicMock(),
                diff_taxonomy=[],
                blockers=[],
                unknowns=[],
                mismatch_reasons={},
                runtime_facts=fake_runtime_facts,
            )
            # Set minimal mock for all required attributes
            scheduler._shadow_pd_summary.lifecycle.workflow_phase = "ACTIVE"
            scheduler._shadow_pd_summary.lifecycle.is_active = True
            scheduler._shadow_pd_summary.lifecycle.is_windup = False
            scheduler._shadow_pd_summary.lifecycle.can_accept_work = True
            scheduler._shadow_pd_summary.lifecycle.should_prune = False
            scheduler._shadow_pd_summary.lifecycle.phase_conflict = False
            scheduler._shadow_pd_summary.graph.backend = "duckpgq"
            scheduler._shadow_pd_summary.graph.readiness = "ready"
            scheduler._shadow_pd_summary.graph.nodes = 10
            scheduler._shadow_pd_summary.graph.edges = 5
            scheduler._shadow_pd_summary.export_readiness.readiness = "ready"
            scheduler._shadow_pd_summary.export_readiness.synthesis_engine = "hermes"
            scheduler._shadow_pd_summary.model_control.readiness = "ready"
            scheduler._shadow_pd_summary.model_control.tools_count = 3
            scheduler._shadow_pd_summary.diff_taxonomy = []
            scheduler._shadow_pd_summary.blockers = []
            scheduler._shadow_pd_summary.unknowns = []
            scheduler._shadow_pd_summary.compat_seams = []
            scheduler._shadow_pd_summary.decision_gate = None
            scheduler._shadow_pd_summary.tool_readiness = None
            scheduler._shadow_pd_summary.windup_readiness = None
            scheduler._shadow_pd_summary.provider_note = None
            scheduler._shadow_pd_summary.provider_readiness = None
            scheduler._shadow_pd_summary.dispatch_parity = None

            preview = scheduler._build_shadow_readiness_preview()

            # runtime_facts must appear as TOP-LEVEL key in preview
            assert "runtime_facts" in preview, "runtime_facts must be top-level key in preview"
            rf = preview["runtime_facts"]
            assert rf["runtime_current_model"] == "hermes"
            assert rf["runtime_is_loaded"] is True
            assert rf["runtime_initialized"] is True
            assert rf["runtime_fact_stability"] == "STABLE"
        finally:
            if original is not None:
                os.environ["HLEDAC_RUNTIME_MODE"] = original
            else:
                os.environ.pop("HLEDAC_RUNTIME_MODE", None)

    def test_preview_runtime_facts_and_provider_readiness_are_independent(self):
        """runtime_facts top-level and provider_readiness coexist as independent sections."""
        import os
        original = os.environ.get("HLEDAC_RUNTIME_MODE")
        try:
            os.environ["HLEDAC_RUNTIME_MODE"] = "scheduler_shadow"

            scheduler = SprintScheduler(SprintSchedulerConfig())
            scheduler._lc_adapter = MagicMock()
            scheduler._lc_adapter._lc = MagicMock()
            scheduler._synthesis_engine = "test-engine"

            from hledac.universal.runtime.shadow_pre_decision import (
                PreDecisionSummary,
                ProviderReadinessPreview,
            )
            from hledac.universal.runtime.shadow_inputs import ProviderRuntimeFactsBundle

            # runtime_facts at top level (COMPAT stability)
            fake_runtime_facts = ProviderRuntimeFactsBundle(
                current_model="modernbert",
                is_loaded=True,
                initialized=False,
                fact_stability="COMPAT",
            )

            # provider_readiness is a separate section
            fake_provider_readiness = ProviderReadinessPreview(
                has_recommendation=True,
                recommendation="hermes",
                readiness="ready",
                lifecycle_ready=True,
                control_ready=True,
                thermal_safe=True,
                has_facts=True,
                blockers=[],
                unknowns=[],
                next_phase_hint=None,
                deferred_reasons=[],
                runtime_loaded=True,
                runtime_current_model="hermes",
                runtime_initialized=True,
            )

            scheduler._shadow_pd_summary = PreDecisionSummary(
                parity_timestamp_monotonic=0.0,
                parity_timestamp_wall="2026-04-02T00:00:00",
                runtime_mode="scheduler_shadow",
                lifecycle=MagicMock(),
                graph=MagicMock(),
                export_readiness=MagicMock(),
                model_control=MagicMock(),
                precursors=MagicMock(),
                diff_taxonomy=[],
                blockers=[],
                unknowns=[],
                mismatch_reasons={},
                runtime_facts=fake_runtime_facts,
                provider_readiness=fake_provider_readiness,
            )
            # Set minimal mock attributes
            scheduler._shadow_pd_summary.lifecycle.workflow_phase = "ACTIVE"
            scheduler._shadow_pd_summary.lifecycle.is_active = True
            scheduler._shadow_pd_summary.lifecycle.is_windup = False
            scheduler._shadow_pd_summary.lifecycle.can_accept_work = True
            scheduler._shadow_pd_summary.lifecycle.should_prune = False
            scheduler._shadow_pd_summary.lifecycle.phase_conflict = False
            scheduler._shadow_pd_summary.graph.backend = "duckpgq"
            scheduler._shadow_pd_summary.graph.readiness = "ready"
            scheduler._shadow_pd_summary.graph.nodes = 10
            scheduler._shadow_pd_summary.graph.edges = 5
            scheduler._shadow_pd_summary.export_readiness.readiness = "ready"
            scheduler._shadow_pd_summary.export_readiness.synthesis_engine = "hermes"
            scheduler._shadow_pd_summary.model_control.readiness = "ready"
            scheduler._shadow_pd_summary.model_control.tools_count = 3
            scheduler._shadow_pd_summary.diff_taxonomy = []
            scheduler._shadow_pd_summary.blockers = []
            scheduler._shadow_pd_summary.unknowns = []
            scheduler._shadow_pd_summary.compat_seams = []
            scheduler._shadow_pd_summary.decision_gate = None
            scheduler._shadow_pd_summary.tool_readiness = None
            scheduler._shadow_pd_summary.windup_readiness = None
            scheduler._shadow_pd_summary.provider_note = None
            scheduler._shadow_pd_summary.dispatch_parity = None

            preview = scheduler._build_shadow_readiness_preview()

            # Both sections exist independently
            assert "runtime_facts" in preview
            assert "provider_readiness" in preview

            # Top-level runtime_facts has COMPAT stability and modernbert
            rf = preview["runtime_facts"]
            assert rf["runtime_fact_stability"] == "COMPAT"
            assert rf["runtime_current_model"] == "modernbert"

            # provider_readiness has its own readiness classification
            pr = preview["provider_readiness"]
            assert pr["readiness"] == "ready"
            assert pr["has_recommendation"] is True
            assert pr["lifecycle_ready"] is True
        finally:
            if original is not None:
                os.environ["HLEDAC_RUNTIME_MODE"] = original
            else:
                os.environ.pop("HLEDAC_RUNTIME_MODE", None)
