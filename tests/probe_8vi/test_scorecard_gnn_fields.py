"""
Sprint 8VI §E: run_windup scorecard must contain GNN fields.
"""
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from runtime.windup_engine import run_windup

@pytest.mark.asyncio
async def test_scorecard_gnn_fields():
    """Scorecard dict must contain gnn_predicted_links, gnn_anomalies, ioc_graph."""
    scheduler = MagicMock()
    scheduler._finding_count = 3
    scheduler._all_findings = []
    scheduler._ioc_graph = MagicMock()
    scheduler._ioc_graph.stats.return_value = {"nodes": 2, "edges": 1, "pgq_active": False}
    scheduler._ioc_graph.export_edge_list.return_value = []
    scheduler._ioc_graph.get_top_nodes_by_degree.return_value = []
    scheduler._ioc_graph.checkpoint = MagicMock()
    scheduler.deduplicate_and_rank_findings = MagicMock(return_value=None)
    scheduler.enqueue_pivot = AsyncMock()
    scheduler._synthesis_engine = "heuristic"
    scheduler.record_pivot_outcome = MagicMock()
    scheduler._pivot_rewards = {}
    scheduler._recent_iocs = []

    import time
    t = time.monotonic()

    with patch("runtime.windup_engine._safe_get_breaker_states", return_value={}):
        scorecard = await run_windup(scheduler, "test", t, t + 1.0)

    assert "gnn_predicted_links" in scorecard, "gnn_predicted_links required"
    assert "gnn_anomalies" in scorecard, "gnn_anomalies required"
    assert "ioc_graph" in scorecard, "ioc_graph required"
    assert "accepted_findings_count" in scorecard
    assert "peak_rss_mb" in scorecard
