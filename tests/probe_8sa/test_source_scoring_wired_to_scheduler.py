"""
D.11: SprintScheduler s mock source list → run() volá prioritize_sources().
"""
import asyncio
import sys
import time
from unittest.mock import patch

sys.path.insert(0, ".")


async def test_source_scoring_wired_to_scheduler():
    from hledac.universal.runtime.sprint_scheduler import (
        SprintScheduler,
        SprintSchedulerConfig,
    )
    from hledac.universal.runtime.sprint_lifecycle import SprintLifecycleManager

    config = SprintSchedulerConfig(max_cycles=2, sprint_duration_s=2.0)
    sched = SprintScheduler(config)
    lc = SprintLifecycleManager(sprint_duration_s=2.0)

    # Spy on prioritize_sources
    called = False

    original_prioritize = sched.prioritize_sources

    def spy_prioritize(candidates, graph_stats=None):
        nonlocal called
        called = True
        return original_prioritize(candidates, graph_stats)

    sched.prioritize_sources = spy_prioritize

    # Short 500ms sprint — should call prioritize at start
    sources = ["cisa_kev", "threatfox_ioc", "urlhaus_recent"]
    try:
        await asyncio.wait_for(
            sched.run(lifecycle=lc, sources=sources, now_monotonic=None),
            timeout=1.0,
        )
    except asyncio.TimeoutError:
        pass  # expected

    assert called, "prioritize_sources was NOT called in run() loop"
    print("PASS: prioritize_sources() called in run() loop")


if __name__ == "__main__":
    asyncio.run(test_source_scoring_wired_to_scheduler())
