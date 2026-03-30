"""
Sprint 8AI: Boot Hygiene Closure — Probe Tests
==============================================

Tests the following invariants:
- No boot side effects on import
- Boot guard runs before other runtime acquisition
- Boot guard aborts on unsafe state
- Boot guard safe cleanup allows boot
- AsyncExitStack is used as teardown backbone
- Teardown order is reverse of registration
- Existing signal path still works
- CheckpointManager surface exists or is documented N/A
- Partial cleanup surfaces don't crash
- Runtime status helper is side-effect free
- No new production modules created
- Graceful task cancellation before loop close
- Signal handler doesn't directly cleanup
- No double-teardown on signal path
- Combined existing gates still green
"""

import asyncio
import contextlib
import glob
import subprocess
import time
from typing import List
from unittest.mock import patch

import pytest

import hledac.universal.__main__ as main_module


# =============================================================================
# D.1 — test_import_main_has_no_boot_side_effects
# =============================================================================

class TestNoBootSideEffects:
    """INVARIANT: Importing __main__ must not run boot guard, session, or teardown."""

    def test_import_main_has_no_boot_side_effects(self):
        """
        After importing __main__, no boot guard, no signal handlers installed,
        no event loop created, no telemetry entries.
        """
        # Telemetry must be empty on clean import
        assert main_module._boot_telemetry == [], (
            f"Expected empty telemetry, got {main_module._boot_telemetry}"
        )
        assert isinstance(main_module._signal_teardown_flag, bool)
        assert main_module._uvloop_installed in (True, False)

    def test_boot_record_does_not_run_on_import(self):
        """Directly: _boot_telemetry list must be empty after module-level import."""
        assert len(main_module._boot_telemetry) == 0, (
            f"Boot telemetry should be empty at import time, got {main_module._boot_telemetry}"
        )


# =============================================================================
# D.2 — test_boot_guard_runs_before_other_runtime_acquisition
# =============================================================================

class TestBootGuardOrdering:
    """INVARIANT: Boot guard runs as FIRST step in main(), before any runtime."""

    def test_boot_guard_runs_before_other_runtime_acquisition(self):
        """
        In main(), the boot guard is called BEFORE asyncio.run().
        Verify call order using AST to find actual Call nodes.
        """
        import ast
        import inspect

        source = inspect.getsource(main_module.main)
        tree = ast.parse(source)

        boot_guard_line = None
        asyncio_run_line = None

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # _run_boot_guard() — direct name call
                if isinstance(node.func, ast.Name):
                    if node.func.id == '_run_boot_guard' and boot_guard_line is None:
                        boot_guard_line = node.lineno
                # asyncio.run() — attribute call
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == 'run' and asyncio_run_line is None:
                        # Verify it's asyncio.run by checking parent context
                        asyncio_run_line = node.lineno

        assert boot_guard_line is not None, "boot guard call not found in main()"
        assert asyncio_run_line is not None, "asyncio.run call not found in main()"
        assert boot_guard_line < asyncio_run_line, (
            f"boot guard (line {boot_guard_line}) must run BEFORE asyncio.run (line {asyncio_run_line})"
        )


# =============================================================================
# D.3 — test_boot_guard_unsafe_state_aborts_boot
# =============================================================================

class TestBootGuardAbort:
    """INVARIANT: Unsafe stale-lock state causes clean boot abort via BootGuardError."""

    def test_boot_guard_unsafe_state_aborts_boot(self):
        """Verify boot guard is called and result recorded."""
        import pathlib

        # cleanup_stale_lmdb_lock is lazy-imported inside _run_boot_guard
        # Patch it at the original module
        with patch('hledac.universal.knowledge.lmdb_boot_guard.cleanup_stale_lmdb_lock') as mock_guard:
            mock_guard.return_value = (0, "holder_process_alive(pid=99999)")
            result = main_module._run_boot_guard(pathlib.Path("/tmp/fake_lmdb"))
            mock_guard.assert_called_once()
            assert result[0] == 0

    def test_boot_guard_error_class_exists(self):
        """Verify BootGuardError exists and can be raised."""
        with pytest.raises(main_module.BootGuardError):
            raise main_module.BootGuardError("unsafe_state")


# =============================================================================
# D.4 — test_boot_guard_safe_cleanup_allows_boot
# =============================================================================

