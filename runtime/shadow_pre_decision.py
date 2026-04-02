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

from dataclasses import dataclass, field
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

    Každá kategorie má také `_stability` tag:
    - STABLE mismatch: problém v stable/typed path, vyžaduje pozornost
    - COMPAT mismatch: problém v compat/legacy path, může být expected
    - UNKNOWN mismatch: nedostatek informací, obvykle není blocker
    """
    # Základní stav
    NONE = auto()               # Všechny pre-decision vstupy jsou dostatečné

    # Input quality
    INSUFFICIENT_INPUT = auto()  # Fact bundles nemají dost informací pro pre-decision

    # Lifecycle mismatch — STABLE (from SprintLifecycleManager)
    LIFECYCLE_MISMATCH = auto()  # Lifecycle fáze je v nekonzistentním stavu

    # Phase layer conflict — STABLE (structural invariant check)
    PHASE_LAYER_CONFLICT = auto()  # Dvě nebo více phase vrstev si odporují

    # Graph capability ambiguity — STABILITY závisí na path (STABLE pokud duckpgq, UNKNOWN pokud unknown)
    GRAPH_CAPABILITY_AMBIGUITY = auto()  # Graph backend/neural capability je nejasný

    # Export handoff ambiguity — UNKNOWN stability (depends on handoff source)
    EXPORT_HANDOFF_AMBIGUITY = auto()    # Export handoff facts jsou nejasné/neúplné

    # Model/Control ambiguity — STABILITY závisí na path (STABLE pokud AnalyzerResult, COMPAT pokud raw_profile)
    MODEL_CONTROL_AMBIGUITY = auto()     # Model/control konfigurace je nejasná

    # Provider precursor ambiguity — UNKNOWN (provider_recommend is future)
    PROVIDER_PRECURSOR_AMBIGUITY = auto()  # Provider doporučení je nejasné

    # Branch precursor ambiguity — UNKNOWN (depends on branch_decision source)
    BRANCH_PRECURSOR_AMBIGUITY = auto()   # Branch rozhodnutí je nejasné

    # Compat seam warning — COMPAT only, not a real mismatch
    # Toto je FYZIOLOGICKÝ stav, ne problém. Označuje že jsme v compat path.
    COMPAT_SEAM_ACTIVE = auto()   # Compat seam je aktivní (windup_local_phase, scorecard, raw_profile)

    # Decision gate readiness — richer preview (Sprint 8VQ)
    DECISION_GATE_READY = auto()    # Všechny facts dostatečné, žádné blockers
    DECISION_GATE_BLOCKED = auto()  # Hard blockers present — cannot proceed
    DECISION_GATE_INSUFFICIENT = auto()  # Facts insufficient for decision
    DECISION_GATE_UNKNOWN = auto()   # Cannot determine readiness

    # Tool readiness — DIAGNOSTIC ONLY, no dispatch
    TOOL_READINESS_READY = auto()    # Tools available, can execute
    TOOL_READINESS_DEGRADED = auto()  # Some tools unavailable due to resource pressure
    TOOL_READINESS_PRUNED = auto()  # Tools heavily pruned (panic mode)
    TOOL_READINESS_UNKNOWN = auto() # Cannot determine tool readiness

    # Windup readiness — from existing fact bundles only
    WINDUP_READY = auto()           # Windup facts sufficient
    WINDUP_PARTIAL = auto()         # Some windup facts missing
    WINDUP_INSUFFICIENT = auto()    # Windup facts insufficient
    WINDUP_NOT_ACTIVE = auto()      # Not in WINDUP phase

    # Provider activation — deferred/unknown note only, NO simulation
    PROVIDER_DEFERRED = auto()       # Provider activation deferred to future phase
    PROVIDER_UNKNOWN = auto()        # Cannot determine provider readiness
    PROVIDER_NOT_READY = auto()      # Provider not ready
    PROVIDER_BLOCKED = auto()       # Provider blocked by hard constraint


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
class DecisionGateReadiness:
    """
    Decision gate readiness — explicit rozlišení pro scheduler decision gate.

    DIAGNOSTIC ONLY — tento artifact NESMÍ být použit pro skutečná
    scheduler rozhodnutí. Pouze pro diagnostický výstup.

    Rozlišuje:
    - DECISION_GATE_READY: všechny facts dostatečné, žádné blockers
    - DECISION_GATE_BLOCKED: hard blockers present — cannot proceed
    - DECISION_GATE_INSUFFICIENT: facts insufficient for decision
    - DECISION_GATE_UNKNOWN: cannot determine readiness
    """
    gate_status: str  # "ready" | "blocked" | "insufficient" | "unknown"
    blocker_count: int
    unknown_count: int
    compat_seam_count: int
    # Detail per category
    blocker_categories: List[str]  # Which categories are blocking
    unknown_categories: List[str]  # Which categories are unknown
    is_proceed_allowed: bool  # True iff gate_status == "ready"
    defer_to_provider: bool  # Provider activation deferred


@dataclass
class ToolReadinessPreview:
    """
    Tool readiness preview — DIAGNOSTIC ONLY, no dispatch, no execute_with_limits.

    Čte POUZE z existujícího ToolRegistry surface (list_tools, get_tool_cards).
    NESMÍ volat acquire(), load_model(), nebo jakékoli provider activation.

    Tento preview rozlišuje:
    - TOOL_READINESS_READY: tools available, can execute
    - TOOL_READINESS_DEGRADED: some tools unavailable due to resource pressure
    - TOOL_READINESS_PRUNED: tools heavily pruned (panic mode)
    - TOOL_READINESS_UNKNOWN: cannot determine tool readiness
    """
    readiness: str  # "ready" | "degraded" | "pruned" | "unknown"
    tool_count: int
    tool_names: List[str]
    has_network_tools: bool
    has_high_memory_tools: bool
    # Control phase impact
    control_mode: str  # "normal" | "prune" | "panic"
    pruned_tool_count: int  # Estimated pruned tools (based on control mode)
    # Resource-based assessment (read-only, no actual measurement)
    resource_constraint: str  # "none" | "memory" | "thermal" | "unknown"
    can_execute: bool  # True iff readiness in ("ready", "degraded")
    defer_reason: Optional[str]  # Why deferred or unknown


@dataclass
class WindupReadinessPreview:
    """
    Windup readiness preview — from existing fact bundles, DIAGNOSTIC ONLY.

    Čte z LifecycleSnapshotBundle a ExportReadinessSummary.
    NESMÍ měnit ownership, NESMÍ aktivovat windup engine.

    Rozlišuje:
    - WINDUP_READY: windup facts sufficient
    - WINDUP_PARTIAL: some windup facts missing
    - WINDUP_INSUFFICIENT: windup facts insufficient
    - WINDUP_NOT_ACTIVE: not in WINDUP phase
    """
    readiness: str  # "ready" | "partial" | "insufficient" | "not_active"
    is_windup_phase: bool
    synthesis_mode: Optional[str]  # "synthesis" | "structured" | "minimal" | None
    synthesis_engine: str
    has_export_data: bool  # ranked_parquet or gnn_predictions available
    export_data_quality: str  # "none" | "sparse" | "ready"
    defer_reason: Optional[str]  # Why deferred or not ready


@dataclass
class ProviderActivationNote:
    """
    Provider activation note — deferred/unknown only, NO simulation.

    DIAGNOSTIC ONLY. Tento note NESMÍ:
    - Simulovat load order providerů
    - Simulovat provider state machine
    - Vzniknout pseudo-authorita provider plane

    Rozlišuje:
    - PROVIDER_DEFERRED: activation deferred to future phase
    - PROVIDER_UNKNOWN: cannot determine provider readiness
    - PROVIDER_NOT_READY: provider not ready
    - PROVIDER_BLOCKED: blocked by hard constraint
    """
    status: str  # "deferred" | "unknown" | "not_ready" | "blocked"
    deferral_reason: str  # Why deferred
    has_recommendation: bool  # provider_recommend available
    recommendation: Optional[str]  # Raw recommendation string
    next_phase_hint: Optional[str]  # Hint about when activation might proceed
    # NO: load_order, provider_state, activation_sequence


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
    # Compat seams — FYSIOLOGICAL, not blockers. Lists which bundles use legacy paths.
    compat_seams: List[str] = field(default_factory=list)

    # Sprint 8VQ: Richer readiness previews
    decision_gate: Optional[DecisionGateReadiness] = None
    tool_readiness: Optional[ToolReadinessPreview] = None
    windup_readiness: Optional[WindupReadinessPreview] = None
    provider_note: Optional[ProviderActivationNote] = None

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
            "compat_seams": self.compat_seams,
            # Sprint 8VQ: Richer readiness previews
            "decision_gate": {
                "gate_status": self.decision_gate.gate_status,
                "blocker_count": self.decision_gate.blocker_count,
                "unknown_count": self.decision_gate.unknown_count,
                "compat_seam_count": self.decision_gate.compat_seam_count,
                "blocker_categories": self.decision_gate.blocker_categories,
                "unknown_categories": self.decision_gate.unknown_categories,
                "is_proceed_allowed": self.decision_gate.is_proceed_allowed,
                "defer_to_provider": self.decision_gate.defer_to_provider,
            } if self.decision_gate else None,
            "tool_readiness": {
                "readiness": self.tool_readiness.readiness,
                "tool_count": self.tool_readiness.tool_count,
                "tool_names": self.tool_readiness.tool_names,
                "has_network_tools": self.tool_readiness.has_network_tools,
                "has_high_memory_tools": self.tool_readiness.has_high_memory_tools,
                "control_mode": self.tool_readiness.control_mode,
                "pruned_tool_count": self.tool_readiness.pruned_tool_count,
                "resource_constraint": self.tool_readiness.resource_constraint,
                "can_execute": self.tool_readiness.can_execute,
                "defer_reason": self.tool_readiness.defer_reason,
            } if self.tool_readiness else None,
            "windup_readiness": {
                "readiness": self.windup_readiness.readiness,
                "is_windup_phase": self.windup_readiness.is_windup_phase,
                "synthesis_mode": self.windup_readiness.synthesis_mode,
                "synthesis_engine": self.windup_readiness.synthesis_engine,
                "has_export_data": self.windup_readiness.has_export_data,
                "export_data_quality": self.windup_readiness.export_data_quality,
                "defer_reason": self.windup_readiness.defer_reason,
            } if self.windup_readiness else None,
            "provider_note": {
                "status": self.provider_note.status,
                "deferral_reason": self.provider_note.deferral_reason,
                "has_recommendation": self.provider_note.has_recommendation,
                "recommendation": self.provider_note.recommendation,
                "next_phase_hint": self.provider_note.next_phase_hint,
            } if self.provider_note else None,
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

    # --- Sprint 8VQ: Decision Gate Readiness ---
    gate_readiness = _compose_decision_gate_readiness(
        blockers, unknowns, parity_artifact.compat_seams
    )

    # --- Sprint 8VQ: Tool Readiness Preview (read-only, no dispatch) ---
    tool_readiness = _compose_tool_readiness_preview(
        lc.control_phase_mode,
        gr,
    )

    # --- Sprint 8VQ: Windup Readiness Preview ---
    windup_readiness = _compose_windup_readiness_preview(
        lc, er
    )

    # --- Sprint 8VQ: Provider Activation Note (deferred/unknown only) ---
    provider_note = _compose_provider_activation_note(
        pr, lc
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
        compat_seams=parity_artifact.compat_seams,
        # Sprint 8VQ: Richer readiness previews
        decision_gate=gate_readiness,
        tool_readiness=tool_readiness,
        windup_readiness=windup_readiness,
        provider_note=provider_note,
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

    compat_seams from ParityArtifact are mapped to COMPAT_SEAM_ACTIVE.
    This is a FYSIOLOGICAL state, not a blocker — it indicates
    we are using legacy compat paths rather than typed contracts.
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

    # Compat seam detection — this is a FYSIOLOGICAL state, not a mismatch
    # It indicates we are using legacy compat paths instead of typed contracts
    # compat_seams are reported separately in PreDecisionSummary
    # and do NOT appear as blockers in the diff taxonomy

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

    Rule: UNKNOWN stability facts go to unknowns (not blockers).
    Only STABLE-phase-conflict facts produce blockers.
    COMPAT seams are physiological, not blockers.

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

    # Fact stability breakdown — determines whether unknown readiness is a blocker
    stability = artifact.fact_stability_breakdown or {}

    # Add interpretation-based blockers — ONLY for STABLE readiness failures
    # UNKNOWN readiness → goes to unknowns, not blockers (insufficient info)
    if not lc.can_accept_work and not lc.is_terminal:
        blockers.append(f"lifecycle not ready: workflow_phase={lc.workflow_phase}")

    # Graph: unknown backend from STABLE path is blocker; from UNKNOWN/COMPAT is unknown
    if gr.readiness == "unknown":
        if stability.get("graph_summary") == "STABLE":
            blockers.append("graph backend unknown — cannot determine graph capability")
        else:
            unknowns.append("graph backend unknown — DuckPGQ may not be initialized")

    # Export: unknown from UNKNOWN handoff source is unknown, not blocker
    if er.readiness == "unknown":
        unknowns.append("export handoff not ready: sprint_id or engine unknown")

    # Model/Control: unknown from STABLE path is blocker; from UNKNOWN/COMPAT is unknown
    if mc.readiness == "unknown":
        if stability.get("model_control_facts") == "STABLE":
            blockers.append("model/control facts unknown: no tools or sources configured")
        else:
            unknowns.append("model/control facts: using legacy compat path")

    # Phase conflict is ALWAYS a blocker (structural invariant violation)
    if lc.phase_conflict:
        blockers.append(f"phase layer conflict: {lc.phase_conflict_reason}")

    # Unknowns (things we don't know but would help) — non-blocking
    if pr.readiness == "unknown":
        unknowns.append("branch decision precursor: no branch_decision_id available")
        unknowns.append("provider recommendation precursor: no provider_recommend available")

    if gr.readiness == "sparse":
        unknowns.append("graph data sparse: low node/edge count for meaningful analysis")

    if not mc.is_high_quality:
        unknowns.append(f"model/control quality: privacy={mc.privacy}, depth={mc.depth}")

    return blockers, unknowns, mismatch_reasons


def _compose_decision_gate_readiness(
    blockers: List[str],
    unknowns: List[str],
    compat_seams: List[str],
) -> DecisionGateReadiness:
    """
    Sestaví DecisionGateReadiness z blockers/unknowns/compat_seams.

    DIAGNOSTIC ONLY — tento artifact NESMÍ být použit pro skutečná
    scheduler rozhodnutí.

    Rozlišuje:
    - gate_status = "ready": žádné blockers, může proceed
    - gate_status = "blocked": hard blockers present
    - gate_status = "insufficient": insufficient facts for decision
    - gate_status = "unknown": cannot determine readiness
    """
    blocker_count = len(blockers)
    unknown_count = len(unknowns)
    compat_seam_count = len(compat_seams)

    # Determine gate status
    if blocker_count > 0:
        gate_status = "blocked"
        is_proceed_allowed = False
    elif unknown_count > 2:
        # Too many unknowns — insufficient for decision
        gate_status = "insufficient"
        is_proceed_allowed = False
    elif unknown_count > 0:
        # Some unknowns but can still proceed with caution
        gate_status = "ready"  # Proceed allowed despite unknowns
        is_proceed_allowed = True
    else:
        gate_status = "ready"
        is_proceed_allowed = True

    # Provider deferral: if we have unknowns about providers, defer activation
    defer_to_provider = any("provider" in u.lower() for u in unknowns)

    # Categorize blockers
    blocker_categories = []
    for b in blockers:
        if "phase" in b.lower() or "lifecycle" in b.lower():
            blocker_categories.append("lifecycle")
        elif "graph" in b.lower():
            blocker_categories.append("graph")
        elif "model" in b.lower() or "tool" in b.lower():
            blocker_categories.append("model_control")
        elif "export" in b.lower():
            blocker_categories.append("export")
        else:
            blocker_categories.append("unknown")

    # Categorize unknowns
    unknown_categories = []
    for u in unknowns:
        if "provider" in u.lower():
            unknown_categories.append("provider")
        elif "branch" in u.lower():
            unknown_categories.append("branch")
        elif "graph" in u.lower():
            unknown_categories.append("graph")
        elif "export" in u.lower():
            unknown_categories.append("export")
        else:
            unknown_categories.append("general")

    return DecisionGateReadiness(
        gate_status=gate_status,
        blocker_count=blocker_count,
        unknown_count=unknown_count,
        compat_seam_count=compat_seam_count,
        blocker_categories=blocker_categories,
        unknown_categories=unknown_categories,
        is_proceed_allowed=is_proceed_allowed,
        defer_to_provider=defer_to_provider,
    )


def _compose_tool_readiness_preview(
    control_mode: str,
    graph: GraphCapabilitySummary,
) -> ToolReadinessPreview:
    """
    Sestaví ToolReadinessPreview z control_phase_mode a graph readiness.

    DIAGNOSTIC ONLY — čte pouze z existujících fact bundles.
    NESMÍ volat execute_with_limits() ani provider activation.

    Read-only resource assessment based on thermal/graph hints:
    - "none": nominal conditions
    - "memory": graph is rich (high memory consumer)
    - "thermal": thermal state indicates pressure
    """
    if control_mode == "panic":
        readiness = "pruned"
        pruned_tool_count = 3  # Estimated pruned tools in panic
        can_execute = False
        defer_reason = "panic mode: tools heavily pruned"
        resource_constraint = "memory" if graph.is_rich else "thermal"
    elif control_mode == "prune":
        readiness = "degraded"
        pruned_tool_count = 1
        can_execute = True
        defer_reason = None
        resource_constraint = "memory" if graph.is_rich else "none"
    else:
        readiness = "ready"
        pruned_tool_count = 0
        can_execute = True
        defer_reason = None
        resource_constraint = "memory" if graph.is_rich else "none"

    return ToolReadinessPreview(
        readiness=readiness,
        tool_count=0,  # Filled by consumer seam from ToolRegistry
        tool_names=[],  # Filled by consumer seam from ToolRegistry
        has_network_tools=False,  # Filled by consumer seam
        has_high_memory_tools=graph.is_rich,
        control_mode=control_mode,
        pruned_tool_count=pruned_tool_count,
        resource_constraint=resource_constraint,
        can_execute=can_execute,
        defer_reason=defer_reason,
    )


def _compose_windup_readiness_preview(
    lifecycle: LifecycleInterpretation,
    export: ExportReadinessSummary,
) -> WindupReadinessPreview:
    """
    Sestaví WindupReadinessPreview z LifecycleInterpretation a ExportReadinessSummary.

    DIAGNOSTIC ONLY — z existujících fact bundles.
    NESMÍ měnit ownership, NESMÍ aktivovat windup engine.
    """
    if not lifecycle.is_windup:
        return WindupReadinessPreview(
            readiness="not_active",
            is_windup_phase=False,
            synthesis_mode=None,
            synthesis_engine=export.synthesis_engine,
            has_export_data=export.has_ranked_data or export.has_gnn_predictions,
            export_data_quality=_assess_export_quality(export),
            defer_reason="not in WINDUP phase",
        )

    # In WINDUP — assess windup readiness
    synthesis_mode = lifecycle.windup_local_mode
    has_export_data = export.has_ranked_data or export.has_gnn_predictions
    export_quality = _assess_export_quality(export)

    if export_quality == "none":
        readiness = "insufficient"
        defer_reason = "no export data available for windup synthesis"
    elif export_quality == "sparse":
        readiness = "partial"
        defer_reason = "limited export data for windup synthesis"
    else:
        readiness = "ready"
        defer_reason = None

    return WindupReadinessPreview(
        readiness=readiness,
        is_windup_phase=True,
        synthesis_mode=synthesis_mode,
        synthesis_engine=export.synthesis_engine,
        has_export_data=has_export_data,
        export_data_quality=export_quality,
        defer_reason=defer_reason,
    )


def _assess_export_quality(export: ExportReadinessSummary) -> str:
    """Assess export data quality for windup synthesis."""
    if not export.has_ranked_data and not export.has_gnn_predictions:
        return "none"
    if export.has_ranked_data and export.gnn_predictions > 0:
        return "ready"
    return "sparse"


def _compose_provider_activation_note(
    precursors: PrecursorSummary,
    lifecycle: LifecycleInterpretation,
) -> ProviderActivationNote:
    """
    Sestaví ProviderActivationNote z PrecursorSummary a LifecycleInterpretation.

    DIAGNOSTIC ONLY — deferred/unknown only.
    NESMÍ simulovat load order, NESMÍ simulovat provider state machine.
    NESMÍ vytvořit pseudo-authoritu provider plane.

    Rozlišuje:
    - status = "deferred": activation deferred to future phase
    - status = "unknown": cannot determine provider readiness
    - status = "not_ready": provider not ready
    - status = "blocked": blocked by hard constraint
    """
    # Provider activation deferred in these cases:
    # 1. Not in ACTIVE phase yet
    # 2. No provider recommendation available
    # 3. Hard constraints (lifecycle not ready)

    if lifecycle.is_terminal:
        status = "blocked"
        deferral_reason = "lifecycle in terminal phase — sprint ending"
        next_phase_hint = None
    elif not lifecycle.is_active and not lifecycle.is_windup:
        status = "deferred"
        deferral_reason = f"lifecycle phase={lifecycle.workflow_phase} — not ACTIVE or WINDUP"
        next_phase_hint = "ACTIVATE phase required"
    elif lifecycle.should_prune:
        status = "deferred"
        deferral_reason = "resource pressure — control mode=prune/panic"
        next_phase_hint = "NORMAL control mode required"
    elif not precursors.has_provider_recommend:
        status = "unknown"
        deferral_reason = "no provider_recommend available in precursors"
        next_phase_hint = "capabilities.py provider recommendation required"
    elif lifecycle.phase_conflict:
        status = "blocked"
        deferral_reason = f"phase conflict: {lifecycle.phase_conflict_reason}"
        next_phase_hint = None
    else:
        # Provider could activate but we defer to future phase
        status = "deferred"
        deferral_reason = "provider activation deferred — decision gate not yet passed"
        next_phase_hint = "DECISION_GATE_READY required"

    return ProviderActivationNote(
        status=status,
        deferral_reason=deferral_reason,
        has_recommendation=precursors.has_provider_recommend,
        recommendation=precursors.provider_recommend,
        next_phase_hint=next_phase_hint,
    )


# =============================================================================
# TYPE CHECKING imports — only used behind TYPE_CHECKING guard
# =============================================================================

if TYPE_CHECKING:
    from .shadow_parity import ParityArtifact
