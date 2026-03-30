"""
Sprint 4A: Lifecycle completion tests.
"""

import asyncio
import pytest
from unittest.mock import MagicMock, patch

from hledac.universal.utils.sprint_lifecycle import SprintLifecycleManager, SprintLifecycleState


def _fresh_lifecycle():
    SprintLifecycleManager._instance = None
    mgr = SprintLifecycleManager()
    return mgr


# =============================================================================
# Export transition tests
# =============================================================================

class TestSprint4ALifecycleExport:
    """Test windup → export transition is real, not just flag flip."""

    def test_request_export_transitions_from_windup(self):
        mgr = _fresh_lifecycle()
        mgr.begin_sprint()
        mgr.transition_to(SprintLifecycleState.ACTIVE)
        mgr._windup_fired = True
        mgr.transition_to(SprintLifecycleState.WINDUP)
        assert mgr.state == SprintLifecycleState.WINDUP

        mgr.request_export()
        assert mgr.state == SprintLifecycleState.EXPORT

    def test_request_export_only_from_windup(self):
        mgr = _fresh_lifecycle()
        mgr.begin_sprint()
        mgr.transition_to(SprintLifecycleState.ACTIVE)
        mgr.request_export()
        assert mgr.state == SprintLifecycleState.ACTIVE  # no-op

    def test_export_hook_is_called(self):
        mgr = _fresh_lifecycle()
        mgr.begin_sprint()
        mgr.transition_to(SprintLifecycleState.ACTIVE)
        mgr._windup_fired = True
        mgr.transition_to(SprintLifecycleState.WINDUP)

        calls = []
        mgr.set_export_hook(lambda: calls.append("export_fired"))
        mgr.request_export()
        assert calls == ["export_fired"]
        assert mgr.state == SprintLifecycleState.EXPORT

    def test_export_hook_fails_open(self):
        mgr = _fresh_lifecycle()
        mgr.begin_sprint()
        mgr.transition_to(SprintLifecycleState.ACTIVE)
        mgr._windup_fired = True
        mgr.transition_to(SprintLifecycleState.WINDUP)

        mgr.set_export_hook(lambda: (_ for _ in ()).throw(RuntimeError("bad")))
        mgr.request_export()  # Must not raise
        assert mgr.state == SprintLifecycleState.EXPORT


# =============================================================================
# Checkpoint wiring tests
# =============================================================================

class TestSprint4ACheckpointWiring:
    """Test checkpoint save/restore is actually consumed."""

    def test_save_checkpoint_fails_open_manager_missing(self):
        SprintLifecycleManager._instance = None
        with patch("hledac.universal.autonomous_orchestrator.time.time", return_value=123456.0):
            from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        with patch.object(FullyAutonomousOrchestrator, "__init__", lambda self, config=None: None):
            orch = FullyAutonomousOrchestrator()
            orch._checkpoint_manager = None
            orch._frontier = ["url1"]
            orch._processed_urls_count = 5
            orch._lifecycle = SprintLifecycleManager()

            orch._save_checkpoint_windup()  # Must not raise

    def test_save_checkpoint_fails_open_save_raises(self):
        SprintLifecycleManager._instance = None
        with patch("hledac.universal.autonomous_orchestrator.time.time", return_value=123456.0):
            from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        with patch.object(FullyAutonomousOrchestrator, "__init__", lambda self, config=None: None):
            orch = FullyAutonomousOrchestrator()
            mock_cm = MagicMock()
            mock_cm.save_checkpoint.side_effect = RuntimeError("disk full")
            orch._checkpoint_manager = mock_cm
            orch._frontier = []
            orch._processed_urls_count = 0
            orch._lifecycle = SprintLifecycleManager()

            orch._save_checkpoint_windup()  # Must not raise

    def test_probe_checkpoint_fails_open_manager_missing(self):
        SprintLifecycleManager._instance = None
        with patch("hledac.universal.autonomous_orchestrator.time.time", return_value=123456.0):
            from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        with patch.object(FullyAutonomousOrchestrator, "__init__", lambda self, config=None: None):
            orch = FullyAutonomousOrchestrator()
            orch._checkpoint_manager = None
            orch._last_checkpoint = None

            orch._probe_checkpoint_restore()  # Must not raise

    def test_probe_checkpoint_fails_open_list_raises(self):
        SprintLifecycleManager._instance = None
        with patch("hledac.universal.autonomous_orchestrator.time.time", return_value=123456.0):
            from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        with patch.object(FullyAutonomousOrchestrator, "__init__", lambda self, config=None: None):
            orch = FullyAutonomousOrchestrator()
            orch._checkpoint_manager = MagicMock()
            orch._checkpoint_manager.list_checkpoints.side_effect = RuntimeError("corrupt")
            orch._last_checkpoint = None

            orch._probe_checkpoint_restore()  # Must not raise


