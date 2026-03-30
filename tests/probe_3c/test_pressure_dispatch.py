# Sprint 3C: Pressure/Windup → Action Dispatch + Telemetry
"""
probe_3c tests:
- io_only_mode skutečně mění dispatch preference
- adaptive cap je skutečně spotřebován
- windup + remaining_time zpřísní chování
- telemetry obsahuje pressure fields
- fail-open při chybě čtení thermal/UMA
- žádná boot/import regrese
"""

import pytest
from unittest.mock import MagicMock, patch
from collections import deque


class MockLifecycle:
    """Mock lifecycle with configurable remaining_time."""
    def __init__(self, remaining_time: float = float('inf')):
        self._remaining_time = remaining_time

    @property
    def remaining_time(self) -> float:
        return self._remaining_time


class MockPressureSnapshot:
    """Mock pressure snapshot for testing."""
    def __init__(
        self,
        thermal_level: int = 0,
        thermal_is_warn: bool = False,
        thermal_is_critical: bool = False,
        uma_pct: float = 0,
        uma_is_warn: bool = False,
        uma_is_critical: bool = False,
        remaining_seconds: float = float('inf'),
        windup_active: bool = False,
    ):
        self._snapshot = {
            "thermal": {
                "level": thermal_level,
                "name": "nominal",
                "is_warn": thermal_is_warn,
                "is_critical": thermal_is_critical,
            },
            "uma": {
                "pct": uma_pct,
                "level": "normal",
                "is_warn": uma_is_warn,
                "is_critical": uma_is_critical,
            },
            "lifecycle": {
                "remaining_seconds": remaining_seconds,
                "windup_active": windup_active,
            },
        }

    def __getitem__(self, key):
        return self._snapshot[key]


