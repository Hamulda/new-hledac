"""
Sprint 8VK: Shadow Scheduler Inputs Scaffold
============================================

Parity-ready scaffold pro sběr shadow inputs pro budoucí shadow scheduler.
NESAHÁ na runtime behavior — pouze scaffolding a pure functions.

Design rules:
- Pure functions, no side effects
- No scheduler dependency
- No shell mutation
- Typed contracts kde existují, compat dict kde ne

Phase systems (STRICTLY SEPARATED):
- workflow_phase: BOOT | WARMUP | ACTIVE | WINDUP | EXPORT | TEARDOWN (SprintLifecycleManager)
- control_phase: tool pruning / resource governance decisions (model/control split)
- windup_local_phase: synthesis mode within windup (structured generation)

Feature flag vocabulary (scaffold only, NOT activated):
- legacy_runtime: today's runtime path (default)
- scheduler_shadow: shadow mode, reads only
- scheduler_active: full scheduler-driven mode (future)

Inventory of shadow inputs:
1. lifecycle_snapshot   → SprintLifecycleManager.snapshot()
2. export_handoff       → ExportHandoff (typed) or scorecard dict (compat)
3. graph_summary        → duckdb_store._ioc_graph.stats() (DuckPGQGraph)
4. graph_backend_caps   → which graph backend (Kuzu vs DuckPGQ)
5. model/control_facts → AnalyzerResult / AutoResearchProfile
6. provider_recommend   → from capabilities.py registry (future)
7. branch_decision_facts → BranchDecision (typed, Sprint 8WA)
8. top_nodes_facts      → top_nodes from export handoff

Owned by: this module (shadow scaffold)
Future owners:
- lifecycle_snapshot → runtime/sprint_lifecycle.py (already there)
- export_handoff → export/COMPAT_HANDOFF.py (already there)
- graph_summary → knowledge/duckdb_store.py (duckdb_store._ioc_graph.stats())
- graph_backend_caps → knowledge/ioc_graph.py or knowledge/graph_layer.py
- model/control_facts → autonomous_analyzer.py / capabilities.py
- provider_recommend → capabilities.py CapabilityRegistry
- branch_decision_facts → types.py BranchDecision (already there)
- top_nodes_facts → export/COMPAT_HANDOFF.py (from_windup)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import os

if TYPE_CHECKING:
    from hledac.universal.types import (
        AnalyzerResult,
        ExportHandoff,
    )
    from hledac.universal.runtime.sprint_lifecycle import SprintLifecycleManager


# =============================================================================
# Feature flag vocabulary — scaffold only, NOT runtime-activated
# =============================================================================

class RuntimeMode:
    """
    Feature flag vocabulary pro budoucí scheduler režimy.

    Nikdy neaktivováno v tomto scaffoldu — pouze dokumentační.
    Aktivace půjde přes explicitní flag v config nebo env var.

    Enums:
        LEGACY_RUNTIME — dnešní runtime path (default)
        SCHEDULER_SHADOW — shadow mode, čte facts, žádné řízení
        SCHEDULER_ACTIVE — plný scheduler-driven režim (budoucí)
    """
    LEGACY_RUNTIME = "legacy_runtime"
    SCHEDULER_SHADOW = "scheduler_shadow"
    SCHEDULER_ACTIVE = "scheduler_active"

    @classmethod
    def get_current(cls) -> str:
        """
        Return current runtime mode string based on environment.

        Default: LEGACY_RUNTIME
        Shadow mode: HLEDAC_RUNTIME_MODE=scheduler_shadow
        Active mode: HLEDAC_RUNTIME_MODE=scheduler_active (future)
        """
        mode = os.getenv("HLEDAC_RUNTIME_MODE", cls.LEGACY_RUNTIME)
        if mode == cls.SCHEDULER_SHADOW:
            return cls.SCHEDULER_SHADOW
        if mode == cls.SCHEDULER_ACTIVE:
            return cls.SCHEDULER_ACTIVE
        return cls.LEGACY_RUNTIME

    @classmethod
    def is_shadow_mode(cls) -> bool:
        """True if running in scheduler shadow mode."""
        return cls.get_current() == cls.SCHEDULER_SHADOW

    @classmethod
    def is_active_mode(cls) -> bool:
        """True if running in scheduler active mode."""
        return cls.get_current() == cls.SCHEDULER_ACTIVE

    @classmethod
    def is_legacy_mode(cls) -> bool:
        """True if running in legacy runtime mode (default)."""
        return cls.get_current() == cls.LEGACY_RUNTIME
    """
    Feature flag vocabulary pro budoucí scheduler režimy.

    Nikdy neaktivováno v tomto scaffoldu — pouze dokumentační.
    Aktivace půjde přes explicitní flag v config nebo env var.
    """
    # Dnešní runtime path — scheduler volá lifecycle, lifecycle řídí fáze
    LEGACY_RUNTIME = "legacy_runtime"
    # Shadow mode — scheduler čte facts, žádné řízení
    SCHEDULER_SHADOW = "scheduler_shadow"
    # Plný scheduler-driven režim (budoucí)
    SCHEDULER_ACTIVE = "scheduler_active"


# =============================================================================
# Phase systems — STRICTLY SEPARATED, NEVER merged
# =============================================================================

@dataclass(frozen=True)
class WorkflowPhase:
    """
    Workflow phase — řídí celý sprint lifecycle.

    Canonical owner: SprintLifecycleManager (runtime/sprint_lifecycle.py)
    This scaffold only READS and packages it.
    """
    phase: str  # BOOT | WARMUP | ACTIVE | WINDUP | EXPORT | TEARDOWN
    entered_at_monotonic: Optional[float] = None
    started_at_monotonic: Optional[float] = None
    sprint_duration_s: float = 1800.0
    windup_lead_s: float = 180.0

    @classmethod
    def from_lifecycle_snapshot(cls, snap: Dict[str, Any]) -> "WorkflowPhase":
        """Extract from SprintLifecycleManager.snapshot() dict."""
        return cls(
            phase=snap.get("current_phase", "UNKNOWN"),
            entered_at_monotonic=snap.get("entered_phase_at"),
            started_at_monotonic=snap.get("started_at_monotonic"),
            sprint_duration_s=snap.get("sprint_duration_s", 1800.0),
            windup_lead_s=snap.get("windup_lead_s", 180.0),
        )


@dataclass(frozen=True)
class ControlPhase:
    """
    Control phase — tool pruning / resource governance decisions.

    Toto řídí JINOU osu než workflow_phase:
    - workflow_phase řídí kdy se co děje (BOOT→ACTIVE→WINDUP)
    - control_phase řídí jak intenzivně se to děje (normal/prune/panic)

    Canonical owner: SprintLifecycleManager.recommended_tool_mode()
    This scaffold only READS and packages it.
    """
    mode: str  # normal | prune | panic
    thermal_state: str = "nominal"  # nominal | throttled | fair | critical
    remaining_s: float = 0.0

    @classmethod
    def from_lifecycle(
        cls,
        lifecycle: "SprintLifecycleManager",
        now_monotonic: Optional[float] = None,
        thermal_state: str = "nominal",
    ) -> "ControlPhase":
        """Derive from SprintLifecycleManager.recommended_tool_mode()."""
        mode = lifecycle.recommended_tool_mode(now_monotonic, thermal_state)
        remaining = lifecycle.remaining_time(now_monotonic)
        return cls(mode=mode, thermal_state=thermal_state, remaining_s=remaining)


@dataclass(frozen=True)
class WindupLocalPhase:
    """
    Windup-local synthesis mode — special режим внутри WINDUP fáze.

    Toto je ODDĚLENÉ od workflow_phase i control_phase.
    Popisuje režim structured generation uvnitř windup:
    - synthesis: normální syntéza
    - structured: structured output režim (např. JSON schema)
    - minimal: pouze scorecard bez plné syntézy

    Canonical owner: windup_engine (runtime/windup_engine.py) — future
    Currently hardcoded in run_windup() as "synthesis" unless exception occurs.
    """
    mode: str = "synthesis"  # synthesis | structured | minimal
    error_encountered: bool = False
    synthesis_engine: str = "unknown"


# =============================================================================
# Shadow input bundles
# =============================================================================

@dataclass
class LifecycleSnapshotBundle:
    """
    Bundle všech lifecycle-related shadow inputs.

    Obsahuje workflow_phase, control_phase, windup_local_phase
    v ODDĚLENÝCH polích — NIKDY neslité do jednoho phase pole.
    """
    workflow_phase: WorkflowPhase
    control_phase: ControlPhase
    windup_local_phase: Optional[WindupLocalPhase] = None
    # Raw snapshot for compatibility
    raw_snapshot: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_phase": self.workflow_phase.phase,
            "workflow_phase_entered_at": self.workflow_phase.entered_at_monotonic,
            "workflow_phase_started_at": self.workflow_phase.started_at_monotonic,
            "control_phase_mode": self.control_phase.mode,
            "control_phase_thermal": self.control_phase.thermal_state,
            "control_phase_remaining_s": self.control_phase.remaining_s,
            "windup_local_mode": self.windup_local_phase.mode if self.windup_local_phase else None,
            "windup_local_synthesis_engine": (
                self.windup_local_phase.synthesis_engine if self.windup_local_phase else None
            ),
        }


@dataclass
class GraphSummaryBundle:
    """
    Bundle graph-related shadow inputs.

    source: duckdb_store._ioc_graph.stats() (DuckPGQGraph)
    compat source: scorecard["top_graph_nodes"]
    """
    node_count: int = 0
    edge_count: int = 0
    pgq_active: bool = False
    top_nodes: List[Any] = field(default_factory=list)  # noqa: A003
    backend: str = "unknown"  # duckpgq | kuzu | none
    raw_stats: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_ioc_graph_stats(cls, stats: Dict[str, Any], top_nodes: Optional[List[Any]] = None) -> "GraphSummaryBundle":
        """Build from DuckPGQGraph.stats() dict."""
        return cls(
            node_count=stats.get("nodes", 0),
            edge_count=stats.get("edges", 0),
            pgq_active=stats.get("pgq_active", False),
            top_nodes=top_nodes or [],
            backend="duckpgq",
            raw_stats=stats,
        )

    @classmethod
    def from_scorecard_top_nodes(cls, top_nodes: List[Any]) -> "GraphSummaryBundle":
        """Build from scorecard top_nodes (compat path)."""
        return cls(
            node_count=0,  # unknown from compat path
            edge_count=0,
            pgq_active=False,
            top_nodes=top_nodes,
            backend="unknown",
            raw_stats={},
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_nodes": self.node_count,
            "graph_edges": self.edge_count,
            "graph_pgq_active": self.pgq_active,
            "graph_backend": self.backend,
            "graph_top_nodes": self.top_nodes,
        }


@dataclass
class ModelControlFactsBundle:
    """
    Bundle model/control-related shadow inputs.

    source: AnalyzerResult (types.py)
    compat source: AutoResearchProfile (autonomous_analyzer.py) via .to_capability_signal()
    """
    tools: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    privacy_level: str = "STANDARD"
    use_tor: bool = False
    depth: str = "STANDARD"
    use_tot: bool = False
    tot_mode: str = "standard"
    models_needed: List[str] = field(default_factory=list)
    # From capability signal
    requires_embeddings: bool = False
    requires_ner: bool = False
    raw_profile: Optional[Dict[str, Any]] = None

    @classmethod
    def from_analyzer_result(cls, result: "AnalyzerResult") -> "ModelControlFactsBundle":
        """Build from AnalyzerResult (typed path)."""
        sig = result.to_capability_signal()
        return cls(
            tools=list(result.tools),
            sources=list(result.sources),
            privacy_level=result.privacy_level,
            use_tor=result.use_tor,
            depth=result.depth,
            use_tot=result.use_tot,
            tot_mode=result.tot_mode,
            models_needed=list(result.models_needed),
            requires_embeddings=sig.get("requires_embeddings", False),
            requires_ner=sig.get("requires_ner", False),
            raw_profile=sig,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mc_tools": self.tools,
            "mc_sources": self.sources,
            "mc_privacy": self.privacy_level,
            "mc_use_tor": self.use_tor,
            "mc_depth": self.depth,
            "mc_use_tot": self.use_tot,
            "mc_tot_mode": self.tot_mode,
            "mc_models_needed": self.models_needed,
            "mc_requires_embeddings": self.requires_embeddings,
            "mc_requires_ner": self.requires_ner,
        }


# =============================================================================
# Main collector function — pure, no side effects
# =============================================================================

def collect_lifecycle_snapshot(
    lifecycle: "SprintLifecycleManager",
    now_monotonic: Optional[float] = None,
    thermal_state: str = "nominal",
    windup_synthesis_mode: str = "synthesis",
    windup_error: bool = False,
    windup_engine: str = "unknown",
) -> LifecycleSnapshotBundle:
    """
    Collect all lifecycle-related shadow inputs.

    This is a PURE function — no side effects, no I/O, no scheduler dependency.

    Args:
        lifecycle: SprintLifecycleManager instance
        now_monotonic: optional fake clock for testing
        thermal_state: nominal | throttled | fair | critical
        windup_synthesis_mode: synthesis | structured | minimal
        windup_error: True if windup encountered an error
        windup_engine: synthesis engine name from windup

    Returns:
        LifecycleSnapshotBundle with SEPARATED phase fields
    """
    raw = lifecycle.snapshot()
    wf_phase = WorkflowPhase.from_lifecycle_snapshot(raw)
    ctrl_phase = ControlPhase.from_lifecycle(lifecycle, now_monotonic, thermal_state)

    windup_local = None
    if wf_phase.phase == "WINDUP":
        windup_local = WindupLocalPhase(
            mode=windup_synthesis_mode,
            error_encountered=windup_error,
            synthesis_engine=windup_engine,
        )

    return LifecycleSnapshotBundle(
        workflow_phase=wf_phase,
        control_phase=ctrl_phase,
        windup_local_phase=windup_local,
        raw_snapshot=raw,
    )


def collect_graph_summary(
    ioc_graph: Optional[Any] = None,
    scorecard: Optional[Dict[str, Any]] = None,
) -> GraphSummaryBundle:
    """
    Collect graph-related shadow inputs.

    PURE function — no side effects, no I/O.

    Args:
        ioc_graph: DuckPGQGraph instance (duckdb_store._ioc_graph) or None
        scorecard: scorecard dict (compat path) or None

    Returns:
        GraphSummaryBundle
    """
    # Primary path: DuckPGQGraph stats
    if ioc_graph is not None:
        try:
            stats = ioc_graph.stats()
            top = []
            try:
                top = ioc_graph.get_top_nodes_by_degree(n=10) or []
            except Exception:
                pass
            return GraphSummaryBundle.from_ioc_graph_stats(stats, top)
        except Exception:
            pass

    # Compat path: scorecard top_graph_nodes
    if scorecard is not None:
        top_nodes = scorecard.get("top_graph_nodes", [])
        if top_nodes:
            return GraphSummaryBundle.from_scorecard_top_nodes(top_nodes)

    return GraphSummaryBundle()


def collect_model_control_facts(
    analyzer_result: Optional["AnalyzerResult"] = None,
    raw_profile: Optional[Dict[str, Any]] = None,
) -> ModelControlFactsBundle:
    """
    Collect model/control-related shadow inputs.

    PURE function.

    Args:
        analyzer_result: AnalyzerResult (typed path) or None
        raw_profile: AutoResearchProfile.asdict() (compat path) or None

    Returns:
        ModelControlFactsBundle
    """
    if analyzer_result is not None:
        return ModelControlFactsBundle.from_analyzer_result(analyzer_result)

    if raw_profile is not None:
        return ModelControlFactsBundle(
            tools=raw_profile.get("tools", []),
            sources=raw_profile.get("sources", []),
            privacy_level=raw_profile.get("privacy_level", "STANDARD"),
            use_tor=raw_profile.get("use_tor", False),
            depth=raw_profile.get("depth", "STANDARD"),
            use_tot=raw_profile.get("use_tot", False),
            tot_mode=raw_profile.get("tot_mode", "standard"),
            models_needed=raw_profile.get("models_needed", []),
            raw_profile=raw_profile,
        )

    return ModelControlFactsBundle()


def collect_export_handoff_facts(
    handoff: Optional["ExportHandoff"] = None,
    scorecard: Optional[Dict[str, Any]] = None,
    sprint_id: str = "unknown",
) -> Dict[str, Any]:
    """
    Collect export handoff facts.

    PURE function — thin wrapper around existing typed/contract.

    Returns a dict with keys:
        - sprint_id
        - synthesis_engine
        - gnn_predictions
        - top_nodes_count
        - ranked_parquet_present
        - phase_durations
    """
    if handoff is not None:
        return {
            "sprint_id": handoff.sprint_id,
            "synthesis_engine": handoff.synthesis_engine,
            "gnn_predictions": handoff.gnn_predictions,
            "top_nodes_count": len(handoff.top_nodes),
            "ranked_parquet_present": handoff.ranked_parquet is not None,
            "phase_durations": handoff.phase_durations,
        }

    if scorecard is not None:
        return {
            "sprint_id": scorecard.get("sprint_id", sprint_id),
            "synthesis_engine": scorecard.get("synthesis_engine_used", "unknown"),
            "gnn_predictions": scorecard.get("gnn_predicted_links", 0),
            "top_nodes_count": len(scorecard.get("top_graph_nodes", [])),
            "ranked_parquet_present": scorecard.get("ranked_parquet") is not None,
            "phase_durations": scorecard.get("phase_duration_seconds", {}),
        }

    return {
        "sprint_id": sprint_id,
        "synthesis_engine": "unknown",
        "gnn_predictions": 0,
        "top_nodes_count": 0,
        "ranked_parquet_present": False,
        "phase_durations": {},
    }
