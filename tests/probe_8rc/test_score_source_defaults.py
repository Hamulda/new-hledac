"""
Sprint 8RC — Test C.1: score_source() default tier ordering.

Invariant: dark > structured_ti > clearnet > academic (base tier weights only).
"""
import pytest
from hledac.universal.runtime.sprint_scheduler import SprintScheduler, SprintSchedulerConfig


class TestSprint8RCScoreSourceDefaults:
    """Test B.1 base tier weights — no hit_rate multipliers, no novelty bonuses."""

    def test_score_source_dark_higher_than_structured_ti(self):
        cfg = SprintSchedulerConfig()
        sched = SprintScheduler(cfg)
        # dark=1.2, structured_ti=1.0 → dark should score higher
        assert sched.score_source("dark") > sched.score_source("structured_ti")

    def test_score_source_structured_ti_higher_than_clearnet(self):
        cfg = SprintSchedulerConfig()
        sched = SprintScheduler(cfg)
        # structured_ti=1.0, clearnet=0.8
        assert sched.score_source("structured_ti") > sched.score_source("clearnet")

    def test_score_source_clearnet_higher_than_academic(self):
        cfg = SprintSchedulerConfig()
        sched = SprintScheduler(cfg)
        # clearnet=0.8, academic=0.6
        assert sched.score_source("clearnet") > sched.score_source("academic")

    def test_score_source_dark_higher_than_academic(self):
        cfg = SprintSchedulerConfig()
        sched = SprintScheduler(cfg)
        assert sched.score_source("dark") > sched.score_source("academic")

    def test_score_source_unknown_defaults_to_07(self):
        cfg = SprintSchedulerConfig()
        sched = SprintScheduler(cfg)
        # unknown type falls to 0.7 — should be between clearnet(0.8) and academic(0.6)
        assert 0.65 < sched.score_source("unknown_type") < 0.85
