"""
Probe: ExportHandoff can be used as shadow input.

Sprint 8VK §Invariant: ExportHandoff (typed) is usable as shadow input
via collect_export_handoff_facts().
"""

import pytest
from unittest.mock import MagicMock


class TestExportHandoffAsShadowInput:
    """Verify ExportHandoff is consumable as shadow input."""

    def test_export_handoff_from_windup_is_usable(self):
        """ExportHandoff.from_windup() produces usable typed handoff."""
        from hledac.universal.types import ExportHandoff
        from hledac.universal.runtime.shadow_inputs import collect_export_handoff_facts

        scorecard = {
            "sprint_id": "sprint-456",
            "synthesis_engine_used": "Hermes3",
            "gnn_predicted_links": 3,
            "top_graph_nodes": ["node1", "node2"],
            "ranked_parquet": "/tmp/ranked.parquet",
            "phase_duration_seconds": {"ACTIVE": 100.0},
        }

        handoff = ExportHandoff.from_windup(
            sprint_id="sprint-456",
            scorecard=scorecard,
        )

        facts = collect_export_handoff_facts(handoff=handoff)

        assert facts["sprint_id"] == "sprint-456"
        assert facts["synthesis_engine"] == "Hermes3"
        assert facts["gnn_predictions"] == 3
        assert facts["top_nodes_count"] == 2
        assert facts["ranked_parquet_present"] is True
        assert facts["phase_durations"] == {"ACTIVE": 100.0}

    def test_export_handoff_vs_scorecard_parity(self):
        """ExportHandoff and scorecard dict produce equivalent facts."""
        from hledac.universal.types import ExportHandoff
        from hledac.universal.runtime.shadow_inputs import collect_export_handoff_facts

        scorecard = {
            "sprint_id": "sprint-789",
            "synthesis_engine_used": "MoE",
            "gnn_predicted_links": 7,
            "top_graph_nodes": [1, 2, 3, 4, 5],
            "ranked_parquet": None,
            "phase_duration_seconds": {"WINDUP": 5.0},
        }

        handoff = ExportHandoff.from_windup(
            sprint_id="sprint-789",
            scorecard=scorecard,
        )

        facts_from_handoff = collect_export_handoff_facts(handoff=handoff)
        facts_from_scorecard = collect_export_handoff_facts(scorecard=scorecard)

        assert facts_from_handoff["sprint_id"] == facts_from_scorecard["sprint_id"]
        assert facts_from_handoff["gnn_predictions"] == facts_from_scorecard["gnn_predictions"]
        assert facts_from_handoff["top_nodes_count"] == facts_from_scorecard["top_nodes_count"]

    def test_none_handoff_returns_defaults(self):
        """None handoff returns default values without crashing."""
        from hledac.universal.runtime.shadow_inputs import collect_export_handoff_facts

        facts = collect_export_handoff_facts(handoff=None, sprint_id="unknown")

        assert facts["sprint_id"] == "unknown"
        assert facts["synthesis_engine"] == "unknown"
        assert facts["gnn_predictions"] == 0
        assert facts["top_nodes_count"] == 0
        assert facts["ranked_parquet_present"] is False
