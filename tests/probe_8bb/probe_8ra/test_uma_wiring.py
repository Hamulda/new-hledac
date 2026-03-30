"""
test_uma_alarm_dispatcher_wiring.py
Sprint 8RA C.5 / D.8 — UMAAlarmDispatcher CRITICAL callback → scheduler.request_early_windup()
"""
import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, ".")


@pytest.mark.asyncio
async def test_uma_critical_triggers_windup():
    """CRITICAL alarm callback must call scheduler.request_early_windup()."""
    from hledac.universal.core.resource_governor import (
        UMAAlarmDispatcher,
        UMA_STATE_CRITICAL,
    )
    from hledac.universal.runtime.sprint_scheduler import (
        SprintScheduler,
        SprintSchedulerConfig,
    )

    config = SprintSchedulerConfig(sprint_duration_s=60.0)
    scheduler = SprintScheduler(config)

    windup_called = False

    async def mock_windup():
        nonlocal windup_called
        windup_called = True

    scheduler.request_early_windup = mock_windup

    dispatcher = UMAAlarmDispatcher()
    dispatcher.register_callback(
        UMA_STATE_CRITICAL,
        lambda: asyncio.create_task(_trigger_critical(scheduler)),
    )

    async def _trigger_critical(sched):
        sched.request_early_windup()

    # Simulate CRITICAL state dispatch
    await dispatcher._dispatch(UMA_STATE_CRITICAL)

    assert windup_called, "request_early_windup was not called"


@pytest.mark.asyncio
async def test_uma_emergency_triggers_abort():
    """EMERGENCY alarm callback must call scheduler.request_immediate_abort()."""
    from hledac.universal.core.resource_governor import (
        UMAAlarmDispatcher,
        UMA_STATE_EMERGENCY,
    )
    from hledac.universal.runtime.sprint_scheduler import (
        SprintScheduler,
        SprintSchedulerConfig,
    )

    config = SprintSchedulerConfig(sprint_duration_s=60.0)
    scheduler = SprintScheduler(config)

    abort_called = False

    async def mock_abort():
        nonlocal abort_called
        abort_called = True

    scheduler.request_immediate_abort = mock_abort

    dispatcher = UMAAlarmDispatcher()
    dispatcher.register_callback(
        UMA_STATE_EMERGENCY,
        lambda: asyncio.create_task(_trigger_emergency(scheduler)),
    )

    async def _trigger_emergency(sched):
        sched.request_immediate_abort()

    await dispatcher._dispatch(UMA_STATE_EMERGENCY)

    assert abort_called, "request_immediate_abort was not called"
