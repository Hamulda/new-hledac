"""
Probe: No new scheduler subsystem was created.

Sprint 8VK §Invariant: shadow_inputs.py must not import from sprint_scheduler.
"""

import pytest
import ast
from pathlib import Path


class TestNoSchedulerSubsystem:
    """Verify shadow_inputs.py has no scheduler dependency."""

    def test_shadow_inputs_no_scheduler_import(self):
        """shadow_inputs.py must not import sprint_scheduler."""
        import hledac.universal.runtime.shadow_inputs as shadow_module

        module_path = Path(shadow_module.__file__).parent / "shadow_inputs.py"
        content = module_path.read_text()

        tree = ast.parse(content)

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)

        # Must not import sprint_scheduler
        scheduler_imports = [i for i in imports if "sprint_scheduler" in i]
        assert len(scheduler_imports) == 0, (
            f"shadow_inputs.py must not import sprint_scheduler. Found: {scheduler_imports}"
        )

    def test_shadow_inputs_no_runtime_behavior_change(self):
        """Collectors must not change any runtime state."""
        from hledac.universal.runtime.shadow_inputs import (
            collect_lifecycle_snapshot,
            collect_graph_summary,
            collect_model_control_facts,
            collect_export_handoff_facts,
        )
        from hledac.universal.runtime.sprint_lifecycle import SprintLifecycleManager

        # Create a lifecycle
        lc = SprintLifecycleManager()
        lc.start()

        # Get initial state
        initial_phase = lc._current_phase
        initial_started = lc._started_at

        # Call all collectors
        collect_lifecycle_snapshot(lc)
        collect_graph_summary()
        collect_model_control_facts()
        collect_export_handoff_facts()

        # State must be unchanged
        assert lc._current_phase == initial_phase
        assert lc._started_at == initial_started
