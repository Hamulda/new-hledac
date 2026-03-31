"""
Sprint 8VI §A: EXPORT fáze — export_sprint() + _generate_next_sprint_seeds()

Extrahováno z __main__.py EXPORT sekce.
JSON report, HTML report stub, seed tasky pro příští sprint.
"""

from __future__ import annotations

import json
import logging
import pathlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..runtime.sprint_scheduler import SprintScheduler

logger = logging.getLogger(__name__)


async def export_sprint(
    scheduler: "SprintScheduler",
    scorecard: dict,
    sprint_id: str,
) -> dict:
    """
    EXPORT fáze — JSON report, seed tasky pro příští sprint.

    Vrátí: {"report_json": path, "seeds_json": path}
    Nikdy nevyhodí výjimku.

    Součásti:
      1. JSON report do ~/.hledac/reports/{sprint_id}_report.json
      2. Seed tasky pro příští sprint z top IOC graph nodes
    """
    from paths import SPRINT_STORE_ROOT

    report_dir = SPRINT_STORE_ROOT.parent / "reports"
    try:
        report_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"[EXPORT] Could not create report_dir: {e}")
        report_dir = SPRINT_STORE_ROOT  # fallback

    # 1. JSON report
    report_path = report_dir / f"{sprint_id}_report.json"
    try:
        serializable_scorecard = _make_serializable(scorecard)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(serializable_scorecard, f, indent=2, default=str)
        logger.info(f"[EXPORT] JSON report → {report_path}")
    except Exception as e:
        logger.warning(f"[EXPORT] JSON write failed: {e}")
        report_path = None

    # 2. Seed tasky pro příští sprint
    seeds_path = _generate_next_sprint_seeds(scheduler, sprint_id, report_dir)

    return {
        "report_json": str(report_path) if report_path else "",
        "seeds_json": str(seeds_path),
    }


def _generate_next_sprint_seeds(
    scheduler: "SprintScheduler",
    sprint_id: str,
    output_dir: pathlib.Path,
) -> pathlib.Path:
    """
    Generuje PivotTask seed JSON pro příští sprint.

    Zdroj: top IOC nodes z DuckPGQGraph (nejvíce connected = nejzajímavější).
    Každý top IOC generuje 3 follow-up tasky:
      - rdap_lookup (nejvyšší priorita)
      - domain_to_ct
      - dht_infohash_lookup
    """
    seeds_path = output_dir / f"{sprint_id}_next_seeds.json"
    seeds: list[dict[str, Any]] = []

    try:
        if hasattr(scheduler, "_ioc_graph") and scheduler._ioc_graph is not None:
            top_nodes = scheduler._ioc_graph.get_top_nodes_by_degree(n=5)
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

        seeds_path_str = seeds_path.write_text(
            json.dumps(seeds, indent=2, default=str)
        )
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
