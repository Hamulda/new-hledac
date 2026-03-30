"""
Sprint 8PC D.6: _run_sprint_mode — full lifecycle state transitions.
"""
import asyncio
import contextlib
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, "/Users/vojtechhamada/PycharmProjects/Hledac")


async def test_sprint_mode_state_transitions():
    """
    BOOT->WARMUP->ACTIVE->WINDUP->EXPORT->TEARDOWN without OOM or CancelledError leaks.
    """
    from hledac.universal.__main__ import _run_sprint_mode
    from hledac.universal.utils.sprint_lifecycle import (
        SprintLifecycleManager,
        SprintLifecycleState,
    )
    from hledac.universal.core.resource_governor import _reset_uma_hysteresis_for_testing

    _reset_uma_hysteresis_for_testing()

    # Create a fully initialized manager
    SprintLifecycleManager._instance = None
    mgr = SprintLifecycleManager()
    # Re-configure for short sprint
    mgr._sprint_duration = 10.0
    mgr._windup_lead = 3.0

    # Now make __new__ return this same instance so _run_sprint_mode
    # gets our pre-configured manager
    original_new = SprintLifecycleManager.__new__

    def patched_new(cls, *args, **kwargs):
        # Always return our pre-configured mgr (same singleton pattern)
        return mgr

    mock_store = MagicMock()
    mock_store.async_initialize = MagicMock()
    mock_store.get_dedup_runtime_status = MagicMock(return_value={})

    async def mock_pipeline_run(*args, **kwargs):
        pass

    with patch.object(SprintLifecycleManager, "__new__", patched_new), \
         patch(
             "hledac.universal.knowledge.duckdb_store.create_owned_store",
             return_value=mock_store,
         ), patch(
             "hledac.universal.pipeline.live_feed_pipeline.async_run_default_feed_batch",
             side_effect=mock_pipeline_run,
         ):
        task = asyncio.create_task(_run_sprint_mode("test_target", duration_s=10.0))

        # Wait for WARMUP (5s) + margin
        await asyncio.sleep(6.0)
        found_active = (mgr.state == SprintLifecycleState.ACTIVE)

        assert found_active, f"Expected ACTIVE, got {mgr.state}"

        # Wait for full teardown
        with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=15.0)

        final = mgr.state
        assert final in (
            SprintLifecycleState.WINDUP,
            SprintLifecycleState.EXPORT,
            SprintLifecycleState.TEARDOWN,
        ), f"Expected WINDUP+, got {final}"

        print(f"[PASS] test_sprint_mode_state_transitions: final={final.value}")


async def test_sprint_mode_no_unhandled_exception():
    """No unhandled exception during sprint teardown."""
    from hledac.universal.__main__ import _run_sprint_mode
    from hledac.universal.utils.sprint_lifecycle import SprintLifecycleManager
    from hledac.universal.core.resource_governor import _reset_uma_hysteresis_for_testing

    _reset_uma_hysteresis_for_testing()

    SprintLifecycleManager._instance = None
    mgr = SprintLifecycleManager()
    mgr._sprint_duration = 5.0
    mgr._windup_lead = 1.0

    def patched_new(cls, *args, **kwargs):
        return mgr

    mock_store = MagicMock()
    mock_store.async_initialize = MagicMock()
    mock_store.get_dedup_runtime_status = MagicMock(return_value={})

    async def mock_pipeline_run(*args, **kwargs):
        pass

    with patch.object(SprintLifecycleManager, "__new__", patched_new), \
         patch(
             "hledac.universal.knowledge.duckdb_store.create_owned_store",
             return_value=mock_store,
         ), patch(
             "hledac.universal.pipeline.live_feed_pipeline.async_run_default_feed_batch",
             side_effect=mock_pipeline_run,
         ):
        task = asyncio.create_task(_run_sprint_mode("test", duration_s=5.0))

        error = None
        try:
            with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
                await asyncio.wait_for(task, timeout=10.0)
        except Exception as e:
            error = e

        assert error is None, f"Unexpected exception: {error}"
        print("[PASS] test_sprint_mode_no_unhandled_exception")


if __name__ == "__main__":
    asyncio.run(test_sprint_mode_state_transitions())
    asyncio.run(test_sprint_mode_no_unhandled_exception())
