"""
Sprint 7K: Lifecycle Closure — Unload Ordering + Batch Worker Shutdown + Safe Emergency Clear
================================================================================================
"""

import asyncio
import gc
import time
from unittest.mock import MagicMock, AsyncMock, patch

import pytest


class MockKVCache:
    """Minimal mock KV cache for warmup testing."""
    pass


def _make_engine():
    """Factory for Hermes3Engine with minimal mock state."""
    from hledac.universal.brain.hermes3_engine import Hermes3Engine
    engine = Hermes3Engine.__new__(Hermes3Engine)
    engine.config = MagicMock()
    engine._model = None
    engine._tokenizer = None
    engine._outlines_model = None
    engine._outlines_generators = {}
    engine._draft_model_obj = None
    engine._draft_model_name = None
    engine._speculative_enabled = False
    engine._num_draft_tokens = 4
    engine._supports_stream_generate = False
    engine._supports_draft = False
    engine._supports_kv_quant = False
    engine._kv_cache_stats = {}
    engine._system_prompt = ""
    engine._system_prompt_cache = None
    engine._system_prompt_hash = None
    engine._prefix_cache = {}
    engine._inference_executor = MagicMock()
    engine._inference_semaphore = asyncio.Semaphore(1)
    engine._batch_queue = None
    engine._batch_worker_task = None
    engine._batch_max_size = 8
    engine._batch_default_flush_interval = 2.0
    engine._batch_flush_interval = 2.0
    engine._batch_medium_pressure_depth = 64
    engine._batch_high_pressure_depth = 192
    engine._telemetry_ema = {
        'enqueue_to_dispatch_ms': 0.0, 'dispatch_to_result_ms': 0.0, 'batch_size': 0, 'queue_depth': 0
    }
    engine._telemetry_counters = {
        'batch_submitted': 0, 'batch_executed': 0, 'batch_fallback_single': 0,
        'schema_mismatch_flushes': 0, 'length_bin_mismatch_flushes': 0,
        'batch_shattered': 0, 'prompt_mismatch_flushes': 0,
        'emergency_guard_triggered': 0, 'emergency_batch_rejected': 0,
        'emergency_single_rejected': 0, 'emergency_pending_failed': 0,
        'adaptive_flush_default_entries': 0, 'adaptive_flush_medium_entries': 0,
        'adaptive_flush_fast_entries': 0,
    }
    engine._pending_futures = set()
    engine._ema_alpha = 0.3
    engine._flush_cycle_count = 0
    engine._age_bump_interval = 3
    engine._last_age_bump = 0
    engine._warmup_cache = None
    engine._last_gpu_memory = 0
    engine._prompt_cache = None
    engine._kv_cache_enabled = False
    engine._save_cache = AsyncMock()
    engine.invalidate_prefix_cache = MagicMock()
    engine._batch_worker_shutting_down = False
    return engine


async def _cleanup_worker(engine):
    """Cleanup helper for worker tasks."""
    if engine._batch_worker_task and not engine._batch_worker_task.done():
        engine._batch_worker_task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(engine._batch_worker_task), timeout=1.0)
        except (asyncio.CancelledError, asyncio.TimeoutError, RuntimeError):
            pass
    gc.collect()


@pytest.mark.asyncio
async def test_warmup_cache_evicted_on_unload():
    """_warmup_cache MUST be None after unload() completes."""
    engine = _make_engine()
    engine._warmup_cache = MockKVCache()
    assert engine._warmup_cache is not None
    await engine.unload()
    assert engine._warmup_cache is None


@pytest.mark.asyncio
async def test_batch_queue_nulled_post_unload():
    """_batch_queue MUST be None after unload() completes."""
    engine = _make_engine()
    engine._batch_queue = asyncio.PriorityQueue(maxsize=256)
    engine._pending_futures = set()
    engine._batch_worker_task = asyncio.create_task(engine._batch_worker())
    await asyncio.sleep(0.05)
    assert engine._batch_queue is not None
    await engine.unload()
    assert engine._batch_queue is None
    assert engine._batch_worker_task is None


