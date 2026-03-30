"""
Sprint 7H — Watchdog Active-Lifecycle Wiring + Persistent DuckDB + Clean Gates
==============================================================================

Tests cover:
1. Gate cleanup (probe_1b drift fixed, probe_7d clean)
2. Watchdog → ACTIVE lifecycle wiring
3. Safe emergency seam (no direct unload from watchdog)
4. DuckDB persistent _file_conn + prewarm
5. True bulk write (executemany + transaction)
6. Lock release with retry loop
7. Batch dry-run N=1/10/50
8. Import regression
"""

import asyncio
import gc
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

# Import path
sys.path.insert(0, '/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal')


class TestGateCleanup(unittest.TestCase):
    """Verify probe_1b and probe_7d are clean after fixes."""

    def test_probe_1b_uma_threshold_fixed(self):
        """UMA threshold is correctly 6144 MB (Sprint 6B)."""
        from hledac.universal.utils.uma_budget import (
            _WARN_THRESHOLD_MB,
            _CRITICAL_THRESHOLD_MB,
        )
        assert _WARN_THRESHOLD_MB == 6144, f"Expected 6144, got {_WARN_THRESHOLD_MB}"
        assert _CRITICAL_THRESHOLD_MB == 6656, f"Expected 6656, got {_CRITICAL_THRESHOLD_MB}"

    def test_probe_7d_model_lifecycle_imports_clean(self):
        """model_lifecycle imports without errors."""
        try:
            from hledac.universal.brain import model_lifecycle
            self.assertTrue(hasattr(model_lifecycle, 'unload_model'))
            self.assertTrue(hasattr(model_lifecycle, 'ensure_mlx_runtime_initialized'))
        except ImportError as e:
            self.fail(f"Failed to import model_lifecycle: {e}")

    def test_probe_7d_unload_model_idempotent(self):
        """unload_model is idempotent and fail-open."""
        from hledac.universal.brain.model_lifecycle import unload_model

        # Should not raise on None inputs
        unload_model(model=None, tokenizer=None, prompt_cache=None)
        unload_model(model=None, tokenizer=None, prompt_cache=None)  # Second call = idempotency


class TestEmergencySeam(unittest.TestCase):
    """Tests for safe emergency unload seam in model_lifecycle."""

    def test_emergency_flag_api_exists(self):
        """Emergency flag API exists in model_lifecycle."""
        from hledac.universal.brain.model_lifecycle import (
            request_emergency_unload,
            is_emergency_unload_requested,
            clear_emergency_unload_request,
        )
        self.assertTrue(callable(request_emergency_unload))
        self.assertTrue(callable(is_emergency_unload_requested))
        self.assertTrue(callable(clear_emergency_unload_request))

    def test_emergency_flag_set_and_clear(self):
        """Emergency flag can be set and cleared."""
        from hledac.universal.brain.model_lifecycle import (
            request_emergency_unload,
            is_emergency_unload_requested,
            clear_emergency_unload_request,
        )

        # Initially False
        clear_emergency_unload_request()  # Ensure clean state
        assert not is_emergency_unload_requested()

        # Set flag
        request_emergency_unload()
        assert is_emergency_unload_requested()

        # Clear flag
        clear_emergency_unload_request()
        assert not is_emergency_unload_requested()

    def test_emergency_callback_api(self):
        """Emergency callback can be registered and retrieved."""
        from hledac.universal.brain.model_lifecycle import (
            set_emergency_callback,
            get_emergency_callback,
        )

        def dummy_callback():
            pass

        set_emergency_callback(dummy_callback)
        assert get_emergency_callback() is dummy_callback