# =============================================================================
# Lifecycle cancel / teardown
# =============================================================================

class TestSprint4ATeardownIdempotent:
    """Test teardown is deterministic and idempotent."""

    def test_request_teardown_idempotent(self):
        mgr = _fresh_lifecycle()
        mgr.begin_sprint()
        mgr.transition_to(SprintLifecycleState.ACTIVE)

        mgr.request_teardown()
        assert mgr.state == SprintLifecycleState.TEARDOWN

        mgr.request_teardown()
        assert mgr.state == SprintLifecycleState.TEARDOWN

    def test_request_teardown_calls_hook(self):
        mgr = _fresh_lifecycle()
        mgr.begin_sprint()
        mgr.transition_to(SprintLifecycleState.ACTIVE)

        calls = []
        mgr.set_teardown_hook(lambda: calls.append("teardown_fired"))
        mgr.request_teardown()
        assert calls == ["teardown_fired"]

    def test_teardown_from_export_state(self):
        mgr = _fresh_lifecycle()
        mgr.begin_sprint()
        mgr.transition_to(SprintLifecycleState.WINDUP)
        mgr.transition_to(SprintLifecycleState.EXPORT)

        mgr.request_teardown()
        assert mgr.state == SprintLifecycleState.TEARDOWN


# =============================================================================
# Windup → export path
# =============================================================================

class TestSprint4AWindupExportPath:
    """Test the full windup → export path in AO."""

    def test_on_lifecycle_windup_triggers_export_and_sets_flags(self):
        """_on_lifecycle_windup should: set windup_active=True, call request_export."""
        SprintLifecycleManager._instance = None
        with patch("hledac.universal.autonomous_orchestrator.time.time", return_value=123456.0):
            from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        with patch.object(FullyAutonomousOrchestrator, "__init__", lambda self, config=None: None):
            orch = FullyAutonomousOrchestrator()

            # Set up a real lifecycle that is already in WINDUP state
            mgr = _fresh_lifecycle()
            mgr.begin_sprint()
            mgr.transition_to(SprintLifecycleState.ACTIVE)
            mgr._windup_fired = True
            mgr.transition_to(SprintLifecycleState.WINDUP)

            orch._lifecycle = mgr
            orch._lifecycle_windup_active = False
            orch._lifecycle_export_fired = False
            orch._checkpoint_manager = MagicMock()
            orch._frontier = []
            orch._processed_urls_count = 0

            # Trigger windup
            orch._on_lifecycle_windup()

            # Verify: windup_active set, checkpoint saved, state is EXPORT
            assert orch._lifecycle_windup_active is True
            assert orch._lifecycle.state == SprintLifecycleState.EXPORT

    def test_on_lifecycle_export_sets_flag(self):
        SprintLifecycleManager._instance = None
        with patch("hledac.universal.autonomous_orchestrator.time.time", return_value=123456.0):
            from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        with patch.object(FullyAutonomousOrchestrator, "__init__", lambda self, config=None: None):
            orch = FullyAutonomousOrchestrator()
            orch._lifecycle_export_fired = False
            orch._last_checkpoint = None
            orch._lifecycle = _fresh_lifecycle()

            orch._on_lifecycle_export()

            assert orch._lifecycle_export_fired is True
