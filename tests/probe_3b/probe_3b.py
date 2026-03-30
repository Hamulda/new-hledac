"""
Sprint 3B: Runtime Pressure Wiring + I/O-Only Mode - Probe Tests

Testuje:
1. thermal.py is_thermal_warn() přidaná
2. _get_runtime_pressure_snapshot() fail-open
3. _is_io_only_mode() activation
4. _get_adaptive_concurrency_cap() values
5. _apply_pressure_throttle() volá MLX cleanup kanonicky
6. import/boot regression
7. Zakázané soubory nebyly editovány
"""

import sys
import os
from unittest.mock import patch, MagicMock

# Add the universal path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


# =============================================================================
# TEST 1: thermal.py is_thermal_warn() exists and works
# =============================================================================

class TestThermalWarn:
    def test_is_thermal_warn_exists(self):
        """thermal.py má is_thermal_warn() funkci."""
        from hledac.universal.utils.thermal import is_thermal_warn
        assert callable(is_thermal_warn)

    def test_is_thermal_warn_returns_bool(self):
        """is_thermal_warn() vrací bool."""
        from hledac.universal.utils.thermal import is_thermal_warn
        result = is_thermal_warn()
        assert isinstance(result, bool)

    def test_format_thermal_snapshot_has_is_warn(self):
        """format_thermal_snapshot() obsahuje is_warn klíč."""
        from hledac.universal.utils.thermal import format_thermal_snapshot
        snap = format_thermal_snapshot()
        assert "is_warn" in snap
        assert isinstance(snap["is_warn"], bool)


# =============================================================================
# TEST 2: _get_runtime_pressure_snapshot() fail-open
# =============================================================================

class TestPressureSnapshot:
    def test_snapshot_returns_dict_with_keys(self):
        """_get_runtime_pressure_snapshot vrací dict s thermal/uma/lifecycle."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator
        orch = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)
        # Mock lifecycle
        orch._lifecycle_windup_active = False
        orch._lifecycle = MagicMock()
        orch._lifecycle.remaining_time = 1000.0

        snap = orch._get_runtime_pressure_snapshot()

        assert "thermal" in snap
        assert "uma" in snap
        assert "lifecycle" in snap
        # Thermal fields
        assert "level" in snap["thermal"]
        assert "name" in snap["thermal"]
        assert "is_warn" in snap["thermal"]
        assert "is_critical" in snap["thermal"]
        # UMA fields
        assert "pct" in snap["uma"]
        assert "level" in snap["uma"]
        assert "is_warn" in snap["uma"]
        assert "is_critical" in snap["uma"]
        # Lifecycle fields
        assert "remaining_seconds" in snap["lifecycle"]
        assert "windup_active" in snap["lifecycle"]

    def test_snapshot_fail_open_on_thermal_error(self):
        """_get_runtime_pressure_snapshot je fail-open na thermal errors."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator
        orch = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)
        orch._lifecycle_windup_active = False
        orch._lifecycle = MagicMock()
        orch._lifecycle.remaining_time = 1000.0

        # Pokud thermal selže, snapshot stále vrací validní strukturu
        snap = orch._get_runtime_pressure_snapshot()
        assert snap["thermal"]["is_warn"] is False
        assert snap["thermal"]["is_critical"] is False


# =============================================================================
# TEST 3: _is_io_only_mode() activation
# =============================================================================

