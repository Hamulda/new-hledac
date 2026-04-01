# hledac/universal/export/COMPAT_HANDOFF.py
# Sprint 8VJ §A: Export plane compat handoff — runtime doc only
# ⚠️  DEPRECATED LAYER — DO NOT EXTEND
"""
Dokumentační seam pro compat handoff mezi runtime state (store/scheduler)
a export plane.

Hlavní body:
  1. sprint_exporter._generate_next_sprint_seeds() volá scheduler._ioc_graph.get_top_nodes_by_degree(n=5)
     → scheduler._ioc_graph je IOCGraph (Kuzu), ale get_top_nodes_by_degree je DuckPGQGraph metoda
     → store._ioc_graph (duckdb_store) drží správně DuckPGQGraph
     → Future: duckdb_store.get_top_graph_nodes(n=5) přes store API

  2. export_sprint() defined ale not wired v __main__.py
     → lifecycle.request_export() nema registered callback
     → Wire do _print_scorecard_report()

  3. __main__._export_markdown_report() je inline duplikát markdown_reporter.render_diagnostic_markdown_to_path()
     → Refaktoruj na delegaci

  4. _compat_scheduler bridge v __main__.py:2549
     → store-first arch je cíl, removal po SprintScheduler cutover
"""

#Compat: duckdb_store → SprintScheduler IOC graph bridge
# Lokace: __main__.py:2549
# Kód: _compat_scheduler = getattr(store_instance, "_ioc_graph", None) if store_instance else None
# Poznámka: store._ioc_graph drží DuckPGQGraph — toto JE správná dnešní runtime cesta

# =============================================================================
# Sprint 8VJ §C: Typed ExportHandoff adapter
# =============================================================================
# Thin adapter: ExportHandoff | dict → ExportHandoff
# Zajišťuje že export_sprint() má vždy typed input bez změny path semantics.
# scorecard["top_graph_nodes"] zůstává current compat seam.
# Future owner: __main__.py (producer side) — po cutover bude handoff vznikat tam
# Removal condition: export_sprint() přijímá pouze ExportHandoff (ne dict)
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
