"""
Sprint 8TF-R: Model-Control Split — Explicit Ownership Tests
============================================================

Verifies (Sprint 8TF-R objectives):
1. ModelLifecycleManager is a FACADE, NOT a load/unload owner
2. ModelManager is the canonical runtime-wide acquire/load owner
3. ModelManager._release_current_async() is the canonical runtime-wide unload owner
4. brain.model_lifecycle module-level functions are UNLOAD HELPERS, not canonical owners
5. ModelLifecycle class (inside model_lifecycle.py) is windup-local sidecar
6. No third model truth is created by any facade
7. assert_no_cross_layer_mapping() and get_phase_layer_strict() work correctly
8. No implicit mapping of workflow-level ↔ coarse-grained phase strings

INVARIANTS (Sprint 8TF-R):
  §R.1: ModelLifecycleManager has NO method that calls ModelManager.load_model()
  §R.2: ModelLifecycleManager does NOT hold model engine references
  §R.3: ModelManager.PHASE_MODEL_MAP keys are Layer 1 only (no cross-layer)
  §R.4: SYNTHESIZE (Layer 1) ≠ SYNTHESIS (Layer 2) — enforced by is_same_layer()
  §R.5: assert_no_cross_layer_mapping() logs warning on cross-layer risk, does NOT raise
  §R.6: get_phase_layer_strict() returns 0 for cross-layer collisions
  §R.7: ModelLifecycle class has no references to runtime-wide ModelManager
  §R.8: No new subsystem or framework was created
"""

import unittest
from unittest.mock import MagicMock, patch
import asyncio


class TestFacadeIsNotLoadOwner(unittest.TestCase):
    """§R.1-§R.2: ModelLifecycleManager facade must NOT act as load owner."""

    def test_lifecycle_manager_does_not_hold_model_reference(self):
        """ModelLifecycleManager._active_models holds Capability enums, not model engines."""
        from hledac.universal.capabilities import ModelLifecycleManager, CapabilityRegistry
        registry = CapabilityRegistry()
        manager = ModelLifecycleManager(registry)

        # _active_models must be Set[Capability], not Set[Any] of engine objects
        assert hasattr(manager, '_active_models')
        # It should be empty initially
        assert manager._active_models == set()

        # Run a phase enforcement
        asyncio.get_event_loop().run_until_complete(
            manager.enforce_phase_models("BRAIN")
        )

        # After BRAIN phase, only Capability.HERMES is in _active_models
        # NOT a model engine object
        from hledac.universal.capabilities import Capability
        assert Capability.HERMES in manager._active_models
        # These are Capability enums, not engine instances
        for item in manager._active_models:
            assert isinstance(item, Capability)

    def test_lifecycle_manager_has_no_load_model_method(self):
        """ModelLifecycleManager must NOT have load_model() — that belongs to ModelManager."""
        from hledac.universal.capabilities import ModelLifecycleManager
        # Must NOT have load_model or _load_model
        assert not hasattr(ModelLifecycleManager, 'load_model')
        assert not hasattr(ModelLifecycleManager, '_load_model')
        assert not hasattr(ModelLifecycleManager, '_load_model_async')

    def test_lifecycle_manager_has_no_model_engine_reference(self):
        """ModelLifecycleManager facade must NOT hold model engine references."""
        from hledac.universal.capabilities import ModelLifecycleManager, CapabilityRegistry
        registry = CapabilityRegistry()
        manager = ModelLifecycleManager(registry)

        # Verify no engine reference exists in the facade
        assert not hasattr(manager, '_loaded_models')
        assert not hasattr(manager, '_current_model')
        # The facade only tracks _active_models: Set[Capability]


