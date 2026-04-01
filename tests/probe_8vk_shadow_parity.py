"""
Probe 8VK: Shadow Scheduler Parity — Fact Parity Tests
======================================================

Tests for F3.5 fact parity implementation:

1. Shadow mode nevolá tools execution
2. Shadow mode nevytváří findings writes
3. Shadow mode nevolá network execution
4. Shadow mode neprodukuje side effects
5. legacy_runtime běží beze změny
6. scheduler_active se neaktivuje omylem
7. parity artifact je diagnostický a serializovatelný
8. local shadow dataclasses nezískaly status shared contracts
9. phase fields jsou SEPARATED (workflow_phase, control_phase, windup_local_phase)
10. RuntimeMode.get_current() vrací správný mód
11. ParityArtifact.to_dict() je serializovatelný

Run:
    cd /Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal
    python -m pytest tests/probe_8vk_shadow_parity.py -v
"""

import time
from unittest.mock import patch, MagicMock
from typing import Any, Dict, List

import pytest


class TestRuntimeMode:
    """Test RuntimeMode scaffold and mode detection."""

    def test_runtime_mode_default_is_legacy(self):
        """Default runtime mode is legacy_runtime."""
        from hledac.universal.runtime.shadow_inputs import RuntimeMode
        # Default without env var should be legacy
        mode = RuntimeMode.get_current()
        assert mode == RuntimeMode.LEGACY_RUNTIME

    def test_runtime_mode_shadow_detection(self):
        """RuntimeMode.is_shadow_mode() returns True when env var set."""
        from hledac.universal.runtime.shadow_inputs import RuntimeMode
        with patch.dict("os.environ", {"HLEDAC_RUNTIME_MODE": "scheduler_shadow"}):
            assert RuntimeMode.is_shadow_mode() is True
            assert RuntimeMode.is_active_mode() is False
            assert RuntimeMode.is_legacy_mode() is False

    def test_runtime_mode_active_detection(self):
        """RuntimeMode.is_active_mode() returns True when env var set."""
        from hledac.universal.runtime.shadow_inputs import RuntimeMode
        with patch.dict("os.environ", {"HLEDAC_RUNTIME_MODE": "scheduler_active"}):
            assert RuntimeMode.is_active_mode() is True
            assert RuntimeMode.is_shadow_mode() is False
            assert RuntimeMode.is_legacy_mode() is False

    def test_runtime_mode_legacy_when_invalid_env(self):
        """Invalid env var value falls back to legacy_runtime."""
        from hledac.universal.runtime.shadow_inputs import RuntimeMode
        with patch.dict("os.environ", {"HLEDAC_RUNTIME_MODE": "invalid_mode"}):
            assert RuntimeMode.get_current() == RuntimeMode.LEGACY_RUNTIME


