"""
Sprint 8VI §B: record_pivot_outcome monotonicity test.
"""
import pytest
from runtime.sprint_scheduler import SprintScheduler, SprintSchedulerConfig

def test_rl_record_outcome_monotonic():
    """record_pivot_outcome must accumulate rewards without raising."""
    config = SprintSchedulerConfig()
    scheduler = SprintScheduler(config)

    scheduler.record_pivot_outcome("multi_engine_search", found_count=10, elapsed_s=5.0)
    scheduler.record_pivot_outcome("multi_engine_search", found_count=10, elapsed_s=5.0)

    assert "multi_engine_search" in scheduler._pivot_rewards
    assert len(scheduler._pivot_rewards["multi_engine_search"]) == 2

    # Unknown type with elapsed_s=0 is dropped (no reward)
    scheduler.record_pivot_outcome("unknown_type_zero", found_count=0, elapsed_s=0.0)
    assert "unknown_type_zero" not in scheduler._pivot_rewards  # dropped

    # Unknown type with valid elapsed_s is recorded
    scheduler.record_pivot_outcome("unknown_type_valid", found_count=0, elapsed_s=1.0)
    assert "unknown_type_valid" in scheduler._pivot_rewards
