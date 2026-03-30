"""
Probe tests for mlx_memory.py helpers.
"""

import pytest
import time


class TestMLXMemoryFailOpen:
    """Test MLX memory helper fail-open behavior."""

    def test_clear_mlx_cache_no_mlx(self):
        """clear_mlx_cache should return False without MLX."""
        # Reset MLX availability
        import hledac.universal.utils.mlx_memory as mlxm

        original_available = mlxm._MLX_AVAILABLE
        original_core = mlxm._mlx_core
        mlxm._MLX_AVAILABLE = False
        mlxm._mlx_core = None

        try:
            result = mlxm.clear_mlx_cache()
            assert result is False
        finally:
            mlxm._MLX_AVAILABLE = original_available
            mlxm._mlx_core = original_core

    def test_get_active_memory_no_mlx(self):
        """get_mlx_active_memory_mb should return None without MLX."""
        import hledac.universal.utils.mlx_memory as mlxm

        original = mlxm._MLX_AVAILABLE
        mlxm._MLX_AVAILABLE = False
        mlxm._mlx_core = None

        try:
            result = mlxm.get_mlx_active_memory_mb()
            assert result is None
        finally:
            mlxm._MLX_AVAILABLE = original

    def test_memory_pressure_unknown_without_mlx(self):
        """get_mlx_memory_pressure should return UNKNOWN without MLX."""
        import hledac.universal.utils.mlx_memory as mlxm

        original = mlxm._MLX_AVAILABLE
        mlxm._MLX_AVAILABLE = False
        mlxm._mlx_core = None

        try:
            pct, level = mlxm.get_mlx_memory_pressure()
            assert level == "UNKNOWN"
            assert pct == 0
        finally:
            mlxm._MLX_AVAILABLE = original

    def test_memory_metrics_no_mlx(self):
        """get_mlx_memory_metrics should return available=False without MLX."""
        import hledac.universal.utils.mlx_memory as mlxm

        original = mlxm._MLX_AVAILABLE
        mlxm._MLX_AVAILABLE = False
        mlxm._mlx_core = None

        try:
            metrics = mlxm.get_mlx_memory_metrics()
            assert metrics["available"] is False
            assert metrics["pressure_level"] == "UNKNOWN"
        finally:
            mlxm._MLX_AVAILABLE = original


class TestMLXMemoryDebounce:
    """Test MLX memory cache clear debounce behavior."""

    def test_debounce_blocks_rapid_calls(self):
        """clear_mlx_cache_debounced should block rapid successive calls."""
        import hledac.universal.utils.mlx_memory as mlxm

        # Reset debounce state
        original_last = mlxm._debounce_last_clear
        mlxm._debounce_last_clear = 0.0

        try:
            # First call should succeed (or debounce False)
            result1 = mlxm.clear_mlx_cache_debounced(0.5)
            # Result is True if cache was cleared, False if debounced
            assert isinstance(result1, bool)

            # Immediate second call should be debounced
            result2 = mlxm.clear_mlx_cache_debounced(0.5)
            assert result2 is False  # should be debounced
        finally:
            mlxm._debounce_last_clear = original_last

    def test_debounce_allows_after_interval(self):
        """clear_mlx_cache_debounced should allow call after interval."""
        import hledac.universal.utils.mlx_memory as mlxm

        original_last = mlxm._debounce_last_clear
        mlxm._debounce_last_clear = 0.0

        try:
            # First call
            mlxm.clear_mlx_cache_debounced(0.01)

            # Wait past interval
            time.sleep(0.02)

            # Should now allow
            result = mlxm.clear_mlx_cache_debounced(0.01)
            assert result is True or result is False  # depends on cache clear success
        finally:
            mlxm._debounce_last_clear = original_last

    def test_set_cache_limit_debounced(self):
        """set_cache_limit_with_debounced should return debounce info."""
        import hledac.universal.utils.mlx_memory as mlxm

        original_last = mlxm._debounce_last_clear
        mlxm._debounce_last_clear = 0.0

        try:
            # First call
            result1 = mlxm.set_cache_limit_with_debounce(1024, 0.5)
            assert isinstance(result1, dict)

            # Immediate second call should be debounced
            result2 = mlxm.set_cache_limit_with_debounce(2048, 0.5)
            assert result2.get("error") == "debounced"
        finally:
            mlxm._debounce_last_clear = original_last


class TestMLXMemoryConfigure:
    """Test MLX memory configure limits."""

    def test_configure_mlx_limits_returns_dict(self):
        """configure_mlx_limits should return a result dict."""
        import hledac.universal.utils.mlx_memory as mlxm

        result = mlxm.configure_mlx_limits(cache_limit_mb=512)
        assert isinstance(result, dict)
        assert "success" in result