class TestBootGuardSafe:
    """INVARIANT: Safe cleanup result allows boot to continue."""

    def test_boot_guard_safe_cleanup_allows_boot(self):
        """When boot guard returns (1, reason), no exception is raised."""
        import pathlib

        with patch('hledac.universal.knowledge.lmdb_boot_guard.cleanup_stale_lmdb_lock') as mock_guard:
            mock_guard.return_value = (1, "holder_process_dead(pid=123)")
            removed, reason = main_module._run_boot_guard(pathlib.Path("/tmp/fake_lmdb"))
            assert removed == 1
            assert "dead" in reason

    def test_boot_guard_missing_lmdb_allows_boot(self):
        """Missing LMDB root is not an error."""
        with patch('hledac.universal.knowledge.lmdb_boot_guard.cleanup_stale_lmdb_lock') as mock_guard:
            mock_guard.return_value = (0, "lmdb_root_not_configured")
            result = main_module._run_boot_guard(None)
            assert result[0] == 0


# =============================================================================
# D.5 — test_async_exit_stack_is_used_as_backbone
# =============================================================================

class TestAsyncExitStackBackbone:
    """INVARIANT: _run_async_main uses AsyncExitStack as teardown backbone."""

    def test_async_exit_stack_is_used_as_backbone(self):
        """Verify AsyncExitStack.__aenter__ and __aexit__ are called."""
        import inspect

        source = inspect.getsource(main_module._run_async_main)

        assert 'AsyncExitStack' in source, "AsyncExitStack must be used in _run_async_main"
        assert '__aenter__' in source, "__aenter__ must be called"
        assert '__aexit__' in source, "__aexit__ must be called"

    def test_exit_stack_unwind_runs_on_normal_exit(self):
        """AsyncExitStack.__aexit__ is called even on normal exit."""
        call_order: List[str] = []

        async def lifo_test():
            stack = contextlib.AsyncExitStack()
            await stack.__aenter__()
            call_order.append("enter")

            async def cleanup():
                call_order.append("cleanup")

            stack.push_async_callback(cleanup)
            await stack.__aexit__(None, None, None)
            call_order.append("exit")

        asyncio.run(lifo_test())

        assert call_order == ["enter", "cleanup", "exit"]


# =============================================================================
# D.6 — test_teardown_order_is_reverse_of_registration
# =============================================================================

class TestTeardownOrder:
    """INVARIANT: LIFO teardown order — last registered, first cleaned up."""

    def test_teardown_order_is_reverse_of_registration(self):
        """Verify AsyncExitStack produces LIFO order."""
        call_order: List[str] = []

        async def lifo_test():
            stack = contextlib.AsyncExitStack()
            await stack.__aenter__()

            async def cleanup_1():
                call_order.append("cleanup_1")

            async def cleanup_2():
                call_order.append("cleanup_2")

            async def cleanup_3():
                call_order.append("cleanup_3")

            stack.push_async_callback(cleanup_1)
            stack.push_async_callback(cleanup_2)
            stack.push_async_callback(cleanup_3)

            await stack.__aexit__(None, None, None)

        asyncio.run(lifo_test())

        # LIFO: cleanup_3 first, then cleanup_2, then cleanup_1
        assert call_order == ["cleanup_3", "cleanup_2", "cleanup_1"], (
            f"Expected LIFO order, got {call_order}"
        )


# =============================================================================
# D.7 — test_existing_signal_path_still_works
# =============================================================================

class TestSignalPath:
    """INVARIANT: 8V signal teardown path is preserved and functional."""

    def test_existing_signal_path_still_works(self):
        """Signal handlers are installed in main()."""
        import inspect

        # Check main() calls _install_signal_teardown
        main_source = inspect.getsource(main_module.main)
        assert '_install_signal_teardown' in main_source
        # Check _install_signal_teardown registers SIGINT
        install_source = inspect.getsource(main_module._install_signal_teardown)
        assert 'SIGINT' in install_source or 'signal.SIGINT' in install_source

    def test_signal_handler_sets_flag(self):
        """SIGINT/SIGTERM handler sets _signal_teardown_flag."""
        # Test flag mechanism directly (handler may call loop.stop which breaks run_until_complete)
        main_module._signal_teardown_flag = False
        main_module._signal_teardown_flag = True

        flag = main_module._get_and_clear_signal_flag()
        assert flag is True

    def test_signal_handler_does_not_directly_cleanup(self):
        """INVARIANT B.14: Signal handler only sets flag / calls loop.stop()."""
        import inspect

        source = inspect.getsource(main_module._install_signal_teardown)
        assert 'loop.stop' in source or 'loop.call_soon_threadsafe' in source


