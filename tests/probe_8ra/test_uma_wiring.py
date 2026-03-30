"""
test_uma_alarm_dispatcher_wiring.py
Sprint 8RA C.5 / D.8 — CRITICAL/EMERGENCY callbacks registered and callable
"""
import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, ".")


@pytest.mark.asyncio
async def test_scheduler_has_request_early_windup():
    """SprintScheduler must have request_early_windup method."""
    from hledac.universal.runtime.sprint_scheduler import (
        SprintScheduler,
        SprintSchedulerConfig,
    )

    config = SprintSchedulerConfig(sprint_duration_s=60.0)
    scheduler = SprintScheduler(config)

    assert hasattr(scheduler, "request_early_windup")
    assert callable(scheduler.request_early_windup)


@pytest.mark.asyncio
async def test_scheduler_has_request_immediate_abort():
    """SprintScheduler must have request_immediate_abort method."""
    from hledac.universal.runtime.sprint_scheduler import (
        SprintScheduler,
        SprintSchedulerConfig,
    )

    config = SprintSchedulerConfig(sprint_duration_s=60.0)
    scheduler = SprintScheduler(config)

    assert hasattr(scheduler, "request_immediate_abort")
    assert callable(scheduler.request_immediate_abort)


@pytest.mark.asyncio
async def test_uma_dispatcher_accepts_critical_callback():
    """UMAAlarmDispatcher.register_callback accepts CRITICAL state."""
    from hledac.universal.core.resource_governor import (
        UMAAlarmDispatcher,
        UMA_STATE_CRITICAL,
    )

    dispatcher = UMAAlarmDispatcher()
    called = False

    async def cb():
        nonlocal called
        called = True

    dispatcher.register_callback(UMA_STATE_CRITICAL, cb)
    await dispatcher.start_monitoring(interval_s=0.1)
    await asyncio.sleep(0.3)
    await dispatcher.stop()
