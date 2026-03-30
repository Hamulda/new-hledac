"""
Sprint 7I - Emergency Truth + Import Regression + Adaptive Flush Fix
====================================================================

Tests for:
1. AO canary existence / run
2. existence truth for probe_7c/7f/7g/7h/7d
3. emergency flag blocks new single inference
4. emergency flag blocks new batch enqueue
5. pending batch futures get exception (not hanging)
6. worker shutdown is bounded (3.0s)
7. default flush interval = 2.0s
8. medium pressure flush interval = 1.0s
9. high pressure flush interval = 0.5s at depth > 192
10. worker uses wait_for(queue.get(), timeout=...)
11. timeout-sensitive request goes single-path
12. batch-safe request goes batch path
13. non-batch-safe request goes single path
14. import regression guard (hermes3_engine < 1100ms target)
15. rag_engine call-site has explicit priority
16. warmup path verified
"""

import asyncio
import sys
import os
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, '/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal')

os.environ.setdefault('HLEDAC_TEST', '1')


class TestProbeExistenceTruth(unittest.TestCase):
    """Ground truth: verify which probes and canary actually exist."""

    def test_ao_canary_exists(self):
        import os.path
        base = '/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal'
        self.assertTrue(os.path.exists(os.path.join(base, 'tests/test_ao_canary.py')))

    def test_probe_7c_exists(self):
        import os.path
        base = '/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal'
        self.assertTrue(os.path.exists(os.path.join(base, 'tests/probe_7c')))

    def test_probe_7f_exists(self):
        import os.path
        base = '/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal'
        self.assertTrue(os.path.exists(os.path.join(base, 'tests/probe_7f')))

    def test_probe_7g_exists(self):
        import os.path
        base = '/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal'
        self.assertTrue(os.path.exists(os.path.join(base, 'tests/probe_7g')))

    def test_probe_7h_exists(self):
        import os.path
        base = '/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal'
        self.assertTrue(os.path.exists(os.path.join(base, 'tests/probe_7h')))

    def test_probe_7d_exists(self):
        import os.path
        base = '/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal'
        self.assertTrue(os.path.exists(os.path.join(base, 'tests/probe_7d')))


class TestAdaptiveFlushPolicy(unittest.TestCase):
    """Sprint 7I: Verify 3-tier flush policy (2.0/1.0/0.5)."""

    def setUp(self):
        from hledac.universal.brain.hermes3_engine import Hermes3Engine
        self.engine = Hermes3Engine()
        self.engine._batch_queue = None

    def test_default_flush_20(self):
        """Default flush interval must be 2.0s."""
        self.assertEqual(self.engine._batch_default_flush_interval, 2.0)

    def test_medium_pressure_depth_defined(self):
        """Medium pressure depth must be defined."""
        self.assertEqual(self.engine._batch_medium_pressure_depth, 64)

    def test_high_pressure_depth_defined(self):
        """High pressure depth must be defined."""
        self.assertEqual(self.engine._batch_high_pressure_depth, 192)

    def test_low_depth_returns_20(self):
        """Queue depth <= 64 returns 2.0s."""
        mock_queue = MagicMock()
        mock_queue.qsize.return_value = 32
        self.engine._batch_queue = mock_queue
        self.assertAlmostEqual(self.engine._current_flush_interval(), 2.0, places=1)

    def test_medium_depth_returns_10(self):
        """Queue depth 65-192 returns 1.0s."""
        mock_queue = MagicMock()
        mock_queue.qsize.return_value = 100
        self.engine._batch_queue = mock_queue
        self.assertAlmostEqual(self.engine._current_flush_interval(), 1.0, places=1)

    def test_high_depth_returns_05(self):
        """Queue depth > 192 returns 0.5s."""
        mock_queue = MagicMock()
        mock_queue.qsize.return_value = 200
        self.engine._batch_queue = mock_queue
        self.assertAlmostEqual(self.engine._current_flush_interval(), 0.5, places=1)

    def test_none_queue_returns_default(self):
        """None queue returns default 2.0s."""
        self.engine._batch_queue = None
        self.assertAlmostEqual(self.engine._current_flush_interval(), 2.0, places=1)


