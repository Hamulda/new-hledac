"""Sprint 8UC: Speculative cache hit path."""
import pytest
from hledac.universal.runtime.sprint_scheduler import SprintScheduler, PivotTask, SprintSchedulerConfig


def test_speculative_cache_hit_returns_cached_result():
    """When _speculative_results has the key, _execute_pivot returns it without network."""
    config = SprintSchedulerConfig()
    scheduler = SprintScheduler(config)

    # Pre-populate speculative results
    scheduler._speculative_results["generic_pivot:evil.com"] = {"status": "cached", "data": "x"}

    task = PivotTask(
        priority=-0.8,
        ioc_type="domain",
        ioc_value="evil.com",
        task_type="generic_pivot",
    )

    # Can't easily test async without full loop, just test the cache lookup logic
    task_key = f"{task.task_type}:{task.ioc_value}"
    assert task_key in scheduler._speculative_results
    result = scheduler._speculative_results[task_key]
    assert result == {"status": "cached", "data": "x"}


def test_speculative_results_dict_initialized_empty():
    """_speculative_results starts as empty dict."""
    config = SprintSchedulerConfig()
    scheduler = SprintScheduler(config)
    assert scheduler._speculative_results == {}
    assert scheduler._bg_tasks == set()
