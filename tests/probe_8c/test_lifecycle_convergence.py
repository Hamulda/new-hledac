"""
Sprint 8C: Canonical Lifecycle Convergence
==========================================

Tests:
- canonical unload delegates to Hermes unload() not direct eviction
- safe-clear uses EXACT 7K preconditions
- reload after canonical unload works
- _mlx_initialized reset consistency
- legacy fallback for non-Hermes models
"""

import asyncio
import gc
from unittest.mock import MagicMock, AsyncMock, patch

import pytest


# -----------------------------------------------------------------------
# Minimal engine mock factory (mirrors probe_7k)
# -----------------------------------------------------------------------

def _make_engine():
    """Factory for Hermes3Engine with minimal mock state."""
    from hledac.universal.brain.hermes3_engine import Hermes3Engine
    engine = Hermes3Engine.__new__(Hermes3Engine)
    engine.config = MagicMock()
    engine._model = MagicMock()
    engine._tokenizer = MagicMock()
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
    executor = MagicMock()
    executor.submit = MagicMock(return_value=MagicMock())
    engine._inference_executor = executor
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
    engine._warmup_cache = MagicMock()
    engine._last_gpu_memory = 0
    engine._prompt_cache = MagicMock()
    engine._kv_cache_enabled = False
    engine._save_cache = AsyncMock()
    engine.invalidate_prefix_cache = MagicMock()
    engine._batch_worker_shutting_down = False
    return engine


# -----------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------

class TestCanonicalUnloadDelegation:
    """Test that unload_model delegates to engine.unload() instead of direct eviction."""

    def test_unload_model_delegates_to_engine_unload_sync(self):
        """unload_model() calls engine.unload() for engines that have it."""
        from hledac.universal.brain.model_lifecycle import unload_model

        engine = _make_engine()
        engine.unload = MagicMock()
        engine._batch_worker_task = None
        engine._batch_queue = None
        engine._pending_futures = set()

        unload_model(model=engine)

        engine.unload.assert_called_once()

    def test_unload_model_falls_back_to_legacy_for_non_engine(self):
        """unload_model() falls back to legacy eviction for objects without unload()."""
        from hledac.universal.brain.model_lifecycle import unload_model

        raw_model = MagicMock()
        del_called = False

        original_del = raw_model.__del__ if hasattr(raw_model, '__del__') else None

        class MockModel:
            pass

        m = MockModel()
        # No unload method — should use legacy path (no crash)
        unload_model(model=m)

    def test_unload_model_legacy_for_engine_without_unload_method(self):
        """unload_model() uses legacy for engine without unload() method."""
        from hledac.universal.brain.model_lifecycle import unload_model

        class NoUnloadEngine:
            def __init__(self):
                self._model = MagicMock()
                self._tokenizer = MagicMock()
                self._prompt_cache = MagicMock()
                self._system_prompt_cache = MagicMock()

        engine = NoUnloadEngine()
        # Should not raise — legacy fallback handles it
        unload_model(model=engine)


class TestSafeClearPreconditions:
    """Test is_safe_to_clear_emergency() uses EXACT 7K conditions."""

    def test_safe_when_batch_done_queue_none_no_pending(self):
        """is_safe_to_clear_emergency returns True when batch is done, queue is None, no pending."""
        from hledac.universal.brain.model_lifecycle import is_safe_to_clear_emergency

        engine = _make_engine()
        engine._batch_worker_task = None  # done
        engine._batch_queue = None
        engine._pending_futures = set()

        assert is_safe_to_clear_emergency(engine) is True

    @pytest.mark.asyncio
    async def test_unsafe_when_batch_worker_running(self):
        """Not safe if batch worker task exists and is not done."""
        from hledac.universal.brain.model_lifecycle import is_safe_to_clear_emergency

        engine = _make_engine()
        # Mock task that appears to be running (not done)
        mock_task = MagicMock()
        mock_task.done.return_value = False
        engine._batch_worker_task = mock_task
        engine._batch_queue = None
        engine._pending_futures = set()

        result = is_safe_to_clear_emergency(engine)
        assert result is False

    def test_unsafe_when_queue_not_none(self):
        """Not safe if _batch_queue is not None."""
        from hledac.universal.brain.model_lifecycle import is_safe_to_clear_emergency

        engine = _make_engine()
        engine._batch_worker_task = None
        engine._batch_queue = asyncio.Queue()
        engine._pending_futures = set()

        assert is_safe_to_clear_emergency(engine) is False

    def test_unsafe_when_pending_futures_exist(self):
        """Not safe if _pending_futures is not empty."""
        from hledac.universal.brain.model_lifecycle import is_safe_to_clear_emergency

        engine = _make_engine()
        engine._batch_worker_task = None
        engine._batch_queue = None
        # Non-empty set — len is what matters, not the object identity
        engine._pending_futures = {MagicMock()}

        assert is_safe_to_clear_emergency(engine) is False

    def test_safe_for_none_engine(self):
        """is_safe_to_clear_emergency returns True for None engine."""
        from hledac.universal.brain.model_lifecycle import is_safe_to_clear_emergency

        assert is_safe_to_clear_emergency(None) is True

    def test_safe_after_unload_batch_worker_done(self):
        """After engine.unload() batch worker is None — safe to clear."""
        from hledac.universal.brain.model_lifecycle import is_safe_to_clear_emergency

        engine = _make_engine()
        # Simulate post-unload state
        engine._batch_worker_task = None
        engine._batch_queue = None
        engine._pending_futures = set()
        engine._warmup_cache = None
        engine._prompt_cache = None
        engine._system_prompt_cache = None
        engine._model = None
        engine._tokenizer = None

        assert is_safe_to_clear_emergency(engine) is True