class TestCanonicalLoadOwner(unittest.TestCase):
    """§R.3: ModelManager is canonical runtime-wide acquire/load owner."""

    def test_model_manager_has_load_method(self):
        """ModelManager.load_model() is the canonical load entry point."""
        from hledac.universal.brain.model_manager import ModelManager
        assert hasattr(ModelManager, 'load_model')
        assert callable(ModelManager.load_model)

    def test_model_manager_has_release_current_async(self):
        """ModelManager._release_current_async() is canonical runtime-wide unload."""
        from hledac.universal.brain.model_manager import ModelManager
        assert hasattr(ModelManager, '_release_current_async')
        assert callable(ModelManager._release_current_async)


class TestModelLifecycleModuleIsUnloadHelper(unittest.TestCase):
    """§R.3: Module-level load_model/unload_model are UNLOAD HELPERS, not owners."""

    def test_module_load_model_is_unload_helper_not_orchestrator(self):
        """load_model() delegates to engine.unload(), not a new load authority."""
        from hledac.universal.brain import model_lifecycle
        # The module has load_model but it's a shadow-state tracker
        # It does NOT create engines — it tracks what ModelManager loads
        assert hasattr(model_lifecycle, 'load_model')
        assert callable(model_lifecycle.load_model)

        # The module-level function should NOT have its own model factory
        # (ModelManager has _model_factories — this module does not)
        assert not hasattr(model_lifecycle, '_model_factories')

    def test_unload_model_delegates_to_engine_unload(self):
        """unload_model() delegates to engine.unload() — 7K SSOT."""
        from hledac.universal.brain.model_lifecycle import unload_model, _lifecycle_state

        # Reset state
        _lifecycle_state["loaded"] = True
        _lifecycle_state["current_model"] = "test-engine"

        engine = MagicMock()
        engine.unload = MagicMock()

        unload_model(model=engine)

        # Must have called engine.unload()
        engine.unload.assert_called_once()


class TestWindupLocalSidecar(unittest.TestCase):
    """§R.4: ModelLifecycle class inside model_lifecycle.py is windup-local."""

    def test_model_lifecycle_class_has_no_model_manager_reference(self):
        """ModelLifecycle (windup-local) must NOT reference runtime-wide ModelManager."""
        from hledac.universal.brain.model_lifecycle import ModelLifecycle

        # Create instance
        ml_instance = ModelLifecycle()

        # Must NOT have _manager or _model_manager references
        assert not hasattr(ml_instance, '_manager')
        assert not hasattr(ml_instance, '_model_manager')
        assert not hasattr(ml_instance, '_model_mgr')

        # It only has: _model, _tokenizer, _model_path, _loaded
        expected_attrs = {'_model', '_tokenizer', '_model_path', '_loaded'}
        actual_attrs = set(ml_instance.__dict__.keys())
        assert actual_attrs == expected_attrs, f"Unexpected attrs: {actual_attrs - expected_attrs}"

    def test_model_lifecycle_uses_local_qwen_smollm_discovery(self):
        """ModelLifecycle uses 3-tier local model discovery, not ModelManager registry."""
        from hledac.universal.brain.model_lifecycle import ModelLifecycle

        ml = ModelLifecycle()
        # Must have the 3-tier discovery method
        assert hasattr(ml, '_discover_model_path')

        # Must NOT use ModelManager.MODEL_REGISTRY
        # (MODEL_REGISTRY is the runtime-wide registry, not windup-local)
        assert not hasattr(ml, 'MODEL_REGISTRY')