class TestWatchdogLifecycleWiring(unittest.TestCase):
    """Tests for watchdog → ACTIVE lifecycle wiring."""

    def test_lifecycle_has_uma_watchdog_attributes(self):
        """SprintLifecycleManager has watchdog tracking attributes."""
        from hledac.universal.utils.sprint_lifecycle import SprintLifecycleManager

        mgr = SprintLifecycleManager()
        assert hasattr(mgr, '_uma_watchdog')
        assert hasattr(mgr, '_uma_watchdog_task')

    def test_mark_warmup_done_calls_watchdog_start(self):
        """mark_warmup_done transitions to ACTIVE and starts watchdog."""
        from hledac.universal.utils.sprint_lifecycle import (
            SprintLifecycleManager,
            SprintLifecycleState,
        )

        mgr = SprintLifecycleManager()
        mgr.begin_sprint()  # BOOT → WARMUP

        # Mock _start_uma_watchdog
        started = []
        original = mgr._start_uma_watchdog
        def mock_start():
            started.append(True)
        mgr._start_uma_watchdog = mock_start

        mgr.mark_warmup_done()  # WARMUP → ACTIVE

        assert mgr.state == SprintLifecycleState.ACTIVE
        assert len(started) == 1, "watchdog should be started on ACTIVE"

    def test_request_windup_stops_watchdog(self):
        """request_windup stops the watchdog."""
        from hledac.universal.utils.sprint_lifecycle import SprintLifecycleManager

        mgr = SprintLifecycleManager()
        mgr.begin_sprint()
        mgr.mark_warmup_done()

        # Mock watchdog
        mgr._uma_watchdog = MagicMock()
        stopped = []
        def mock_stop():
            stopped.append(True)
        mgr._uma_watchdog.stop = mock_stop

        mgr.request_windup()

        assert len(stopped) == 1, "watchdog should be stopped on windup"
        assert mgr._uma_watchdog is None


class TestWatchdogCallbacks(unittest.TestCase):
    """Tests for watchdog callback contracts."""

    def test_warn_callback_exists(self):
        """UmaWatchdogCallbacks has on_warn."""
        from hledac.universal.utils.uma_budget import UmaWatchdogCallbacks

        cb = UmaWatchdogCallbacks()
        assert hasattr(cb, 'on_warn')
        assert callable(cb.on_warn)

    def test_critical_callback_exists(self):
        """UmaWatchdogCallbacks has on_critical."""
        from hledac.universal.utils.uma_budget import UmaWatchdogCallbacks

        cb = UmaWatchdogCallbacks()
        assert hasattr(cb, 'on_critical')
        assert callable(cb.on_critical)

    def test_emergency_callback_exists(self):
        """UmaWatchdogCallbacks has on_emergency."""
        from hledac.universal.utils.uma_budget import UmaWatchdogCallbacks

        cb = UmaWatchdogCallbacks()
        assert hasattr(cb, 'on_emergency')
        assert callable(cb.on_emergency)


class TestDuckDBPersistentConnection(unittest.TestCase):
    """Tests for DuckDB persistent file connection."""

    def setUp(self):
        """Create temp dir for file-mode tests."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_duckdb.duckdb"

    def tearDown(self):
        """Clean up temp files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_file_conn_initialized_on_file_mode(self):
        """_file_conn is initialized for file mode."""
        # Patch _resolve_path to use our temp path
        from hledac.universal.knowledge.duckdb_store import DuckDBShadowStore

        store = DuckDBShadowStore()
        # Mock _resolve_path to return our temp path
        store._db_path = self.db_path
        store._temp_dir = Path(self.temp_dir)

        # Run init on worker thread
        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        executor.submit(store._init_connection).result()
        executor.shutdown(wait=True)

        assert store._file_conn is not None, "_file_conn should be initialized for file mode"

    def test_prewarm_file_conn_returns_bool(self):
        """_prewarm_file_conn returns True on success."""
        from hledac.universal.knowledge.duckdb_store import DuckDBShadowStore

        store = DuckDBShadowStore()
        store._db_path = self.db_path
        store._temp_dir = Path(self.temp_dir)

        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        executor.submit(store._init_connection).result()
        executor.shutdown(wait=True)

        result = store._prewarm_file_conn()
        assert isinstance(result, bool)

    def test_close_closes_file_conn(self):
        """_sync_close_on_worker closes _file_conn."""
        from hledac.universal.knowledge.duckdb_store import DuckDBShadowStore

        store = DuckDBShadowStore()
        store._db_path = self.db_path
        store._temp_dir = Path(self.temp_dir)

        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        executor.submit(store._init_connection).result()
        executor.shutdown(wait=True)

        assert store._file_conn is not None

        # Close
        store._sync_close_on_worker()
        assert store._file_conn is None


