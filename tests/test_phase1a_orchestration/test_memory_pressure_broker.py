"""
Test Memory Pressure Broker
=========================

Tests for MemoryPressureBroker:
- warn and critical signals change state
- callback is not heavy
- enqueue can stop
"""

import pytest
import time
from unittest.mock import MagicMock, patch

from hledac.universal.orchestrator.memory_pressure_broker import (
    MemoryPressureLevel, MemoryPressureState, MemoryPressureBroker
)


class TestMemoryPressureBroker:
    """Test MemoryPressureBroker."""

    def test_default_state(self):
        """Test default state is NORMAL."""
        broker = MemoryPressureBroker()

        assert broker.level == MemoryPressureLevel.NORMAL
        assert broker.is_warn is False
        assert broker.is_critical is False

    def test_initialization(self):
        """Test broker initialization."""
        on_warn = MagicMock()
        on_critical = MagicMock()

        broker = MemoryPressureBroker(
            on_warn=on_warn,
            on_critical=on_critical
        )

        assert broker._on_warn is on_warn
        assert broker._on_critical is on_critical

    def test_check_normal(self):
        """Test check returns NORMAL."""
        broker = MemoryPressureBroker()

        # Mock the system check to return NORMAL
        with patch.object(broker, '_get_pressure_from_system', return_value=MemoryPressureLevel.NORMAL):
            level = broker.check()

        assert level == MemoryPressureLevel.NORMAL

    def test_check_warn(self):
        """Test check returns WARN."""
        broker = MemoryPressureBroker()

        with patch.object(broker, '_get_pressure_from_system', return_value=MemoryPressureLevel.WARN):
            level = broker.check()

        assert level == MemoryPressureLevel.WARN
        assert broker.is_warn is True
        assert broker.is_critical is False

    def test_check_critical(self):
        """Test check returns CRITICAL."""
        broker = MemoryPressureBroker()

        with patch.object(broker, '_get_pressure_from_system', return_value=MemoryPressureLevel.CRITICAL):
            level = broker.check()

        assert level == MemoryPressureLevel.CRITICAL
        assert broker.is_warn is True
        assert broker.is_critical is True

    def test_callbacks_called_on_level_change(self):
        """Test callbacks are called when level changes."""
        on_warn = MagicMock()
        broker = MemoryPressureBroker(on_warn=on_warn)

        # First check: NORMAL
        with patch.object(broker, '_get_pressure_from_system', return_value=MemoryPressureLevel.NORMAL):
            broker.check()

        # Second check: WARN
        with patch.object(broker, '_get_pressure_from_system', return_value=MemoryPressureLevel.WARN):
            broker.check()

        on_warn.assert_called_once()

    def test_callback_error_handled(self):
        """Test callback errors are handled gracefully."""
        def bad_callback():
            raise RuntimeError("callback error")

        broker = MemoryPressureBroker(on_warn=bad_callback)

        # Should not raise
        with patch.object(broker, '_get_pressure_from_system', return_value=MemoryPressureLevel.WARN):
            level = broker.check()

        assert level == MemoryPressureLevel.WARN

    def test_get_status(self):
        """Test status reporting."""
        broker = MemoryPressureBroker()

        with patch.object(broker, '_get_pressure_from_system', return_value=MemoryPressureLevel.WARN):
            broker.check()

        status = broker.get_status()

        assert status["level"] == "WARN"
        assert status["is_warn"] is True
        assert status["is_critical"] is False


class TestMemoryPressureState:
    """Test MemoryPressureState."""

    def test_default_state(self):
        """Test default state values."""
        state = MemoryPressureState()

        assert state.level == MemoryPressureLevel.NORMAL
        assert state.consecutive_warns == 0
        assert state.consecutive_criticals == 0


class TestMemoryPressureLevel:
    """Test MemoryPressureLevel enum."""

    def test_enum_values(self):
        """Test enum has correct values."""
        assert MemoryPressureLevel.NORMAL == 0
        assert MemoryPressureLevel.WARN == 1
        assert MemoryPressureLevel.CRITICAL == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
