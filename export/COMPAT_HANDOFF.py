# hledac/universal/export/COMPAT_HANDOFF.py
# Sprint 8VJ §A: Export plane compat handoff — runtime doc only
# Sprint 8VX §A: Updated — export_sprint IS wired (removed outdated "not wired" claim)
# ⚠️  DEPRECATED LAYER — DO NOT EXTEND
"""
Dokumentační seam pro compat handoff mezi runtime state (store/scheduler)
a export plane.

Hlavní body (Sprint 8VX):
  1. export_sprint() JE wireovaný v __main__.py:2343 — removed "not wired" claim
  2. ExportHandoff.from_windup() je producer-side construction point
  3. scorecard["top_graph_nodes"] → top_nodes zůstává compat seam (viz removal cond)
  4. __main__._export_markdown_report() deleguje na sprint_markdown_reporter.render_sprint_markdown()
     — canonical renderer exists, path debt documented in __main__.py

Remaining compat seams:
  - COMPAT_HANDOFF.ensure_export_handoff(): thin adapter, removal when
    export_sprint() accepts only ExportHandoff (not dict/None)
  - store.get_top_seed_nodes() fallback in export_sprint():
    Sprint 8VX §B: switched from store._ioc_graph.get_top_nodes_by_degree()
    REMOVAL CONDITION: duckdb_store.get_top_seed_nodes() covers all export use cases
  - __main__._compat_scheduler bridge: REMOVAL CONDITION: SprintScheduler cutover complete
"""

# Accepted compat: duckdb_store → SprintScheduler IOC graph bridge
# Lokace: __main__.py (store_instance._ioc_graph)
# Poznámka: store._ioc_graph drží DuckPGQGraph — toto JE správná dnešní runtime cesta
# REMOVAL CONDITION: SprintScheduler cutover complete

# =============================================================================
# Sprint 8VJ §C: Typed ExportHandoff adapter
# Sprint 8VX §A: Header updated — wired reality reflected
# =============================================================================
# Thin adapter: ExportHandoff | dict → ExportHandoff
# Zajišťuje že export_sprint() má vždy typed input bez změny path semantics.
# scorecard["top_graph_nodes"] zůstává current compat seam.
# Producer side: __main__.py:2343 — constructs ExportHandoff.from_windup()
# REMOVAL CONDITION: export_sprint() accepts only ExportHandoff (not dict/None)
# =============================================================================

from typing import TYPE_CHECKING, Any, Dict, Union

if TYPE_CHECKING:
    from hledac.universal.types import ExportHandoff  # noqa: F401


def ensure_export_handoff(
    handoff: Union["ExportHandoff", Dict[str, Any], None],  # type: ignore[name-defined]
    default_sprint_id: str = "unknown",
) -> "ExportHandoff":  # type: ignore[name-defined]
    """
    Normalize ExportHandoff | dict | None → ExportHandoff.

    Používá ExportHandoff.from_windup() pro dict,
    vrací ExportHandoff unchanged, vrací prázdný handoff pro None.

    Current compat seam: scorecard["top_graph_nodes"] → top_nodes extraction.
    Toto zůstává dočasné — po cutover windup_engine vrátí přímo ExportHandoff.

    Args:
        handoff: ExportHandoff instance, dict (scorecard-style), or None
        default_sprint_id: fallback sprint_id pokud handoff neobsahuje

    Returns:
        ExportHandoff — vždy typed, nikdy None

    NOTE: Toto je thin compat adapter, ne nový DTO. Nemění path semantics.
    """
    # Import we need it at runtime
    from hledac.universal.types import ExportHandoff as TypesExportHandoff

    if handoff is None:
        return TypesExportHandoff(
            sprint_id=default_sprint_id,
            scorecard={},
            top_nodes=[],
        )

    if isinstance(handoff, TypesExportHandoff):
        return handoff

    if isinstance(handoff, dict):
        # Use from_windup for dict → typed conversion
        sprint_id = handoff.get("sprint_id", default_sprint_id)
        return TypesExportHandoff.from_windup(
            sprint_id=sprint_id,
            scorecard=handoff,
        )

    raise TypeError(
        f"ensure_export_handoff() got unexpected type: {type(handoff).__name__}. "
        f"Expected ExportHandoff, dict, or None."
    )
