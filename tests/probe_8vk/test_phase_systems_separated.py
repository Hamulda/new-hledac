"""
Probe: Phase systems remain SEPARATED, not merged into single phase field.

Sprint 8VK §Invariant: workflow_phase, control_phase, windup_local_phase
must be in separate fields, NEVER merged into one phase field.
"""

import pytest
from hledac.universal.runtime.sprint_lifecycle import SprintLifecycleManager, SprintPhase


class TestPhaseSystemsSeparated:
    """Verify workflow_phase, control_phase, windup_local_phase are separated."""

    def test_workflow_phase_is_separate_field(self):
        """WorkflowPhase must be a separate dataclass field, not a string in main dict."""
        from hledac.universal.runtime.shadow_inputs import (
            WorkflowPhase,
            ControlPhase,
            WindupLocalPhase,
            LifecycleSnapshotBundle,
        )
        import inspect

        # Verify LifecycleSnapshotBundle has separate fields
        fields = {f.name for f in LifecycleSnapshotBundle.__dataclass_fields__.values()}
        assert "workflow_phase" in fields, "workflow_phase must be a named field"
        assert "control_phase" in fields, "control_phase must be a named field"
        assert "windup_local_phase" in fields, "windup_local_phase must be a named field"

        # Verify these are typed as dataclass instances, not raw strings
        wf_field = LifecycleSnapshotBundle.__dataclass_fields__["workflow_phase"]
        ctrl_field = LifecycleSnapshotBundle.__dataclass_fields__["control_phase"]

        assert wf_field.type is WorkflowPhase or "WorkflowPhase" in str(wf_field.type)
        assert ctrl_field.type is ControlPhase or "ControlPhase" in str(ctrl_field.type)

    def test_workflow_phase_enum_values(self):
        """WorkflowPhase.phase must contain valid SprintPhase values."""
        from hledac.universal.runtime.shadow_inputs import WorkflowPhase

        # Valid phases
        for phase_name in ["BOOT", "WARMUP", "ACTIVE", "WINDUP", "EXPORT", "TEARDOWN"]:
            wp = WorkflowPhase(phase=phase_name)
            assert wp.phase == phase_name

        # Invalid phase should be stored (this is a read-only scaffold)
        wp = WorkflowPhase(phase="UNKNOWN")
        assert wp.phase == "UNKNOWN"

    def test_control_phase_values(self):
        """ControlPhase.mode must contain valid tool mode values."""
        from hledac.universal.runtime.shadow_inputs import ControlPhase

        for mode in ["normal", "prune", "panic"]:
            cp = ControlPhase(mode=mode)
            assert cp.mode == mode

    def test_windup_local_phase_values(self):
        """WindupLocalPhase.mode must contain valid synthesis values."""
        from hledac.universal.runtime.shadow_inputs import WindupLocalPhase

        for mode in ["synthesis", "structured", "minimal"]:
            wp = WindupLocalPhase(mode=mode)
            assert wp.mode == mode

    def test_bundle_to_dict_separates_phases(self):
        """LifecycleSnapshotBundle.to_dict() keeps phases in separate keys."""
        from hledac.universal.runtime.shadow_inputs import (
            LifecycleSnapshotBundle,
            WorkflowPhase,
            ControlPhase,
            WindupLocalPhase,
        )

        bundle = LifecycleSnapshotBundle(
            workflow_phase=WorkflowPhase(phase="ACTIVE"),
            control_phase=ControlPhase(mode="normal"),
            windup_local_phase=WindupLocalPhase(mode="synthesis"),
        )

        d = bundle.to_dict()
        assert "workflow_phase" in d
        assert "control_phase_mode" in d
        assert "windup_local_mode" in d
        # Must NOT have a single "phase" field that merges all three
        assert "phase" not in d or d.get("phase") is None

    def test_lifecycle_snapshot_collect_separates_phases(self):
        """collect_lifecycle_snapshot() returns bundle with separated phases."""
        from hledac.universal.runtime.shadow_inputs import (
            collect_lifecycle_snapshot,
        )

        lc = SprintLifecycleManager()
        lc.start()
        lc.transition_to(SprintPhase.ACTIVE)

        bundle = collect_lifecycle_snapshot(lc, windup_synthesis_mode="synthesis")

        assert bundle.workflow_phase.phase in ["WARMUP", "ACTIVE"]
        assert bundle.control_phase.mode in ["normal", "prune", "panic"]
        # windup_local only set when in WINDUP phase
        if bundle.workflow_phase.phase == "WINDUP":
            assert bundle.windup_local_phase is not None
