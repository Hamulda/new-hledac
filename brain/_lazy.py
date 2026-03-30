"""
brain._lazy — Lazy Import Cache for Brain Modules
=================================================

Reduces startup overhead by importing brain modules only when first used,
not at module load time.

Usage:
    from brain._lazy import get, get_attr

    # Lazy import a module
    gnn = get("gnn_predictor")

    # Lazy import a specific attribute
    GNNPredictor = get_attr("gnn_predictor", "GNNPredictor")
"""

from __future__ import annotations

import importlib
from typing import Any

_cache: dict[str, Any] = {}


def get(module_name: str) -> Any:
    """Lazy import brain.{module_name} and return the module."""
    if module_name not in _cache:
        _cache[module_name] = importlib.import_module(f"brain.{module_name}")
    return _cache[module_name]


def get_attr(module_name: str, attr: str) -> Any:
    """Lazy import brain.{module_name}.{attr} and return the attribute."""
    mod = get(module_name)
    return getattr(mod, attr)


def clear_cache() -> None:
    """Clear the lazy import cache. For testing only."""
    _cache.clear()
