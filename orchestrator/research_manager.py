"""
Research Manager - THIN SECONDARY RE-EXPORT
==========================================

CONTAINMENT METADATA (Sprint F13d)
==================================
role: SECONDARY_THIN_REEXPORT
    Tento modul je THIN SECONDARY RE-EXPORT layer.
    NENÍ canonical owner implementace.

chain_of_authority:
    orchestrator/research_manager.py (SECONDARY RE-EXPORT)
        → autonomous_orchestrator.py (ROOT RE-EXPORT FACADE, NON_CANONICAL)
            → legacy/autonomous_orchestrator.py (IMPLEMENTATION TRUTH)

NOT a refactor - behavior remains unchanged.

Wording note: Původní "implementation remains in autonomous_orchestrator.py"
bylo zavádějící. autonomous_orchestrator.py sám je re-export facade,
ne implementation owner. Canonical implementation:
legacy/autonomous_orchestrator.py
"""

# Re-export from root facade chain for backward compatibility
# Implementation truth: legacy/autonomous_orchestrator.py (via root facade)
from ..autonomous_orchestrator import _ResearchManager

__all__ = ["_ResearchManager"]
