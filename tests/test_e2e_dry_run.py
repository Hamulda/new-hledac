"""
Sprint 8VI §E: E2E dry-run test — celá pipeline bez reálných HTTP requestů.
30s timeout, max 10 findings, všechny external fetches mockované.
"""
import asyncio
import pathlib
import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


def test_none_file_absent_after_run():
    """P0 guard: soubor 'None' nesmí existovat."""
    assert not pathlib.Path("None").exists(), \
        "Soubor 'None' existuje — porušen P0 guard"


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_e2e_pipeline_completes():
    """Spustí WARMUP → mock ACTIVE → WINDUP → EXPORT."""
    # Sprint 8VY: run_warmup moved from runtime/sprint_lifecycle → __main__.py (canonical WARMUP truth)
    # Use importlib to load __main__ directly (pytest's --main__ is pytest's own module)
    import os, importlib.util
    _ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    _MAIN_PY = os.path.join(_ROOT, "hledac", "universal", "__main__.py")
    _spec = importlib.util.spec_from_file_location("hledac_main", _MAIN_PY)
    assert _spec is not None, f"Failed to load spec for {_MAIN_PY}"
    _main_mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_main_mod)  # type: ignore
    run_warmup = _main_mod.run_warmup
    from runtime.windup_engine import run_windup
    from export.sprint_exporter import export_sprint
    from runtime.sprint_scheduler import SprintScheduler, SprintSchedulerConfig

    # Mock scheduler s potřebnými atributy
    config = SprintSchedulerConfig()
    scheduler = SprintScheduler(config)
    scheduler._finding_count = 5
    scheduler._all_findings = [
        {"url": f"http://test{i}.com", "title": f"Finding {i}",
         "snippet": f"C2 at 10.0.0.{i}", "source": "test", "confidence": 0.8}
        for i in range(5)
    ]
    scheduler._ioc_graph = MagicMock()
    scheduler._ioc_graph.stats.return_value = {"nodes": 3, "edges": 2, "pgq_active": False}
    scheduler._ioc_graph.export_edge_list.return_value = []
    scheduler._ioc_graph.get_top_nodes_by_degree.return_value = []
    scheduler._ioc_graph.checkpoint = MagicMock()
    scheduler._ioc_graph.merge_from_parquet = MagicMock(return_value=0)
    scheduler.deduplicate_and_rank_findings = MagicMock(return_value="/tmp/test.parquet")
    scheduler.enqueue_pivot = AsyncMock()
    scheduler._synthesis_engine = "heuristic"
    scheduler.record_pivot_outcome = MagicMock()
    scheduler._pivot_rewards = {}
    scheduler._recent_iocs = []
    scheduler._ioc_scorer = None

    import time
    t_now = time.monotonic()

    # WARMUP
    warmup_result = await run_warmup(scheduler, {})
    assert isinstance(warmup_result, dict)

    # WINDUP
    scorecard = await run_windup(
        scheduler, "test threat query", t_now, t_now + 5.0
    )
    assert isinstance(scorecard, dict)
    assert "peak_rss_mb" in scorecard
    assert "accepted_findings_count" in scorecard

    # EXPORT — Sprint 8VI: export_sprint(store, scorecard, sprint_id) signature
    # top_graph_nodes already in scorecard from run_windup()
    with patch("runtime.windup_engine._safe_get_breaker_states", return_value={}):
        export_result = await export_sprint(None, scorecard, "test_sprint_001")
    assert "report_json" in export_result
    assert "seeds_json" in export_result
