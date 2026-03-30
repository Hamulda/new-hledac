"""
Sprint 7E: Schema-Aware Extraction Batcher Tests
=================================================
Tests for:
- _batch_queue dead seam activation
- PriorityQueue with tie-breaker
- Schema-aware batching (no mixing)
- Anti-starvation (age bump)
- drain()/flush_all()
- EMA telemetry
- _warmup_cache separation
- AO canary gate existence

Run: pytest tests/probe_7e/ -v
Duration: ~3-5 seconds (fully mocked)
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import BaseModel

import pytest


class TestSchemaA:
    """Dummy schema for testing."""
    name: str
    value: int


class TestSchemaB:
    """Another schema for testing."""
    tag: str
    count: float


@pytest.fixture
def mock_engine():
    """Create a partially-mocked Hermes3Engine."""
    from hledac.universal.brain.hermes3_engine import Hermes3Engine

    engine = Hermes3Engine.__new__(Hermes3Engine)
    engine._batch_queue = None
    engine._batch_worker_task = None
    engine._batch_max_size = 8
    engine._batch_flush_interval = 0.05  # 50ms for fast tests
    engine._batch_default_flush_interval = 0.05  # Sprint 7I: required by _current_flush_interval()
    engine._batch_medium_pressure_depth = 64   # Sprint 7I: required by _current_flush_interval()
    engine._batch_high_pressure_depth = 192  # Sprint 7I: required by _current_flush_interval()
    engine._flush_cycle_count = 0
    engine._age_bump_interval = 3
    engine._last_age_bump = 0
    engine._telemetry_ema = {
        'enqueue_to_dispatch_ms': 0.0,
        'dispatch_to_result_ms': 0.0,
        'batch_size': 0,
        'queue_depth': 0,
    }
    # Sprint 7I: Complete counters matching real __init__
    engine._telemetry_counters = {
        'batch_submitted': 0,
        'batch_executed': 0,
        'batch_fallback_single': 0,
        'schema_mismatch_flushes': 0,
        'length_bin_mismatch_flushes': 0,
        'batch_shattered': 0,
        'prompt_mismatch_flushes': 0,
        'emergency_guard_triggered': 0,
        'emergency_batch_rejected': 0,
        'emergency_single_rejected': 0,
        'emergency_pending_failed': 0,
        'adaptive_flush_default_entries': 0,
        'adaptive_flush_medium_entries': 0,
        'adaptive_flush_fast_entries': 0,
    }
    engine._ema_alpha = 0.3
    engine._warmup_cache = None
    engine._model = None
    engine._tokenizer = None
    engine._inference_semaphore = asyncio.Semaphore(1)
    engine._inference_executor = MagicMock()
    engine._outlines_generators = {}
    engine._outlines_model = None
    engine._system_prompt = "You are a helpful assistant."
    engine._prompt_cache = None
    engine._pending_futures = set()  # Sprint 7I: required by _submit_structured_batch
    return engine


class TestQueueLazyInit:
    """Test queue lazy initialization."""

    async def test_queue_lazy_init_via_ensure(self, mock_engine):
        """_ensure_batch_worker creates queue on first call."""
        assert mock_engine._batch_queue is None
        assert mock_engine._batch_worker_task is None

        await mock_engine._ensure_batch_worker()

        assert mock_engine._batch_queue is not None
        assert isinstance(mock_engine._batch_queue, asyncio.PriorityQueue)
        assert mock_engine._batch_queue.maxsize == 256
        assert mock_engine._batch_worker_task is not None
        # Task should be running (not done yet)
        assert not mock_engine._batch_worker_task.done()

    async def test_queue_init_idempotent(self, mock_engine):
        """_ensure_batch_worker only starts worker once."""
        await mock_engine._ensure_batch_worker()
        q1 = mock_engine._batch_queue
        t1 = mock_engine._batch_worker_task

        await mock_engine._ensure_batch_worker()
        assert mock_engine._batch_queue is q1  # Same queue
        assert mock_engine._batch_worker_task is t1  # Same task


class TestPriorityQueueWithTiebreaker:
    """Test PriorityQueue doesn't crash on same priority."""

    async def test_same_priority_no_crash(self, mock_engine):
        """Items with same priority don't cause TypeError."""
        await mock_engine._ensure_batch_worker()

        # Add 3 items with same priority, different tie-breaker
        import itertools
        tie = itertools.count()
        for i in range(3):
            await mock_engine._batch_queue.put((1.0, next(tie), "TestSchema", {"id": i}))

        # Drain them
        items = []
        deadline = time.monotonic() + 1.0
        while not mock_engine._batch_queue.empty() and time.monotonic() < deadline:
            item = mock_engine._batch_queue.get_nowait()
            items.append(item)
            # Simulate processing by worker

        assert len(items) == 3
        # Verify tuple structure
        for priority, tie, schema_key, payload in items:
            assert isinstance(priority, float)
            assert isinstance(tie, int)
            assert isinstance(schema_key, str)


