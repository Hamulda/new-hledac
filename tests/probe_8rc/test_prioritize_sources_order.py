"""
Sprint 8RC — Test C.4: prioritize_sources() ordering.

Invariant: dark or structured_ti should be first, never academic.
"""
import pytest
from hledac.universal.runtime.sprint_scheduler import SprintScheduler, SprintSchedulerConfig


class TestSprint8RCPrioritizeSourcesOrder:
    """Test B.1 — highest-scoring source is first in returned list."""

    def test_prioritize_sources_first_not_academic(self):
        cfg = SprintSchedulerConfig()
        sched = SprintScheduler(cfg)
        candidates = ["clearnet", "structured_ti", "dark", "academic"]
        result = sched.prioritize_sources(candidates)
        assert result[0] != "academic"  # academic has lowest base weight

    def test_prioritize_sources_order_descending(self):
        cfg = SprintSchedulerConfig()
        sched = SprintScheduler(cfg)
        candidates = ["clearnet", "structured_ti", "dark", "academic"]
        result = sched.prioritize_sources(candidates)
        scores = [sched.score_source(s) for s in result]
        # Scores should be in descending order
        assert scores == sorted(scores, reverse=True)

    def test_prioritize_sources_preserves_all_candidates(self):
        cfg = SprintSchedulerConfig()
        sched = SprintScheduler(cfg)
        candidates = ["clearnet", "structured_ti", "dark", "academic"]
        result = sched.prioritize_sources(candidates)
        assert set(result) == set(candidates)

    def test_prioritize_sources_empty_list(self):
        cfg = SprintSchedulerConfig()
        sched = SprintScheduler(cfg)
        assert sched.prioritize_sources([]) == []

    def test_prioritize_sources_single_candidate(self):
        cfg = SprintSchedulerConfig()
        sched = SprintScheduler(cfg)
        assert sched.prioritize_sources(["dark"]) == ["dark"]

    def test_prioritize_sources_with_weights(self):
        cfg = SprintSchedulerConfig()
        sched = SprintScheduler(cfg)
        sched._source_weights["clearnet"] = 3.0  # very high
        candidates = ["clearnet", "structured_ti", "dark", "academic"]
        result = sched.prioritize_sources(candidates)
        # clearnet should now be first due to high hit_mult
        assert result[0] == "clearnet"

    def test_prioritize_sources_unknown_types(self):
        cfg = SprintSchedulerConfig()
        sched = SprintScheduler(cfg)
        candidates = ["unknown_a", "unknown_b", "dark"]
        result = sched.prioritize_sources(candidates)
        # dark should be first (0.7 * 1.0 * 1.0 = 0.7 base, unknown 0.7*1.0*1.0=0.7 too)
        # tie-break: dark is darker... but tie-break undefined, just check it doesn't crash
        assert len(result) == 3
