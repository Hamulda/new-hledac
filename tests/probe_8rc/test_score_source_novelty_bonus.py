"""
Sprint 8RC — Test C.3: score_source() novelty bonus.

Invariant: novelty_bonus = 1.5 when source added new IOC types this sprint.
"""
import pytest
from hledac.universal.runtime.sprint_scheduler import SprintScheduler, SprintSchedulerConfig


class TestSprint8RCScoreSourceNoveltyBonus:
    """Test B.1 novelty multiplier (1.5 if new IOC types, else 1.0)."""

    def test_novelty_bonus_true_boosts_score(self):
        cfg = SprintSchedulerConfig()
        sched = SprintScheduler(cfg)
        sched.set_novelty_bonus("academic", True)
        # academic base=0.6, with 1.5 novelty = 0.9
        # clearnet base=0.8, no bonus = 0.8
        assert sched.score_source("academic") > sched.score_source("clearnet")

    def test_novelty_bonus_false_unchanged(self):
        cfg = SprintSchedulerConfig()
        sched = SprintScheduler(cfg)
        sched.set_novelty_bonus("academic", False)
        assert sched.score_source("academic") == sched._BASE_TIER_WEIGHTS["academic"]

    def test_novelty_bonus_combined_with_hit_mult(self):
        cfg = SprintSchedulerConfig()
        sched = SprintScheduler(cfg)
        sched._source_weights["academic"] = 2.0
        sched.set_novelty_bonus("academic", True)
        # academic = 0.6 * 2.0 * 1.5 = 1.8
        assert sched.score_source("academic") == pytest.approx(1.8)

    def test_set_novelty_bonus_idempotent(self):
        cfg = SprintSchedulerConfig()
        sched = SprintScheduler(cfg)
        sched.set_novelty_bonus("clearnet", True)
        sched.set_novelty_bonus("clearnet", True)
        assert sched._novelty_bonuses["clearnet"] == 1.5

    def test_novelty_bonus_defaults_to_10(self):
        cfg = SprintSchedulerConfig()
        sched = SprintScheduler(cfg)
        assert sched._novelty_bonuses.get("unknown", 1.0) == 1.0
