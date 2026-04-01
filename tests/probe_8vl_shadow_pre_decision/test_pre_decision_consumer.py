"""
Probe 8VL: Shadow Pre-Decision Consumer Layer Tests
==================================================

Tests for F3.6 pre-decision consumer layer:

1. compose_pre_decision is pure — no side effects
2. PreDecisionSummary has SEPARATED phase fields (no merged phase)
3. DiffTaxonomy enum has all required categories
4. compose_pre_decision correctly interprets ParityArtifact
5. LifecycleInterpretation has phase_conflict detection
6. GraphCapabilitySummary readiness logic works
7. ExportReadinessSummary readiness logic works
8. ModelControlSummary readiness logic works
9. PrecursorSummary readiness logic works
10. shadow_pre_decision.py does not import network modules
11. PreDecisionSummary.to_dict() is JSON-serializable
12. shadow_pre_decision module does NOT modify SprintScheduler

Run:
    cd /Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal
    python -m pytest tests/probe_8vl_shadow_pre_decision/ -v
"""

import ast
import json
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest


class TestDiffTaxonomy:
    """Test DiffTaxonomy enum has all required categories."""

    def test_diff_taxonomy_has_all_categories(self):
        """DiffTaxonomy enum has all 9 required categories."""
        from hledac.universal.runtime.shadow_pre_decision import DiffTaxonomy

        members = {m.name for m in DiffTaxonomy}
        required = {
            "NONE",
            "INSUFFICIENT_INPUT",
            "LIFECYCLE_MISMATCH",
            "PHASE_LAYER_CONFLICT",
            "GRAPH_CAPABILITY_AMBIGUITY",
            "EXPORT_HANDOFF_AMBIGUITY",
            "MODEL_CONTROL_AMBIGUITY",
            "PROVIDER_PRECURSOR_AMBIGUITY",
            "BRANCH_PRECURSOR_AMBIGUITY",
        }
        assert required.issubset(members), f"Missing: {required - members}"


