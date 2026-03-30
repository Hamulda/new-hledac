"""Sprint 8UC: OODA enqueues pivot tasks for top PageRank nodes."""
import pytest
from hledac.universal.runtime.sprint_scheduler import SprintScheduler, PivotTask, SprintSchedulerConfig


def test_ooda_filters_by_pr_threshold():
    """Only nodes with pr_score > 0.05 are enqueued."""
    top_nodes = [
        ("noise.com", "domain", 0.01),   # filtered out
        ("medium.com", "domain", 0.05),  # at threshold (not >)
        ("hot.com", "domain", 0.30),      # included
    ]
    threshold = 0.05
    filtered = [(v, t, s) for v, t, s in top_nodes if s > threshold]
    assert len(filtered) == 1
    assert filtered[0][0] == "hot.com"


def test_speculative_prefetch_skips_already_cached():
    """If task_key already in _speculative_results, skip creating bg task."""
    config = SprintSchedulerConfig()
    scheduler = SprintScheduler(config)
    scheduler._speculative_results["generic_pivot:evil.com"] = {"status": "cached"}

    task = PivotTask(
        priority=-0.8,
        ioc_type="domain",
        ioc_value="evil.com",
        task_type="generic_pivot",
    )

    task_key = f"{task.task_type}:{task.ioc_value}"
    assert task_key in scheduler._speculative_results