@pytest.mark.asyncio
async def test_batch_worker_task_nulled_post_unload():
    """_batch_worker_task MUST be None after unload() completes."""
    engine = _make_engine()
    engine._batch_queue = asyncio.PriorityQueue(maxsize=256)
    engine._pending_futures = set()
    engine._batch_worker_task = asyncio.create_task(engine._batch_worker())
    await asyncio.sleep(0.05)
    assert engine._batch_worker_task is not None
    await engine.unload()
    assert engine._batch_worker_task is None


@pytest.mark.asyncio
async def test_pending_futures_resolved_normal_unload():
    """Pending futures MUST NOT hang on normal unload."""
    engine = _make_engine()
    engine._batch_queue = asyncio.PriorityQueue(maxsize=256)
    engine._pending_futures = set()
    engine._batch_worker_task = asyncio.create_task(engine._batch_worker())
    await asyncio.sleep(0.05)
    future1 = asyncio.Future()
    future2 = asyncio.Future()
    engine._pending_futures.add(future1)
    engine._pending_futures.add(future2)
    await engine.unload()
    assert future1.done()
    assert future2.done()


@pytest.mark.asyncio
async def test_pending_futures_failed_emergency_unload():
    """Pending futures MUST get RuntimeError on emergency unload."""
    engine = _make_engine()
    engine._batch_queue = asyncio.PriorityQueue(maxsize=256)
    engine._pending_futures = set()
    engine._batch_worker_task = asyncio.create_task(engine._batch_worker())
    await asyncio.sleep(0.05)
    with patch('hledac.universal.brain.hermes3_engine.is_emergency_unload_requested', return_value=True):
        future1 = asyncio.Future()
        future2 = asyncio.Future()
        engine._pending_futures.add(future1)
        engine._pending_futures.add(future2)
        await engine._shutdown_batch_worker(timeout=1.0)
    assert future1.done()
    assert future2.done()
    exc1 = future1.exception()
    exc2 = future2.exception()
    assert future1.cancelled() or (exc1 and 'emergency' in str(exc1).lower())
    assert future2.cancelled() or (exc2 and 'emergency' in str(exc2).lower())


@pytest.mark.asyncio
async def test_safe_clear_conditions_not_auto_cleared():
    """Emergency flag MUST NOT be auto-cleared by unload()."""
    from hledac.universal.brain.model_lifecycle import (
        request_emergency_unload,
        is_emergency_unload_requested,
        clear_emergency_unload_request
    )
    request_emergency_unload()
    assert is_emergency_unload_requested() is True
    engine = _make_engine()
    await engine.unload()
    assert is_emergency_unload_requested() is True
    clear_emergency_unload_request()


@pytest.mark.asyncio
async def test_reload_recreates_worker_after_unload():
    """After unload(), _ensure_batch_worker() MUST recreate worker/queue."""
    engine = _make_engine()
    engine._batch_queue = asyncio.PriorityQueue(maxsize=256)
    engine._pending_futures = set()
    engine._batch_worker_task = asyncio.create_task(engine._batch_worker())
    await asyncio.sleep(0.05)
    await engine.unload()
    assert engine._batch_queue is None
    assert engine._batch_worker_task is None
    await engine._ensure_batch_worker()
    assert engine._batch_queue is not None
    assert isinstance(engine._batch_queue, asyncio.PriorityQueue)
    assert engine._batch_worker_task is not None
    assert not engine._batch_worker_task.done()
    await _cleanup_worker(engine)


@pytest.mark.asyncio
async def test_reload_reruns_warmup_after_unload():
    """After unload(), _warmup_cache MUST be None allowing fresh warmup."""
    engine = _make_engine()
    engine._warmup_cache = MockKVCache()
    engine._model = MagicMock()
    engine._tokenizer = MagicMock()
    await engine.unload()
    assert engine._warmup_cache is None


@pytest.mark.asyncio
async def test_worker_shutdown_latency_within_timeout():
    """Worker shutdown MUST complete within 3.0s timeout."""
    engine = _make_engine()
    engine._batch_queue = asyncio.PriorityQueue(maxsize=256)
    engine._pending_futures = set()
    engine._batch_worker_task = asyncio.create_task(engine._batch_worker())
    await asyncio.sleep(0.05)
    t0 = time.perf_counter()
    await engine._shutdown_batch_worker(timeout=3.0)
    elapsed = time.perf_counter() - t0
    assert elapsed < 3.5
    await _cleanup_worker(engine)


