"""
Sprint 8VI §B: _get_adaptive_priority range test.
"""
import pytest
from runtime.sprint_scheduler import SprintScheduler, SprintSchedulerConfig

def test_rl_adaptive_priority_range():
    """_get_adaptive_priority must return value in [0.0, 1.0]."""
    config = SprintSchedulerConfig()
    scheduler = SprintScheduler(config)

    scheduler._pivot_rewards["domain_to_ct"] = [0.9, 0.8, 0.95]
    p = scheduler._get_adaptive_priority("domain_to_ct", base_priority=0.5)
    assert 0.0 <= p <= 1.0

    # Good history should beat unknown
    p_unknown = scheduler._get_adaptive_priority("unknown_type", base_priority=0.5)
    assert p >= p_unknown

    # Unknown type returns base
    p_base = scheduler._get_adaptive_priority("never_seen", base_priority=0.4)
    assert p_base == 0.4
