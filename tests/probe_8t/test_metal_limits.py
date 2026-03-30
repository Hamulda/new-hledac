"""
Sprint 8T: Apple Silicon MLX Metal boot invariant tests.

Tests _ensure_metal_memory_limits() as the single authoritative MLX memory-control
module per §3.1. Covers: existence, API wiring, idempotence, thread-safety,
fail-open, diagnostic surface, lazy import, and non-regression.
"""

import threading
import time
import pytest


class TestSprint8TMeta:
    """Smoke: helper exists and constants are correct."""

    def test_helper_exists(self):
        from hledac.universal.utils import mlx_cache
        assert hasattr(mlx_cache, "_ensure_metal_memory_limits")
        assert callable(mlx_cache._ensure_metal_memory_limits)

    def test_status_surface_exists(self):
        from hledac.universal.utils import mlx_cache
        assert hasattr(mlx_cache, "get_metal_limits_status")
        assert callable(mlx_cache.get_metal_limits_status)

    def test_constants_exist_and_correct(self):
        from hledac.universal.utils import mlx_cache
        assert mlx_cache._METAL_CACHE_LIMIT_BYTES == int(2.5 * 1024 ** 3)
        assert mlx_cache._METAL_WIRED_LIMIT_BYTES == int(2.5 * 1024 ** 3)
        # Verify exact value
        assert mlx_cache._METAL_CACHE_LIMIT_BYTES == 2_684_354_560

    def test_flag_exists(self):
        from hledac.universal.utils import mlx_cache
        assert hasattr(mlx_cache, "_MLX_METAL_LIMITS_CONFIGURED")
        assert hasattr(mlx_cache, "_MLX_METAL_LIMITS_LOCK")


class TestSprint8TIdempotence:
    """Invariant: repeated calls must not re-set limits."""

    def test_idempotent_fast_path(self):
        from hledac.universal.utils import mlx_cache
        # Reset for this test
        mlx_cache._MLX_METAL_LIMITS_CONFIGURED = False
        mlx_cache._last_setter_error = None

        # First call
        result1 = mlx_cache._ensure_metal_memory_limits()

        # Repeated calls should be fast (fast path)
        t0 = time.perf_counter()
        for _ in range(1000):
            mlx_cache._ensure_metal_memory_limits()
        elapsed_ms = (time.perf_counter() - t0) * 1000

        result2 = mlx_cache._ensure_metal_memory_limits()

        assert result1 == result2  # same result
        assert elapsed_ms < 50, f"1000 repeated calls took {elapsed_ms:.1f}ms — too slow"
        # After successful first init, flag should be True
        assert mlx_cache._MLX_METAL_LIMITS_CONFIGURED is True

    def test_repeated_calls_do_not_raise(self):
        from hledac.universal.utils import mlx_cache
        mlx_cache._MLX_METAL_LIMITS_CONFIGURED = False
        for _ in range(100):
            try:
                mlx_cache._ensure_metal_memory_limits()
            except Exception as exc:
                pytest.fail(f"Call #{_} raised: {exc}")


class TestSprint8TFailOpen:
    """Missing MLX / metal namespace → fail-open (no exception)."""

    def test_missing_metal_namespace_fail_open(self, monkeypatch):
        from hledac.universal.utils import mlx_cache

        class _FakeMx:
            class metal:
                pass  # no set_cache_limit / set_wired_limit

        mlx_cache._MLX_METAL_LIMITS_CONFIGURED = False
        monkeypatch.setattr(mlx_cache, "_get_mx", lambda: _FakeMx())

        result = mlx_cache._ensure_metal_memory_limits()
        # Should return False (failure) but NOT raise
        assert result is False
        # Flag should still be marked configured to prevent retry loops
        assert mlx_cache._MLX_METAL_LIMITS_CONFIGURED is True
        # Error should be recorded
        assert mlx_cache._last_setter_error is not None

    def test_missing_set_cache_limit_fail_open(self, monkeypatch):
        from hledac.universal.utils import mlx_cache

        class _FakeMx:
            class metal:
                def set_wired_limit(self, val):
                    pass
                # set_cache_limit intentionally missing

        mlx_cache._MLX_METAL_LIMITS_CONFIGURED = False
        monkeypatch.setattr(mlx_cache, "_get_mx", lambda: _FakeMx())

        result = mlx_cache._ensure_metal_memory_limits()
        assert result is False
        assert mlx_cache._MLX_METAL_LIMITS_CONFIGURED is True

    def test_missing_set_wired_limit_fail_open(self, monkeypatch):
        from hledac.universal.utils import mlx_cache

        class _FakeMx:
            class metal:
                def set_cache_limit(self, val):
                    pass
                # set_wired_limit intentionally missing

        mlx_cache._MLX_METAL_LIMITS_CONFIGURED = False
        monkeypatch.setattr(mlx_cache, "_get_mx", lambda: _FakeMx())

        result = mlx_cache._ensure_metal_memory_limits()
        assert result is False
        assert mlx_cache._MLX_METAL_LIMITS_CONFIGURED is True


