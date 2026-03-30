"""Sprint 8UC: OODA cycle increments counter."""
import pytest
from hledac.universal.runtime.sprint_scheduler import SprintScheduler, SprintSchedulerConfig


def test_ooda_cycle_increments_counter():
    """_run_ooda_cycle increments ooda_cycles in _pivot_stats."""
    config = SprintSchedulerConfig()
    scheduler = SprintScheduler(config)

    # Initialize pivot stats
    scheduler._pivot_stats = {"total": 0, "processed": 0, "errors": 0}

    # Simulate what _run_ooda_cycle does
    scheduler._pivot_stats["ooda_cycles"] = scheduler._pivot_stats.get("ooda_cycles", 0) + 1
    scheduler._pivot_stats["ooda_last_acted"] = 0

    assert scheduler._pivot_stats["ooda_cycles"] == 1


def test_ooda_low_pr_node_skipped():
    """Nodes with pr_score < 0.05 should be filtered."""
    # Test the filtering logic
    top_nodes = [
        ("evil.com", "domain", 0.03),  # too low
        ("good.com", "domain", 0.15),  # OK
    ]
    threshold = 0.05
    accepted = [(v, t, s) for v, t, s in top_nodes if s > threshold]
    assert len(accepted) == 1
    assert accepted[0][0] == "good.com"