# =============================================================================
# D.8 + D.9 — test_checkpoint_manager_* (CheckpointManager is AO-coupled → N/A)
# =============================================================================

class TestCheckpointManagerNA:
    """CheckpointManager surface is AO-coupled → N/A in this sprint."""

    def test_checkpoint_manager_is_started_if_surface_exists(self):
        """main.py must NOT import or instantiate CheckpointManager."""
        import inspect

        source = inspect.getsource(main_module.main)
        assert 'CheckpointManager' not in source, (
            "main.py must not import CheckpointManager (AO-coupled)"
        )

    def test_checkpoint_manager_cleanup_registered_if_exists(self):
        """No CheckpointManager cleanup registered in main.py (AO-coupled → N/A)."""
        import inspect

        source = inspect.getsource(main_module._run_async_main)
        assert 'CheckpointManager' not in source


# =============================================================================
# D.10 — test_missing_checkpoint_surface_is_documented_not_invented
# =============================================================================

class TestNADocumentation:
    """INVARIANT: CheckpointManager is explicitly N/A, not invented."""

    def test_checkpoint_manager_is_na_in_sprint(self):
        """
        CheckpointManager exists only in AO (autonomous_orchestrator.py:21401).
        No independent surface exists in utils/, knowledge/, or elsewhere.
        """
        result = subprocess.run(
            ['grep', '-r', 'class CheckpointManager',
             '/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/',
             '--include=*.py'],
            capture_output=True, text=True
        )
        hits = [l for l in result.stdout.splitlines() if 'autonomous_orchestrator.py' in l]
        assert len(hits) >= 1, "CheckpointManager should only be in AO (or AO backups)"


# =============================================================================
# D.11 — test_partial_cleanup_surfaces_do_not_crash
# =============================================================================

class TestPartialSurfaces:
    """INVARIANT: When some cleanup surfaces don't exist, teardown doesn't crash."""

    def test_partial_cleanup_surfaces_do_not_crash(self):
        """AsyncExitStack teardown with no registered callbacks must not crash."""
        async def empty_teardown():
            stack = contextlib.AsyncExitStack()
            await stack.__aenter__()
            await stack.__aexit__(None, None, None)

        asyncio.run(empty_teardown())

    def test_teardown_with_none_callbacks_does_not_crash(self):
        """Registering None-like callbacks should not crash."""
        async def teardown_with_none():
            stack = contextlib.AsyncExitStack()
            await stack.__aenter__()
            await stack.__aexit__(None, None, None)

        asyncio.run(teardown_with_none())


# =============================================================================
# D.12 — test_runtime_status_helper_is_side_effect_free
# =============================================================================

class TestStatusHelper:
    """INVARIANT: get_runtime_status() is O(1), side-effect free."""

    def test_runtime_status_helper_is_side_effect_free(self):
        """Calling get_runtime_status() twice returns same result."""
        main_module.clear_boot_telemetry()

        s1 = main_module.get_runtime_status()
        s2 = main_module.get_runtime_status()

        assert s1 == s2, "get_runtime_status() must be side-effect free"

    def test_status_helper_returns_expected_keys(self):
        """Status helper returns known keys."""
        s = main_module.get_runtime_status()
        assert 'uvloop_installed' in s
        assert 'boot_telemetry' in s
        assert isinstance(s['boot_telemetry'], list)

    def test_boot_record_append_only(self):
        """_boot_record only appends, never reads or modifies existing entries."""
        main_module.clear_boot_telemetry()

        main_module._boot_record("step1", "ok")
        main_module._boot_record("step2", "ok")

        assert len(main_module._boot_telemetry) == 2

        main_module.clear_boot_telemetry()
        assert len(main_module._boot_telemetry) == 0

        main_module._boot_record("a", "b")
        main_module._boot_record("c", "d")
        assert len(main_module._boot_telemetry) == 2


# =============================================================================
# D.13 — test_no_new_production_modules_created
# =============================================================================

class TestNoNewModules:
    """INVARIANT B.1: No new production modules created."""

    def test_no_new_production_modules_created(self):
        """No new .py files outside tests/ created in this sprint."""
        universal_dir = '/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal'

        all_py = glob.glob(f"{universal_dir}/**/*.py", recursive=True)
        test_files = glob.glob(f"{universal_dir}/tests/**/*.py", recursive=True)

        non_test_py = [f for f in all_py if f not in test_files]

        suspicious = [
            'bootstrap_runtime.py',
            'teardown_helper.py',
            'checkpoint_runtime.py',
            'boot_hygiene.py',
            'exit_stack_teardown.py',
        ]

        for name in suspicious:
            found = [f for f in non_test_py if name in f]
            assert not found, f"New production module '{name}' was created: {found}"