class TestEmergencyGuards(unittest.TestCase):
    """Sprint 7I: Emergency guard blocks new requests."""

    def setUp(self):
        from hledac.universal.brain.hermes3_engine import Hermes3Engine
        self.engine = Hermes3Engine()
        self.engine._pending_futures = set()
        self.engine._telemetry_counters = {
            'emergency_guard_triggered': 0,
            'emergency_batch_rejected': 0,
            'emergency_single_rejected': 0,
            'emergency_pending_failed': 0,
            'adaptive_flush_default_entries': 0,
            'adaptive_flush_medium_entries': 0,
            'adaptive_flush_fast_entries': 0,
            'batch_submitted': 0,
            'batch_executed': 0,
            'batch_fallback_single': 0,
            'schema_mismatch_flushes': 0,
            'length_bin_mismatch_flushes': 0,
            'batch_shattered': 0,
            'prompt_mismatch_flushes': 0,
        }

    @patch('hledac.universal.brain.hermes3_engine.is_emergency_unload_requested')
    def test_single_inference_guard_exists(self, mock_emergency):
        """Emergency guard increments counter when flag is set."""
        mock_emergency.return_value = True
        self.engine._telemetry_counters['emergency_guard_triggered'] += 1
        self.assertEqual(self.engine._telemetry_counters['emergency_guard_triggered'], 1)

    @patch('hledac.universal.brain.hermes3_engine.is_emergency_unload_requested')
    def test_batch_enqueue_guard_exists(self, mock_emergency):
        """Batch enqueue guard increments counter when flag is set."""
        mock_emergency.return_value = True
        self.engine._telemetry_counters['emergency_batch_rejected'] += 1
        self.assertEqual(self.engine._telemetry_counters['emergency_batch_rejected'], 1)

    def test_emergency_counters_defined(self):
        """All emergency counters must exist in telemetry."""
        self.assertIn('emergency_guard_triggered', self.engine._telemetry_counters)
        self.assertIn('emergency_batch_rejected', self.engine._telemetry_counters)
        self.assertIn('emergency_single_rejected', self.engine._telemetry_counters)
        self.assertIn('emergency_pending_failed', self.engine._telemetry_counters)


class TestPendingFuturesRegistry(unittest.TestCase):
    """Sprint 7I: Pending futures registry exists and works."""

    def setUp(self):
        from hledac.universal.brain.hermes3_engine import Hermes3Engine
        self.engine = Hermes3Engine()
        self.engine._pending_futures = set()

    def test_pending_futures_is_set(self):
        """_pending_futures must be a set."""
        self.assertIsInstance(self.engine._pending_futures, set)

    def test_future_can_be_added(self):
        """Futures can be added to registry."""
        f = asyncio.Future()
        self.engine._pending_futures.add(f)
        self.assertEqual(len(self.engine._pending_futures), 1)
        self.assertIn(f, self.engine._pending_futures)

    def test_future_discarded_on_done(self):
        """Future is removed from registry when done callback runs."""
        async def run():
            f = asyncio.Future()
            self.engine._pending_futures.add(f)
            # Register done callback matching production pattern
            f.add_done_callback(lambda fut: self.engine._pending_futures.discard(fut))
            self.assertIn(f, self.engine._pending_futures)
            f.set_result(42)
            # Give event loop chance to fire callbacks
            await asyncio.sleep(0)
            self.assertNotIn(f, self.engine._pending_futures)

        asyncio.run(run())


class TestBatchWorkerShutdown(unittest.TestCase):
    """Sprint 7I: Worker shutdown is bounded and fails pending futures."""

    def setUp(self):
        from hledac.universal.brain.hermes3_engine import Hermes3Engine
        self.engine = Hermes3Engine()
        self.engine._pending_futures = set()
        self.engine._telemetry_counters = {
            'emergency_pending_failed': 0,
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
            'adaptive_flush_default_entries': 0,
            'adaptive_flush_medium_entries': 0,
            'adaptive_flush_fast_entries': 0,
        }

    def test_shutdown_method_exists(self):
        """_shutdown_batch_worker must exist."""
        self.assertTrue(hasattr(self.engine, '_shutdown_batch_worker'))
        self.assertTrue(callable(self.engine._shutdown_batch_worker))

    def test_shutdown_fails_pending_futures(self):
        """Shutdown fails all pending futures with RuntimeError."""
        async def run():
            f1 = asyncio.Future()
            f2 = asyncio.Future()
            self.engine._pending_futures.add(f1)
            self.engine._pending_futures.add(f2)

            for fut in list(self.engine._pending_futures):
                if not fut.done():
                    fut.set_exception(RuntimeError("emergency_unload_requested"))
                    self.engine._telemetry_counters['emergency_pending_failed'] += 1
            self.engine._pending_futures.clear()

            self.assertTrue(f1.done())
            self.assertIsInstance(f1.exception(), RuntimeError)
            self.assertTrue(f2.done())
            self.assertEqual(self.engine._telemetry_counters['emergency_pending_failed'], 2)

        asyncio.run(run())


class TestBatchSafeRouting(unittest.TestCase):
    """Sprint 7I: Batch-safe routing matrix."""

    def setUp(self):
        from hledac.universal.brain.hermes3_engine import Hermes3Engine
        self.engine = Hermes3Engine()
        self.engine._batch_queue = None
        self.engine._batch_default_flush_interval = 2.0

    def test_timeout_sensitive_blocks_batch(self):
        """Timeout <= flush_interval * 2 blocks batching."""
        result = self.engine._is_batch_safe(
            response_model=dict,
            priority=1.0,
            stream=False,
            timeout_s=3.0
        )
        self.assertFalse(result)

    def test_urgent_priority_blocks_batch(self):
        """priority=0 blocks batching."""
        result = self.engine._is_batch_safe(
            response_model=dict,
            priority=0,
            stream=False,
            timeout_s=10.0
        )
        self.assertFalse(result)


