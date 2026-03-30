"""
autonomous_orchestrator — RE-EXPORT FACADE (8VC)
=============================================

.. deprecated::
    This module has been migrated to ``legacy/autonomous_orchestrator.py``.
    This file is kept for backward compatibility only.
"""

import sys
import os

# Sprint 8VC: CRITICAL - Register this module in sys.modules BEFORE any other imports
# This prevents __init__.py from failing when it does "from .autonomous_orchestrator import ..."
# The key: Python checks sys.modules first, so if we're already there, it won't re-import

_legacy_path = os.path.join(os.path.dirname(__file__), "legacy", "autonomous_orchestrator.py")

# Create a placeholder so recursive imports find this module already in sys.modules
import types
_facade_mod = types.ModuleType("hledac.universal.autonomous_orchestrator")
_facade_mod.__file__ = __file__
_facade_mod.__package__ = "hledac.universal"
_facade_mod.__name__ = "hledac.universal.autonomous_orchestrator"
sys.modules["hledac.universal.autonomous_orchestrator"] = _facade_mod

# Now do the actual loading - this WON'T trigger __init__.py re-entry
# because hledac.universal.autonomous_orchestrator is already in sys.modules
import warnings
warnings.warn(
    "autonomous_orchestrator has been migrated to legacy/. "
    "Import FullyAutonomousOrchestrator from runtime/sprint_scheduler.py instead. "
    "This facade will be removed in a future sprint.",
    DeprecationWarning,
    stacklevel=2,
)

# Load the legacy module directly
import importlib.util
_spec = importlib.util.spec_from_file_location("legacy.autonomous_orchestrator", _legacy_path)
_legacy_mod = importlib.util.module_from_spec(_spec)
_legacy_mod.__package__ = "hledac.universal"
_legacy_mod.__path__ = [os.path.dirname(__file__)]
sys.modules["legacy.autonomous_orchestrator"] = _legacy_mod
_spec.loader.exec_module(_legacy_mod)

# Copy all exported names to this facade module
_for_export = [
    "FullyAutonomousOrchestrator",
    "autonomous_research",
    "DiscoveryDepth",
    "ResearchPhase",
    "SourceType",
    "AutonomousStrategy",
    "ResearchSource",
    "ResearchFinding",
    "ComprehensiveResearchResult",
    "ResilientExecutionManager",
    "AutonomousWorkflowEngine",
    "WorkflowState",
    "UnifiedToolRegistry",
    "ToolCategory",
    "ToolCapability",
    "deep_research",
    "create",
    "AdmissionResult",
    "BacklogCandidate",
    "TokenBucket",
    "WelfordStats",
    "ReservoirSampler",
    "ThermalState",
    "IterationTrace",
    "NetworkReconRunTrace",
    "CapabilityHealth",
    "SynthesisCompression",
    "SimHash",
    # Internal managers used by orchestrator/
    "_SecurityManager",
    "_ResearchManager",
    "_ToolRegistryManager",
    "_StateManager",
    "_BrainManager",
    "_ForensicsManager",
    "_IntelligenceManager",
    "_SynthesisManager",
]

for _name in _for_export:
    _val = getattr(_legacy_mod, _name, None)
    if _val is not None:
        setattr(_facade_mod, _name, _val)
        globals()[_name] = _val

create_autonomous_orchestrator = getattr(_legacy_mod, "autonomous_research", None)
globals()["create_autonomous_orchestrator"] = create_autonomous_orchestrator
setattr(_facade_mod, "create_autonomous_orchestrator", create_autonomous_orchestrator)

__all__ = _for_export + ["create_autonomous_orchestrator"]
