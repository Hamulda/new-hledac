"""
Sprint 8PC D.3: UMAAlarmDispatcher — clean stop without unhandled exceptions.
"""
import asyncio
import sys
from unittest.mock import patch, AsyncMock

sys.path.insert(0, "/Users/vojtechhamada/PycharmProjects/Hledac")

from hledac.universal.core.resource_governor import (
    UMAAlarmDispatcher,
    UMA_STATE_EMERGENCY,
)


async def test_dispatcher_stop_is_clean():
    """stop() cancels the monitoring task cleanly with no unhandled exceptions."""
    from hledac.universal.core.resource_governor import _reset_uma_hysteresis_for_testing

    _reset_uma_hysteresis_for_testing()

    dispatcher = UMAAlarmDispatcher()

    async def noop_callback():
        pass

    dispatcher.register_callback(UMA_STATE_EMERGENCY, noop_callback)

    with patch("hledac.universal.core.resource_governor.sample_uma_status") as mock_sample_fn:
        mock_status = AsyncMock()
        mock_status.state = "ok"
        mock_status.system_used_gib = 5.0
        mock_sample_fn.return_value = mock_status

        await dispatcher.start_monitoring(interval_s=0.05)
        await asyncio.sleep(0.1)

        # Stop must be clean — no CancelledError leaks
        await dispatcher.stop()

        # Task should be None after stop
        assert dispatcher._task is None, "Task should be None after stop"
        assert dispatcher._running is False, "Dispatcher should not be running after stop"

    print("[PASS] test_dispatcher_stop_is_clean")


async def test_stop_idempotent():
    """Calling stop() twice is safe (no double-cancel)."""
    from hledac.universal.core.resource_governor import _reset_uma_hysteresis_for_testing

    _reset_uma_hysteresis_for_testing()

    dispatcher = UMAAlarmDispatcher()

    with patch("hledac.universal.core.resource_governor.sample_uma_status") as mock_sample_fn:
        mock_status = AsyncMock()
        mock_status.state = "ok"
        mock_status.system_used_gib = 5.0
        mock_sample_fn.return_value = mock_status

        await dispatcher.start_monitoring(interval_s=0.1)
        await asyncio.sleep(0.05)

        await dispatcher.stop()
        await dispatcher.stop()  # idempotent — must not raise

    print("[PASS] test_stop_idempotent")


if __name__ == "__main__":
    asyncio.run(test_dispatcher_stop_is_clean())
    asyncio.run(test_stop_idempotent())