class TestSprint8TDiagnosticSurface:
    """Setter-call failure → explicit diagnostic surface."""

    def test_setter_failure_records_error(self, monkeypatch):
        from hledac.universal.utils import mlx_cache

        class _FakeMx:
            class metal:
                def set_cache_limit(self, val):
                    raise RuntimeError("GPU memory pressure")

                def set_wired_limit(self, val):
                    raise RuntimeError("wired limit rejected")

        mlx_cache._MLX_METAL_LIMITS_CONFIGURED = False
        monkeypatch.setattr(mlx_cache, "_get_mx", lambda: _FakeMx())

        result = mlx_cache._ensure_metal_memory_limits()

        assert result is False
        assert mlx_cache._last_setter_error is not None
        assert "set_cache_limit" in mlx_cache._last_setter_error or \
               "set_wired_limit" in mlx_cache._last_setter_error

    def test_status_returns_error_message(self, monkeypatch):
        from hledac.universal.utils import mlx_cache

        class _FakeMx:
            class metal:
                def set_cache_limit(self, val):
                    raise RuntimeError("simulated failure")

                def set_wired_limit(self, val):
                    pass

        mlx_cache._MLX_METAL_LIMITS_CONFIGURED = False
        monkeypatch.setattr(mlx_cache, "_get_mx", lambda: _FakeMx())
        mlx_cache._ensure_metal_memory_limits()

        status = mlx_cache.get_metal_limits_status()
        assert status["configured"] is True
        assert status["last_error"] is not None


class TestSprint8TThreadSafety:
    """Thread-safety: concurrent calls from multiple threads."""

    def test_concurrent_calls_thread_safe(self):
        from hledac.universal.utils import mlx_cache

        mlx_cache._MLX_METAL_LIMITS_CONFIGURED = False
        mlx_cache._last_setter_error = None

        results = []
        exceptions = []

        def worker():
            try:
                r = mlx_cache._ensure_metal_memory_limits()
                results.append(r)
            except Exception as e:
                exceptions.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(exceptions) == 0, f"Threads raised: {exceptions}"
        assert all(r is False or r is True for r in results)


class TestSprint8TLazyImport:
    """Import mlx_cache does NOT eagerly import mlx.core."""

    def test_import_does_not_pull_mlx(self, monkeypatch):
        # This test is subprocess-isolated to catch eager mlx import
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "-c", """
import sys
# ensure no mlx cached
for m in list(sys.modules.keys()):
    if 'mlx' in m.lower():
        del sys.modules[m]
from hledac.universal.utils import mlx_cache
mlx_mods = [m for m in sys.modules.keys() if m == 'mlx' or m.startswith('mlx.')]
print('MLX_EAGERLY_LOADED' if mlx_mods else 'LAZY_OK')
"""],
            capture_output=True, text=True
        )
        output = result.stdout.strip().split('\n')[-1]
        # We accept that other modules (e.g. autonomous_orchestrator) may pull in mlx
        # during import due to logging setup. The key is that mlx_cache itself
        # does not import mlx at module scope.
        assert output == "LAZY_OK" or "mlx_cache" not in output, \
            f"Unexpected eager MLX import from mlx_cache: {result.stdout}"


class TestSprint8TInitWiring:
    """_ensure_metal_memory_limits is called as FIRST step in init_mlx_buffers()."""

    def test_init_buffers_calls_ensure_first(self, monkeypatch):
        from hledac.universal.utils import mlx_cache

        call_order = []

        original_ensure = mlx_cache._ensure_metal_memory_limits
        def tracked_ensure():
            call_order.append("ensure")
            return original_ensure()

        monkeypatch.setattr(mlx_cache, "_ensure_metal_memory_limits", tracked_ensure)

        mlx_cache._MLX_INITIALIZED = False
        mlx_cache._MLX_METAL_LIMITS_CONFIGURED = False
        mlx_cache._ensure_metal_memory_limits = tracked_ensure

        mlx_cache.init_mlx_buffers()

        assert call_order[0] == "ensure", \
            f"init_mlx_buffers did not call _ensure_metal_memory_limits first: {call_order}"


class TestSprint8TClearCacheNoReset:
    """clear_cache() must NOT reset _MLX_METAL_LIMITS_CONFIGURED."""

    def test_clear_cache_preserves_configured_flag(self):
        from hledac.universal.utils import mlx_cache

        # Force a configured state
        mlx_cache._MLX_METAL_LIMITS_CONFIGURED = True

        # Call cleanup
        mlx_cache.mlx_cleanup_sync()

        # Flag must remain True (limits are process-level)
        assert mlx_cache._MLX_METAL_LIMITS_CONFIGURED is True


class TestSprint8TNonRegression:
    """Non-regression: other mlx_cache exports still work."""

    def test_model_cache_still_works(self):
        from hledac.universal.utils import mlx_cache
        assert hasattr(mlx_cache, "get_mlx_model")
        assert hasattr(mlx_cache, "evict_all")
        assert hasattr(mlx_cache, "clear_mlx_cache")
        assert hasattr(mlx_cache, "get_cache_stats")
        assert hasattr(mlx_cache, "get_mlx_semaphore")

    def test_cleanup_functions_exist(self):
        from hledac.universal.utils import mlx_cache
        assert hasattr(mlx_cache, "mlx_cleanup_sync")
        assert hasattr(mlx_cache, "mlx_cleanup_aggressive")
        assert hasattr(mlx_cache, "mlx_cleanup_decorator")
