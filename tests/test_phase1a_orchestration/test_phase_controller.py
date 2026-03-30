"""
Test Phase Controller
=====================

Tests for PhaseController:
- phase promotion according to time and signals
- sprint doesn't exceed T=30
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

from hledac.universal.orchestrator.phase_controller import (
    Phase, PhaseConfig, PhaseSignals, PhaseController
)


class TestPhaseController:
    """Test PhaseController."""

    def test_phase_enum_values(self):
        """Test phase enum has correct values."""
        assert Phase.DISCOVERY == 1
        assert Phase.CONTRADICTION == 2
        assert Phase.DEEPEN == 3
        assert Phase.SYNTHESIS == 4

    def test_default_config(self):
        """Test default configuration."""
        config = PhaseConfig()
        assert config.max_time_seconds == 1800.0  # 30 min
        assert config.phase_windows[Phase.DISCOVERY] == 300.0  # 5 min
        assert config.phase_windows[Phase.CONTRADICTION] == 900.0  # 15 min
        assert config.phase_windows[Phase.DEEPEN] == 1440.0  # 24 min

    def test_start(self):
        """Test controller start."""
        controller = PhaseController()
        controller.start()

        assert controller.current_phase == Phase.DISCOVERY
        assert controller.elapsed_time >= 0.0

    def test_phase_promotion_by_time(self):
        """Test phase promotion when max time exceeded."""
        controller = PhaseController()
        controller.start()

        # Override phase start time to simulate elapsed time
        controller._phase_start_time = time.time() - 400.0  # 400s > 300s (Phase 1 max)

        signals = PhaseSignals(strong_hypotheses=0)

        # Should promote because time exceeded
        assert controller.should_promote(signals) is True

    def test_phase_promotion_by_signals(self):
        """Test phase promotion by strong signals."""
        controller = PhaseController()
        controller.start()

        # Phase 1: >= 2 strong hypotheses triggers promotion
        signals = PhaseSignals(strong_hypotheses=2)

        assert controller.should_promote(signals) is True

    def test_no_promotion_below_thresholds(self):
        """Test no promotion when below thresholds."""
        controller = PhaseController()
        controller.start()

        # Weak signals, not enough time
        signals = PhaseSignals(
            strong_hypotheses=1,
            contradiction_pressure=0.3,
            beam_stabilized=False,
            time_remaining_ratio=0.8
        )

        assert controller.should_promote(signals) is False

    def test_maybe_promote(self):
        """Test async maybe_promote."""
        controller = PhaseController()
        controller.start()

        # Create signals that trigger promotion
        signals = PhaseSignals(strong_hypotheses=2)

        result = asyncio.get_event_loop().run_until_complete(
            controller.maybe_promote(signals)
        )

        assert result is True
        assert controller.current_phase == Phase.CONTRADICTION

    def test_maybe_promote_callback(self):
        """Test callback is called on promotion."""
        callback = AsyncMock()
        controller = PhaseController(on_phase_change=callback)
        controller.start()

        signals = PhaseSignals(strong_hypotheses=2)

        asyncio.get_event_loop().run_until_complete(
            controller.maybe_promote(signals)
        )

        callback.assert_called_once()

    def test_phase_priority_modifier(self):
        """Test phase priority modifiers."""
        controller = PhaseController()
        controller.start()

        assert controller.get_phase_priority_modifier() == 0.5  # Discovery

        controller._current_phase = Phase.CONTRADICTION
        assert controller.get_phase_priority_modifier() == 1.0

        controller._current_phase = Phase.SYNTHESIS
        assert controller.get_phase_priority_modifier() == 2.0

    def test_should_continue(self):
        """Test should_continue."""
        controller = PhaseController()
        controller.start()

        # Has time remaining
        assert controller.should_continue() is True

    def test_should_continue_max_time(self):
        """Test should_continue returns False at max time."""
        controller = PhaseController()
        controller.start()

        # Simulate max time exceeded
        controller._start_time = time.time() - 1900.0  # > 1800s

        assert controller.should_continue() is False

    def test_get_status(self):
        """Test status reporting."""
        controller = PhaseController()
        controller.start()

        status = controller.get_status()

        assert "phase" in status
        assert "elapsed_time" in status
        assert status["phase"] == "DISCOVERY"
        assert status["should_continue"] is True


class TestPhaseSignals:
    """Test PhaseSignals dataclass."""

    def test_default_signals(self):
        """Test default signal values."""
        signals = PhaseSignals()

        assert signals.strong_hypotheses == 0
        assert signals.contradiction_pressure == 0.0
        assert signals.beam_stabilized is False
        assert signals.gaps_quality == 0.0
        assert signals.time_remaining_ratio == 1.0

    def test_custom_signals(self):
        """Test custom signal values."""
        signals = PhaseSignals(
            strong_hypotheses=3,
            contradiction_pressure=0.8,
            beam_stabilized=True,
            gaps_quality=0.7,
            time_remaining_ratio=0.2
        )

        assert signals.strong_hypotheses == 3
        assert signals.contradiction_pressure == 0.8
        assert signals.beam_stabilized is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
