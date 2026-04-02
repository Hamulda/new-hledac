# hledac/universal/export/COMPAT_HANDOFF.py
# Sprint 8VX §C: ExportHandoff producer convergence audit
# Sprint 8VY §A: Updated — removal conditions tightened, compat scope explicit
# ⚠️  DEPRECATED THIN ADAPTER — DO NOT EXTEND
"""
Canonical producer-side handoff truth (Sprint 8VY):

  PRIMARY PATH (canonical): __main__._print_scorecard_report() builds
    ExportHandoff.from_windup(sprint_id, scorecard_data) where scorecard_data
    is a dict. The .from_windup() extraction from scorecard["top_graph_nodes"]
    is the CURRENT compat seam — windup_engine returns dict, not typed ExportHandoff.

  COMPAT SEAM (current): scorecard["top_graph_nodes"] is populated by
    windup_engine from scheduler._ioc_graph.get_top_nodes_by_degree(n=10).
    Two chained compat seams: windup dict → scorecard dict → ExportHandoff.

  FUTURE TARGET (post-cutover): windup_engine returns typed ExportHandoff
    directly; from_windup(scorecard) disappears; ensure_export_handoff() shrinks
    to None-only path.

  REMOVAL CONDITIONS:
    1. ensure_export_handoff() for dict → removal when windup returns typed ExportHandoff
    2. ensure_export_handoff() for None → removal when __main__ always passes typed ExportHandoff
    3. scorecard["top_graph_nodes"] compat → removal when windup_engine fills ExportHandoff.top_nodes directly
    4. store.get_top_seed_nodes() fallback → removal when ExportHandoff.top_nodes always populated

  WHAT THIS MODULE IS NOT:
    - NOT a new DTO system — ExportHandoff (types.py) is the only typed handoff
    - NOT an export framework — export plane is sprint_exporter.py
    - NOT a producer factory — __main__ constructs via from_windup(), not via this module
    - NOT growing — new features go to windup_engine or types.py, not here
"""

# =============================================================================
# Sprint 8VY §A: ExportHandoff producer convergence
# =============================================================================
# Thin adapter: ExportHandoff | dict | None → ExportHandoff
# PRIMARY role: ensure export_sprint() always receives typed ExportHandoff.
#
# Two compat seams remaining:
#   A. dict → ExportHandoff: via from_windup(scorecard) extracting scorecard["top_graph_nodes"]
#      REMOVAL: when windup_engine returns typed ExportHandoff directly
#   B. None → empty ExportHandoff: for defensive None handling
#      REMOVAL: when __main__ always passes typed ExportHandoff (never None)
#
# Producer side: __main__._print_scorecard_report() → ExportHandoff.from_windup(sprint_id, scorecard_data)
# Consumer side: export_sprint() — receives typed ExportHandoff
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

    Three dispatch cases:
      1. ExportHandoff instance → returned unchanged (PRIMARY canonical path)
      2. dict (scorecard) → via from_windup(scorecard) — COMPAT SEAM A
      3. None → empty ExportHandoff — COMPAT SEAM B

    Compat seam A (dict path):
      from_windup() extracts scorecard["top_graph_nodes"] → top_nodes.
      Two chained compat seams: windup dict → scorecard dict → ExportHandoff.
      REMOVAL CONDITION: windup_engine returns typed ExportHandoff directly.

    Compat seam B (None path):
      Returns empty ExportHandoff with default_sprint_id.
      REMOVAL CONDITION: __main__ always passes typed ExportHandoff, never None.

    Args:
        handoff: ExportHandoff instance, dict (scorecard-style), or None
        default_sprint_id: fallback sprint_id if handoff is None

    Returns:
        ExportHandoff — always typed, never None

    NOTE: Thin compat adapter only. Does NOT create typed objects from raw facts.
          New features go to windup_engine or types.py ExportHandoff.from_windup().
    """
    # Import we need it at runtime
    from hledac.universal.types import ExportHandoff as TypesExportHandoff

    if handoff is None:
        # Compat seam B: defensive None handling
        return TypesExportHandoff(
            sprint_id=default_sprint_id,
            scorecard={},
            top_nodes=[],
        )

    if isinstance(handoff, TypesExportHandoff):
        # PRIMARY canonical path — ExportHandoff passed through unchanged
        return handoff

    if isinstance(handoff, dict):
        # Compat seam A: dict → typed via from_windup()
        # scorecard["top_graph_nodes"] → top_nodes is the current compat extraction
        sprint_id = handoff.get("sprint_id", default_sprint_id)
        return TypesExportHandoff.from_windup(
            sprint_id=sprint_id,
            scorecard=handoff,
        )

    raise TypeError(
        f"ensure_export_handoff() got unexpected type: {type(handoff).__name__}. "
        f"Expected ExportHandoff, dict, or None."
    )