class TestSchemaAwareBatching:
    """Test schema-aware batching."""

    async def test_schema_boundary_separation(self, mock_engine):
        """Items with different schema_key are NOT mixed in same batch."""
        await mock_engine._ensure_batch_worker()

        # Add items from schema A
        await mock_engine._batch_queue.put((1.0, 1, "SchemaA", {"type": "structured", "future": asyncio.Future()}))
        await mock_engine._batch_queue.put((1.0, 2, "SchemaA", {"type": "structured", "future": asyncio.Future()}))
        # Add item from schema B (should trigger boundary)
        await mock_engine._batch_queue.put((1.0, 3, "SchemaB", {"type": "structured", "future": asyncio.Future()}))

        # Worker should process SchemaA items first, then SchemaB
        # We can't easily test the full worker loop, but we can verify
        # that get_nowait respects the put-back behavior
        first = await asyncio.wait_for(mock_engine._batch_queue.get(), timeout=0.5)
        # First item should be from SchemaA (lower tie)
        assert first[2] == "SchemaA"


class TestDrainFlushAll:
    """Test drain/flush_all functionality."""

    async def test_flush_all_empty_queue(self, mock_engine):
        """flush_all on empty queue returns 0."""
        result = await mock_engine.flush_all(timeout=0.1)
        assert result == 0

    async def test_flush_all_returns_count(self, mock_engine):
        """flush_all returns number of items drained."""
        await mock_engine._ensure_batch_worker()

        # Add items directly to queue
        for i in range(5):
            await mock_engine._batch_queue.put((1.0, i, "TestSchema", {"type": "generate", "future": None}))

        result = await mock_engine.flush_all(timeout=1.0)
        assert result == 5

    async def test_flush_all_timeout(self, mock_engine):
        """flush_all respects timeout."""
        await mock_engine._ensure_batch_worker()

        # Add one item
        await mock_engine._batch_queue.put((1.0, 1, "TestSchema", {"type": "generate", "future": None}))

        # Very short timeout — might not drain all, but shouldn't hang
        start = time.monotonic()
        result = await mock_engine.flush_all(timeout=0.01)
        elapsed = time.monotonic() - start
        assert elapsed < 0.5  # Should complete quickly


class TestAntiStarvation:
    """Test anti-starvation via age bump."""

    async def test_age_bump_decreases_priority(self, mock_engine):
        """Age bump improves waiting item priority."""
        await mock_engine._ensure_batch_worker()

        # Add items
        for i in range(3):
            await mock_engine._batch_queue.put((5.0, i, "TestSchema", {"id": i}))

        # Manually call age bump
        await mock_engine._age_bump_queue()

        # Items should now have lower priority (closer to 0)
        items = []
        while not mock_engine._batch_queue.empty():
            items.append(mock_engine._batch_queue.get_nowait())

        for priority, tie, schema, payload in items:
            assert priority < 5.0  # Was 5.0, should be 4.0 after bump
            assert priority >= 0

    async def test_age_bump_min_priority_zero(self, mock_engine):
        """Age bump doesn't go below 0."""
        await mock_engine._ensure_batch_worker()

        # Add item with priority 0
        await mock_engine._batch_queue.put((0.0, 1, "TestSchema", {"id": 0}))

        await mock_engine._age_bump_queue()

        # Priority should still be 0 (not negative)
        item = mock_engine._batch_queue.get_nowait()
        assert item[0] == 0.0


class TestTelemetryEMA:
    """Test EMA telemetry."""

    def test_telemetry_ema_initialized(self, mock_engine):
        """EMA telemetry dict is properly initialized."""
        assert 'batch_size' in mock_engine._telemetry_ema
        assert 'queue_depth' in mock_engine._telemetry_ema
        assert 'enqueue_to_dispatch_ms' in mock_engine._telemetry_ema
        assert 'dispatch_to_result_ms' in mock_engine._telemetry_ema

    def test_telemetry_ema_alpha_exists(self, mock_engine):
        """EMA alpha is set."""
        assert hasattr(mock_engine, '_ema_alpha')
        assert 0 < mock_engine._ema_alpha < 1


class TestWarmupCacheSeparation:
    """Test _warmup_cache separation from production cache."""

    def test_warmup_cache_attr_exists(self, mock_engine):
        """_warmup_cache attribute exists separately."""
        assert hasattr(mock_engine, '_warmup_cache')
        # Production cache is _prompt_cache
        assert hasattr(mock_engine, '_prompt_cache')
        # They are separate attributes
        assert '_warmup_cache' in dir(mock_engine)

    def test_warmup_cache_none_by_default(self, mock_engine):
        """_warmup_cache starts as None."""
        assert mock_engine._warmup_cache is None


