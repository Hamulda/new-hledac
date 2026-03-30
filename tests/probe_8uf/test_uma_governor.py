"""Test UMA governor callbacks (Sprint 8UF B.2)."""
import pytest
import asyncio
import unittest.mock as mock

from core.resource_governor import (
    UMAAlarmDispatcher,
    UMA_STATE_CRITICAL,
    UMA_STATE_EMERGENCY,
)


class TestUMAGovernor:
    """UMA governor callback tests."""

    @pytest.mark.asyncio
    async def test_critical_callback_fires(self):
        """Critical callback fires when memory exceeds threshold."""
        dispatcher = UMAAlarmDispatcher()
        callback_called = False

        async def critical_cb():
            nonlocal callback_called
            callback_called = True

        dispatcher.register_callback(UMA_STATE_CRITICAL, critical_cb)

        with mock.patch('core.resource_governor.sample_uma_status') as mock_sample:
            mock_sample.return_value = mock.MagicMock(
                state=UMA_STATE_CRITICAL,
                system_used_gib=6.6
            )
            await dispatcher._check_and_dispatch()

        assert callback_called, "Critical callback should fire"

    @pytest.mark.asyncio
    async def test_emergency_callback_fires(self):
        """Emergency callback fires when memory exceeds emergency threshold."""
        dispatcher = UMAAlarmDispatcher()
        callback_called = False

        async def emergency_cb():
            nonlocal callback_called
            callback_called = True

        dispatcher.register_callback(UMA_STATE_EMERGENCY, emergency_cb)

        with mock.patch('core.resource_governor.sample_uma_status') as mock_sample:
            mock_sample.return_value = mock.MagicMock(
                state=UMA_STATE_EMERGENCY,
                system_used_gib=7.1
            )
            await dispatcher._check_and_dispatch()

        assert callback_called, "Emergency callback should fire"

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        """Stop cancels the monitoring task."""
        dispatcher = UMAAlarmDispatcher()
        await dispatcher.start_monitoring(interval_s=0.1)
        task = dispatcher._task
        assert task is not None
        await dispatcher.stop()
        # After stop(), _task is set to None, but the original task should be done/cancelled
        assert task.cancelled() or task.done()

    @pytest.mark.asyncio
    async def test_no_callback_below_threshold(self):
        """No callback fires when memory is below threshold."""
        dispatcher = UMAAlarmDispatcher()
        callback_called = False

        async def critical_cb():
            nonlocal callback_called
            callback_called = True

        dispatcher.register_callback(UMA_STATE_CRITICAL, critical_cb)

        with mock.patch('core.resource_governor.sample_uma_status') as mock_sample:
            mock_sample.return_value = mock.MagicMock(
                state="ok",
                system_used_gib=4.0
            )
            await dispatcher._check_and_dispatch()

        assert not callback_called, "No callback should fire below threshold"