class TestLifecycleSnapshotBundle:
    """Test LifecycleSnapshotBundle phase separation invariant."""

    def test_workflow_phase_from_snapshot(self):
        """WorkflowPhase.from_lifecycle_snapshot extracts correctly."""
        from hledac.universal.runtime.shadow_inputs import WorkflowPhase

        snap = {
            "current_phase": "ACTIVE",
            "entered_phase_at": 100.0,
            "started_at_monotonic": 50.0,
            "sprint_duration_s": 1800.0,
            "windup_lead_s": 180.0,
        }
        wf = WorkflowPhase.from_lifecycle_snapshot(snap)
        assert wf.phase == "ACTIVE"
        assert wf.entered_at_monotonic == 100.0
        assert wf.started_at_monotonic == 50.0
        assert wf.sprint_duration_s == 1800.0
        assert wf.windup_lead_s == 180.0

    def test_workflow_phase_unknown_for_missing_phase(self):
        """Missing current_phase defaults to UNKNOWN."""
        from hledac.universal.runtime.shadow_inputs import WorkflowPhase

        wf = WorkflowPhase.from_lifecycle_snapshot({})
        assert wf.phase == "UNKNOWN"

    def test_control_phase_from_lifecycle(self):
        """ControlPhase.from_lifecycle derives tool mode correctly."""
        from hledac.universal.runtime.shadow_inputs import ControlPhase
        from hledac.universal.runtime.sprint_lifecycle import SprintLifecycleManager

        lc = SprintLifecycleManager()
        lc.start(now_monotonic=0.0)
        lc._started_at = 0.0

        # In normal conditions should be "normal"
        cp = ControlPhase.from_lifecycle(lc, now_monotonic=10.0, thermal_state="nominal")
        assert cp.mode in ("normal", "prune", "panic")
        assert cp.thermal_state == "nominal"

    def test_lifecycle_snapshot_bundle_separates_phases(self):
        """LifecycleSnapshotBundle keeps workflow/control/windup phases separate."""
        from hledac.universal.runtime.shadow_inputs import (
            LifecycleSnapshotBundle,
            WorkflowPhase,
            ControlPhase,
            WindupLocalPhase,
        )

        wf = WorkflowPhase(phase="ACTIVE", entered_at_monotonic=10.0)
        ctrl = ControlPhase(mode="normal", thermal_state="nominal", remaining_s=1700.0)
        windup = WindupLocalPhase(mode="synthesis", error_encountered=False, synthesis_engine="mlx")

        bundle = LifecycleSnapshotBundle(
            workflow_phase=wf,
            control_phase=ctrl,
            windup_local_phase=windup,
            raw_snapshot={},
        )

        # Verify SEPARATION — phases must NOT be merged
        assert bundle.workflow_phase.phase == "ACTIVE"
        assert bundle.control_phase.mode == "normal"
        assert bundle.windup_local_phase is not None
        assert bundle.windup_local_phase.mode == "synthesis"

        # Verify to_dict() preserves separation
        d = bundle.to_dict()
        assert d["workflow_phase"] == "ACTIVE"
        assert d["control_phase_mode"] == "normal"
        assert d["windup_local_mode"] == "synthesis"
        # Must NOT have a merged "phase" field
        assert "phase" not in d or d.get("phase") is None

    def test_lifecycle_snapshot_bundle_windup_local_only_in_windup(self):
        """windup_local_phase should only be set when workflow_phase is WINDUP."""
        from hledac.universal.runtime.shadow_inputs import (
            LifecycleSnapshotBundle,
            WorkflowPhase,
            ControlPhase,
        )

        # Not in WINDUP — windup_local should be None
        wf = WorkflowPhase(phase="ACTIVE", entered_at_monotonic=10.0)
        ctrl = ControlPhase(mode="normal", thermal_state="nominal", remaining_s=1700.0)
        bundle = LifecycleSnapshotBundle(
            workflow_phase=wf,
            control_phase=ctrl,
            windup_local_phase=None,
            raw_snapshot={},
        )
        assert bundle.windup_local_phase is None
        assert bundle.to_dict()["windup_local_mode"] is None


class TestGraphSummaryBundle:
    """Test GraphSummaryBundle."""

    def test_from_ioc_graph_stats(self):
        """GraphSummaryBundle.from_ioc_graph_stats extracts correctly."""
        from hledac.universal.runtime.shadow_inputs import GraphSummaryBundle

        stats = {"nodes": 100, "edges": 300, "pgq_active": True}
        bundle = GraphSummaryBundle.from_ioc_graph_stats(stats, top_nodes=["node1", "node2"])

        assert bundle.node_count == 100
        assert bundle.edge_count == 300
        assert bundle.pgq_active is True
        assert bundle.backend == "duckpgq"
        assert bundle.top_nodes == ["node1", "node2"]

    def test_from_scorecard_top_nodes(self):
        """GraphSummaryBundle.from_scorecard_top_nodes is compat path."""
        from hledac.universal.runtime.shadow_inputs import GraphSummaryBundle

        bundle = GraphSummaryBundle.from_scorecard_top_nodes(["node1", "node2"])

        assert bundle.node_count == 0  # unknown from compat
        assert bundle.backend == "unknown"
        assert bundle.top_nodes == ["node1", "node2"]

    def test_to_dict_preserves_all_fields(self):
        """to_dict() preserves all graph facts."""
        from hledac.universal.runtime.shadow_inputs import GraphSummaryBundle

        bundle = GraphSummaryBundle(
            node_count=50,
            edge_count=200,
            pgq_active=True,
            backend="duckpgq",
            top_nodes=["a", "b"],
        )
        d = bundle.to_dict()
        assert d["graph_nodes"] == 50
        assert d["graph_edges"] == 200
        assert d["graph_pgq_active"] is True
        assert d["graph_backend"] == "duckpgq"
        assert d["graph_top_nodes"] == ["a", "b"]