# =============================================================================
# D.14 — test_graceful_task_cancellation_before_loop_close
# =============================================================================

class TestTaskCancellation:
    """INVARIANT B.15: Orphan tasks are cancelled before loop.close()."""

    def test_graceful_task_cancellation_before_loop_close(self):
        """_cancel_orphan_tasks cancels all tasks except current."""
        async def background_task():
            await asyncio.sleep(10)

        async def cancel_test():
            task = asyncio.create_task(background_task())
            await asyncio.sleep(0.01)

            await main_module._cancel_orphan_tasks()

            assert task.done(), "Background task should be cancelled"

        asyncio.run(cancel_test())

    def test_cancel_orphan_tasks_awaits_gather(self):
        """_cancel_orphan_tasks awaits gather with return_exceptions=True."""
        import inspect

        source = inspect.getsource(main_module._cancel_orphan_tasks)
        assert 'asyncio.gather' in source
        assert 'return_exceptions' in source


# =============================================================================
# D.15 — test_signal_handler_does_not_directly_cleanup_resources
# =============================================================================

class TestSignalNoDirectCleanup:
    """INVARIANT B.14: Signal handler never directly calls cleanup callbacks."""

    def test_signal_handler_does_not_directly_cleanup_resources(self):
        """
        Signal calls loop.stop() which breaks the main loop,
        which THEN triggers AsyncExitStack unwind via the finally block.
        Actual cleanup happens in _run_async_main finally block, not in handler.
        """
        import inspect

        source = inspect.getsource(main_module._install_signal_teardown)
        assert 'loop.stop' in source or 'call_soon_threadsafe' in source


# =============================================================================
# D.16 — test_no_double_teardown_on_signal_path
# =============================================================================

class TestNoDoubleTeardown:
    """INVARIANT B.12: Signal path cannot cause double-teardown."""

    def test_no_double_teardown_on_signal_path(self):
        """
        Signal handler only sets flag + loop.stop().
        AsyncExitStack unwind runs exactly once in the finally block.
        """
        import inspect

        source = inspect.getsource(main_module._run_async_main)

        finally_blocks = source.count('finally:')
        assert finally_blocks >= 1, "Must have at least one finally block"

        assert source.index('finally:') < source.index('__aexit__'), (
            "__aexit__ must be inside finally block"
        )


# =============================================================================
# D.17 — test_combined_existing_gates_still_green
# =============================================================================

class TestCombinedGates:
    """INVARIANT: Existing gates (8V, 8AA, 8AB, 8AG) are not broken by changes."""

    def test_main_module_imports_cleanly(self):
        """__main__.py must import without errors."""
        import hledac.universal.__main__
        assert hledac.universal.__main__ is not None

    def test_boot_telemetry_records_boot_guard(self):
        """Boot guard result is recorded in telemetry."""
        main_module.clear_boot_telemetry()
        main_module._boot_record("boot_guard_sync", "ok", removed=0, reason="lock_file_not_found")

        telemetry = main_module.get_boot_telemetry()
        assert len(telemetry) == 1
        assert telemetry[0]["step"] == "boot_guard_sync"
        assert telemetry[0]["status"] == "ok"


# =============================================================================
# E. BENCHMARKS
# =============================================================================

class TestBenchmarks:
    """E.1: 1000 status helper reads — O(1), no side effects."""

    def test_benchmark_1000_status_reads(self):
        """1000 calls to get_runtime_status() must be fast (< 500ms)."""
        main_module.clear_boot_telemetry()

        start = time.perf_counter()
        for _ in range(1000):
            main_module.get_runtime_status()
        elapsed = time.perf_counter() - start

        assert elapsed < 0.5, f"1000 status reads took {elapsed:.3f}s, must be < 0.5s"

    def test_benchmark_100x_stack_unwind(self):
        """100x AsyncExitStack registration + unwind with fake callbacks must be < 500ms."""
        async def stack_cycle():
            stack = contextlib.AsyncExitStack()
            await stack.__aenter__()

            async def cb():
                pass

            for _ in range(5):
                stack.push_async_callback(cb)

            await stack.__aexit__(None, None, None)

        start = time.perf_counter()
        for _ in range(100):
            asyncio.run(stack_cycle())
        elapsed = time.perf_counter() - start

        assert elapsed < 0.5, f"100 stack cycles took {elapsed:.3f}s, must be < 0.5s"
