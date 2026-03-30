"""
Probe tests for import regression - ensure no boot-path regressions.
"""

import pytest


class TestNoImportRegression:
    """Verify utils can be imported without side effects."""

    def test_thermal_import_no_error(self):
        """thermal.py should import without errors."""
        from hledac.universal.utils.thermal import (
            get_thermal_state,
            get_thermal_state_str,
            is_thermal_critical,
            format_thermal_snapshot,
        )

        assert callable(get_thermal_state)
        assert callable(get_thermal_state_str)
        assert callable(is_thermal_critical)
        assert callable(format_thermal_snapshot)

    def test_uma_budget_import_no_error(self):
        """uma_budget.py should import without errors."""
        from hledac.universal.utils.uma_budget import (
            get_uma_snapshot,
            get_uma_usage_mb,
            get_uma_pressure_level,
            is_uma_critical,
            is_uma_warn,
            format_uma_budget_report,
        )

        assert callable(get_uma_snapshot)
        assert callable(get_uma_usage_mb)
        assert callable(get_uma_pressure_level)
        assert callable(is_uma_critical)
        assert callable(is_uma_warn)
        assert callable(format_uma_budget_report)

    def test_mlx_memory_import_no_error(self):
        """mlx_memory.py should import without errors."""
        from hledac.universal.utils.mlx_memory import (
            clear_mlx_cache,
            clear_mlx_cache_debounced,
            set_cache_limit_with_debounce,
            get_mlx_active_memory_mb,
            get_mlx_peak_memory_mb,
            get_mlx_cache_memory_mb,
            get_mlx_memory_pressure,
            get_mlx_memory_metrics,
            configure_mlx_limits,
            format_mlx_memory_snapshot,
        )

        assert callable(clear_mlx_cache)
        assert callable(clear_mlx_cache_debounced)
        assert callable(set_cache_limit_with_debounce)
        assert callable(get_mlx_active_memory_mb)
        assert callable(get_mlx_peak_memory_mb)
        assert callable(get_mlx_cache_memory_mb)
        assert callable(get_mlx_memory_pressure)
        assert callable(get_mlx_memory_metrics)
        assert callable(configure_mlx_limits)
        assert callable(format_mlx_memory_snapshot)

    def test_duckdb_store_import_no_error(self):
        """duckdb_store.py should import without errors."""
        from hledac.universal.knowledge.duckdb_store import (
            DuckDBShadowStore,
            _get_duckdb,
            _DUCKDB_MEMORY_LIMIT,
            _DUCKDB_MAX_TEMP,
        )

        assert DuckDBShadowStore is not None
        assert callable(_get_duckdb)
        assert isinstance(_DUCKDB_MEMORY_LIMIT, str)
        assert isinstance(_DUCKDB_MAX_TEMP, str)
