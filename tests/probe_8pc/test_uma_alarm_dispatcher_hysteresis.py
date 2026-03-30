"""
Sprint 8PC D.2: UMAAlarmDispatcher — hysteresis prevents rapid re-triggering.

B.2 Invariant: hysteresis cooldown of 2s between same-state callbacks.
"""
import asyncio
import sys
from unittest.mock import patch, AsyncMock

sys.path.insert(0, "/Users/vojtechhamada/PycharmProjects/Hledac")

from hledac.universal.core.resource_governor import (
    UMAAlarmDispatcher,
    UMA_STATE_CRITICAL,
    _HYSTERESIS_COOLDOWN_SEC,
)


async def test_rapid_warn_critical_warn_critical_yields_max_2_calls():
    """Rapid WARN→CRITICAL→WARN→CRITICAL transitions: callback at most 2x."""
    from hledac.universal.core.resource_governor import _reset_uma_hysteresis_for_testing

    _reset_uma_hysteresis_for_testing()

    dispatcher = UMAAlarmDispatcher()

    call_times = []

    async def my_callback():
        call_times.append(asyncio.get_running_loop().time())

    dispatcher.register_callback(UMA_STATE_CRITICAL, my_callback)

    states = [
        ("warn", 6.1),
        ("critical", 6.6),
        ("warn", 6.1),
        ("critical", 6.6),
        ("critical", 6.6),
        ("critical", 6.6),
    ]

    state_iter = iter(states)

    def make_status(state, gib):
        s = AsyncMock()
        s.state = state
        s.system_used_gib = gib
        return s

    with patch("hledac.universal.core.resource_governor.sample_uma_status") as mock_sample_fn:
        mock_sample_fn.return_value = make_status("ok", 5.0)

        await dispatcher.start_monitoring(interval_s=0.02)

        # Inject state changes rapidly
        for _ in range(6):
            state_val, gib = next(state_iter)
            mock_sample_fn.return_value = make_status(state_val, gib)
            await asyncio.sleep(0.05)

        await asyncio.sleep(0.1)
        await dispatcher.stop()

    # Hysteresis is 2s but our intervals are 0.05s — so at most 1-2 calls
    # because first CRITICAL fires, second is <2s away
    max_allowed = 2
    assert len(call_times) <= max_allowed, (
        f"Expected <={max_allowed} calls due to 2s hysteresis, got {len(call_times)}"
    )
    print(f"[PASS] test_rapid_warn_critical: calls={len(call_times)} (hysteresis {_HYSTERESIS_COOLDOWN_SEC}s)")


async def test_hysteresis_cooldown_is_2_seconds():
    """B.2: The cooldown constant is exactly 2.0 seconds."""
    assert _HYSTERESIS_COOLDOWN_SEC == 2.0, f"Expected 2.0, got {_HYSTERESIS_COOLDOWN_SEC}"
    print(f"[PASS] test_hysteresis_cooldown_is_2_seconds: {_HYSTERESIS_COOLDOWN_SEC}s")


if __name__ == "__main__":
    asyncio.run(test_rapid_warn_critical_warn_critical_yields_max_2_calls())
    asyncio.run(test_hysteresis_cooldown_is_2_seconds())
