"""
D.1: SprintScheduler.run() s timeout 2s → žádný AttributeError.
"""
import asyncio
import sys
import time

sys.path.insert(0, ".")


async def test_lifecycle_adapter_no_attribute_error():
    from hledac.universal.runtime.sprint_scheduler import (
        SprintScheduler,
        SprintSchedulerConfig,
    )
    from hledac.universal.runtime.sprint_lifecycle import SprintLifecycleManager

    sched = SprintScheduler(SprintSchedulerConfig())
    lc = SprintLifecycleManager(sprint_duration_s=5.0)
    t = time.monotonic()

    try:
        await asyncio.wait_for(
            sched.run(lifecycle=lc, sources=[], now_monotonic=None), timeout=2
        )
    except asyncio.TimeoutError:
        elapsed = (time.monotonic() - t) * 1000
        assert elapsed > 0
        print(f"PASS: run() reached timeout (2s) — no AttributeError ({elapsed:.0f}ms)")
        return
    except AttributeError as e:
        raise AssertionError(f"BLOCKER AttributeError: {e}")


if __name__ == "__main__":
    asyncio.run(test_lifecycle_adapter_no_attribute_error())