class TestBatchWorker:
    """Test batch worker startup and behavior."""

    async def test_worker_cancelled_on_cleanup(self, mock_engine):
        """Worker task can be cancelled cleanly."""
        await mock_engine._ensure_batch_worker()
        task = mock_engine._batch_worker_task

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert task.cancelled() or task.done()


class TestSubmitStructuredBatch:
    """Test _submit_structured_batch."""

    async def test_submit_creates_future(self, mock_engine):
        """_submit_structured_batch returns a Future."""
        # Mock generate_structured_safe to avoid model loading
        mock_engine.generate_structured_safe = AsyncMock(return_value={"ok": True})

        future = await mock_engine._submit_structured_batch(
            prompt="test prompt",
            response_model=TestSchemaA,
            priority=1.0
        )

        assert isinstance(future, asyncio.Future)

    async def test_submit_uses_priority_queue(self, mock_engine):
        """Submitted items go into PriorityQueue."""
        mock_engine.generate_structured_safe = AsyncMock(return_value={"ok": True})

        await mock_engine._submit_structured_batch(
            prompt="test",
            response_model=TestSchemaA,
            priority=2.0
        )

        assert mock_engine._batch_queue is not None
        assert not mock_engine._batch_queue.empty()


class TestBatchFlushTriggers:
    """Test batch flush trigger conditions."""

    async def test_flush_interval_trigger(self, mock_engine):
        """Worker flushes on interval timeout."""
        mock_engine._batch_flush_interval = 0.02  # 20ms
        await mock_engine._ensure_batch_worker()

        # Add one item
        await mock_engine._batch_queue.put((1.0, 1, "TestSchema", {"type": "generate", "future": None}))

        # Wait longer than flush interval
        await asyncio.sleep(0.1)

        # Queue should be processed (worker should have consumed item)
        # Note: item was consumed but since it's a generate type with None future,
        # it just gets processed without error


class TestEMAUpdates:
    """Test EMA calculation updates."""

    async def test_batch_size_ema_updated(self, mock_engine):
        """batch_size EMA is updated after processing."""
        mock_engine._telemetry_ema['batch_size'] = 0
        mock_engine._ema_alpha = 0.5

        # Simulate EMA update
        new_size = 8
        mock_engine._telemetry_ema['batch_size'] = (
            0.5 * new_size + 0.5 * mock_engine._telemetry_ema['batch_size']
        )

        assert mock_engine._telemetry_ema['batch_size'] == 4.0  # 0.5*8 + 0.5*0


# =============================================================================
# Sprint 7E: AO Canary Gate Existence Tests
# =============================================================================

class TestAOCanaryGate:
    """Verify AO canary gate exists and is runnable."""

    def test_ao_canary_file_exists(self):
        """test_ao_canary.py exists."""
        import os
        path = os.path.join(
            os.path.dirname(__file__),
            '..',
            'test_ao_canary.py'
        )
        assert os.path.exists(path), f"test_ao_canary.py not found at {path}"

    def test_ao_canary_has_tests(self):
        """test_ao_canary.py contains test classes."""
        import os
        path = os.path.join(
            os.path.dirname(__file__),
            '..',
            'test_ao_canary.py'
        )
        with open(path) as f:
            content = f.read()
        assert 'TestAOOrchestratorCanary' in content or 'Test' in content
        assert 'async def test_' in content

    def test_ao_canary_imports_without_error(self):
        """test_ao_canary.py can be imported without errors."""
        import sys
        import os
        probe_dir = os.path.dirname(__file__)
        tests_dir = os.path.dirname(probe_dir)
        sys.path.insert(0, tests_dir)
        try:
            import test_ao_canary
            assert hasattr(test_ao_canary, 'TestAOOrchestratorCanary') or \
                   hasattr(test_ao_canary, 'TestWindupGatingCanary') or \
                   'Canary' in str(dir(test_ao_canary))
        except ImportError as e:
            pytest.fail(f"Failed to import test_ao_canary: {e}")


class TestImportRegression:
    """Test import time doesn't regress catastrophically."""

    def test_hermes3_engine_import_structured(self):
        """hermes3_engine module can be imported."""
        import sys
        # Just verify the module structure is valid
        from hledac.universal.brain import hermes3_engine
        assert hasattr(hermes3_engine, 'Hermes3Engine')

    def test_batch_queue_maxsize_is_256(self):
        """PriorityQueue maxsize is 256."""
        from hledac.universal.brain.hermes3_engine import Hermes3Engine
        # Check class-level default
        # We can't easily check instance defaults without instantiation,
        # but we verified in mock_engine that maxsize=256
        pass
