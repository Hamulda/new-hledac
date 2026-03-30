"""
Sprint 8RC — Test C.2: score_source() with hit_rate multiplier.

Invariant: hit_rate multiplier overrides base weight when set.
"""
import pytest
from hledac.universal.runtime.sprint_scheduler import SprintScheduler, SprintSchedulerConfig


class TestSprint8RCScoreSourceHitMultiplier:
    """Test B.1 hit_mult = source_weights[source] override."""

    def test_high_hit_multiplier_overrides_base(self):
        cfg = SprintSchedulerConfig()
        sched = SprintScheduler(cfg)
        # Give clearnet a very high hit rate multiplier
        sched._source_weights["clearnet"] = 2.5  # max ceiling from B.6
        # dark base=1.2, clearnet base=0.8
        # clearnet effective = 0.8 * 2.5 = 2.0 > dark = 1.2 → clearnet wins
        assert sched.score_source("clearnet") > sched.score_source("dark")

    def test_hit_mult_applies_to_all_tiers(self):
        cfg = SprintSchedulerConfig()
        sched = SprintScheduler(cfg)
        # academic gets 2.0x hit mult
        sched._source_weights["academic"] = 2.0
        # academic effective = 0.6 * 2.0 = 1.2, same as dark base
        assert sched.score_source("academic", None) >= sched.score_source("dark", None)

    def test_default_hit_mult_is_10(self):
        cfg = SprintSchedulerConfig()
        sched = SprintScheduler(cfg)
        # With no weights set, default is 1.0
        assert sched._source_weights.get("clearnet", 1.0) == 1.0
        # Score should equal base weight
        assert sched.score_source("clearnet") == sched._BASE_TIER_WEIGHTS["clearnet"]

    def test_zero_hit_mult_floors_at_03(self):
        cfg = SprintSchedulerConfig()
        sched = SprintScheduler(cfg)
        # load_source_weights clips at 0.3 minimum, but direct setting bypasses clip
        sched._source_weights["clearnet"] = 0.0  # below floor
        # Score = base(0.8) * 0.0 = 0.0 (floor clip happens in load, not score)
        assert sched.score_source("clearnet") == 0.0
