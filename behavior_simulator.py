"""
Behavior Simulator — GHOST FEATURE (F191E Census)
================================================

.. status::
    GHOST_FEATURE — This file is a re-export stub, NOT an implementation.
    CANONICAL location: layers.stealth_layer:BehaviorSimulator
    ZERO imports within hledac/universal/ (confirmed by census).

.. why_ghost::
    This file was an early draft of BehaviorSimulator that was superseded
    when the canonical implementation was established in layers/stealth_layer.py.
    It was NEVER imported by any module in hledac/universal/.
    Kept as stub for backward-compat reference only.

.. guards::
    - GHOST_FEATURE_DO_NOTIMPORT: DO NOT import from this file
    - Use layers.stealth_layer:BehaviorSimulator for all production use
    - This stub exists only to prevent import errors from stale references

.. canonical_path::
    layers.stealth_layer:BehaviorSimulator (IMPLEMENTATION TRUTH)
    enhanced_research.py imports from layers.stealth_layer (correct path)
"""

from __future__ import annotations

# GHOST_FEATURE_GUARD: Re-export everything from canonical location
# All production use must go through layers.stealth_layer
from layers.stealth_layer import BehaviorSimulator
from layers.stealth_layer import (
    BehaviorPattern,
    SimulationConfig,
    MouseMovement,
    ScrollAction,
)

# Module-level markers for any code that inspects this module
GHOST_FEATURE = True
"""This file is a ghost feature — do not use directly"""

GHOST_FEATURE_DO_NOTIMPORT = True
"""Guard: explicit flag that this module should not be imported"""

__deprecated__ = True
"""This module is deprecated — use layers.stealth_layer instead"""

__all__ = [
    "BehaviorSimulator",
    "BehaviorPattern",
    "SimulationConfig",
    "MouseMovement",
    "ScrollAction",
]