class TestDuckDBBulkWrite(unittest.TestCase):
    """Tests for true bulk write with executemany + transaction."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_bulk.duckdb"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_store(self) -> "DuckDBShadowStore":
        from hledac.universal.knowledge.duckdb_store import DuckDBShadowStore
        store = DuckDBShadowStore()
        store._db_path = self.db_path
        store._temp_dir = Path(self.temp_dir)
        return store

    def _make_findings(self, n: int) -> List[Dict[str, Any]]:
        return [
            {
                "id": f"finding_{i}",
                "query": f"query_{i}",
                "source_type": "test",
                "confidence": 0.5 + (i % 100) / 100.0,
            }
            for i in range(n)
        ]

    def test_bulk_insert_n1(self):
        """Bulk insert N=1 works."""
        from hledac.universal.knowledge.duckdb_store import DuckDBShadowStore

        store = DuckDBShadowStore()
        store._db_path = self.db_path
        store._temp_dir = Path(self.temp_dir)

        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        executor.submit(store._init_connection).result()
        executor.shutdown(wait=True)

        findings = self._make_findings(1)
        count = store._sync_insert_findings_bulk(findings)
        assert count == 1, f"Expected 1, got {count}"

        # Verify read-back
        result = store._sync_query_findings(10)
        assert len(result) == 1
        assert result[0]["id"] == "finding_0"

    def test_bulk_insert_n10(self):
        """Bulk insert N=10 works."""
        from hledac.universal.knowledge.duckdb_store import DuckDBShadowStore

        store = DuckDBShadowStore()
        store._db_path = self.db_path
        store._temp_dir = Path(self.temp_dir)

        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        executor.submit(store._init_connection).result()
        executor.shutdown(wait=True)

        findings = self._make_findings(10)
        count = store._sync_insert_findings_bulk(findings)
        assert count == 10, f"Expected 10, got {count}"

        # Verify read-back
        result = store._sync_query_findings(20)
        assert len(result) == 10

    def test_bulk_insert_n50(self):
        """Bulk insert N=50 works."""
        from hledac.universal.knowledge.duckdb_store import DuckDBShadowStore

        store = DuckDBShadowStore()
        store._db_path = self.db_path
        store._temp_dir = Path(self.temp_dir)

        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        executor.submit(store._init_connection).result()
        executor.shutdown(wait=True)

        findings = self._make_findings(50)
        count = store._sync_insert_findings_bulk(findings)
        assert count == 50, f"Expected 50, got {count}"

        # Verify read-back
        result = store._sync_query_findings(60)
        assert len(result) == 50

    def test_batch_async_n1(self):
        """async_record_shadow_findings_batch N=1 works."""
        from hledac.universal.knowledge.duckdb_store import DuckDBShadowStore

        store = DuckDBShadowStore()
        store._db_path = self.db_path
        store._temp_dir = Path(self.temp_dir)
        # Prevent _resolve_path from overwriting our test paths
        store._initialized = True  # Skip async_initialize's _resolve_path
        # Manually init connection (bypass async_initialize's _resolve_path)
        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        executor.submit(store._init_connection).result()
        executor.shutdown(wait=True)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            findings = self._make_findings(1)
            count = loop.run_until_complete(
                store.async_record_shadow_findings_batch(findings)
            )
            assert count == 1, f"Expected 1, got {count}"
        finally:
            loop.run_until_complete(store.aclose())
            loop.close()

    def test_batch_async_n10(self):
        """async_record_shadow_findings_batch N=10 works."""
        from hledac.universal.knowledge.duckdb_store import DuckDBShadowStore

        store = DuckDBShadowStore()
        store._db_path = self.db_path
        store._temp_dir = Path(self.temp_dir)
        store._initialized = True
        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        executor.submit(store._init_connection).result()
        executor.shutdown(wait=True)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            findings = self._make_findings(10)
            count = loop.run_until_complete(
                store.async_record_shadow_findings_batch(findings)
            )
            assert count == 10, f"Expected 10, got {count}"
        finally:
            loop.run_until_complete(store.aclose())
            loop.close()

    def test_batch_async_n50(self):
        """async_record_shadow_findings_batch N=50 works."""
        from hledac.universal.knowledge.duckdb_store import DuckDBShadowStore

        store = DuckDBShadowStore()
        store._db_path = self.db_path
        store._temp_dir = Path(self.temp_dir)
        store._initialized = True
        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        executor.submit(store._init_connection).result()
        executor.shutdown(wait=True)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            findings = self._make_findings(50)
            count = loop.run_until_complete(
                store.async_record_shadow_findings_batch(findings)
            )
            assert count == 50, f"Expected 50, got {count}"
        finally:
            loop.run_until_complete(store.aclose())
            loop.close()


class TestLockRelease(unittest.TestCase):
    """Tests for lock release with retry loop."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_lock.duckdb"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_close_reopen_no_lock_with_retry(self):
        """After close/reopen, DB is accessible (no lock hanging)."""
        from hledac.universal.knowledge.duckdb_store import DuckDBShadowStore

        max_retries = 5
        delay = 0.1

        for attempt in range(max_retries):
            store = DuckDBShadowStore()
            store._db_path = self.db_path
            store._temp_dir = Path(self.temp_dir)

            import concurrent.futures
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            executor.submit(store._init_connection).result()
            executor.shutdown(wait=True)

            # Insert something
            store._sync_insert_findings_bulk([{
                "id": f"retry_{attempt}",
                "query": "test",
                "source_type": "test",
                "confidence": 0.5,
            }])

            # Close
            store._sync_close_on_worker()

            # Re-open with retry
            store2 = DuckDBShadowStore()
            store2._db_path = self.db_path
            store2._temp_dir = Path(self.temp_dir)

            try:
                executor2 = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                executor2.submit(store2._init_connection).result()
                executor2.shutdown(wait=True)

                # Query should work
                result = store2._sync_query_findings(10)
                assert isinstance(result, list), f"Retry {attempt}: expected list, got {result}"
                store2._sync_close_on_worker()
                break  # Success
            except Exception as e:
                if attempt == max_retries - 1:
                    self.fail(f"Lock still held after {max_retries} retries: {e}")
                time.sleep(delay)


