"""
Sprint 8TF: Phase Drift Guard — Pure Facts Helper
================================================

Tiny pre-seam scaffold for reading phase/model facts without implicit
cross-layer confusion.

PURPOSE:
  - Provide an authoritative single place to look up phase-layer facts
  - Prevent implicit conflation of workflow-level ↔ coarse-grained phases
  - Help future scheduler/shadow code to read phase facts correctly

WHAT THIS IS:
  - Pure facts helper (no state, no side effects, no new subsystem)
  - Late-import accessor (imported only when needed)
  - Compatibility alias surface

WHAT THIS IS NOT:
  - NOT a new model subsystem
  - NOT a new orchestrating class
  - NOT a cross-plane model API layer
  - NOT a replacement for ModelManager or ModelLifecycleManager

PHASE LAYERS:

  Layer 1 — Workflow-level (ModelManager.PHASE_MODEL_MAP):
    PLAN      → hermes
    DECIDE    → hermes
    SYNTHESIZE → hermes
    EMBED     → modernbert
    DEDUP     → modernbert
    ROUTING   → modernbert
    NER       → gliner
    ENTITY    → gliner

  Layer 2 — Coarse-grained (ModelLifecycleManager.enforce_phase_models):
    BRAIN     → hermes loaded, others released
    TOOLS     → hermes released, others on-demand
    SYNTHESIS → hermes loaded, others released
    CLEANUP   → all released

  Layer 3 — Windup-local (windup_engine.SynthesisRunner):
    Qwen/SmolLM isolated from runtime-wide model plane

AUTHORITY:
  This file is a COMPATIBILITY AID — not a new authority.
  The canonical owners remain:
    - ModelManager (acquire/load)
    - ModelLifecycleManager (phase enforcement facade)
    - brain.model_lifecycle (unload cleanup)

USAGE:
  from brain.model_phase_facts import (
      WORKFLOW_PHASES,
      COARSE_GRAINED_PHASES,
      is_workflow_phase,
      is_coarse_grained_phase,
      get_phase_layer,
  )
"""

from __future__ import annotations

# =============================================================================
# Layer 1 — Workflow-level phase strings
# =============================================================================
WORKFLOW_PHASES: frozenset[str] = frozenset({
    "PLAN",
    "DECIDE",
    "SYNTHESIZE",
    "EMBED",
    "DEDUP",
    "ROUTING",
    "NER",
    "ENTITY",
})

# =============================================================================
# Layer 2 — Coarse-grained phase strings
# =============================================================================
COARSE_GRAINED_PHASES: frozenset[str] = frozenset({
    "BRAIN",
    "TOOLS",
    "SYNTHESIS",
    "CLEANUP",
})

# =============================================================================
# Phase-layer classification
# =============================================================================
def get_phase_layer(phase: str) -> int:
    """
    Return which phase layer a string belongs to.

    Returns:
        1 = workflow-level (ModelManager.PHASE_MODEL_MAP)
        2 = coarse-grained (ModelLifecycleManager)
        0 = unknown/unclassified

    Note:
        Returns 0 for unknown phases — does NOT raise.
        This is intentional: future phases may be added without updating this file.
    """
    normalized = phase.upper()
    if normalized in WORKFLOW_PHASES:
        return 1
    if normalized in COARSE_GRAINED_PHASES:
        return 2
    return 0


def is_workflow_phase(phase: str) -> bool:
    """Return True if phase is a Layer 1 workflow-level phase string."""
    return phase.upper() in WORKFLOW_PHASES


def is_coarse_grained_phase(phase: str) -> bool:
    """Return True if phase is a Layer 2 coarse-grained phase string."""
    return phase.upper() in COARSE_GRAINED_PHASES


def is_same_layer(phase_a: str, phase_b: str) -> bool:
    """
    Return True if both phases belong to the same layer.

    This is the canonical check BEFORE comparing or mapping phases —
    comparing a Layer 1 phase (e.g., "SYNTHESIZE") with a Layer 2 phase
    (e.g., "SYNTHESIS") would be a category error.
    """
    return get_phase_layer(phase_a) == get_phase_layer(phase_b) != 0
