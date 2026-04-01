"""
Sprint F3.6: Shadow Pre-Decision Consumer Layer
================================================

Shadow-only, read-only vrstva která čte ParityArtifact (z shadow_parity.py)
a skládá z něj pre-decision summary — interpretaci faktů pro scheduler decision,
aniž by sahala do core decision loopu.

STRICT BOUNDARIES:
- Shadow mode NIKDY nevolá tools execution
- Shadow mode NIKDY nevytváří findings writes
- Shadow mode NIKDY nevolá network execution
- Shadow mode NIKDY neprodukuje side effects
- Shadow mode NIKDY nezapisuje do produkčních ledgerů
- Pre-decision summary je DIAGNOSTICKÝ artifact, NENÍ nový truth store
- Žádné nové mutable fields na SprintScheduler
- Žádné background tasks
- Žádné nové caches

Co pre-decision consumer UMÍ:
- Čte ParityArtifact z run_shadow_parity()
- Skládá lifecycle interpretation summary
- Skládá graph capability summary
- Skládá export readiness summary
- Skládá model/control fact summary
- Skládá provider/branch precursor summary
- Generuje diff taxonomy (insufficient_input, lifecycle_mismatch, etc.)
- Identifikuje mismatch reasons
- Produkuje PreDecisionSummary artifact

Co pre-decision consumer NESMÍ:
- Nesahej do SprintScheduler.run() decision loopu
- Nepřidávej scheduler state
- Nevytvářej side effects
- Neaktivuj tools/providery
- Nezapisuj parity do produkčních ledgerů
- Nesluj phase vrstvy do jednoho pole

Owned by: runtime/shadow_pre_decision.py
Inputs: ParityArtifact (from shadow_parity.py)
Outputs: PreDecisionSummary (diagnostic artifact)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Dict, List, Optional, TYPE_CHECKING


# =============================================================================
# Diff Taxonomy — categorizace pre-decision mismatch reasons
# =============================================================================

class DiffTaxonomy(Enum):
    """
    Diff taxonomy pro pre-decision mismatch reasons.

    Každá kategorie reprezentuje distinct failure mode
    v pre-decision layer — NENÍ to scheduler decision samo.

    unlike ParityArtifact.mismatch_categories which are RAW mismatch flags,
    DiffTaxonomy je COMPOSED interpretation — bere raw mismatches
    a skládá z nich higher-level diagnosis.
    """
    # Základní stav
    NONE = auto()               # Všechny pre-decision vstupy jsou dostatečné

    # Input quality
    INSUFFICIENT_INPUT = auto()  # Fact bundles nemají dost informací pro pre-decision

    # Lifecycle mismatch
    LIFECYCLE_MISMATCH = auto()  # Lifecycle fáze je v nekonzistentním stavu

    # Phase layer conflict — workflow/control/windup fáze jsou v konfliktu
    PHASE_LAYER_CONFLICT = auto()  # Dvě nebo více phase vrstev si odporují

    # Graph capability ambiguity
    GRAPH_CAPABILITY_AMBIGUITY = auto()  # Graph backend/neural能力 je nejasný

    # Export handoff ambiguity
    EXPORT_HANDOFF_AMBIGUITY = auto()    # Export handoff facts jsou nejasné/neúplné

    # Model/Control ambiguity
    MODEL_CONTROL_AMBIGUITY = auto()     # Model/control konfigurace je nejasná

    # Provider precursor ambiguity
    PROVIDER_PRECURSOR_AMBIGUITY = auto()  # Provider doporučení je nejasné

    # Branch precursor ambiguity
    BRANCH_PRECURSOR_AMBIGUITY = auto()   # Branch rozhodnutí je nejasné


# =============================================================================
# Pre-Decision Summary — diagnostic artifact, NOT a truth store
# =============================================================================

@dataclass
class LifecycleInterpretation:
    """
    Lifecycle interpretation summary — composed from ParityArtifact.

    Interpretuje workflow_phase, control_phase a windup_local_phase
    z hlediska scheduler pre-decision, aniž by zasahovalo do lifecycle.
    """
    workflow_phase: str
    workflow_phase_entered_at: Optional[float]
    control_phase_mode: str
    control_phase_thermal: str
    windup_local_mode: Optional[str]

    # Pre-decision interpretation
    is_active: bool          # workflow_phase == ACTIVE
    is_windup: bool          # workflow_phase == WINDUP
    is_export_ready: bool     # workflow_phase == EXPORT
    is_terminal: bool        # workflow_phase in (EXPORT, TEARDOWN)
    can_accept_work: bool    # workflow_phase in (BOOT, WARMUP, ACTIVE)
    should_prune: bool       # control_phase_mode in (prune, panic)
    synthesis_mode_known: bool  # windup_local_mode is known

    # Phase conflict detection
    phase_conflict: bool     # True pokud phase vrstvy jsou v konfliktu
    phase_conflict_reason: Optional[str]  # Popis konfliktu pokud existuje


@dataclass
class GraphCapabilitySummary:
    """
    Graph capability summary — composed from ParityArtifact.

    Interpretuje graph facts z hlediska pre-decision.
    """
    backend: str
    nodes: int
    edges: int
    pgq_active: bool
    top_nodes_count: int

    # Pre-decision interpretation
    is_initialized: bool    # backend != "unknown"
    has_structured_data: bool  # nodes > 0 and edges > 0
    is_rich: bool           # top_nodes_count >= 5
    readiness: str           # "unknown" | "sparse" | "ready" | "rich"


@dataclass
class ExportReadinessSummary:
    """
    Export readiness summary — composed from ParityArtifact.

    Interpretuje export handoff facts z hlediska pre-decision.
    """
    sprint_id: str
    synthesis_engine: str
    ranked_parquet_present: bool
    gnn_predictions: int

    # Pre-decision interpretation
    is_ready: bool           # sprint_id known and engine known
    has_gnn_predictions: bool  # gnn_predictions > 0
    has_ranked_data: bool    # ranked_parquet_present
    readiness: str           # "unknown" | "partial" | "ready"


@dataclass
class ModelControlSummary:
    """
    Model/control fact summary — composed from ParityArtifact.

    Interpretuje model/control facts z hlediska pre-decision.
    """
    tools_count: int
    sources_count: int
    privacy: str
    depth: str
    models_needed: List[str]

    # Pre-decision interpretation
    has_tools: bool         # tools_count > 0
    has_sources: bool       # sources_count > 0
    is_high_quality: bool   # depth in (DEEP, STANDARD) and privacy != UNKNOWN
    readiness: str          # "unknown" | "partial" | "ready"


@dataclass
class PrecursorSummary:
    """
    Provider/Branch precursor summary — composed from ParityArtifact.

    Interpretuje provider a branch decision precursors z hlediska pre-decision.
    """
    branch_decision_id: Optional[str]
    provider_recommend: Optional[str]
    correlation_run_id: Optional[str]
    correlation_branch_id: Optional[str]

    # Pre-decision interpretation
    has_branch_decision: bool  # branch_decision_id is not None
    has_provider_recommend: bool  # provider_recommend is not None
    has_correlation: bool     # correlation_run_id is not None
    is_correlation_linked: bool  # correlation_run_id == branch_decision_id (if both set)

    # Readiness
    readiness: str  # "unknown" | "partial" | "ready"


@dataclass
class PreDecisionSummary:
    """
    Pre-decision summary artifact — composed from ParityArtifact.

    Toto je DIAGNOSTICKÝ artifact. Nesmí být zapsán do produkčních ledgerů
    jako runtime facts. Nesmí participovat v control flow rozhodnutích.

    Struktura:
    - lifecycle: LifecycleInterpretation (composed from ParityArtifact)
    - graph: GraphCapabilitySummary (composed from ParityArtifact)
    - export: ExportReadinessSummary (composed from ParityArtifact)
    - model_control: ModelControlSummary (composed from ParityArtifact)
    - precursors: PrecursorSummary (composed from ParityArtifact)
    - diff_taxonomy: List[DiffTaxonomy] (composed from ParityArtifact.mismatch_categories)
    - blockers: List[str] — co brání pre-decision confidence
    - unknowns: List[str] — co je neznámé
    - mismatch_reasons: Dict[str, str] — pro každý mismatch category důvod

    Phase separation: VŠECHNY phase fields jsou ODDĚLENÉ v LifecycleInterpretation.
    Žádné slité phase pole neexistuje.
    """
    # Source parity artifact reference
    parity_timestamp_monotonic: float
    parity_timestamp_wall: str
    runtime_mode: str

    # Composed interpretations
    lifecycle: LifecycleInterpretation
    graph: GraphCapabilitySummary
    export_readiness: ExportReadinessSummary
    model_control: ModelControlSummary
    precursors: PrecursorSummary

    # Diff taxonomy — composed from parity artifact mismatches
    diff_taxonomy: List[DiffTaxonomy]

    # Diagnostic metadata
    blockers: List[str]  # Co brání pre-decision confidence
    unknowns: List[str]  # Co je neznámé
    mismatch_reasons: Dict[str, str]  # category → reason string

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parity_timestamp_monotonic": self.parity_timestamp_monotonic,
            "parity_timestamp_wall": self.parity_timestamp_wall,
            "runtime_mode": self.runtime_mode,
            "lifecycle": {
                "workflow_phase": self.lifecycle.workflow_phase,
                "workflow_phase_entered_at": self.lifecycle.workflow_phase_entered_at,
                "control_phase_mode": self.lifecycle.control_phase_mode,
                "control_phase_thermal": self.lifecycle.control_phase_thermal,
                "windup_local_mode": self.lifecycle.windup_local_mode,
                "is_active": self.lifecycle.is_active,
                "is_windup": self.lifecycle.is_windup,
                "is_export_ready": self.lifecycle.is_export_ready,
                "is_terminal": self.lifecycle.is_terminal,
                "can_accept_work": self.lifecycle.can_accept_work,
                "should_prune": self.lifecycle.should_prune,
                "synthesis_mode_known": self.lifecycle.synthesis_mode_known,
                "phase_conflict": self.lifecycle.phase_conflict,
                "phase_conflict_reason": self.lifecycle.phase_conflict_reason,
            },
            "graph": {
                "backend": self.graph.backend,
                "nodes": self.graph.nodes,
                "edges": self.graph.edges,
                "pgq_active": self.graph.pgq_active,
                "top_nodes_count": self.graph.top_nodes_count,
                "is_initialized": self.graph.is_initialized,
                "has_structured_data": self.graph.has_structured_data,
                "is_rich": self.graph.is_rich,
                "readiness": self.graph.readiness,
            },
            "export_readiness": {
                "sprint_id": self.export_readiness.sprint_id,
                "synthesis_engine": self.export_readiness.synthesis_engine,
                "ranked_parquet_present": self.export_readiness.ranked_parquet_present,
                "gnn_predictions": self.export_readiness.gnn_predictions,
                "is_ready": self.export_readiness.is_ready,
                "has_gnn_predictions": self.export_readiness.has_gnn_predictions,
                "has_ranked_data": self.export_readiness.has_ranked_data,
                "readiness": self.export_readiness.readiness,
            },
            "model_control": {
                "tools_count": self.model_control.tools_count,
                "sources_count": self.model_control.sources_count,
                "privacy": self.model_control.privacy,
                "depth": self.model_control.depth,
                "models_needed": self.model_control.models_needed,
                "has_tools": self.model_control.has_tools,
                "has_sources": self.model_control.has_sources,
                "is_high_quality": self.model_control.is_high_quality,
                "readiness": self.model_control.readiness,
            },
            "precursors": {
                "branch_decision_id": self.precursors.branch_decision_id,
                "provider_recommend": self.precursors.provider_recommend,
                "correlation_run_id": self.precursors.correlation_run_id,
                "correlation_branch_id": self.precursors.correlation_branch_id,
                "has_branch_decision": self.precursors.has_branch_decision,
                "has_provider_recommend": self.precursors.has_provider_recommend,
                "has_correlation": self.precursors.has_correlation,
                "is_correlation_linked": self.precursors.is_correlation_linked,
                "readiness": self.precursors.readiness,
            },
            "diff_taxonomy": [dt.name for dt in self.diff_taxonomy],
            "blockers": self.blockers,
            "unknowns": self.unknowns,
            "mismatch_reasons": self.mismatch_reasons,
        }


# =============================================================================
# Pre-Decision Composer — pure function, no side effects
# =============================================================================

def compose_pre_decision(
    parity_artifact: "ParityArtifact",
) -> PreDecisionSummary:
    """
    Sestaví PreDecisionSummary z ParityArtifact.

    Toto je PURE FUNCTION — žádné side effects, žádné I/O, žádné network.

    Args:
        parity_artifact: ParityArtifact z run_shadow_parity()

    Returns:
        PreDecisionSummary — composed pre-decision artifact
    """
    # --- Lifecycle Interpretation ---
    lc = _compose_lifecycle_interpretation(parity_artifact)

    # --- Graph Capability Summary ---
    gr = _compose_graph_capability_summary(parity_artifact)

    # --- Export Readiness Summary ---
    er = _compose_export_readiness_summary(parity_artifact)

    # --- Model/Control Summary ---
    mc = _compose_model_control_summary(parity_artifact)

    # --- Precursor Summary ---
    pr = _compose_precursor_summary(parity_artifact)

    # --- Diff Taxonomy ---
    diffs = _compose_diff_taxonomy(parity_artifact, lc, gr, er, pr)

    # --- Blockers, Unknowns, Mismatch Reasons ---
    blockers, unknowns, mismatch_reasons = _compose_diagnostic_metadata(
        parity_artifact, lc, gr, er, mc, pr
    )

    return PreDecisionSummary(
        parity_timestamp_monotonic=parity_artifact.timestamp_monotonic,
        parity_timestamp_wall=parity_artifact.timestamp_wall,
        runtime_mode=parity_artifact.mode,
        lifecycle=lc,
        graph=gr,
        export_readiness=er,
        model_control=mc,
        precursors=pr,
        diff_taxonomy=diffs,
        blockers=blockers,
        unknowns=unknowns,
        mismatch_reasons=mismatch_reasons,
    )


def _compose_lifecycle_interpretation(
    artifact: "ParityArtifact",
) -> LifecycleInterpretation:
    """Sestaví lifecycle interpretation z ParityArtifact."""
    wf = artifact.workflow_phase
    ctrl = artifact.control_phase_mode
    ctrl_thermal = artifact.control_phase_thermal
    windup = artifact.windup_local_mode

    # Phase state
    is_active = wf == "ACTIVE"
    is_windup = wf == "WINDUP"
    is_export_ready = wf == "EXPORT"
    is_terminal = wf in ("EXPORT", "TEARDOWN")
    can_accept_work = wf in ("BOOT", "WARMUP", "ACTIVE")

    # Control phase
    should_prune = ctrl in ("prune", "panic")

    # Windup local
    synthesis_mode_known = windup is not None

    # Phase conflict detection
    phase_conflict = False
    phase_conflict_reason: Optional[str] = None

    # Konflikt: WINDUP bez windup_local_mode
    if is_windup and not synthesis_mode_known:
        phase_conflict = True
        phase_conflict_reason = "workflow_phase=WINDUP but windup_local_mode is None"

    # Konflikt: non-WINDUP s windup_local_mode
    if not is_windup and synthesis_mode_known:
        phase_conflict = True
        phase_conflict_reason = f"workflow_phase={wf} but windup_local_mode={windup}"

    return LifecycleInterpretation(
        workflow_phase=wf,
        workflow_phase_entered_at=artifact.workflow_phase_entered_at,
        control_phase_mode=ctrl,
        control_phase_thermal=ctrl_thermal,
        windup_local_mode=windup,
        is_active=is_active,
        is_windup=is_windup,
        is_export_ready=is_export_ready,
        is_terminal=is_terminal,
        can_accept_work=can_accept_work,
        should_prune=should_prune,
        synthesis_mode_known=synthesis_mode_known,
        phase_conflict=phase_conflict,
        phase_conflict_reason=phase_conflict_reason,
    )


def _compose_graph_capability_summary(
    artifact: "ParityArtifact",
) -> GraphCapabilitySummary:
    """Sestaví graph capability summary z ParityArtifact."""
    backend = artifact.graph_backend
    nodes = artifact.graph_nodes
    edges = artifact.graph_edges
    pgq = artifact.graph_pgq_active
    top_n = artifact.graph_top_nodes_count

    is_initialized = backend != "unknown"
    has_structured_data = nodes > 0 and edges > 0
    is_rich = top_n >= 5

    if backend == "unknown":
        readiness = "unknown"
    elif not is_initialized:
        readiness = "unknown"
    elif nodes == 0 and edges == 0:
        readiness = "sparse"
    elif top_n >= 5:
        readiness = "rich"
    else:
        readiness = "ready"

    return GraphCapabilitySummary(
        backend=backend,
        nodes=nodes,
        edges=edges,
        pgq_active=pgq,
        top_nodes_count=top_n,
        is_initialized=is_initialized,
        has_structured_data=has_structured_data,
        is_rich=is_rich,
        readiness=readiness,
    )


def _compose_export_readiness_summary(
    artifact: "ParityArtifact",
) -> ExportReadinessSummary:
    """Sestaví export readiness summary z ParityArtifact."""
    sprint_id = artifact.export_sprint_id
    engine = artifact.export_synthesis_engine
    ranked = artifact.export_ranked_parquet_present
    gnn = artifact.export_gnn_predictions

    is_ready = sprint_id != "unknown" and engine != "unknown"
    has_gnn = gnn > 0
    has_ranked = ranked

    if sprint_id == "unknown":
        readiness = "unknown"
    elif engine == "unknown":
        readiness = "partial"
    else:
        readiness = "ready"

    return ExportReadinessSummary(
        sprint_id=sprint_id,
        synthesis_engine=engine,
        ranked_parquet_present=ranked,
        gnn_predictions=gnn,
        is_ready=is_ready,
        has_gnn_predictions=has_gnn,
        has_ranked_data=has_ranked,
        readiness=readiness,
    )


def _compose_model_control_summary(
    artifact: "ParityArtifact",
) -> ModelControlSummary:
    """Sestaví model/control summary z ParityArtifact."""
    tools = artifact.mc_tools_count
    sources = artifact.mc_sources_count
    privacy = artifact.mc_privacy
    depth = artifact.mc_depth
    models = artifact.mc_models_needed

    has_tools = tools > 0
    has_sources = sources > 0
    is_high_quality = depth in ("DEEP", "STANDARD") and privacy != "UNKNOWN"

    if not has_tools and not has_sources:
        readiness = "unknown"
    elif not has_tools or not has_sources:
        readiness = "partial"
    else:
        readiness = "ready"

    return ModelControlSummary(
        tools_count=tools,
        sources_count=sources,
        privacy=privacy,
        depth=depth,
        models_needed=models,
        has_tools=has_tools,
        has_sources=has_sources,
        is_high_quality=is_high_quality,
        readiness=readiness,
    )


def _compose_precursor_summary(
    artifact: "ParityArtifact",
) -> PrecursorSummary:
    """Sestaví precursor summary z ParityArtifact."""
    branch_id = artifact.branch_decision_id
    provider = artifact.provider_recommend
    corr_run = artifact.correlation_run_id
    corr_branch = artifact.correlation_branch_id

    has_branch = branch_id is not None
    has_provider = provider is not None
    has_corr = corr_run is not None
    is_linked = has_branch and has_corr and (corr_branch == branch_id)

    if not has_branch and not has_provider:
        readiness = "unknown"
    elif not has_branch or not has_provider:
        readiness = "partial"
    else:
        readiness = "ready"

    return PrecursorSummary(
        branch_decision_id=branch_id,
        provider_recommend=provider,
        correlation_run_id=corr_run,
        correlation_branch_id=corr_branch,
        has_branch_decision=has_branch,
        has_provider_recommend=has_provider,
        has_correlation=has_corr,
        is_correlation_linked=is_linked,
        readiness=readiness,
    )


def _compose_diff_taxonomy(
    artifact: "ParityArtifact",
    lc: LifecycleInterpretation,
    gr: GraphCapabilitySummary,
    er: ExportReadinessSummary,
    pr: PrecursorSummary,
) -> List[DiffTaxonomy]:
    """
    Sestaví diff taxonomy z ParityArtifact mismatch_categories
    a composed interpretations.

    Unlike ParityArtifact.mismatch_categories (raw flags),
    DiffTaxonomy je composed higher-level diagnosis.
    """
    diffs: List[DiffTaxonomy] = []
    raw_mismatches = artifact.mismatch_categories or []

    # Map raw mismatches to DiffTaxonomy
    for mismatch in raw_mismatches:
        if mismatch == "NONE":
            diffs.append(DiffTaxonomy.NONE)
        elif mismatch == "LIFECYCLE":
            diffs.append(DiffTaxonomy.LIFECYCLE_MISMATCH)
        elif mismatch == "GRAPH_CAPABILITY":
            diffs.append(DiffTaxonomy.GRAPH_CAPABILITY_AMBIGUITY)
        elif mismatch == "MODEL_CONTROL":
            diffs.append(DiffTaxonomy.MODEL_CONTROL_AMBIGUITY)
        elif mismatch == "EXPORT_HANDOFF":
            diffs.append(DiffTaxonomy.EXPORT_HANDOFF_AMBIGUITY)
        elif mismatch == "PHASE_FIELD_MERGE":
            # PHASE_FIELD_MERGE is a BUG — elevated to PHASE_LAYER_CONFLICT
            diffs.append(DiffTaxonomy.PHASE_LAYER_CONFLICT)
        elif mismatch == "INSUFFICIENT_INPUT":
            diffs.append(DiffTaxonomy.INSUFFICIENT_INPUT)

    # Compose additional diffs from interpretations (not just raw mismatches)
    # Phase layer conflict detection
    if lc.phase_conflict and DiffTaxonomy.PHASE_LAYER_CONFLICT not in diffs:
        diffs.append(DiffTaxonomy.PHASE_LAYER_CONFLICT)

    # Insufficient input detection
    if gr.readiness == "unknown" and er.readiness == "unknown":
        if DiffTaxonomy.INSUFFICIENT_INPUT not in diffs:
            diffs.append(DiffTaxonomy.INSUFFICIENT_INPUT)

    # Provider precursor ambiguity
    if pr.readiness == "unknown" and DiffTaxonomy.PROVIDER_PRECURSOR_AMBIGUITY not in diffs:
        diffs.append(DiffTaxonomy.PROVIDER_PRECURSOR_AMBIGUITY)

    # Branch precursor ambiguity
    if pr.readiness == "unknown" and DiffTaxonomy.BRANCH_PRECURSOR_AMBIGUITY not in diffs:
        diffs.append(DiffTaxonomy.BRANCH_PRECURSOR_AMBIGUITY)

    # Deduplicate
    seen: set[DiffTaxonomy] = set()
    result: List[DiffTaxonomy] = []
    for d in diffs:
        if d not in seen:
            seen.add(d)
            result.append(d)

    # NONE only if nothing else
    if not result:
        result.append(DiffTaxonomy.NONE)

    return result


def _compose_diagnostic_metadata(
    artifact: "ParityArtifact",
    lc: LifecycleInterpretation,
    gr: GraphCapabilitySummary,
    er: ExportReadinessSummary,
    mc: ModelControlSummary,
    pr: PrecursorSummary,
) -> tuple[List[str], List[str], Dict[str, str]]:
    """
    Sestaví blockers, unknowns a mismatch_reasons z composed interpretations.

    Returns:
        (blockers, unknowns, mismatch_reasons)
    """
    blockers: List[str] = []
    unknowns: List[str] = []
    mismatch_reasons: Dict[str, str] = {}

    # Map raw mismatch details to reasons
    details = artifact.mismatch_details or {}
    for category, detail in details.items():
        if category == "note":
            continue
        mismatch_reasons[category] = str(detail)

    # Add interpretation-based blockers
    if not lc.can_accept_work and not lc.is_terminal:
        blockers.append(f"lifecycle not ready: workflow_phase={lc.workflow_phase}")

    if gr.readiness == "unknown":
        blockers.append("graph backend unknown — cannot determine graph capability")

    if er.readiness == "unknown":
        blockers.append("export handoff not ready: sprint_id or engine unknown")

    if mc.readiness == "unknown":
        blockers.append("model/control facts unknown: no tools or sources configured")

    if lc.phase_conflict:
        blockers.append(f"phase layer conflict: {lc.phase_conflict_reason}")

    # Add unknowns (things we don't know but would help)
    if pr.readiness == "unknown":
        unknowns.append("branch decision precursor: no branch_decision_id available")
        unknowns.append("provider recommendation precursor: no provider_recommend available")

    if gr.readiness == "sparse":
        unknowns.append("graph data sparse: low node/edge count for meaningful analysis")

    if not mc.is_high_quality:
        unknowns.append(f"model/control quality: privacy={mc.privacy}, depth={mc.depth}")

    return blockers, unknowns, mismatch_reasons


# =============================================================================
# TYPE CHECKING imports — only used behind TYPE_CHECKING guard
# =============================================================================

if TYPE_CHECKING:
    from shadow_parity import ParityArtifact  # type: ignore[import-not-found]
