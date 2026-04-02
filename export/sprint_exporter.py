# Sprint 8VX §A: Export plane finish-up
# - ExportHandoff confirmed as primary handoff surface (wired in __main__.py:2343)
# - compat fallback documented with explicit removal conditions
# - No new framework, no new store API
"""
Sprint 8VI §A: EXPORT fáze — export_sprint() + _generate_next_sprint_seeds()
Sprint 8VJ §C: ExportHandoff | dict → typed handoff spotřeba
Sprint 8VX §A: Finish-up — removal conditions tightened, comments aligned with reality
"""

from __future__ import annotations

import json
import logging
import pathlib
from typing import Any, Union

logger = logging.getLogger(__name__)


async def export_sprint(
    store: Any,
    handoff: Union["ExportHandoff", dict, None],
    sprint_id: str | None = None,
) -> dict:
    """
    EXPORT fáze — JSON report, seed tasky pro příští sprint.

    Voláno z _print_scorecard_report() v __main__.py EXPORT fázi.
    Nikdy nevyhodí výjimku.

    Accepts typed ExportHandoff OR raw dict (backward compat via ensure_export_handoff).

    Součásti:
      1. JSON report do ~/.hledac/reports/{sprint_id}_report.json
      2. Seed tasky pro příští sprint z top IOC graph nodes

    PRIMARY HANDOFF SURFACE (Sprint 8VX):
      - ExportHandoff.top_nodes — kanonický zdroj pro seed generation
      - ExportHandoff.scorecard — kanonický zdroj pro JSON report

    ACCEPTED COMPAT SEAM — graph fallback:
      - Pokud top_nodes prázdné (windup běžel ale neplnil top_graph_nodes),
        zkusí store._ioc_graph.get_top_nodes_by_degree(n=5)
      - REMOVAL CONDITION: duckdb_store.get_top_seed_nodes() pokrývá všechny
        export use cases. Dokud neexistuje, fallback zůstává.
      - Future owner: duckdb_store.get_top_seed_nodes()
    """
    from paths import SPRINT_STORE_ROOT
    from export.COMPAT_HANDOFF import ensure_export_handoff

    # Sprint 8VJ §C: Normalize ExportHandoff | dict | None → typed ExportHandoff
    # Maintains backward compat: dict input → from_windup() extraction
    eh = ensure_export_handoff(handoff, default_sprint_id=sprint_id or "unknown")

    # Resolve sprint_id — prefer from handoff (typed path)
    _sprint_id = eh.sprint_id if eh.sprint_id != "unknown" else (sprint_id or "unknown")
    report_dir = SPRINT_STORE_ROOT.parent / "reports"
    try:
        report_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"[EXPORT] Could not create report_dir: {e}")
        report_dir = SPRINT_STORE_ROOT  # fallback

    # 1. JSON report — use handoff.scorecard (preserves full scorecard)
    report_path = report_dir / f"{_sprint_id}_report.json"
    try:
        serializable_scorecard = _make_serializable(eh.scorecard)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(serializable_scorecard, f, indent=2, default=str)
        logger.info(f"[EXPORT] JSON report → {report_path}")
    except Exception as e:
        logger.warning(f"[EXPORT] JSON write failed: {e}")
        report_path = None

    # 2. Seed tasky pro příští sprint — top_nodes z ExportHandoff (typed)
    # COMPAT SEAM: windup_engine.run_windup() získal top_graph_nodes z
    # scheduler._ioc_graph.get_top_nodes_by_degree(n=10) a uložil do scorecard.
    # ExportHandoff.from_windup() extrahuje top_graph_nodes → top_nodes.
    # Tím pádem export nepotřebuje přístup ke scheduler._ioc_graph přímo.
    top_nodes = eh.top_nodes if eh.top_nodes else []

    # COMPAT BRIDGE: If top_nodes still empty (e.g. _windup_synthesis()
    # ran but windup_engine.run_windup() did NOT populate scorecard), try store.
    # Sprint 8VX §B: switched from store._ioc_graph.get_top_nodes_by_degree()
    # to store.get_top_seed_nodes() — store-facing seam, no graph internals.
    # Future owner: duckdb_store.get_top_seed_nodes()
    # Removal condition: ExportHandoff.top_nodes is populated in ALL windup paths
    if not top_nodes and store is not None:
        try:
            if hasattr(store, "get_top_seed_nodes"):
                top_nodes = store.get_top_seed_nodes(n=5)
        except Exception:
            pass

    seeds_path = _generate_next_sprint_seeds(top_nodes, _sprint_id, report_dir)

    return {
        "report_json": str(report_path) if report_path else "",
        "seeds_json": str(seeds_path),
    }


def _generate_next_sprint_seeds(
    top_nodes: list,
    sprint_id: str,
    output_dir: pathlib.Path,
) -> pathlib.Path:
    """
    Generuje PivotTask seed JSON pro příští sprint.

    Zdroj: top IOC nodes z windup phase scorecard (windup_engine.run_windup()
    získal data z scheduler._ioc_graph.get_top_nodes_by_degree()).

    COMPAT SEAM — future owner: duckdb_store.get_top_seed_nodes()
    Removal condition: export_sprint() převezme store param a volá
    store.get_top_seed_nodes() přímo; top_nodes pak půjde z ExportHandoff.top_nodes

    Každý top IOC generuje 3 follow-up tasky:
      - rdap_lookup (nejvyšší priorita)
      - domain_to_ct
      - dht_infohash_lookup
    """
    seeds_path = output_dir / f"{sprint_id}_next_seeds.json"
    seeds: list[dict[str, Any]] = []

    try:
        for node in top_nodes:
            # node může být dict nebo tuple
            if isinstance(node, dict):
                ioc_value = node.get("value", "")
                ioc_type = node.get("ioc_type", "unknown")
            elif isinstance(node, (list, tuple)) and len(node) >= 2:
                ioc_value = str(node[0])
                ioc_type = str(node[1])
            else:
                continue

            if not ioc_value or len(ioc_value) < 3:
                continue

            # Každý top IOC generuje 3 follow-up tasky
            seeds.extend([
                {
                    "task_type": "rdap_lookup",
                    "value": ioc_value,
                    "priority": 0.85,
                    "reason": f"top_graph_node/{ioc_type}",
                },
                {
                    "task_type": "domain_to_ct",
                    "value": ioc_value,
                    "priority": 0.80,
                    "reason": f"top_graph_node/{ioc_type}",
                },
                {
                    "task_type": "dht_infohash_lookup",
                    "value": ioc_value,
                    "priority": 0.70,
                    "reason": f"top_graph_node/{ioc_type}",
                },
            ])

        seeds_path.write_text(json.dumps(seeds, indent=2, default=str))
        logger.info(f"[EXPORT] {len(seeds)} seed tasks → {seeds_path}")
    except Exception as e:
        logger.warning(f"[EXPORT] Seed generation failed: {e}")
        seeds_path.write_text(json.dumps([], indent=2))

    return seeds_path


def _make_serializable(obj: Any) -> Any:
    """Rekurzivně převede objekt na JSON-serializovatelný dict."""
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_serializable(v) for v in obj]
    if hasattr(obj, "__dict__"):
        return _make_serializable(obj.__dict__)
    return str(obj)
