"""
Probe: Shadow collectors are PURE functions — no side effects.

Sprint 8VK §Invariant: collect_* functions must not mutate their inputs
or produce any side effects.
"""

import pytest
from unittest.mock import MagicMock
from hledac.universal.runtime.sprint_lifecycle import SprintLifecycleManager, SprintPhase


class TestShadowCollectorsPure:
    """Verify collectors have no side effects."""

    def test_collect_lifecycle_snapshot_is_pure(self):
        """collect_lifecycle_snapshot must not mutate lifecycle."""
        from hledac.universal.runtime.shadow_inputs import collect_lifecycle_snapshot

        lc = SprintLifecycleManager()
        lc.start()
        original_phase = lc._current_phase

        # Call collector multiple times
        bundle1 = collect_lifecycle_snapshot(lc)
        bundle2 = collect_lifecycle_snapshot(lc)

        # Phase must not have changed
        assert lc._current_phase == original_phase
        assert bundle1.workflow_phase.phase == bundle2.workflow_phase.phase

    def test_collect_graph_summary_no_side_effects(self):
        """collect_graph_summary must not mutate ioc_graph."""
        from hledac.universal.runtime.shadow_inputs import collect_graph_summary

        mock_graph = MagicMock()
        mock_graph.stats.return_value = {"nodes": 10, "edges": 20, "pgq_active": True}
        mock_graph.get_top_nodes_by_degree.return_value = [{"id": "node1"}]

        # Call twice
        result1 = collect_graph_summary(ioc_graph=mock_graph)
        result2 = collect_graph_summary(ioc_graph=mock_graph)

        # Stats called same number of times (no extra calls from side effects)
        assert mock_graph.stats.call_count == 2
        assert result1.node_count == result2.node_count == 10

    def test_collect_model_control_facts_no_side_effects(self):
        """collect_model_control_facts must not mutate analyzer_result."""
        from hledac.universal.runtime.shadow_inputs import collect_model_control_facts

        mock_result = MagicMock()
        mock_result.tools = {"tool1", "tool2"}
        mock_result.sources = {"source1"}
        mock_result.privacy_level = "HIGH"
        mock_result.use_tor = False
        mock_result.depth = "DEEP"
        mock_result.use_tot = True
        mock_result.tot_mode = "standard"
        mock_result.models_needed = {"hermes"}
        mock_result.to_capability_signal.return_value = {
            "requires_embeddings": False,
            "requires_ner": True,
        }

        result1 = collect_model_control_facts(analyzer_result=mock_result)
        result2 = collect_model_control_facts(analyzer_result=mock_result)

        # to_capability_signal called same number of times (no extra calls)
        assert mock_result.to_capability_signal.call_count == 2
        assert result1.tools == result2.tools == ["tool1", "tool2"]

    def test_collect_export_handoff_facts_idempotent(self):
        """collect_export_handoff_facts must be idempotent (same input = same output)."""
        from hledac.universal.runtime.shadow_inputs import collect_export_handoff_facts

        scorecard = {
            "sprint_id": "sprint-123",
            "synthesis_engine_used": "Hermes3",
            "gnn_predicted_links": 5,
            "top_graph_nodes": [1, 2, 3],
            "ranked_parquet": "/path/to/parquet",
            "phase_duration_seconds": {"WARMUP": 10.0},
        }

        result1 = collect_export_handoff_facts(scorecard=scorecard, sprint_id="sprint-123")
        result2 = collect_export_handoff_facts(scorecard=scorecard, sprint_id="sprint-123")

        assert result1 == result2
        assert result1["sprint_id"] == "sprint-123"
        assert result1["gnn_predictions"] == 5