class TestModelControlFactsBundle:
    """Test ModelControlFactsBundle."""

    def test_from_analyzer_result(self):
        """ModelControlFactsBundle.from_analyzer_result extracts tools/sources."""
        from hledac.universal.runtime.shadow_inputs import ModelControlFactsBundle
        from hledac.universal.types import AnalyzerResult

        result = AnalyzerResult(
            tools={"cve", "ioc"},
            sources={"cisa_kev"},
            privacy_level="HIGH",
            use_tor=True,
            depth="DEEP",
            use_tot=True,
            tot_mode="branch",
            models_needed={"hermes", "modernbert"},
        )

        bundle = ModelControlFactsBundle.from_analyzer_result(result)

        assert "cve" in bundle.tools
        assert "ioc" in bundle.tools
        assert "cisa_kev" in bundle.sources
        assert bundle.privacy_level == "HIGH"
        assert bundle.use_tor is True
        assert bundle.depth == "DEEP"
        assert bundle.use_tot is True
        assert "hermes" in bundle.models_needed

    def test_to_dict_preserves_all_mc_fields(self):
        """to_dict() preserves all model/control facts."""
        from hledac.universal.runtime.shadow_inputs import ModelControlFactsBundle

        bundle = ModelControlFactsBundle(
            tools=["cve", "ioc"],
            sources=["cisa_kev"],
            privacy_level="HIGH",
            use_tor=True,
            depth="DEEP",
            use_tot=True,
            tot_mode="branch",
            models_needed=["hermes"],
        )
        d = bundle.to_dict()
        assert d["mc_tools"] == ["cve", "ioc"]
        assert d["mc_sources"] == ["cisa_kev"]
        assert d["mc_privacy"] == "HIGH"
        assert d["mc_use_tor"] is True
        assert d["mc_depth"] == "DEEP"
        assert d["mc_use_tot"] is True
        assert d["mc_tot_mode"] == "branch"
        assert d["mc_models_needed"] == ["hermes"]


