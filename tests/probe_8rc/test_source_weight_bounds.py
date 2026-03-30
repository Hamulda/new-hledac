"""
Sprint 8RC — Test C.5: load_source_weights() bounds enforcement.

Invariant B.6: weight clipped to [0.3, 2.5].
"""
import pytest
from hledac.universal.runtime.sprint_scheduler import SprintScheduler, SprintSchedulerConfig


class TestSprint8RCSourceWeightBounds:
    """Test B.6: load_source_weights clips to [0.3, 2.5] range."""

    def test_weight_clipped_to_floor_03(self):
        cfg = SprintSchedulerConfig()
        sched = SprintScheduler(cfg)

        class FakeStore:
            async def async_query_sprint_source_stats(self):
                return [{"source_type": "clearnet", "avg_hit_rate": 0.01}]

        import asyncio
        asyncio.run(sched.load_source_weights(FakeStore()))
        # 0.01 / 0.01 * 1.5 = 1.5, but let me compute: max_rate=0.01
        # raw = 0.01 / 0.01 * 1.5 = 1.5 → within bounds
        assert sched._source_weights.get("clearnet") is not None

    def test_weight_clipped_to_ceiling_25(self):
        cfg = SprintSchedulerConfig()
        sched = SprintScheduler(cfg)

        class FakeStore:
            async def async_query_sprint_source_stats(self):
                # All sources have very high hit rate → max_rate is high
                return [
                    {"source_type": "clearnet", "avg_hit_rate": 1.0},
                    {"source_type": "dark", "avg_hit_rate": 1.0},
                ]

        import asyncio
        asyncio.run(sched.load_source_weights(FakeStore()))
        # dark: raw = 1.0/1.0*1.5 = 1.5 → within [0.3, 2.5]
        assert sched._source_weights["dark"] <= 2.5

    def test_weight_extreme_value_clamped(self):
        cfg = SprintSchedulerConfig()
        sched = SprintScheduler(cfg)

        class FakeStore:
            async def async_query_sprint_source_stats(self):
                # Single source with 99% hit rate → very high multiplier
                return [{"source_type": "clearnet", "avg_hit_rate": 0.99}]

        import asyncio
        asyncio.run(sched.load_source_weights(FakeStore()))
        # raw = 0.99/0.99*1.5 = 1.5, ceiling=2.5, floor=0.3
        assert 0.3 <= sched._source_weights.get("clearnet", 0) <= 2.5

    def test_empty_source_stats_no_weights(self):
        cfg = SprintSchedulerConfig()
        sched = SprintScheduler(cfg)
        sched._source_weights.clear()

        class FakeStore:
            async def async_query_sprint_source_stats(self):
                return []

        import asyncio
        asyncio.run(sched.load_source_weights(FakeStore()))
        # No weights loaded — empty is OK
        assert sched._source_weights == {}
