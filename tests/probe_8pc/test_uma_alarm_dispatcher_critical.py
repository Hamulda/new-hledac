"""
Sprint 8PC D.1: UMAAlarmDispatcher — CRITICAL callback fired on state transition.
B.1: UMA_STATE_CRITICAL imported from resource_governor (never raw strings).
B.2: Hysteresis 2s prevents callback storm.
"""
import asyncio
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, "/Users/vojtechhamada/PycharmProjects/Hledac")

from hledac.universal.core.resource_governor import (
    UMAAlarmDispatcher,
    UMA_STATE_CRITICAL,
    _reset_uma_hysteresis_for_testing,
)


async def test_dispatcher_calls_callback_on_critical_transition():
    """
    CRITICAL callback invoked when state transitions to critical.
    Tests the dispatcher via _check_and_dispatch directly (bypasses
    sample_uma_status closure-binding patch issue in mock context).
    """
    _reset_uma_hysteresis_for_testing()

    dispatcher = UMAAlarmDispatcher()
    call_count = 0

    async def my_callback():
        nonlocal call_count
        call_count += 1

    dispatcher.register_callback(UMA_STATE_CRITICAL, my_callback)

    # Build a plain status object (not MagicMock) to avoid nested-mock issues
    class MockStatus:
        def __init__(self, state_val, gib):
            self.state = state_val
            self.system_used_gib = gib

    mock_status = MockStatus(UMA_STATE_CRITICAL, 6.6)

    # Directly invoke _check_and_dispatch — this bypasses the
    # sample_uma_status closure-binding that makes module-level patch() ineffective
    with patch(
        "hledac.universal.core.resource_governor.sample_uma_status",
        return_value=mock_status,
    ):
        await dispatcher._check_and_dispatch()

    assert call_count >= 1, f"Expected >=1 callback, got {call_count}"
    print(f"[PASS] test_dispatcher_calls_callback_on_critical_transition: call_count={call_count}")


async def test_hysteresis_prevents_double_trigger():
    """
    B.2: Second CRITICAL within 2s cooldown does NOT call callback again.
    Tests via _check_and_dispatch to avoid sample_uma_status patch issue.
    """
    _reset_uma_hysteresis_for_testing()

    dispatcher = UMAAlarmDispatcher()
    call_count = 0

    async def my_callback():
        nonlocal call_count
        call_count += 1

    dispatcher.register_callback(UMA_STATE_CRITICAL, my_callback)

    class MockStatus:
        def __init__(self, state_val, gib):
            self.state = state_val
            self.system_used_gib = gib

    mock_status = MockStatus(UMA_STATE_CRITICAL, 6.6)

    with patch(
        "hledac.universal.core.resource_governor.sample_uma_status",
        return_value=mock_status,
    ):
        # First dispatch — should fire
        await dispatcher._check_and_dispatch()
        first_count = call_count

        # Immediate second dispatch (< 2s) — should be blocked by hysteresis
        await dispatcher._check_and_dispatch()

    assert first_count >= 1, f"First dispatch should fire: got {first_count}"
    # Second dispatch should be blocked by hysteresis (2s cooldown not elapsed)
    assert call_count == first_count, (
        f"Hysteresis failed: expected {first_count} calls, got {call_count}"
    )
    print(f"[PASS] test_hysteresis_prevents_double_trigger: calls={call_count}")


if __name__ == "__main__":
    asyncio.run(test_dispatcher_calls_callback_on_critical_transition())
    asyncio.run(test_hysteresis_prevents_double_trigger())