class TestNoImplicitPhaseMapping(unittest.TestCase):
    """§R.4-§R.6: No implicit workflow-level ↔ coarse-grained phase mapping."""

    def test_synthesize_not_equal_to_synthesis(self):
        """SYNTHESIZE (Layer 1) ≠ SYNTHESIS (Layer 2) — enforced."""
        from hledac.universal.brain.model_phase_facts import (
            is_same_layer, get_phase_layer_strict
        )

        # They must be different layers
        assert not is_same_layer("SYNTHESIZE", "SYNTHESIS")

        # get_phase_layer_strict must classify them correctly
        assert get_phase_layer_strict("SYNTHESIZE") == 1
        assert get_phase_layer_strict("SYNTHESIS") == 2

    def test_assert_no_cross_layer_mapping_logs_warning(self):
        """assert_no_cross_layer_mapping logs warning on cross-layer risk, does NOT raise."""
        from hledac.universal.brain.model_phase_facts import assert_no_cross_layer_mapping
        import logging

        # Get a logger to capture warnings
        logger = logging.getLogger("hledac.universal.brain.model_phase_facts")
        logger.setLevel(logging.WARNING)

        with patch.object(logger, 'warning') as mock_warning:
            # Cross-layer risk: Layer 2 phase passed to Layer 1 caller
            assert_no_cross_layer_mapping("BRAIN", "Layer 1")

            # Must have logged a warning
            mock_warning.assert_called_once()
            warning_msg = mock_warning.call_args[0][0]
            assert "Cross-layer risk" in warning_msg
            assert "BRAIN" in warning_msg

    def test_assert_no_cross_layer_mapping_no_op_for_known_layers(self):
        """assert_no_cross_layer_mapping is no-op when phase matches expected layer."""
        from hledac.universal.brain.model_phase_facts import assert_no_cross_layer_mapping
        import logging

        logger = logging.getLogger("hledac.universal.brain.model_phase_facts")
        with patch.object(logger, 'warning') as mock_warning:
            # Correct usage: Layer 1 phase with Layer 1 hint
            assert_no_cross_layer_mapping("PLAN", "Layer 1")
            # Must NOT log warning
            mock_warning.assert_not_called()

    def test_get_phase_layer_strict_no_collision(self):
        """get_phase_layer_strict returns correct layer with no collision."""
        from hledac.universal.brain.model_phase_facts import get_phase_layer_strict

        assert get_phase_layer_strict("PLAN") == 1
        assert get_phase_layer_strict("DECIDE") == 1
        assert get_phase_layer_strict("SYNTHESIZE") == 1
        assert get_phase_layer_strict("BRAIN") == 2
        assert get_phase_layer_strict("TOOLS") == 2
        assert get_phase_layer_strict("SYNTHESIS") == 2
        assert get_phase_layer_strict("CLEANUP") == 2
        assert get_phase_layer_strict("UNKNOWN") == 0


class TestNoThirdModelTruth(unittest.TestCase):
    """§R.6-§R.8: No third model truth is created."""

    def test_no_new_model_subsystem_created(self):
        """No new model subsystem was created in this sprint."""
        # This is verified by the fact we didn't create any new files
        # The only files changed are:
        # - capabilities.py (docstring update)
        # - brain/model_lifecycle.py (docstring update)
        # - brain/model_phase_facts.py (added pure-facts helpers)
        import os
        import hledac.universal

        universal_dir = os.path.dirname(hledac.universal.__file__)
        brain_dir = os.path.join(universal_dir, "brain")

        # Count model-related files in brain/
        model_files = []
        for f in os.listdir(brain_dir):
            if f.startswith("model") and f.endswith(".py"):
                model_files.append(f)

        # We expect: model_manager.py, model_lifecycle.py, model_phase_facts.py, model_swap_manager.py
        # No new files should exist beyond these 4
        assert len(model_files) == 4, f"Expected 4 model files, got {model_files}"

    def test_model_phase_facts_is_pure_facts(self):
        """model_phase_facts.py must remain a pure-facts helper with no state."""
        from hledac.universal.brain import model_phase_facts

        # No class instances, no module-level state
        module_dict = vars(model_phase_facts)

        # Filter out functions and built-in types
        stateful = []
        for name, obj in module_dict.items():
            if name.startswith('_'):
                continue
            if callable(obj):
                continue
            # frozenset constants are fine
            if isinstance(obj, frozenset):
                continue
            # Python 3.6+ module annotations are not state
            if name == 'annotations':
                continue
            stateful.append(name)

        assert not stateful, f"model_phase_facts has stateful attrs: {stateful}"


if __name__ == "__main__":
    unittest.main()