class TestImportRegression(unittest.TestCase):
    """Tests for import regression."""

    def test_uma_budget_imports_clean(self):
        """utils.uma_budget imports without errors."""
        try:
            from hledac.universal.utils import uma_budget
            self.assertTrue(hasattr(uma_budget, 'get_uma_snapshot'))
            self.assertTrue(hasattr(uma_budget, 'UmaWatchdog'))
        except ImportError as e:
            self.fail(f"Failed to import uma_budget: {e}")

    def test_sprint_lifecycle_imports_clean(self):
        """utils.sprint_lifecycle imports without errors."""
        try:
            from hledac.universal.utils import sprint_lifecycle
            self.assertTrue(hasattr(sprint_lifecycle, 'SprintLifecycleManager'))
            self.assertTrue(hasattr(sprint_lifecycle, 'SprintLifecycleState'))
        except ImportError as e:
            self.fail(f"Failed to import sprint_lifecycle: {e}")

    def test_duckdb_store_imports_clean(self):
        """knowledge.duckdb_store imports without errors."""
        try:
            from hledac.universal.knowledge import duckdb_store
            self.assertTrue(hasattr(duckdb_store, 'DuckDBShadowStore'))
        except ImportError as e:
            self.fail(f"Failed to import duckdb_store: {e}")

    def test_model_lifecycle_imports_clean(self):
        """brain.model_lifecycle imports without errors."""
        try:
            from hledac.universal.brain import model_lifecycle
            self.assertTrue(hasattr(model_lifecycle, 'unload_model'))
            self.assertTrue(hasattr(model_lifecycle, 'request_emergency_unload'))
        except ImportError as e:
            self.fail(f"Failed to import model_lifecycle: {e}")


class TestAoCanary(unittest.TestCase):
    """AO canary gate — verifies test file exists."""

    def test_ao_canary_exists(self):
        """tests/test_ao_canary.py should exist."""
        canary_path = Path(__file__).parent.parent / "test_ao_canary.py"
        self.assertTrue(
            canary_path.exists(),
            f"AO canary not found at {canary_path}"
        )


if __name__ == '__main__':
    unittest.main(verbosity=2)
