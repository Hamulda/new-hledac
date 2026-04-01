"""
Probe: Graph facts can be collected without scheduler dependency.

Sprint 8VK §Invariant: graph facts can be collected from duckdb_store._ioc_graph
without any SprintScheduler involvement.
"""

import pytest
from unittest.mock import MagicMock


class TestGraphSummaryCollector:
    """Verify graph facts collection works independently of scheduler."""

    def test_ioc_graph_stats_collected(self):
        """DuckPGQGraph.stats() can be collected directly."""
        from hledac.universal.runtime.shadow_inputs import collect_graph_summary

        mock_graph = MagicMock()
        mock_graph.stats.return_value = {
            "nodes": 42,
            "edges": 137,
            "pgq_active": True,
        }
        mock_graph.get_top_nodes_by_degree.return_value = [
            {"id": "cve-2024-1", "type": "cve"},
            {"id": "192.168.1.1", "type": "ip"},
        ]

        bundle = collect_graph_summary(ioc_graph=mock_graph)

        assert bundle.node_count == 42
        assert bundle.edge_count == 137
        assert bundle.pgq_active is True
        assert bundle.backend == "duckpgq"
        assert len(bundle.top_nodes) == 2

    def test_scorecard_top_nodes_as_compat_path(self):
        """scorecard top_graph_nodes works as compat path."""
        from hledac.universal.runtime.shadow_inputs import collect_graph_summary

        scorecard = {
            "top_graph_nodes": [{"id": "node-a"}, {"id": "node-b"}, {"id": "node-c"}],
        }

        bundle = collect_graph_summary(scorecard=scorecard)

        assert bundle.top_nodes == [{"id": "node-a"}, {"id": "node-b"}, {"id": "node-c"}]
        assert bundle.backend == "unknown"
        assert bundle.node_count == 0  # unknown from compat path

    def test_empty_inputs_returns_empty_bundle(self):
        """None inputs return empty bundle without crashing."""
        from hledac.universal.runtime.shadow_inputs import collect_graph_summary

        bundle = collect_graph_summary()

        assert bundle.node_count == 0
        assert bundle.edge_count == 0
        assert bundle.top_nodes == []
        assert bundle.backend == "unknown"

    def test_graph_stats_without_top_nodes(self):
        """Graph stats works even if get_top_nodes_by_degree fails."""
        from hledac.universal.runtime.shadow_inputs import collect_graph_summary

        mock_graph = MagicMock()
        mock_graph.stats.return_value = {"nodes": 10, "edges": 5, "pgq_active": False}
        mock_graph.get_top_nodes_by_degree.side_effect = RuntimeError("DB not ready")

        bundle = collect_graph_summary(ioc_graph=mock_graph)

        assert bundle.node_count == 10
        assert bundle.edge_count == 5
        assert bundle.top_nodes == []  # graceful fallback