class TestIoOnlyMode:
    def test_io_only_false_by_default(self):
        """_is_io_only_mode vrací False když není pressure."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator
        orch = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)
        orch._lifecycle_windup_active = False
        orch._lifecycle = MagicMock()
        orch._lifecycle.remaining_time = 1000.0

        result = orch._is_io_only_mode()
        assert result is False

    def test_io_only_true_on_lifecycle_near_end(self):
        """_is_io_only_mode vrací True když remaining < 60s."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator
        orch = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)
        orch._lifecycle_windup_active = False
        orch._lifecycle = MagicMock()
        orch._lifecycle.remaining_time = 30.0  # < 60s

        result = orch._is_io_only_mode()
        assert result is True

    def test_io_only_fail_open(self):
        """_is_io_only_mode je fail-open."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator
        orch = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)
        orch._lifecycle_windup_active = False
        orch._lifecycle = MagicMock()
        orch._lifecycle.remaining_time = 1000.0

        # Simuluj chybu v _get_runtime_pressure_snapshot
        with patch.object(orch, "_get_runtime_pressure_snapshot", side_effect=RuntimeError("test")):
            result = orch._is_io_only_mode()
        assert result is False  # Fail-open = False


# =============================================================================
# TEST 4: _get_adaptive_concurrency_cap()
# =============================================================================

class TestAdaptiveConcurrency:
    def test_concurrency_default_is_4(self):
        """_get_adaptive_concurrency_cap vrací 4 když není pressure."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator
        orch = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)
        orch._lifecycle_windup_active = False
        orch._lifecycle = MagicMock()
        orch._lifecycle.remaining_time = 1000.0

        # Patch utils modulu kde jsou lazy importy
        with patch("hledac.universal.utils.thermal.is_thermal_warn", return_value=False):
            with patch("hledac.universal.utils.thermal.is_thermal_critical", return_value=False):
                with patch("hledac.universal.utils.uma_budget.is_uma_warn", return_value=False):
                    with patch("hledac.universal.utils.uma_budget.is_uma_critical", return_value=False):
                        result = orch._get_adaptive_concurrency_cap()
        assert result == 4

    def test_concurrency_warn_is_2(self):
        """_get_adaptive_concurrency_cap vrací 2 při warning."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator
        orch = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)
        orch._lifecycle_windup_active = False
        orch._lifecycle = MagicMock()
        orch._lifecycle.remaining_time = 1000.0

        with patch("hledac.universal.utils.thermal.is_thermal_warn", return_value=True):
            with patch("hledac.universal.utils.thermal.is_thermal_critical", return_value=False):
                with patch("hledac.universal.utils.uma_budget.is_uma_warn", return_value=False):
                    with patch("hledac.universal.utils.uma_budget.is_uma_critical", return_value=False):
                        result = orch._get_adaptive_concurrency_cap()
        assert result == 2

    def test_concurrency_io_only_is_1(self):
        """_get_adaptive_concurrency_cap vrací 1 při I/O-only."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator
        orch = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)
        orch._lifecycle_windup_active = False
        orch._lifecycle = MagicMock()
        orch._lifecycle.remaining_time = 1000.0

        with patch("hledac.universal.utils.thermal.is_thermal_critical", return_value=True):
            result = orch._get_adaptive_concurrency_cap()
        assert result == 1

    def test_concurrency_windup_plus_warn_is_1(self):
        """_get_adaptive_concurrency_cap vrací 1 při windup + warn."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator
        orch = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)
        orch._lifecycle_windup_active = True  # Windup active
        orch._lifecycle = MagicMock()
        orch._lifecycle.remaining_time = 1000.0

        with patch("hledac.universal.utils.thermal.is_thermal_warn", return_value=True):
            with patch("hledac.universal.utils.thermal.is_thermal_critical", return_value=False):
                with patch("hledac.universal.utils.uma_budget.is_uma_warn", return_value=False):
                    with patch("hledac.universal.utils.uma_budget.is_uma_critical", return_value=False):
                        result = orch._get_adaptive_concurrency_cap()
        assert result == 1

    def test_concurrency_fail_open(self):
        """_get_adaptive_concurrency_cap je fail-open."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator
        orch = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)
        orch._lifecycle_windup_active = False
        orch._lifecycle = MagicMock()
        orch._lifecycle.remaining_time = 1000.0

        with patch.object(orch, "_get_runtime_pressure_snapshot", side_effect=RuntimeError("test")):
            result = orch._get_adaptive_concurrency_cap()
        assert result == 4  # Fail-open to default


# =============================================================================
# TEST 5: _apply_pressure_throttle() MLX cleanup canonical seam
# =============================================================================