@pytest.mark.asyncio
async def test_unload_no_batch_queue_leak():
    """After unload, _batch_queue reference must be fully cleared."""
    engine = _make_engine()
    engine._batch_queue = asyncio.PriorityQueue(maxsize=256)
    engine._pending_futures = set()
    engine._batch_worker_task = asyncio.create_task(engine._batch_worker())
    await asyncio.sleep(0.05)
    await engine.unload()
    assert engine._batch_queue is None
    gc.collect()


@pytest.mark.asyncio
async def test_import_time_guard():
    """Importing hermes3_engine MUST complete within 3000ms."""
    import time
    import sys
    times = []
    for _ in range(3):
        for mod_name in list(sys.modules.keys()):
            if 'hermes3_engine' in mod_name:
                del sys.modules[mod_name]
        t = time.perf_counter()
        import hledac.universal.brain.hermes3_engine
        elapsed_ms = (time.perf_counter() - t) * 1000
        times.append(elapsed_ms)
        gc.collect()
    median_ms = sorted(times)[1]
    assert median_ms < 3000, f"Import time {median_ms:.0f}ms exceeds 3000ms"


# =============================================================================
# Safe Clear Protocol
# =============================================================================

@pytest.mark.asyncio
async def test_safe_clear_requires_batch_worker_done():
    """After _shutdown_batch_worker, task must be None or done."""
    engine = _make_engine()
    engine._batch_queue = asyncio.PriorityQueue(maxsize=256)
    engine._pending_futures = set()
    engine._batch_worker_task = asyncio.create_task(engine._batch_worker())
    await asyncio.sleep(0.05)
    await engine._shutdown_batch_worker(timeout=3.0)
    assert engine._batch_worker_task is None or engine._batch_worker_task.done()


@pytest.mark.asyncio
async def test_safe_clear_requires_queue_none():
    """After _shutdown_batch_worker, _batch_queue must be None."""
    engine = _make_engine()
    engine._batch_queue = asyncio.PriorityQueue(maxsize=256)
    engine._pending_futures = set()
    engine._batch_worker_task = asyncio.create_task(engine._batch_worker())
    await asyncio.sleep(0.05)
    assert engine._batch_queue is not None
    await engine._shutdown_batch_worker(timeout=3.0)
    assert engine._batch_queue is None


@pytest.mark.asyncio
async def test_safe_clear_requires_pending_futures_empty():
    """After _shutdown_batch_worker, _pending_futures must be empty."""
    engine = _make_engine()
    engine._batch_queue = asyncio.PriorityQueue(maxsize=256)
    engine._pending_futures = set()
    engine._batch_worker_task = asyncio.create_task(engine._batch_worker())
    await asyncio.sleep(0.05)
    future = asyncio.Future()
    engine._pending_futures.add(future)
    assert len(engine._pending_futures) == 1
    await engine._shutdown_batch_worker(timeout=3.0)
    assert len(engine._pending_futures) == 0


# =============================================================================
# Regressions
# =============================================================================

@pytest.mark.asyncio
async def test_unload_idempotent():
    """Unload must be safe to call multiple times."""
    engine = _make_engine()
    engine._model = MagicMock()
    engine._tokenizer = MagicMock()
    await engine.unload()
    await engine.unload()  # Must not raise


@pytest.mark.asyncio
async def test_shutdown_batch_worker_idempotent():
    """_shutdown_batch_worker must be safe to call multiple times."""
    engine = _make_engine()
    await engine._shutdown_batch_worker(timeout=1.0)
    await engine._shutdown_batch_worker(timeout=1.0)  # Must not raise


@pytest.mark.asyncio
async def test_ensure_batch_worker_after_idempotent_shutdown():
    """_ensure_batch_worker must work after double shutdown."""
    engine = _make_engine()
    await engine._shutdown_batch_worker(timeout=1.0)
    await engine._shutdown_batch_worker(timeout=1.0)
    await engine._ensure_batch_worker()
    assert engine._batch_worker_task is not None
    assert engine._batch_queue is not None
    await _cleanup_worker(engine)