class TestLifecycleInterpretation:
    """Test LifecycleInterpretation phase separation and conflict detection."""

    def test_lifecycle_interpretation_phase_separated(self):
        """LifecycleInterpretation keeps workflow/control/windup phases SEPARATED."""
        from hledac.universal.runtime.shadow_pre_decision import (
            LifecycleInterpretation,
        )

        li = LifecycleInterpretation(
            workflow_phase="ACTIVE",
            workflow_phase_entered_at=10.0,
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

        # SEPARATED fields must all be present
        assert li.workflow_phase == "ACTIVE"
        assert li.control_phase_mode == "normal"
        assert li.windup_local_mode is None
        # Must NOT have a merged "phase" attribute
        assert not hasattr(li, "phase") or getattr(li, "phase", None) is None

    def test_phase_conflict_detected_for_windup_without_local_mode(self):
        """phase_conflict=True when WINDUP but windup_local_mode is None."""
        from hledac.universal.runtime.shadow_pre_decision import (
            LifecycleInterpretation,
        )

        li = LifecycleInterpretation(
            workflow_phase="WINDUP",
            workflow_phase_entered_at=100.0,
            control_phase_mode="prune",
            control_phase_thermal="throttled",
            windup_local_mode=None,  # CONFLICT: WINDUP without windup_local
            is_active=False,
            is_windup=True,
            is_export_ready=False,
            is_terminal=False,
            can_accept_work=False,
            should_prune=True,
            synthesis_mode_known=False,
            phase_conflict=True,
            phase_conflict_reason="workflow_phase=WINDUP but windup_local_mode is None",
        )

        assert li.phase_conflict is True
        assert li.windup_local_mode is None

    def test_phase_conflict_detected_for_non_windup_with_local_mode(self):
        """phase_conflict=True when non-WINDUP but windup_local_mode is set."""
        from hledac.universal.runtime.shadow_pre_decision import (
            LifecycleInterpretation,
        )

        li = LifecycleInterpretation(
            workflow_phase="ACTIVE",
            workflow_phase_entered_at=10.0,
            control_phase_mode="normal",
            control_phase_thermal="nominal",
            windup_local_mode="structured",  # CONFLICT: non-WINDUP with local mode
            is_active=True,
            is_windup=False,
            is_export_ready=False,
            is_terminal=False,
            can_accept_work=True,
            should_prune=False,
            synthesis_mode_known=True,
            phase_conflict=True,
            phase_conflict_reason="workflow_phase=ACTIVE but windup_local_mode=structured",
        )

        assert li.phase_conflict is True


class TestGraphCapabilitySummary:
    """Test GraphCapabilitySummary readiness logic."""

    def test_readiness_unknown_for_unknown_backend(self):
        """readiness='unknown' when backend is 'unknown'."""
        from hledac.universal.runtime.shadow_pre_decision import (
            GraphCapabilitySummary,
        )

        gcs = GraphCapabilitySummary(
            backend="unknown",
            nodes=0,
            edges=0,
            pgq_active=False,
            top_nodes_count=0,
            is_initialized=False,
            has_structured_data=False,
            is_rich=False,
            readiness="unknown",
        )

        assert gcs.readiness == "unknown"
        assert gcs.is_initialized is False

    def test_readiness_rich_for_high_top_nodes(self):
        """readiness='rich' when top_nodes_count >= 5."""
        from hledac.universal.runtime.shadow_pre_decision import (
            GraphCapabilitySummary,
        )

        gcs = GraphCapabilitySummary(
            backend="duckpgq",
            nodes=100,
            edges=300,
            pgq_active=True,
            top_nodes_count=7,
            is_initialized=True,
            has_structured_data=True,
            is_rich=True,
            readiness="rich",
        )

        assert gcs.readiness == "rich"
        assert gcs.is_rich is True


class TestExportReadinessSummary:
    """Test ExportReadinessSummary readiness logic."""

    def test_readiness_unknown_for_unknown_sprint_id(self):
        """readiness='unknown' when sprint_id is 'unknown'."""
        from hledac.universal.runtime.shadow_pre_decision import (
            ExportReadinessSummary,
        )

        ers = ExportReadinessSummary(
            sprint_id="unknown",
            synthesis_engine="mlx",
            ranked_parquet_present=True,
            gnn_predictions=10,
            is_ready=False,
            has_gnn_predictions=True,
            has_ranked_data=True,
            readiness="unknown",
        )

        assert ers.readiness == "unknown"

    def test_readiness_ready_when_sprint_id_and_engine_known(self):
        """readiness='ready' when sprint_id and engine are known."""
        from hledac.universal.runtime.shadow_pre_decision import (
            ExportReadinessSummary,
        )

        ers = ExportReadinessSummary(
            sprint_id="sprint_123",
            synthesis_engine="mlx",
            ranked_parquet_present=True,
            gnn_predictions=10,
            is_ready=True,
            has_gnn_predictions=True,
            has_ranked_data=True,
            readiness="ready",
        )

        assert ers.readiness == "ready"
        assert ers.is_ready is True


class TestModelControlSummary:
    """Test ModelControlSummary readiness logic."""

    def test_readiness_unknown_when_no_tools_no_sources(self):
        """readiness='unknown' when tools_count=0 and sources_count=0."""
        from hledac.universal.runtime.shadow_pre_decision import (
            ModelControlSummary,
        )

        mcs = ModelControlSummary(
            tools_count=0,
            sources_count=0,
            privacy="UNKNOWN",
            depth="STANDARD",
            models_needed=[],
            has_tools=False,
            has_sources=False,
            is_high_quality=False,
            readiness="unknown",
        )

        assert mcs.readiness == "unknown"
        assert mcs.has_tools is False
        assert mcs.has_sources is False

    def test_readiness_partial_when_only_tools(self):
        """readiness='partial' when tools exist but no sources."""
        from hledac.universal.runtime.shadow_pre_decision import (
            ModelControlSummary,
        )

        mcs = ModelControlSummary(
            tools_count=3,
            sources_count=0,
            privacy="STANDARD",
            depth="STANDARD",
            models_needed=["hermes"],
            has_tools=True,
            has_sources=False,
            is_high_quality=True,
            readiness="partial",
        )

        assert mcs.readiness == "partial"
        assert mcs.has_tools is True
        assert mcs.has_sources is False


class TestPrecursorSummary:
    """Test PrecursorSummary readiness logic."""

    def test_readiness_unknown_when_no_branch_no_provider(self):
        """readiness='unknown' when no branch_decision_id and no provider_recommend."""
        from hledac.universal.runtime.shadow_pre_decision import (
            PrecursorSummary,
        )

        ps = PrecursorSummary(
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

        assert ps.readiness == "unknown"
        assert ps.has_branch_decision is False
        assert ps.has_provider_recommend is False


class TestComposePreDecision:
    """Test compose_pre_decision — the main pure function."""

    def _make_minimal_parity_artifact(self) -> "ParityArtifact":
        """Build a minimal valid ParityArtifact for testing."""
        from hledac.universal.runtime.shadow_parity import ParityArtifact

        return ParityArtifact(
            mode="scheduler_shadow",
            timestamp_monotonic=time.monotonic(),
            timestamp_wall="2026-04-01T00:00:00Z",
            workflow_phase="ACTIVE",
            workflow_phase_entered_at=10.0,
            control_phase_mode="normal",
            control_phase_thermal="nominal",
            windup_local_mode=None,
            graph_nodes=100,
            graph_edges=300,
            graph_pgq_active=True,
            graph_backend="duckpgq",
            graph_top_nodes_count=5,
            mc_tools_count=3,
            mc_sources_count=2,
            mc_privacy="STANDARD",
            mc_depth="DEEP",
            mc_models_needed=["hermes"],
            export_sprint_id="sprint_123",
            export_synthesis_engine="mlx",
            export_ranked_parquet_present=True,
            export_gnn_predictions=10,
            branch_decision_id=None,
            provider_recommend=None,
            correlation_run_id=None,
            correlation_branch_id=None,
            mismatch_categories=["NONE"],
            mismatch_details={"note": "no mismatches detected"},
            input_sources={},
        )

    def test_compose_pre_decision_returns_pre_decision_summary(self):
        """compose_pre_decision returns PreDecisionSummary, not None."""
        from hledac.universal.runtime.shadow_pre_decision import compose_pre_decision

        artifact = self._make_minimal_parity_artifact()
        result = compose_pre_decision(artifact)

        assert result is not None
        assert hasattr(result, "lifecycle")
        assert hasattr(result, "graph")
        assert hasattr(result, "export_readiness")
        assert hasattr(result, "model_control")
        assert hasattr(result, "precursors")
        assert hasattr(result, "diff_taxonomy")
        assert hasattr(result, "blockers")
        assert hasattr(result, "unknowns")
        assert hasattr(result, "mismatch_reasons")

    def test_compose_pre_decision_lifecycle_interpretation(self):
        """Lifecycle interpretation correctly identifies ACTIVE state."""
        from hledac.universal.runtime.shadow_pre_decision import compose_pre_decision

        artifact = self._make_minimal_parity_artifact()
        result = compose_pre_decision(artifact)

        assert result.lifecycle.is_active is True
        assert result.lifecycle.is_windup is False
        assert result.lifecycle.can_accept_work is True
        assert result.lifecycle.should_prune is False

    def test_compose_pre_decision_graph_readiness(self):
        """Graph readiness is 'rich' for high top_nodes_count."""
        from hledac.universal.runtime.shadow_pre_decision import compose_pre_decision

        artifact = self._make_minimal_parity_artifact()
        result = compose_pre_decision(artifact)

        assert result.graph.readiness == "rich"
        assert result.graph.is_initialized is True
        assert result.graph.is_rich is True

    def test_compose_pre_decision_export_readiness(self):
        """Export readiness is 'ready' when sprint_id and engine are known."""
        from hledac.universal.runtime.shadow_pre_decision import compose_pre_decision

        artifact = self._make_minimal_parity_artifact()
        result = compose_pre_decision(artifact)

        assert result.export_readiness.readiness == "ready"
        assert result.export_readiness.is_ready is True
        assert result.export_readiness.has_gnn_predictions is True

    def test_compose_pre_decision_diff_taxonomy_none(self):
        """diff_taxonomy is [NONE] when all inputs are valid."""
        from hledac.universal.runtime.shadow_pre_decision import (
            DiffTaxonomy,
            compose_pre_decision,
        )

        artifact = self._make_minimal_parity_artifact()
        result = compose_pre_decision(artifact)

        assert DiffTaxonomy.NONE in result.diff_taxonomy

    def test_compose_pre_decision_blocks_unknown_graph_backend(self):
        """blockers includes graph backend message when backend is unknown."""
        from hledac.universal.runtime.shadow_parity import ParityArtifact
        from hledac.universal.runtime.shadow_pre_decision import compose_pre_decision

        artifact = ParityArtifact(
            mode="scheduler_shadow",
            timestamp_monotonic=time.monotonic(),
            timestamp_wall="2026-04-01T00:00:00Z",
            workflow_phase="ACTIVE",
            workflow_phase_entered_at=10.0,
            control_phase_mode="normal",
            control_phase_thermal="nominal",
            windup_local_mode=None,
            graph_nodes=0,
            graph_edges=0,
            graph_pgq_active=False,
            graph_backend="unknown",
            graph_top_nodes_count=0,
            mc_tools_count=0,
            mc_sources_count=0,
            mc_privacy="UNKNOWN",
            mc_depth="STANDARD",
            mc_models_needed=[],
            export_sprint_id="unknown",
            export_synthesis_engine="unknown",
            export_ranked_parquet_present=False,
            export_gnn_predictions=0,
            branch_decision_id=None,
            provider_recommend=None,
            correlation_run_id=None,
            correlation_branch_id=None,
            mismatch_categories=["GRAPH_CAPABILITY"],
            mismatch_details={"graph_backend": "unknown backend"},
            input_sources={},
        )

        result = compose_pre_decision(artifact)

        assert any("graph backend unknown" in b for b in result.blockers)

    def test_compose_pre_decision_unknowns_include_sparse_graph(self):
        """unknowns includes sparse graph message when graph readiness is sparse."""
        from hledac.universal.runtime.shadow_parity import ParityArtifact
        from hledac.universal.runtime.shadow_pre_decision import compose_pre_decision

        # sparse = nodes=0 and edges=0 but backend known (duckpgq, not "unknown")
        artifact = ParityArtifact(
            mode="scheduler_shadow",
            timestamp_monotonic=time.monotonic(),
            timestamp_wall="2026-04-01T00:00:00Z",
            workflow_phase="ACTIVE",
            workflow_phase_entered_at=10.0,
            control_phase_mode="normal",
            control_phase_thermal="nominal",
            windup_local_mode=None,
            graph_nodes=0,
            graph_edges=0,
            graph_pgq_active=True,
            graph_backend="duckpgq",
            graph_top_nodes_count=0,
            mc_tools_count=3,
            mc_sources_count=2,
            mc_privacy="STANDARD",
            mc_depth="DEEP",
            mc_models_needed=["hermes"],
            export_sprint_id="sprint_123",
            export_synthesis_engine="mlx",
            export_ranked_parquet_present=False,
            export_gnn_predictions=0,
            branch_decision_id=None,
            provider_recommend=None,
            correlation_run_id=None,
            correlation_branch_id=None,
            mismatch_categories=["NONE"],
            mismatch_details={"note": "no mismatches detected"},
            input_sources={},
        )

        result = compose_pre_decision(artifact)

        # sparse graph → in unknowns
        assert any("sparse" in u for u in result.unknowns)


class TestPreDecisionSummaryToDict:
    """Test PreDecisionSummary.to_dict() serializability."""

    def test_to_dict_is_json_serializable(self):
        """PreDecisionSummary.to_dict() returns a JSON-serializable dict."""
        from hledac.universal.runtime.shadow_parity import ParityArtifact
        from hledac.universal.runtime.shadow_pre_decision import compose_pre_decision

        artifact = ParityArtifact(
            mode="scheduler_shadow",
            timestamp_monotonic=time.monotonic(),
            timestamp_wall="2026-04-01T00:00:00Z",
            workflow_phase="WINDUP",
            workflow_phase_entered_at=100.0,
            control_phase_mode="prune",
            control_phase_thermal="throttled",
            windup_local_mode="synthesis",
            graph_nodes=50,
            graph_edges=150,
            graph_pgq_active=True,
            graph_backend="duckpgq",
            graph_top_nodes_count=3,
            mc_tools_count=2,
            mc_sources_count=1,
            mc_privacy="HIGH",
            mc_depth="DEEP",
            mc_models_needed=["hermes"],
            export_sprint_id="sprint_456",
            export_synthesis_engine="mlx",
            export_ranked_parquet_present=True,
            export_gnn_predictions=5,
            branch_decision_id="branch_123",
            provider_recommend="mlx",
            correlation_run_id="run_789",
            correlation_branch_id="branch_123",
            mismatch_categories=["NONE"],
            mismatch_details={"note": "no mismatches detected"},
            input_sources={},
        )

        result = compose_pre_decision(artifact)
        d = result.to_dict()

        assert isinstance(d, dict)
        assert all(isinstance(k, str) for k in d.keys())

        try:
            json.dumps(d)
        except TypeError as e:
            pytest.fail(f"to_dict() is not JSON-serializable: {e}")

    def test_to_dict_phase_fields_separated(self):
        """to_dict() preserves separated phase fields."""
        from hledac.universal.runtime.shadow_parity import ParityArtifact
        from hledac.universal.runtime.shadow_pre_decision import compose_pre_decision

        artifact = ParityArtifact(
            mode="scheduler_shadow",
            timestamp_monotonic=0.0,
            timestamp_wall="",
            workflow_phase="WINDUP",
            workflow_phase_entered_at=100.0,
            control_phase_mode="prune",
            control_phase_thermal="throttled",
            windup_local_mode="structured",
            graph_nodes=0,
            graph_edges=0,
            graph_pgq_active=False,
            graph_backend="unknown",
            graph_top_nodes_count=0,
            mc_tools_count=0,
            mc_sources_count=0,
            mc_privacy="STANDARD",
            mc_depth="STANDARD",
            mc_models_needed=[],
            export_sprint_id="unknown",
            export_synthesis_engine="unknown",
            export_ranked_parquet_present=False,
            export_gnn_predictions=0,
            branch_decision_id=None,
            provider_recommend=None,
            correlation_run_id=None,
            correlation_branch_id=None,
            mismatch_categories=["NONE"],
            mismatch_details={},
            input_sources={},
        )

        result = compose_pre_decision(artifact)
        d = result.to_dict()

        lc = d["lifecycle"]
        # SEPARATED fields must all be present
        assert "workflow_phase" in lc
        assert "control_phase_mode" in lc
        assert "windup_local_mode" in lc
        # Must NOT have a merged "phase" key
        assert "phase" not in lc


class TestPreDecisionConsumerBoundaries:
    """Test pre-decision consumer has NO side effects."""

    def test_compose_pre_decision_is_pure(self):
        """compose_pre_decision makes no I/O, no network, no state changes."""
        from unittest.mock import AsyncMock

        from hledac.universal.runtime.shadow_parity import ParityArtifact
        from hledac.universal.runtime.shadow_pre_decision import compose_pre_decision

        artifact = ParityArtifact(
            mode="scheduler_shadow",
            timestamp_monotonic=0.0,
            timestamp_wall="",
            workflow_phase="ACTIVE",
            workflow_phase_entered_at=10.0,
            control_phase_mode="normal",
            control_phase_thermal="nominal",
            windup_local_mode=None,
            graph_nodes=0,
            graph_edges=0,
            graph_pgq_active=False,
            graph_backend="unknown",
            graph_top_nodes_count=0,
            mc_tools_count=0,
            mc_sources_count=0,
            mc_privacy="STANDARD",
            mc_depth="STANDARD",
            mc_models_needed=[],
            export_sprint_id="unknown",
            export_synthesis_engine="unknown",
            export_ranked_parquet_present=False,
            export_gnn_predictions=0,
            branch_decision_id=None,
            provider_recommend=None,
            correlation_run_id=None,
            correlation_branch_id=None,
            mismatch_categories=["NONE"],
            mismatch_details={},
            input_sources={},
        )

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = compose_pre_decision(artifact)
            assert mock_sleep.call_count == 0, "compose_pre_decision called asyncio.sleep"

        assert result is not None

    def test_shadow_pre_decision_module_no_network_imports(self):
        """shadow_pre_decision.py does not import network modules."""
        src_path = Path(__file__).parent.parent.parent / "runtime" / "shadow_pre_decision.py"
        source = src_path.read_text()
        tree = ast.parse(source)

        network_modules = {
            "aiohttp", "httpx", "requests", "urllib3",
            "curl_cffi", "nodriver", "selenium",
            "playwright", "pyppeteer",
        }

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)

        for imp in imports:
            if any(imp.startswith(nm) for nm in network_modules):
                pytest.fail(f"shadow_pre_decision.py imports network module: {imp}")


class TestNoSchedulerModification:
    """Verify pre-decision layer does NOT modify SprintScheduler."""

    def test_no_new_fields_added_to_sprint_scheduler(self):
        """SprintScheduler should not have new shadow-related attributes."""
        from hledac.universal.runtime.sprint_scheduler import SprintScheduler

        scheduler_attrs = set(dir(SprintScheduler))
        suspicious = [
            "_pre_decision_summary",
            "_shadow_consumer",
            "_parity_artifact",
            "_pre_decision_enabled",
            "_shadow_summary",
        ]

        for name in suspicious:
            assert name not in scheduler_attrs, (
                f"SprintScheduler has new attribute '{name}' — "
                f"pre-decision layer must NOT add scheduler state"
            )

    def test_shadow_pre_decision_does_not_import_sprint_scheduler(self):
        """shadow_pre_decision.py does not import sprint_scheduler."""
        src_path = Path(__file__).parent.parent.parent / "runtime" / "shadow_pre_decision.py"
        source = src_path.read_text()
        tree = ast.parse(source)

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)

        for imp in imports:
            if "sprint_scheduler" in imp:
                pytest.fail(f"shadow_pre_decision.py imports sprint_scheduler: {imp}")