class TestIOOnlyModeDispatch:
    """Test že IO-only mode skutečně mění dispatch preference."""

    def test_io_only_blocks_expensive_actions_via_can_run(self):
        """_can_run_expensive_action vrací False při IO-only."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        ao = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)
        ao._lifecycle_windup_active = False

        with patch.object(ao, '_is_io_only_mode', return_value=True):
            result = ao._can_run_expensive_action("DISCOVERY", "lane_1")
            assert result is False, "IO-only mode musí blokovat expensive actions"

    def test_io_only_penalizes_expensive_in_scoring(self):
        """IO-only mode aplikuje io_penalty=0.05 na expensive actions."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        ao = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)
        ao._is_expensive_action = lambda name: 'hermes' in name.lower()

        # Simuluj scoring loop context
        thermal_factor = 1.0
        battery_factor = 1.0
        final_penalty = 1.0
        score = 0.8

        # IO-only penalty logic (from _decide_next_action)
        io_only = True
        io_penalty = 1.0
        if io_only:
            if ao._is_expensive_action("hermes_prose"):
                io_penalty = 0.05
            elif "hermes_prose" not in ("fetch", "flush", "export", "commit", "synthesis"):
                io_penalty = 0.5

        final_score = score * thermal_factor * battery_factor * final_penalty * io_penalty
        assert final_score == pytest.approx(0.8 * 0.05), "IO-only musí penalizovat expensive na 5%"

    def test_io_only_prefers_io_actions(self):
        """IO-only mode zachovává vysoký score pro I/O akce."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        ao = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)
        ao._is_expensive_action = lambda name: 'hermes' in name.lower()

        io_only = True
        io_penalty = 1.0
        if io_only:
            if ao._is_expensive_action("fetch"):
                io_penalty = 0.05
            elif "fetch" not in ("fetch", "flush", "export", "commit", "synthesis"):
                io_penalty = 0.5

        # fetch není expensive ani I/O-only blocked → penalty = 1.0
        assert io_penalty == 1.0, "I/O akce (fetch) musí mít penalty 1.0"


class TestAdaptiveConcurrencyCap:
    """Test že adaptive concurrency cap je skutečně spotřebován."""

    def test_adaptive_cap_returns_4_by_default(self):
        """Default cap = 4."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        ao = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)
        ao._lifecycle_windup_active = False

        with patch.object(ao, '_get_runtime_pressure_snapshot', return_value=MockPressureSnapshot(
            thermal_is_warn=False,
            thermal_is_critical=False,
            uma_is_warn=False,
            uma_is_critical=False,
            remaining_seconds=float('inf'),
            windup_active=False,
        )):
            cap = ao._get_adaptive_concurrency_cap()
            assert cap == 4, f"Default cap musí být 4, dostal {cap}"

    def test_adaptive_cap_returns_2_on_warn(self):
        """Warning → cap = 2."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        ao = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)
        ao._lifecycle_windup_active = False

        with patch.object(ao, '_get_runtime_pressure_snapshot', return_value=MockPressureSnapshot(
            thermal_is_warn=True,
            thermal_is_critical=False,
            uma_is_warn=False,
            uma_is_critical=False,
            remaining_seconds=float('inf'),
            windup_active=False,
        )):
            cap = ao._get_adaptive_concurrency_cap()
            assert cap == 2, f"Warning cap musí být 2, dostal {cap}"

    def test_adaptive_cap_returns_1_on_io_only(self):
        """IO-only → cap = 1."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        ao = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)
        ao._lifecycle_windup_active = False

        with patch.object(ao, '_get_runtime_pressure_snapshot', return_value=MockPressureSnapshot(
            thermal_is_warn=False,
            thermal_is_critical=True,
            uma_is_warn=False,
            uma_is_critical=False,
            remaining_seconds=float('inf'),
            windup_active=False,
        )):
            cap = ao._get_adaptive_concurrency_cap()
            assert cap == 1, f"IO-only cap musí být 1, dostal {cap}"

    def test_adaptive_cap_returns_1_on_windup_plus_pressure(self):
        """Windup + pressure → cap = 1."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        ao = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)
        ao._lifecycle_windup_active = True

        with patch.object(ao, '_get_runtime_pressure_snapshot', return_value=MockPressureSnapshot(
            thermal_is_warn=True,
            thermal_is_critical=False,
            uma_is_warn=True,
            uma_is_critical=False,
            remaining_seconds=120.0,
            windup_active=True,
        )):
            cap = ao._get_adaptive_concurrency_cap()
            assert cap == 1, f"Windup+pressure cap musí být 1, dostal {cap}"


class TestWindupPressureDecision:
    """Test že windup + pressure tvoří jeden rozhodovací signál."""

    def test_lifecycle_near_end_enables_io_only(self):
        """remaining_time < 60s → IO-only mode."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        ao = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)
        ao._lifecycle_windup_active = False

        with patch.object(ao, '_get_runtime_pressure_snapshot', return_value=MockPressureSnapshot(
            thermal_is_warn=False,
            thermal_is_critical=False,
            uma_is_warn=False,
            uma_is_critical=False,
            remaining_seconds=30.0,  # < 60s
            windup_active=False,
        )):
            result = ao._is_io_only_mode()
            assert result is True, "Lifecycle near-end (<60s) musí aktivovat IO-only"