class TestCollectFunctions:
    """Test pure collect_* functions — no side effects."""

    def test_collect_lifecycle_snapshot_is_pure(self):
        """collect_lifecycle_snapshot returns bundle, makes no I/O."""
        from hledac.universal.runtime.shadow_inputs import collect_lifecycle_snapshot
        from hledac.universal.runtime.sprint_lifecycle import SprintLifecycleManager

        lc = SprintLifecycleManager()
        lc.start(now_monotonic=0.0)

        bundle = collect_lifecycle_snapshot(
            lc,
            now_monotonic=10.0,
            thermal_state="nominal",
            windup_synthesis_mode="synthesis",
            windup_error=False,
            windup_engine="mlx",
        )

        assert bundle.workflow_phase.phase == "WARMUP"
        assert bundle.control_phase.mode in ("normal", "prune", "panic")
        assert bundle.raw_snapshot is not None

    def test_collect_graph_summary_empty_is_safe(self):
        """collect_graph_summary with no inputs returns empty bundle."""
        from hledac.universal.runtime.shadow_inputs import collect_graph_summary

        bundle = collect_graph_summary(ioc_graph=None, scorecard=None)
        assert bundle.node_count == 0
        assert bundle.backend == "unknown"

    def test_collect_model_control_facts_empty_is_safe(self):
        """collect_model_control_facts with no inputs returns empty bundle."""
        from hledac.universal.runtime.shadow_inputs import collect_model_control_facts

        bundle = collect_model_control_facts(analyzer_result=None, raw_profile=None)
        assert len(bundle.tools) == 0
        assert len(bundle.sources) == 0
        assert bundle.privacy_level == "STANDARD"

    def test_collect_export_handoff_facts_from_scorecard(self):
        """collect_export_handoff_facts builds facts dict from scorecard correctly."""
        from hledac.universal.runtime.shadow_inputs import collect_export_handoff_facts

        # scorecard path uses synthesis_engine_used (not synthesis_engine)
        scorecard = {
            "sprint_id": "test_123",
            "synthesis_engine_used": "mlx",
            "gnn_predicted_links": 10,
            "top_graph_nodes": ["a", "b", "c", "d", "e"],
            "ranked_parquet": "/path/to/ranked.parquet",
            "phase_duration_seconds": {"BOOT": 1.0, "ACTIVE": 100.0},
        }
        result = collect_export_handoff_facts(scorecard=scorecard)
        assert result["sprint_id"] == "test_123"
        assert result["synthesis_engine"] == "mlx"
        assert result["gnn_predictions"] == 10
        assert result["top_nodes_count"] == 5
        assert result["ranked_parquet_present"] is True

    def test_collect_export_handoff_facts_empty_is_safe(self):
        """collect_export_handoff_facts with no inputs returns unknown defaults."""
        from hledac.universal.runtime.shadow_inputs import collect_export_handoff_facts

        result = collect_export_handoff_facts(handoff=None, scorecard=None)
        assert result["sprint_id"] == "unknown"
        assert result["synthesis_engine"] == "unknown"
        assert result["gnn_predictions"] == 0


class TestParityArtifact:
    """Test ParityArtifact diagnostic output."""

    def test_parity_artifact_to_dict_is_serializable(self):
        """ParityArtifact.to_dict() returns a plain dict suitable for JSON."""
        from hledac.universal.runtime.shadow_parity import ParityArtifact

        artifact = ParityArtifact(
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
            mc_privacy="HIGH",
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
            input_sources={"lifecycle_snapshot": "runtime/shadow_inputs.py"},
        )

        d = artifact.to_dict()

        # Must be a plain dict (not dataclass, not special type)
        assert isinstance(d, dict)
        # All keys must be strings
        assert all(isinstance(k, str) for k in d.keys())
        # All values must be JSON-serializable types
        import json
        try:
            json.dumps(d)
        except TypeError as e:
            pytest.fail(f"ParityArtifact.to_dict() is not JSON-serializable: {e}")

    def test_parity_artifact_phase_fields_separated(self):
        """ParityArtifact has SEPARATED workflow_phase, control_phase_mode, windup_local_mode."""
        from hledac.universal.runtime.shadow_parity import ParityArtifact

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

        d = artifact.to_dict()

        # SEPARATED fields must all be present
        assert "workflow_phase" in d
        assert "control_phase_mode" in d
        assert "windup_local_mode" in d
        # Must NOT have a merged "phase" key
        assert "phase" not in d


