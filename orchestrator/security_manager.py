"""
Security Manager - THIN RE-EXPORT MODULE (Sprint F13)
======================================================

CONTAINMENT METADATA
====================
role: SECONDARY_THIN_REEXPORT
    Tento modul je thin re-export layer. Není canonical owner implementace.

chain_of_authority:
    orchestrator/security_manager.py (RE-EXPORT)
        → autonomous_orchestrator.py (ROOT FACADE, NON_CANONICAL)
            → legacy/autonomous_orchestrator.py (IMPLEMENTATION TRUTH)

migration_blocker: smoke_runner.py, __init__.py re-export chain
removal_precondition: consumers redirected to legacy/autonomous_orchestrator.py

NOT a refactor - behavior remains unchanged.
"""

# Re-export from original location for backward compatibility
from ..autonomous_orchestrator import _SecurityManager

__all__ = ["_SecurityManager"]
