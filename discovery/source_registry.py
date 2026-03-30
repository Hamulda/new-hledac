"""
Lightweight source registry for structured TI adapters.

Provides a simple registry pattern for source adapters without
introducing heavy plugin infrastructure.

Sprint 8BN — Structured TI Ingest V1
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Registry — stores adapter classes by source_type string
# ---------------------------------------------------------------------------

_SOURCE_REGISTRY: dict[str, object] = {}


def register_source_adapter(source_type: str, adapter_class: object) -> None:
    """
    Register a source adapter class for the given source_type.

    Parameters
    ----------
    source_type:
        Unique identifier for the source type (e.g. "nvd", "cisa_kev", "rss").
    adapter_class:
        The adapter class implementing SourceAdapter protocol.

    Raises
    ------
    ValueError
        If source_type is already registered.
    """
    if source_type in _SOURCE_REGISTRY:
        raise ValueError(f"source_type already registered: {source_type}")
    _SOURCE_REGISTRY[source_type] = adapter_class


def get_source_adapter(source_type: str) -> object | None:
    """
    Return a new instance of the registered adapter for source_type.

    Returns None if source_type is not registered.
    """
    cls = _SOURCE_REGISTRY.get(source_type)
    if cls is None:
        return None
    return cls()


def list_registered_source_types() -> list[str]:
    """Return sorted list of all registered source types."""
    return sorted(_SOURCE_REGISTRY.keys())


def source_quality_score(
    parseable: bool,
    stable_schema: bool,
    identifier_rich: bool,
    source_tier: str,
) -> int:
    """
    Compute deterministic quality score for a source.

    Scoring (V1):
    - parseable: +30 points
    - stable_schema: +25 points
    - identifier_rich: +20 points
    - tier structured_ti: +15 points
    - tier surface: +5 points
    - tier overlay_ready: +0 points
    """
    score = 0
    if parseable:
        score += 30
    if stable_schema:
        score += 25
    if identifier_rich:
        score += 20
    if source_tier == "structured_ti":
        score += 15
    elif source_tier == "surface":
        score += 5
    return score