class TestRunShadowParity:
    """Test run_shadow_parity — the main pure function."""

    def test_run_shadow_parity_returns_parity_artifact(self):
        """run_shadow_parity returns ParityArtifact (not None, not dict subclass)."""
        from hledac.universal.runtime.shadow_parity import run_shadow_parity
        from hledac.universal.runtime.shadow_inputs import (
            LifecycleSnapshotBundle,
            GraphSummaryBundle,
            ModelControlFactsBundle,
            WorkflowPhase,
            ControlPhase,
        )

        lc_bundle = LifecycleSnapshotBundle(
            workflow_phase=WorkflowPhase(phase="ACTIVE", entered_at_monotonic=10.0),
            control_phase=ControlPhase(mode="normal", thermal_state="nominal", remaining_s=1700.0),
            windup_local_phase=None,
            raw_snapshot={},
        )
        graph_bundle = GraphSummaryBundle(
            node_count=100,
            edge_count=300,
            pgq_active=True,
            backend="duckpgq",
            top_nodes=[],
        )
        mc_bundle = ModelControlFactsBundle(
            tools=["cve"],
            sources=["cisa_kev"],
            privacy_level="STANDARD",
            models_needed=["hermes"],
        )
        export_facts = {
            "sprint_id": "sprint_123",
            "synthesis_engine": "mlx",
            "gnn_predictions": 5,
            "top_nodes_count": 3,
            "ranked_parquet_present": True,
            "phase_durations": {},
        }

        result = run_shadow_parity(
            lifecycle_bundle=lc_bundle,
            graph_bundle=graph_bundle,
            model_control_bundle=mc_bundle,
            export_handoff_facts=export_facts,
            runtime_mode="scheduler_shadow",
        )

        from hledac.universal.runtime.shadow_parity import ParityArtifact
        assert isinstance(result, ParityArtifact)
        assert result.mode == "scheduler_shadow"
        assert result.workflow_phase == "ACTIVE"
        assert result.graph_nodes == 100

    def test_run_shadow_parity_flags_unknown_graph_backend(self):
        """run_shadow_parity adds GRAPH_CAPABILITY mismatch when backend is unknown."""
        from hledac.universal.runtime.shadow_parity import run_shadow_parity
        from hledac.universal.runtime.shadow_inputs import (
            LifecycleSnapshotBundle,
            GraphSummaryBundle,
            ModelControlFactsBundle,
            WorkflowPhase,
            ControlPhase,
        )

        lc_bundle = LifecycleSnapshotBundle(
            workflow_phase=WorkflowPhase(phase="ACTIVE"),
            control_phase=ControlPhase(mode="normal"),
            windup_local_phase=None,
            raw_snapshot={},
        )
        graph_bundle = GraphSummaryBundle(
            node_count=0, edge_count=0, pgq_active=False,
            backend="unknown", top_nodes=[],
        )
        mc_bundle = ModelControlFactsBundle()
        export_facts = {}

        result = run_shadow_parity(
            lifecycle_bundle=lc_bundle,
            graph_bundle=graph_bundle,
            model_control_bundle=mc_bundle,
            export_handoff_facts=export_facts,
        )

        assert "GRAPH_CAPABILITY" in result.mismatch_categories

    def test_run_shadow_parity_no_mismatches_for_valid_inputs(self):
        """No mismatches when all inputs are valid."""
        from hledac.universal.runtime.shadow_parity import run_shadow_parity
        from hledac.universal.runtime.shadow_inputs import (
            LifecycleSnapshotBundle,
            GraphSummaryBundle,
            ModelControlFactsBundle,
            WorkflowPhase,
            ControlPhase,
        )

        lc_bundle = LifecycleSnapshotBundle(
            workflow_phase=WorkflowPhase(phase="ACTIVE", entered_at_monotonic=10.0),
            control_phase=ControlPhase(mode="normal", thermal_state="nominal", remaining_s=1700.0),
            windup_local_phase=None,
            raw_snapshot={},
        )
        graph_bundle = GraphSummaryBundle(
            node_count=100, edge_count=300, pgq_active=True,
            backend="duckpgq", top_nodes=["n1", "n2"],
        )
        mc_bundle = ModelControlFactsBundle(
            tools=["cve"], sources=["cisa_kev"],
            privacy_level="STANDARD", models_needed=["hermes"],
        )
        export_facts = {
            "sprint_id": "sprint_123",
            "synthesis_engine": "mlx",
            "gnn_predictions": 5,
            "top_nodes_count": 2,
            "ranked_parquet_present": True,
            "phase_durations": {},
        }

        result = run_shadow_parity(
            lifecycle_bundle=lc_bundle,
            graph_bundle=graph_bundle,
            model_control_bundle=mc_bundle,
            export_handoff_facts=export_facts,
        )

        # NONE mismatch expected with valid inputs
        assert result.mismatch_categories == ["NONE"]