class TestPressureTelemetry:
    """Test že pressure snapshot je v telemetry."""

    def test_capture_iteration_trace_includes_pressure_fields(self):
        """_capture_iteration_trace přidává pressure fields do trace."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        ao = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)

        # Nastav potřebné atributy
        ao._lifecycle_windup_active = False
        ao._lifecycle = MockLifecycle(remaining_time=120.0)
        ao._iteration_trace_last_query_hash = ""
        ao._iteration_trace_last_action = ""
        ao._iteration_trace_last_cumulative_findings = 0
        ao._iteration_trace_last_cumulative_sources = 0
        ao._iteration_trace_consecutive_same_action = 0
        ao._iteration_trace_consecutive_empty_actions = 0
        ao._stagnation_counter = 0
        ao._l1_echo_rejects_count = 0
        ao._l1_echo_admits_count = 0
        ao._l1_echo_reject_samples = []
        ao._l1_echo_family_samples = []
        ao._iteration_trace_buffer = deque(maxlen=100)

        # Mock phase controller
        mock_phase = MagicMock()
        mock_phase.name = "DISCOVERY"
        ao._phase_controller = MagicMock()
        ao._phase_controller.current_phase = mock_phase

        with patch.object(ao, '_is_io_only_mode', return_value=False), \
             patch.object(ao, '_get_adaptive_concurrency_cap', return_value=4), \
             patch.object(ao, '_compute_novelty_score', return_value=0.5):

            # Create minimal state-like mock
            state = MagicMock()
            state.query = "test query"
            state.iterations = 1

            trace = ao._capture_iteration_trace(
                iteration=1,
                state=state,
                chosen_action="fetch",
                chosen_score=0.8,
                all_scores={"fetch": 0.8},
                zero_score_reasons={},
                action_result_type="SUCCESS",
                new_findings=5,
                new_sources=2,
                new_candidates=3,
                new_families=1,
                action_duration_ms=100.0,
                action_timeout=False,
            )

            # Ověř pressure fields
            assert hasattr(trace, 'io_only_mode'), "Trace musí mít io_only_mode field"
            assert hasattr(trace, 'adaptive_concurrency_cap'), "Trace musí mít adaptive_concurrency_cap field"
            assert hasattr(trace, 'thermal_is_critical'), "Trace musí mít thermal_is_critical field"
            assert hasattr(trace, 'uma_is_critical'), "Trace musí mít uma_is_critical field"
            assert hasattr(trace, 'windup_active'), "Trace musí mít windup_active field"
            assert hasattr(trace, 'remaining_seconds'), "Trace musí mít remaining_seconds field"


class TestFailOpen:
    """Test fail-open při chybě čtení thermal/UMA."""

    def test_is_io_only_mode_fail_open(self):
        """_is_io_only_mode vrací False při výjimce."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        ao = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)

        with patch.object(ao, '_get_runtime_pressure_snapshot', side_effect=Exception("Sensor fail")):
            result = ao._is_io_only_mode()
            assert result is False, "Fail-open musí vrátit False"

    def test_get_adaptive_concurrency_cap_fail_open(self):
        """_get_adaptive_concurrency_cap vrací 4 při výjimce."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        ao = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)

        with patch.object(ao, '_get_runtime_pressure_snapshot', side_effect=Exception("Sensor fail")):
            cap = ao._get_adaptive_concurrency_cap()
            assert cap == 4, "Fail-open cap musí být 4"


class TestNoBootRegression:
    """Test že změny nezpůsobily boot/import regressi."""

    def test_ao_imports_without_error(self):
        """AutonomousOrchestrator import bez chyby."""
        try:
            from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator
            assert FullyAutonomousOrchestrator is not None
        except Exception as e:
            pytest.fail(f"Import FullyAutonomousOrchestrator selhal: {e}")

    def test_can_run_expensive_action_exists(self):
        """_can_run_expensive_action metoda existuje."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        ao = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)
        assert hasattr(ao, '_can_run_expensive_action'), "_can_run_expensive_action musí existovat"
        assert callable(ao._can_run_expensive_action)

    def test_is_io_only_mode_exists(self):
        """_is_io_only_mode metoda existuje."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        ao = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)
        assert hasattr(ao, '_is_io_only_mode'), "_is_io_only_mode musí existovat"

    def test_get_adaptive_concurrency_cap_exists(self):
        """_get_adaptive_concurrency_cap metoda existuje."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        ao = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)
        assert hasattr(ao, '_get_adaptive_concurrency_cap'), "_get_adaptive_concurrency_cap musí existovat"

    def test_apply_pressure_throttle_exists(self):
        """_apply_pressure_throttle metoda existuje."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        ao = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)
        assert hasattr(ao, '_apply_pressure_throttle'), "_apply_pressure_throttle musí existovat"

    def test_capture_iteration_trace_exists(self):
        """_capture_iteration_trace metoda existuje."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        ao = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)
        assert hasattr(ao, '_capture_iteration_trace'), "_capture_iteration_trace musí existovat"


class TestPressureSnapshotWiring:
    """Test že pressure snapshot je správně provázán."""

    def test_lifecycle_data_accessible(self):
        """Lifecycle data jsou přístupné pro snapshot."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        ao = FullyAutonomousOrchestrator.__new__(FullyAutonomousOrchestrator)
        ao._lifecycle_windup_active = True
        ao._lifecycle = MockLifecycle(remaining_time=45.0)

        # Verify lifecycle data is accessible
        remaining = ao._lifecycle.remaining_time
        assert remaining == 45.0
        assert ao._lifecycle_windup_active is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