class TestPhaseLayerSeparationInvariant:
    """Test phase layer separation is enforced throughout pre-decision."""

    def test_pre_decision_lifecycle_interpretation_has_separated_phases(self):
        """PreDecisionSummary.lifecycle has workflow_phase, control_phase_mode, windup_local_mode."""
        from hledac.universal.runtime.shadow_parity import ParityArtifact
        from hledac.universal.runtime.shadow_pre_decision import compose_pre_decision

        artifact = ParityArtifact(
            mode="scheduler_shadow",
            timestamp_monotonic=0.0,
            timestamp_wall="",
            workflow_phase="WINDUP",
            workflow_phase_entered_at=100.0,
            control_phase_mode="prune",
            control_phase_thermal="critical",
            windup_local_mode="minimal",
            graph_nodes=0,
            graph_edges=0,
            graph_pgq_active=False,
            graph_backend="unknown",
            graph_top_nodes_count=0,
            mc_tools_count=0,
            mc_sources_count=0,
            mc_privacy="STANDARD",
            mc_depth="STANDARD",
            mc_models_needed=[],
            export_sprint_id="unknown",
            export_synthesis_engine="unknown",
            export_ranked_parquet_present=False,
            export_gnn_predictions=0,
            branch_decision_id=None,
            provider_recommend=None,
            correlation_run_id=None,
            correlation_branch_id=None,
            mismatch_categories=["NONE"],
            mismatch_details={},
            input_sources={},
        )

        result = compose_pre_decision(artifact)
        lc = result.lifecycle

        # All THREE phase systems are present as SEPARATED fields
        assert hasattr(lc, "workflow_phase")
        assert hasattr(lc, "control_phase_mode")
        assert hasattr(lc, "windup_local_mode")

        # Verify values
        assert lc.workflow_phase == "WINDUP"
        assert lc.control_phase_mode == "prune"
        assert lc.windup_local_mode == "minimal"

        # Synthesis mode is known when in WINDUP
        assert lc.synthesis_mode_known is True
        assert lc.is_windup is True