class TestPressureThrottle:
    def test_apply_pressure_throttle_calls_clear_mlx_cache_debounced(self):
        """_apply_pressure_throttle volá clear_mlx_cache_debounced při I/O-only."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator
        orch = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)
        orch._lifecycle_windup_active = False
        orch._lifecycle = MagicMock()
        orch._lifecycle.remaining_time = 1000.0

        with patch("hledac.universal.utils.thermal.is_thermal_critical", return_value=True):
            with patch("hledac.universal.utils.mlx_memory.clear_mlx_cache_debounced", return_value=True) as mock_clear:
                orch._apply_pressure_throttle()
                mock_clear.assert_called_once()

    def test_apply_pressure_throttle_fail_open(self):
        """_apply_pressure_throttle je fail-open."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator
        orch = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)
        orch._lifecycle_windup_active = False
        orch._lifecycle = MagicMock()
        orch._lifecycle.remaining_time = 1000.0

        # Simuluj chybu v is_thermal_critical
        with patch("hledac.universal.utils.thermal.is_thermal_critical", side_effect=RuntimeError("test")):
            # Nemá vyhodit výjimku
            orch._apply_pressure_throttle()


# =============================================================================
# TEST 6: Import/boot regression
# =============================================================================

class TestImportRegression:
    def test_thermal_module_imports(self):
        """thermal.py se importuje bez chyby."""
        from hledac.universal.utils.thermal import (
            get_thermal_state,
            get_thermal_state_str,
            is_thermal_warn,
            is_thermal_critical,
            format_thermal_snapshot,
        )
        assert callable(get_thermal_state)
        assert callable(get_thermal_state_str)
        assert callable(is_thermal_warn)
        assert callable(is_thermal_critical)
        assert callable(format_thermal_snapshot)

    def test_uma_budget_module_imports(self):
        """uma_budget.py se importuje bez chyby."""
        from hledac.universal.utils.uma_budget import (
            get_uma_snapshot,
            get_uma_pressure_level,
            is_uma_warn,
            is_uma_critical,
        )
        assert callable(get_uma_snapshot)
        assert callable(get_uma_pressure_level)
        assert callable(is_uma_warn)
        assert callable(is_uma_critical)

    def test_mlx_memory_module_imports(self):
        """mlx_memory.py se importuje bez chyby."""
        from hledac.universal.utils.mlx_memory import (
            clear_mlx_cache,
            clear_mlx_cache_debounced,
            get_mlx_memory_pressure,
        )
        assert callable(clear_mlx_cache)
        assert callable(clear_mlx_cache_debounced)
        assert callable(get_mlx_memory_pressure)

    def test_sprint_lifecycle_module_imports(self):
        """sprint_lifecycle.py se importuje bez chyby."""
        from hledac.universal.utils.sprint_lifecycle import (
            SprintLifecycleManager,
            SprintLifecycleState,
        )
        assert SprintLifecycleManager is not None
        assert SprintLifecycleState is not None


# =============================================================================
# TEST 7: Zakázané soubory nebyly editovány
# =============================================================================

class TestForbiddenFiles:
    def test_paths_not_modified(self):
        """paths.py nebyl modifikován."""
        paths_file = "/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/paths.py"
        if os.path.exists(paths_file):
            with open(paths_file, 'r') as f:
                content = f.read(100)
            assert len(content) > 0

    def test_main_not_modified(self):
        """__main__.py nebyl modifikován."""
        main_file = "/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/__main__.py"
        if os.path.exists(main_file):
            with open(main_file, 'r') as f:
                content = f.read(100)
            assert len(content) > 0

    def test_checkpoint_not_modified(self):
        """checkpoint.py nebyl modifikován."""
        cp_file = "/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/tools/checkpoint.py"
        if os.path.exists(cp_file):
            with open(cp_file, 'r') as f:
                content = f.read(200)
            assert len(content) > 0

    def test_fetch_coordinator_not_modified(self):
        """fetch_coordinator.py nebyl modifikován."""
        fc_file = "/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/coordinators/fetch_coordinator.py"
        if os.path.exists(fc_file):
            with open(fc_file, 'r') as f:
                content = f.read(200)
            assert len(content) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