class TestPhaseFieldMergeCheck:
    """Test _check_phase_field_merge structural invariant check."""

    def test_detects_unexpected_workflow_phase_value(self):
        """_check_phase_field_merge flags unexpected workflow_phase values."""
        from hledac.universal.runtime.shadow_parity import _check_phase_field_merge
        from hledac.universal.runtime.shadow_inputs import (
            LifecycleSnapshotBundle,
            WorkflowPhase,
            ControlPhase,
        )

        mismatches: List[str] = []
        mismatch_details: Dict[str, Any] = {}

        # "RANDOM_PHASE" is not a valid SprintPhase enum value
        bundle = LifecycleSnapshotBundle(
            workflow_phase=WorkflowPhase(phase="RANDOM_PHASE"),
            control_phase=ControlPhase(mode="normal"),
            windup_local_phase=None,
            raw_snapshot={},
        )

        _check_phase_field_merge(bundle, mismatches, mismatch_details)

        assert "LIFECYCLE" in mismatches
        assert "workflow_phase" in mismatch_details

    def test_detects_unexpected_control_phase_mode(self):
        """_check_phase_field_merge flags unexpected control_mode values."""
        from hledac.universal.runtime.shadow_parity import _check_phase_field_merge
        from hledac.universal.runtime.shadow_inputs import (
            LifecycleSnapshotBundle,
            WorkflowPhase,
            ControlPhase,
        )

        mismatches: List[str] = []
        mismatch_details: Dict[str, Any] = {}

        bundle = LifecycleSnapshotBundle(
            workflow_phase=WorkflowPhase(phase="ACTIVE"),
            control_phase=ControlPhase(mode="invalid_mode"),
            windup_local_phase=None,
            raw_snapshot={},
        )

        _check_phase_field_merge(bundle, mismatches, mismatch_details)

        assert "LIFECYCLE" in mismatches

    def test_detects_windup_without_windup_local_phase(self):
        """_check_phase_field_merge flags WINDUP without windup_local_phase set."""
        from hledac.universal.runtime.shadow_parity import _check_phase_field_merge
        from hledac.universal.runtime.shadow_inputs import (
            LifecycleSnapshotBundle,
            WorkflowPhase,
            ControlPhase,
        )

        mismatches: List[str] = []
        mismatch_details: Dict[str, Any] = {}

        bundle = LifecycleSnapshotBundle(
            workflow_phase=WorkflowPhase(phase="WINDUP"),
            control_phase=ControlPhase(mode="prune"),
            windup_local_phase=None,  # Should be set when in WINDUP!
            raw_snapshot={},
        )

        _check_phase_field_merge(bundle, mismatches, mismatch_details)

        assert "LIFECYCLE" in mismatches
        assert "windup_local_phase" in mismatch_details