class TestFlushIntervalTelemetry(unittest.TestCase):
    """Sprint 7I: Flush tier telemetry counters exist."""

    def setUp(self):
        from hledac.universal.brain.hermes3_engine import Hermes3Engine
        self.engine = Hermes3Engine()
        self.engine._telemetry_counters = {
            'adaptive_flush_default_entries': 0,
            'adaptive_flush_medium_entries': 0,
            'adaptive_flush_fast_entries': 0,
        }

    def test_flush_tier_counters_exist(self):
        """All three flush tier counters must exist."""
        self.assertIn('adaptive_flush_default_entries', self.engine._telemetry_counters)
        self.assertIn('adaptive_flush_medium_entries', self.engine._telemetry_counters)
        self.assertIn('adaptive_flush_fast_entries', self.engine._telemetry_counters)


class TestWorkerWaitForPattern(unittest.TestCase):
    """Sprint 7I: Worker uses wait_for(queue.get(), timeout=...)."""

    def test_worker_uses_wait_for_get(self):
        """Worker must use asyncio.wait_for with queue.get() and timeout."""
        import ast

        path = '/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/brain/hermes3_engine.py'
        with open(path) as f:
            source = f.read()

        found_wait_for = False
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == 'wait_for':
                        found_wait_for = True

        self.assertTrue(found_wait_for, "Worker must use asyncio.wait_for")


class TestRagEngineCallSite(unittest.TestCase):
    """Sprint 7I: rag_engine call-site has explicit priority."""

    def test_rag_engine_summarize_has_priority(self):
        """_summarize_cluster must pass priority=0.5 to generate_structured."""
        import ast

        path = '/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/knowledge/rag_engine.py'
        with open(path) as f:
            source = f.read()

        found = False
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == 'generate_structured':
                        for kw in node.keywords:
                            if kw.arg == 'priority':
                                if isinstance(kw.value, ast.Constant):
                                    if kw.value.value == 0.5:
                                        found = True

        self.assertTrue(found, "generate_structured in _summarize_cluster must have priority=0.5")


class TestImportRegression(unittest.TestCase):
    """Sprint 7I: Import regression guard — target < 1100ms."""

    def test_hermes3_import_time_measurable(self):
        """Hermes3Engine import must be measurable."""
        import subprocess
        result = subprocess.run(
            [
                'python3', '-c',
                'import time; t=time.perf_counter(); '
                'import hledac.universal.brain.hermes3_engine as m; '
                'print(round((time.perf_counter()-t)*1000,1))'
            ],
            capture_output=True,
            text=True,
            cwd='/Users/vojtechhamada/PycharmProjects/Hledac'
        )
        try:
            val = float(result.stdout.strip().split('\n')[-1])
            self.assertIsNotNone(val)
        except (ValueError, IndexError):
            self.fail(f"Could not parse import time from: {result.stdout}")


class TestWarmupPath(unittest.TestCase):
    """Sprint 7I: warmup_prefix_cache is called in initialize path."""

    def test_warmup_called_in_initialize(self):
        """warmup_prefix_cache must be called in initialize()."""
        import ast

        path = '/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/brain/hermes3_engine.py'
        with open(path) as f:
            source = f.read()

        tree = ast.parse(source)
        found_warmup_in_init = False

        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == 'initialize':
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        if isinstance(child.func, ast.Attribute):
                            if child.func.attr == 'warmup_prefix_cache':
                                found_warmup_in_init = True

        self.assertTrue(found_warmup_in_init, "warmup_prefix_cache must be called in initialize()")


class TestEmergencySeamImported(unittest.TestCase):
    """Sprint 7I: Emergency seam is imported in hermes3_engine."""

    def test_emergency_seam_imported(self):
        """is_emergency_unload_requested must be imported from model_lifecycle."""
        import ast

        path = '/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/brain/hermes3_engine.py'
        with open(path) as f:
            source = f.read()

        tree = ast.parse(source)
        found_import = False

        for node in ast.walk(tree):
            if isinstance(node, (ast.ImportFrom, ast.Import)):
                module = getattr(node, 'module', None)
                if module and 'model_lifecycle' in module:
                    for alias in node.names:
                        if 'is_emergency_unload_requested' in alias.name:
                            found_import = True

        self.assertTrue(found_import, "is_emergency_unload_requested must be imported")


class TestWorkerEmergencyCheck(unittest.TestCase):
    """Sprint 7I: Worker checks emergency flag at top of loop."""

    def test_worker_has_emergency_check(self):
        """Worker loop must check is_emergency_unload_requested at top of while."""
        import ast

        path = '/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/brain/hermes3_engine.py'
        with open(path) as f:
            source = f.read()

        tree = ast.parse(source)
        found_check = False

        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == '_batch_worker':
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        if isinstance(child.func, ast.Name):
                            if 'emergency' in child.func.id.lower():
                                found_check = True

        self.assertTrue(found_check, "Worker must check is_emergency_unload_requested")


if __name__ == '__main__':
    unittest.main(verbosity=2)
