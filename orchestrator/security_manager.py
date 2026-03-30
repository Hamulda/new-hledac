"""
Security Manager - Extracted from autonomous_orchestrator.py

This module re-exports _SecurityManager from its original location to establish
the modular structure. The actual implementation remains in autonomous_orchestrator.py
to minimize risk during migration.

Behavior: Identical to original - no functional changes.
"""

# Re-export from original location for backward compatibility
from ..autonomous_orchestrator import _SecurityManager

__all__ = ["_SecurityManager"]