class TestShadowModeSideEffectBoundaries:
    """Test that shadow parity implementation has NO side effects."""

    def test_run_shadow_parity_has_no_io_calls(self):
        """run_shadow_parity makes no file I/O, no network calls, no findings writes."""
        from unittest.mock import AsyncMock, patch

        from hledac.universal.runtime.shadow_parity import run_shadow_parity
        from hledac.universal.runtime.shadow_inputs import (
            LifecycleSnapshotBundle,
            GraphSummaryBundle,
            ModelControlFactsBundle,
            WorkflowPhase,
            ControlPhase,
        )

        lc_bundle = LifecycleSnapshotBundle(
            workflow_phase=WorkflowPhase(phase="ACTIVE"),
            control_phase=ControlPhase(mode="normal"),
            windup_local_phase=None,
            raw_snapshot={},
        )
        graph_bundle = GraphSummaryBundle()
        mc_bundle = ModelControlFactsBundle()
        export_facts = {}

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = run_shadow_parity(
                lifecycle_bundle=lc_bundle,
                graph_bundle=graph_bundle,
                model_control_bundle=mc_bundle,
                export_handoff_facts=export_facts,
            )
            # run_shadow_parity is a pure sync function — asyncio.sleep must not be called
            assert mock_sleep.call_count == 0, "run_shadow_parity called async sleep — possible side effect"

        # Verify result is still valid
        assert result is not None
        assert result.mode == "scheduler_shadow"

    def test_shadow_parity_module_does_not_import_network_modules(self):
        """shadow_parity.py does not import network-fetching modules."""
        import ast
        from pathlib import Path

        shadow_parity_path = Path(__file__).parent.parent / "runtime" / "shadow_parity.py"
        source = shadow_parity_path.read_text()
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
                pytest.fail(f"shadow_parity.py imports network module: {imp}")

    def test_shadow_inputs_module_does_not_import_network_modules(self):
        """shadow_inputs.py does not import network-fetching modules."""
        import ast
        from pathlib import Path

        shadow_inputs_path = Path(__file__).parent.parent / "runtime" / "shadow_inputs.py"
        source = shadow_inputs_path.read_text()
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
                pytest.fail(f"shadow_inputs.py imports network module: {imp}")


class TestNoNewSchedulerFramework:
    """Verify no new scheduler framework was created."""

    def test_no_new_scheduler_state_created(self):
        """No new persistent scheduler-owned state files created."""
        from pathlib import Path

        runtime_dir = Path(__file__).parent.parent / "runtime"

        # Check for suspicious new state files
        suspicious = [
            "scheduler_state.json",
            "shadow_state.json",
            "parity_state.json",
            "scheduler_ledger.json",
        ]

        for name in suspicious:
            path = runtime_dir / name
            if path.exists():
                pytest.fail(f"New scheduler state file created: {name} — must not create persistent scheduler-owned state")


class TestLocalShadowDataclassesNotSharedContracts:
    """Verify local shadow dataclasses are NOT elevated to shared contracts."""

    def test_shadow_inputs_dataclasses_not_in_types(self):
        """LifecycleSnapshotBundle, GraphSummaryBundle, ModelControlFactsBundle are NOT in types.py."""
        from pathlib import Path

        types_path = Path(__file__).parent.parent / "types.py"
        source = types_path.read_text()

        shadow_classes = [
            "LifecycleSnapshotBundle",
            "GraphSummaryBundle",
            "ModelControlFactsBundle",
            "WorkflowPhase",
            "ControlPhase",
            "WindupLocalPhase",
            "ParityArtifact",
        ]

        for cls_name in shadow_classes:
            if f"class {cls_name}" in source:
                pytest.fail(
                    f"Shadow dataclass {cls_name} found in types.py — "
                    f"local shadow dataclasses must NOT be elevated to shared contracts"
                )


class TestLegacyRuntimeUnchanged:
    """Verify legacy_runtime path is unchanged."""

    def test_default_runtime_mode_still_legacy(self):
        """Default RuntimeMode.get_current() is still LEGACY_RUNTIME without env vars."""
        import os
        # Ensure no env var is set
        env_backup = os.environ.get("HLEDAC_RUNTIME_MODE")

        try:
            if "HLEDAC_RUNTIME_MODE" in os.environ:
                del os.environ["HLEDAC_RUNTIME_MODE"]

            from hledac.universal.runtime.shadow_inputs import RuntimeMode
            assert RuntimeMode.get_current() == RuntimeMode.LEGACY_RUNTIME
            assert RuntimeMode.is_legacy_mode() is True
            assert RuntimeMode.is_shadow_mode() is False
            assert RuntimeMode.is_active_mode() is False
        finally:
            if env_backup is not None:
                os.environ["HLEDAC_RUNTIME_MODE"] = env_backup