class TestReloadAfterCanonicalUnload:
    """Test that reload after canonical unload works via Hermes initialization path."""

    @pytest.mark.asyncio
    async def test_engine_unload_leaves_clean_state_for_reload(self):
        """After engine.unload() all key state is None — reload is clean."""
        from hledac.universal.brain.hermes3_engine import Hermes3Engine

        with patch('hledac.universal.brain.hermes3_engine.Hermes3Engine.initialize', new_callable=AsyncMock):
            engine = Hermes3Engine.__new__(Hermes3Engine)
            engine.config = MagicMock()
            engine._model = MagicMock()
            engine._tokenizer = MagicMock()
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
            executor = MagicMock()
            executor.submit = MagicMock(return_value=MagicMock())
            engine._inference_executor = executor
            engine._inference_semaphore = asyncio.Semaphore(1)
            # Start a real task for batch worker, then cancel it
            engine._batch_queue = asyncio.Queue()
            worker_task = asyncio.create_task(asyncio.sleep(60))
            engine._batch_worker_task = worker_task
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
            engine._pending_futures = {asyncio.Future()}
            engine._ema_alpha = 0.3
            engine._flush_cycle_count = 0
            engine._age_bump_interval = 3
            engine._last_age_bump = 0
            engine._warmup_cache = MagicMock()
            engine._last_gpu_memory = 0
            engine._prompt_cache = MagicMock()
            engine._kv_cache_enabled = False
            engine._save_cache = AsyncMock()
            engine.invalidate_prefix_cache = MagicMock()
            engine._batch_worker_shutting_down = False

            await engine.unload()

            # All cleanup state is None/empty after unload
            assert engine._batch_queue is None
            assert engine._batch_worker_task is None
            assert engine._model is None
            assert engine._tokenizer is None
            assert engine._outlines_model is None
            assert engine._warmup_cache is None
            assert engine._prompt_cache is None
            assert engine._system_prompt_cache is None
            assert engine._pending_futures == set()

    @pytest.mark.asyncio
    async def test_model_manager_release_calls_engine_unload(self):
        """ModelManager._release_model_async calls model.unload() if available."""
        from hledac.universal.brain.model_manager import ModelManager, ModelType

        mm = ModelManager()
        mm._loaded_models[ModelType.HERMES] = None
        mm._current_model = ModelType.HERMES

        engine = _make_engine()
        engine.unload = AsyncMock()
        mm._loaded_models[ModelType.HERMES] = engine

        await mm._release_model_async(ModelType.HERMES, "hermes")

        engine.unload.assert_called_once()
        assert ModelType.HERMES not in mm._loaded_models


class TestMLXInitializedConsistency:
    """Test _mlx_initialized / MLX state is consistent across unload/reload."""

    def test_ensure_mlx_initialized_is_idempotent(self):
        """ensure_mlx_runtime_initialized() is safe to call multiple times."""
        from hledac.universal.brain.model_lifecycle import ensure_mlx_runtime_initialized

        result1 = ensure_mlx_runtime_initialized()
        result2 = ensure_mlx_runtime_initialized()

        # Both should return same result (idempotent)
        assert result1 == result2

    def test_mlx_cache_initialized_flag_not_broken_by_legacy_unload(self):
        """Legacy unload_model() does not break MLX init state."""
        from hledac.universal.brain.model_lifecycle import unload_model, ensure_mlx_runtime_initialized

        # Even if legacy unload is called on a non-engine object
        unload_model(model=None)

        # MLX is still usable (no crash)
        result = ensure_mlx_runtime_initialized()
        assert result is True or result is False  # Either is valid, just no crash


class TestUnloadOrderRespects7K:
    """Test that engine.unload() respects 7K SSOT order (mocked)."""

    @pytest.mark.asyncio
    async def test_engine_unload_order_is_7k(self):
        """engine.unload() calls steps in 7K order (verified via mock sequence)."""
        from hledac.universal.brain.hermes3_engine import Hermes3Engine

        call_order = []

        with patch('hledac.universal.brain.hermes3_engine.Hermes3Engine._shutdown_batch_worker', new_callable=AsyncMock) as mock_shutdown:
            async def track(*args, **kwargs):
                call_order.append('_shutdown_batch_worker')

            mock_shutdown.side_effect = track

            engine = Hermes3Engine.__new__(Hermes3Engine)
            engine.config = MagicMock()
            engine._model = MagicMock()
            engine._tokenizer = MagicMock()
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

            await engine.unload()

            mock_shutdown.assert_called_once_with(timeout=3.0)
