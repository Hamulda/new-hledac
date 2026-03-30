"""
Orchestrator Module - Modular organization for autonomous orchestrator components
===============================================================================

This module provides re-exports for components originally in autonomous_orchestrator.py
to maintain backward compatibility while allowing future modularization.

The actual implementation remains in autonomous_orchestrator.py - this is a thin
organization layer that enables cleaner imports over time.

NOTE: This is NOT a refactor - behavior remains unchanged.
"""

# Re-export the main orchestrator class for backward compatibility
from ..autonomous_orchestrator import FullyAutonomousOrchestrator

# Re-export extracted managers (behavior identical to original)
from .research_manager import _ResearchManager
from .security_manager import _SecurityManager

__all__ = [
    "FullyAutonomousOrchestrator",
    "_ResearchManager",
    "_SecurityManager",
]
