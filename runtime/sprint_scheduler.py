"""
Sprint 8BK — Tier-Aware Feed Sprint Scheduler V1.

Sidecar over SprintLifecycleManager (8BI). Operational backbone for
30-minute bounded sprint runs.

Tier ordering (high → low priority):
  surface → structured_ti → deep → archive → other

Key invariants:
- Wind-down respected: no new work after lifecycle says WINDUP
- In-sprint dedup: same entry_hash never processed twice in one sprint
- Lifecycle is authority for time and phase transitions
- Export always runs on teardown (zero-signal too)
- No background threads; TaskGroup for owned concurrency
"""

from __future__ import annotations

import asyncio
import logging
import struct
import time as _time
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Optional, Sequence

from hledac.universal.patterns.pattern_matcher import match_text
from hledac.universal.runtime.sprint_lifecycle import SprintLifecycleManager, SprintPhase
from hledac.universal.runtime.shadow_inputs import (
    collect_lifecycle_snapshot,
    collect_graph_summary,
    collect_model_control_facts,
)
from hledac.universal.runtime.shadow_parity import run_shadow_parity
from hledac.universal.runtime.shadow_pre_decision import compose_pre_decision

if TYPE_CHECKING:
    pass

import lmdb
import xxhash

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifecycle Adapter — bridges utils/ vs runtime/ sprint_lifecycle API
# ---------------------------------------------------------------------------
# Runtime version (hledac.universal.runtime.sprint_lifecycle):
#   start(), tick(), remaining_time(), is_terminal(),
#   should_enter_windup(), _current_phase, recommended_tool_mode(),
#   request_abort(), _abort_requested, _abort_reason
#
# Old utils version (hledac.universal.utils.sprint_lifecycle):
#   begin_sprint(), is_active, remaining_time, state, is_windup_phase()
#
# Scheduler always calls the runtime API. Adapter is a no-op shim for
# any caller that passes the old utils-style object.
# ---------------------------------------------------------------------------

class _LifecycleAdapter:
    """
    Normalizes lifecycle API differences between runtime/ and utils/ versions.

    runtime/sprint_lifecycle: start(), tick(), remaining_time(),
        is_terminal(), should_enter_windup(), _current_phase,
        recommended_tool_mode(), request_abort(), _abort_requested

    Adapter ensures begin_sprint() on any lifecycle object maps to start()
    for runtime objects, and bridges property vs method access patterns.
    """

    __slots__ = ("_lc",)

    def __init__(self, lifecycle: Any) -> None:
        self._lc = lifecycle

    # ── start / begin_sprint ───────────────────────────────────────────────

    def start(self) -> None:
        """runtime: start() — transitions BOOT→WARMUP."""
        lc = self._lc
        if hasattr(lc, "start"):
            lc.start()
        elif hasattr(lc, "begin_sprint"):
            lc.begin_sprint()

    # ── tick ──────────────────────────────────────────────────────────────

    def tick(self, now_monotonic: Optional[float] = None):
        """runtime: tick() returns SprintPhase. Fallback: remaining_time."""
        lc = self._lc
        if hasattr(lc, "tick"):
            return lc.tick(now_monotonic)
        # Fallback: return elapsed as float
        remaining = self.remaining_time(now_monotonic)
        return remaining

    # ── remaining_time ───────────────────────────────────────────────────

    def remaining_time(self, now_monotonic: Optional[float] = None) -> float:
        """runtime: remaining_time(). utils: remaining_time property."""
        lc = self._lc
        if hasattr(lc, "remaining_time"):
            val = lc.remaining_time
            return float(val() if callable(val) else val)
        return 0.0

    # ── is_terminal ──────────────────────────────────────────────────────

    def is_terminal(self) -> bool:
        """runtime: is_terminal(). Returns True when phase is TEARDOWN."""
        lc = self._lc
        if hasattr(lc, "is_terminal"):
            val = lc.is_terminal
            return bool(val() if callable(val) else val)
        # Fallback: check phase name
        phase = self._current_phase
        return phase == "TEARDOWN"

    # ── should_enter_windup ──────────────────────────────────────────────

    def should_enter_windup(self, now_monotonic: Optional[float] = None) -> bool:
        """runtime: should_enter_windup(). utils: is_windup_phase()."""
        lc = self._lc
        if hasattr(lc, "should_enter_windup"):
            val = lc.should_enter_windup
            return bool(val(now_monotonic) if callable(val) else val)
        if hasattr(lc, "is_windup_phase"):
            val = lc.is_windup_phase
            return bool(val() if callable(val) else val)
        return False

    # ── _current_phase ───────────────────────────────────────────────────

    @property
    def _current_phase(self) -> str:
        """runtime: _current_phase (SprintPhase enum). utils: state (SprintLifecycleState)."""
        lc = self._lc
        for attr in ("_current_phase", "phase", "state", "current_phase"):
            if hasattr(lc, attr):
                val = getattr(lc, attr)
                v = val() if callable(val) else val
                return str(v.name if hasattr(v, "name") else v)
        return "UNKNOWN"

    # ── recommended_tool_mode ────────────────────────────────────────────

    def recommended_tool_mode(self, now_monotonic: Optional[float] = None) -> str:
        """runtime: recommended_tool_mode(). Returns 'normal'/'prune'/'panic'."""
        lc = self._lc
        if hasattr(lc, "recommended_tool_mode"):
            val = lc.recommended_tool_mode
            return str(val(now_monotonic) if callable(val) else val)
        return "normal"

    # ── request_abort ────────────────────────────────────────────────────

    def request_abort(self, reason: str = "") -> None:
        """runtime: request_abort(reason)."""
        lc = self._lc
        if hasattr(lc, "request_abort"):
            lc.request_abort(reason)
        elif hasattr(lc, "_abort_requested"):
            lc._abort_requested = True
            if hasattr(lc, "_abort_reason"):
                lc._abort_reason = reason

    # ── _abort_requested ─────────────────────────────────────────────────

    @property
    def _abort_requested(self) -> bool:
        lc = self._lc
        if hasattr(lc, "_abort_requested"):
            val = lc._abort_requested
            return bool(val() if callable(val) else val)
        return False

    @property
    def _abort_reason(self) -> str:
        lc = self._lc
        if hasattr(lc, "_abort_reason"):
            val = lc._abort_reason
            return str(val() if callable(val) else val)
        return ""


# ---------------------------------------------------------------------------
# Source tier
# ---------------------------------------------------------------------------

class SourceTier(Enum):
    """Feed source priority tier."""
    SURFACE = auto()       # high-value real-time feeds (news, alerts)
    STRUCTURED_TI = auto() # structured threat intel feeds
    DEEP = auto()          # deep/dark web, archive feeds
    ARCHIVE = auto()        # historical/wayback/archive feeds
    OTHER = auto()         # everything else — processed only if time allows


_TIER_ORDER = [
    SourceTier.SURFACE,
    SourceTier.STRUCTURED_TI,
    SourceTier.DEEP,
    SourceTier.ARCHIVE,
    SourceTier.OTHER,
]

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SprintSchedulerConfig:
    """Configuration for one sprint run."""
    sprint_duration_s: float = 1800.0          # 30 min
    windup_lead_s: float = 180.0              # enter wind-down 3 min before end
    cycle_sleep_s: float = 5.0                 # sleep between cycles
    max_cycles: int = 100                      # safety cap
    max_parallel_sources: int = 4              # concurrent source fetches
    stop_on_first_accepted: bool = False       # early exit on first accepted
    export_enabled: bool = True
    export_dir: str = ""
    max_entries_per_cycle: int = 50             # per-source cap
    # Tier budgets in seconds — only enforced approximately via cycle limits
    # Sources NOT listed here fall to OTHER tier
    source_tier_map: dict[str, SourceTier] = field(default_factory=dict)

    def tier_of(self, source: str) -> SourceTier:
        return self.source_tier_map.get(source, SourceTier.OTHER)

    def sorted_tiers(self) -> list[SourceTier]:
        return _TIER_ORDER.copy()


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class SprintSchedulerResult:
    """Outcome of one sprint run."""
    cycles_started: int = 0
    cycles_completed: int = 0
    unique_entry_hashes_seen: int = 0
    duplicate_entry_hashes_skipped: int = 0
    total_pattern_hits: int = 0
    accepted_findings: int = 0
    entries_per_source: dict[str, int] = field(default_factory=dict)
    hits_per_source: dict[str, int] = field(default_factory=dict)
    final_phase: str = "BOOT"
    export_paths: list[str] = field(default_factory=list)
    aborted: bool = False
    abort_reason: str = ""
    stop_requested: bool = False  # True when stop_on_first_accepted triggered


# ---------------------------------------------------------------------------
# Source work item
# ---------------------------------------------------------------------------

@dataclass
class SourceWork:
    """A single source fetch unit."""
    feed_url: str
    source: str  # tier key
    tier: SourceTier
    max_entries: int = 50


# ---------------------------------------------------------------------------
# Live-feed pipeline seam (lazy import to avoid heavy cold-import cost)
# ---------------------------------------------------------------------------

def _import_live_feed_pipeline():
    from hledac.universal.pipeline.live_feed_pipeline import (
        async_run_live_feed_pipeline,
        FeedPipelineRunResult,
    )
    return async_run_live_feed_pipeline, FeedPipelineRunResult


# ---------------------------------------------------------------------------
# Exporter seam (lazy import)
# ---------------------------------------------------------------------------

def _import_exporters():
    from hledac.universal.export import (
        render_diagnostic_markdown_to_path,
        render_jsonld_to_path,
        render_stix_bundle_to_path,
    )
    return render_diagnostic_markdown_to_path, render_jsonld_to_path, render_stix_bundle_to_path


# ---------------------------------------------------------------------------
# Sprint Scheduler
# ---------------------------------------------------------------------------

# Sprint 8TB: Agentic Pivot Loop
@dataclass(order=True)
class PivotTask:
    """Pivot task pro agentic pivot loop — prioritizován podle confidence × degree."""
    priority: float                    # negace → max-heap: -(confidence × degree)
    ioc_type: str = field(compare=False)
    ioc_value: str = field(compare=False)
    task_type: str = field(compare=False)  # "cve_to_github" | "ip_to_ct" | "domain_to_dns" | "hash_to_mb"

# Sprint 8RA: Persistent cross-sprint dedup via LMDB
_DEDUP_LMDB_NAME = "sprint_dedup.lmdb"

def _get_dedup_lmdb_path() -> Path:
    from hledac.universal.paths import LMDB_ROOT
    return LMDB_ROOT / _DEDUP_LMDB_NAME


class SprintScheduler:
    """
    Tier-aware sprint scheduler sidecar.

    Runs bounded feed-fetch cycles under a SprintLifecycleManager.
    Does NOT own the lifecycle — lifecycle is passed in and owned by caller.
    """

    def __init__(self, config: SprintSchedulerConfig) -> None:
        self._config = config
        # In-sprint dedup: entry_hash → True
        self._seen_hashes: dict[str, bool] = {}
        # Per-source counters
        self._entries_per_source: dict[str, int] = {}
        self._hits_per_source: dict[str, int] = {}
        # Result accumulators
        self._result = SprintSchedulerResult()
        # Cancellation flag
        self._stop_requested = False
        # Sprint 8RA: Store lifecycle reference for UMA callbacks
        self._lifecycle = None
        # Sprint 8SA: Lifecycle adapter — normalizes runtime/ vs utils/ API
        self._lc_adapter: Optional[_LifecycleAdapter] = None
        # Sprint 8RA: Persistent cross-sprint dedup
        self._dedup_env: Optional[lmdb.Environment] = None
        self._dedup_seen: set[str] = set()  # in-memory cache for fast lookup
        self._dedup_dirty: bool = False  # True if _dedup_seen has un-flushed entries
        # Sprint 8RC: IOC-aware scoring state
        self._source_weights: dict[str, float] = {}  # source_type → hit_rate multiplier
        self._novelty_bonuses: dict[str, float] = {}  # source_type → novelty multiplier
        # Sprint 8TB: Agentic Pivot Loop state
        self._pivot_queue: asyncio.PriorityQueue[PivotTask] = asyncio.PriorityQueue(maxsize=200)
        self._pivot_stats: dict[str, int] = {"total": 0, "processed": 0, "errors": 0}
        self._pivot_ioc_graph: Any = None  # IOCGraph reference injected via inject_ioc_graph
        # Sprint 8UC B.4: Speculative prefetch
        self._bg_tasks: set[asyncio.Task] = set()
        self._speculative_results: dict[str, object] = {}
        self._last_speculative: float = 0.0
        # Sprint 8UC B.5: OODA loop
        self._ooda_interval: float = 60.0
        self._last_ooda: float = 0.0
        # Sprint 8VB: Adaptive timeout EMA
        self._fetch_latency_ema: dict[str, float] = {}
        _EMA_ALPHA: float = 0.3
        _TIMEOUT_MIN: float = 5.0
        _TIMEOUT_MAX: float = 30.0
        _TIMEOUT_MULT: float = 3.0
        # Sprint 8VD §B: Arrow columnar buffer
        self._arrow_batch: list[dict] = []
        self._arrow_last_flush: float = 0.0
        self._duckdb_read_con: Optional[Any] = None
        self._ARROW_FLUSH_N: int = 1000
        self._ARROW_FLUSH_S: float = 60.0
        self._fetch_semaphore: asyncio.Semaphore = asyncio.Semaphore(20)
        self.sprint_id: str = ""
        # Sprint 8VD §F: Scorecard tracking
        self._finding_count: int = 0
        self._synthesis_engine: str = "unknown"
        # Sprint 8VI §B: RL adaptive pivot — task_type → reward history
        self._pivot_rewards: dict[str, list[float]] = {}
        # Sprint 8VI §C: Recent IOC ring buffer for hypothesis feedback
        self._recent_iocs: list[dict] = []
        # Sprint 8VI §D: IOCScorer reference (set during WARMUP)
        self._ioc_scorer: Any = None
        # Sprint 8VI §D: DuckPGQGraph reference (set during WARMUP)
        self._ioc_graph: Any = None
        # Sprint 8VI §C: All findings collected during sprint
        self._all_findings: list[dict] = []
        # Sprint 8VM: Shadow pre-decision consumer — read-only, no mutable state
        self._shadow_pd_summary: Any = None
        # Sprint 8VQ: Advisory gate snapshot — ephemeral, computed at WINDUP entry, diagnostic only
        self._advisory_gate_snapshot: Any = None

    # ── Sprint 8VI §B: RL Adaptive Pivot ────────────────────────────────

    def record_pivot_outcome(
        self, task_type: str, found_count: int, elapsed_s: float
    ) -> None:
        """
        Zaznamenej výsledek pivot tasku jako reward signal pro RL.
        reward = findings per second (FPS) — normalizovaný na [0, 1].
        """
        import math
        if elapsed_s <= 0:
            return
        fps = found_count / elapsed_s
        # log1p pro sub-lineární scaling, max 1.0
        reward = min(1.0, math.log1p(fps) / math.log1p(10))
        history = self._pivot_rewards.setdefault(task_type, [])
        history.append(reward)
        # Udržuj pouze posledních 20 epizod
        if len(history) > 20:
            self._pivot_rewards[task_type] = history[-20:]

    def _get_adaptive_priority(
        self, task_type: str, base_priority: float = 0.5
    ) -> float:
        """
        Vrátí EMA reward jako priority modifikátor.
        Task types s vyšší historickou yield dostávají vyšší prioritu.
        """
        history = self._pivot_rewards.get(task_type, [])
        if not history:
            return base_priority
        # EMA with alpha=0.3 (recent weighted)
        ema = history[0]
        for r in history[1:]:
            ema = 0.3 * r + 0.7 * ema
        # Mix: 70% EMA reward + 30% base priority
        return round(0.7 * ema + 0.3 * base_priority, 4)

    # ── Public API ─────────────────────────────────────────────────────────

    async def run(
        self,
        lifecycle: Any,
        sources: Sequence[str],
        now_monotonic: Optional[float] = None,
    ) -> SprintSchedulerResult:
        """
        Run the sprint to completion.

        Args:
            lifecycle: SprintLifecycleManager instance (owned by caller)
            sources: ordered list of feed URLs to process
            now_monotonic: optional fake clock for testing

        Returns:
            SprintSchedulerResult with final statistics
        """
        # Sprint 8SA: Lifecycle adapter — bridges runtime/ vs utils/ API
        adapter = _LifecycleAdapter(lifecycle)
        # Start lifecycle via adapter (runtime: start(), utils: begin_sprint())
        adapter.start()
        self._reset_result()

        # Sprint 8VD: Set sprint_id from lifecycle if available
        try:
            self.sprint_id = getattr(lifecycle, "sprint_id", "") or ""
        except Exception:
            self.sprint_id = ""

        # Sprint 8RA: Store lifecycle ref for callbacks
        self._lifecycle = lifecycle
        # Sprint 8SA: Store adapter for all lifecycle access in this run
        self._lc_adapter = adapter

        # Initial tick to enter ACTIVE
        phase = adapter.tick(now_monotonic)

        # Sprint 8UA: Fix lifecycle WARMUP→ACTIVE transition
        # start() goes BOOT→WARMUP; tick() does NOT auto-advance to ACTIVE.
        # Manually transition WARMUP→ACTIVE to unstick the scheduler.
        phase_str = str(phase)
        if phase_str == "SprintPhase.WARMUP" or phase_str.endswith(".WARMUP"):
            try:
                from hledac.universal.runtime.sprint_lifecycle import SprintPhase as _SP
                adapter._lc.transition_to(_SP.ACTIVE)
            except Exception:
                pass  # Let scheduler handle - will likely be stuck but won't crash

        # Sprint 8RA: Load persistent dedup at BOOT
        await self._load_dedup()

        # Sprint 8SA: Source scoring — order sources by priority at start of ACTIVE
        _DEFAULT_SOURCE_TYPES = [
            "cisa_kev", "threatfox_ioc", "urlhaus_recent",
            "feodo_ip", "openphish_feed",
        ]
        _graph_stats: dict[str, int] = {"nodes": 0, "edges": 0}
        ordered_sources = self.prioritize_sources(
            list(sources) if sources else _DEFAULT_SOURCE_TYPES, _graph_stats
        )

        try:
            # Sprint 8VD §C: Start memory pressure monitoring loop
            _t = asyncio.create_task(self._memory_pressure_loop())
            self._bg_tasks.add(_t)
            _t.add_done_callback(self._bg_tasks.discard)

            while not adapter.is_terminal():
                if self._stop_requested:
                    break
                # Detect abort requested via lifecycle flag
                if adapter._abort_requested:
                    self._result.aborted = True
                    self._result.abort_reason = adapter._abort_reason or "lifecycle_abort"
                    break

                # Periodic tick
                phase = adapter.tick(now_monotonic)

                # ── Wind-down guard ────────────────────────────────────────
                if adapter.should_enter_windup(now_monotonic):
                    if phase != adapter._current_phase:
                        phase = adapter._current_phase
                    # Sprint 8RA: Flush dedup at WINDUP entry
                    await self._flush_dedup()
                    # Sprint 8VQ: Evaluate advisory gate at WINDUP entry (diagnostic only)
                    self.evaluate_advisory_gate()
                    break  # exit work loop → teardown

                # ── Sprint 8SA: Source scoring re-ordering ───────────────────
                # Re-prioritize at the start of each ACTIVE cycle using latest graph stats
                current_phase_str = adapter._current_phase
                if current_phase_str == "ACTIVE":
                    ordered_sources = self.prioritize_sources(
                        ordered_sources, _graph_stats
                    )

                # ── Run one cycle ───────────────────────────────────────────
                # Enforce max_cycles BEFORE starting new work
                if self._result.cycles_started >= self._config.max_cycles:
                    break

                self._result.cycles_started += 1
                cycle_ok = await self._run_one_cycle(
                    lifecycle, ordered_sources, now_monotonic
                )
                self._result.cycles_completed += 1

                # Sprint 8TB: Drain pivot queue after each ACTIVE cycle
                if current_phase_str == "ACTIVE":
                    pivot_n = await self._drain_pivot_queue()
                    if pivot_n:
                        log.debug(f"Pivot queue drained: {pivot_n} tasks, stats={self._pivot_stats}")

                if not cycle_ok:
                    break

                # Early exit check
                if (
                    self._config.stop_on_first_accepted
                    and self._result.accepted_findings > 0
                ):
                    self._result.stop_requested = True
                    break

                # Sleep between cycles (short interval, not one long sleep)
                await self._sleep_or_abort(self._config.cycle_sleep_s, adapter)

                # Sprint 8UC B.4: Speculative prefetch every 15s
                now_mono = _time.monotonic()
                if (now_mono - self._last_speculative) >= 15.0:
                    _t = asyncio.create_task(self._speculative_prefetch(None, n=3))
                    self._bg_tasks.add(_t)
                    _t.add_done_callback(self._bg_tasks.discard)
                    self._last_speculative = now_mono

                # Sprint 8UC B.5: OODA cycle every 60s
                if (now_mono - self._last_ooda) >= self._ooda_interval:
                    _t = asyncio.create_task(self._run_ooda_cycle(self._pivot_ioc_graph, None))
                    self._bg_tasks.add(_t)
                    _t.add_done_callback(self._bg_tasks.discard)
                    self._last_ooda = now_mono

        except Exception as exc:
            adapter.request_abort(f"scheduler_exception:{type(exc).__name__}")
            self._result.aborted = True
            self._result.abort_reason = f"{type(exc).__name__}"

        # ── Teardown / Export ───────────────────────────────────────────────
        # _final_phase and _run_export need raw lifecycle (mark_export_started, etc.)
        self._final_phase(lifecycle)
        if self._config.export_enabled:
            await self._run_export(lifecycle)

        self._result.final_phase = adapter._current_phase

        # Sprint 8RA: Close persistent dedup at TEARDOWN
        await self._close_dedup()

        # Sprint 8UC B.4: Cancel all background speculative tasks
        for t in list(self._bg_tasks):
            t.cancel()
        if self._bg_tasks:
            await asyncio.gather(*self._bg_tasks, return_exceptions=True)
        self._bg_tasks.clear()

        return self._result

    # ── Cycle logic ────────────────────────────────────────────────────────

    async def _run_one_cycle(
        self,
        lifecycle,
        sources: Sequence[str],
        now_monotonic: Optional[float] = None,
    ) -> bool:
        """
        Run one bounded fetch cycle across all sources, tier-ordered.
        Returns False when lifecycle says stop; True otherwise.
        """
        self._result.cycles_started += 1

        async_run_live_feed, FeedPipelineRunResult = _import_live_feed_pipeline()

        # Build tiered work list
        work_items = self._build_work_items(sources)

        # Filter: skip lower tiers if lifecycle is pruning
        mode = lifecycle.recommended_tool_mode(now_monotonic)
        if mode == "prune":
            work_items = self._prune_work_items(work_items)
        elif mode == "panic":
            work_items = [w for w in work_items if w.tier == SourceTier.SURFACE]

        if not work_items:
            return True  # nothing to do this cycle

        # Run sources under TaskGroup (bounded concurrency)
        semaphore = asyncio.Semaphore(self._config.max_parallel_sources)

        async def fetch_one(work: SourceWork) -> tuple[str, FeedPipelineRunResult]:
            async with semaphore:
                try:
                    result = await asyncio.wait_for(
                        async_run_live_feed(
                            feed_url=work.feed_url,
                            max_entries=work.max_entries,
                        ),
                        timeout=30.0,
                    )
                    return work.feed_url, result
                except asyncio.TimeoutError:
                    return work.feed_url, FeedPipelineRunResult(
                        feed_url=work.feed_url,
                        fetched_entries=0,
                        accepted_findings=0,
                        stored_findings=0,
                        patterns_configured=0,
                        matched_patterns=0,
                        pages=(),
                        error="timeout",
                    )
                except Exception as exc:
                    return work.feed_url, FeedPipelineRunResult(
                        feed_url=work.feed_url,
                        fetched_entries=0,
                        accepted_findings=0,
                        stored_findings=0,
                        patterns_configured=0,
                        matched_patterns=0,
                        pages=(),
                        error=f"exception:{type(exc).__name__}:{exc}",
                    )

        # Execute all source fetches concurrently
        tasks = [fetch_one(w) for w in work_items]
        results: list[tuple[str, FeedPipelineRunResult]] = await asyncio.gather(*tasks)

        # Process results
        for feed_url, result in results:
            self._process_result(feed_url, result)

        return True

    def _build_work_items(
        self, sources: Sequence[str]
    ) -> list[SourceWork]:
        """Build and tier-sort work items from source list."""
        items = []
        for url in sources:
            tier = self._config.tier_of(url)
            items.append(SourceWork(
                feed_url=url,
                source=url,
                tier=tier,
                max_entries=self._config.max_entries_per_cycle,
            ))
        # Sort: high tier first
        items.sort(key=lambda w: _TIER_ORDER.index(w.tier))
        return items

    def _prune_work_items(
        self, items: list[SourceWork]
    ) -> list[SourceWork]:
        """Drop ARCHIVE and OTHER tier items when in prune mode."""
        return [w for w in items if w.tier not in (SourceTier.ARCHIVE, SourceTier.OTHER)]

    def _process_result(self, feed_url: str, result) -> None:
        """Accumulate result stats and dedup."""
        # Accumulate per-source stats
        self._entries_per_source[feed_url] = (
            self._entries_per_source.get(feed_url, 0) + result.fetched_entries
        )
        self._hits_per_source[feed_url] = (
            self._hits_per_source.get(feed_url, 0) + result.matched_patterns
        )
        # Also update _result directly so it's available even without _build_diagnostic_report
        self._result.entries_per_source[feed_url] = self._entries_per_source[feed_url]
        self._result.hits_per_source[feed_url] = self._hits_per_source[feed_url]
        self._result.total_pattern_hits += result.matched_patterns
        self._result.accepted_findings += result.accepted_findings
        # Sprint 8VD §F: Track finding count for scorecard
        self._finding_count += result.accepted_findings

    # ── Dedup ─────────────────────────────────────────────────────────────

    # ── Persistent dedup (Sprint 8RA) ───────────────────────────────────

    async def _load_dedup(self) -> None:
        """Load existing hashes from LMDB at BOOT. Idempotent."""
        db_path = _get_dedup_lmdb_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._dedup_env = lmdb.open(
                str(db_path),
                map_size=100 * 1024 * 1024,  # 100MB max
                max_dbs=1,
            )
            with self._dedup_env.begin() as txn:
                cursor = txn.cursor()
                count = 0
                for key, _ in cursor:
                    self._dedup_seen.add(key.decode())
                    count += 1
            # Sprint 8RA: Bound dedup set to prevent unbounded growth
            if len(self._dedup_seen) > 500_000:
                # Trim to 400k to leave headroom
                excess = list(self._dedup_seen)
                self._dedup_seen = set(excess[-400_000:])
                log.warning(f"Dedup set trimmed to 400k entries (was {count})")
            log.info(f"Dedup LMDB loaded: {count} existing hashes")
        except Exception as exc:
            log.warning(f"Dedup LMDB open failed: {exc} — continuing without persistence")
            self._dedup_env = None

    async def _flush_dedup(self) -> None:
        """Flush in-memory hashes to LMDB. Called at WINDUP."""
        if self._dedup_env is None or not self._dedup_seen:
            return
        try:
            ts_bytes = struct.pack("d", _time.time())
            with self._dedup_env.begin(write=True) as txn:
                for key in self._dedup_seen:
                    txn.put(key.encode(), ts_bytes, overwrite=True)
            log.info(f"Dedup flushed: {len(self._dedup_seen)} hashes")
        except Exception as exc:
            log.warning(f"Dedup flush failed: {exc}")

    async def _close_dedup(self) -> None:
        """Close LMDB at TEARDOWN. Calls flush first."""
        await self._flush_dedup()
        if self._dedup_env is not None:
            try:
                self._dedup_env.close()
            except Exception as exc:
                log.warning(f"Dedup LMDB close failed: {exc}")
            self._dedup_env = None
        # Sprint 8RA: Close DuckDB read connection
        if self._duckdb_read_con is not None:
            try:
                self._duckdb_read_con.close()
            except Exception:
                pass
            self._duckdb_read_con = None

    def is_duplicate(self, source_type: str, url: str, title: str = "") -> bool:
        """Check if (source_type, url, title) was already seen in any sprint."""
        if self._dedup_env is None:
            return False
        key = xxhash.xxh64(f"{source_type}:{url}:{title}".encode()).hexdigest()
        return key in self._dedup_seen

    def mark_seen(self, source_type: str, url: str, title: str = "",
                  sprint_id: str = "") -> None:
        """Mark a finding as seen. Flush happens at WINDUP."""
        if self._dedup_env is None:
            return
        key = xxhash.xxh64(f"{source_type}:{url}:{title}".encode()).hexdigest()
        self._dedup_seen.add(key)
        self._dedup_dirty = True

    def request_early_windup(self) -> None:
        """Sprint 8RA: Request early wind-down (called from UMA CRITICAL callback)."""
        # Trigger lifecycle windup if available
        if hasattr(self, '_lifecycle') and self._lifecycle is not None:
            self._lifecycle.request_windup()
        else:
            # Fallback: set stop flag to exit at next cycle
            self._stop_requested = True

    def request_immediate_abort(self) -> None:
        """Sprint 8RA: Request immediate abort (called from UMA EMERGENCY callback)."""
        self._stop_requested = True
        self._result.aborted = True
        self._result.abort_reason = "uma_emergency"
        if hasattr(self, '_lifecycle') and self._lifecycle is not None:
            self._lifecycle.request_abort("uma_emergency")

    def is_new_entry(self, entry_hash: str) -> bool:
        """Return True if entry_hash has not been seen in this sprint."""
        if not entry_hash:
            return True  # empty hash = always new (backwards compat)
        if entry_hash in self._seen_hashes:
            self._result.duplicate_entry_hashes_skipped += 1
            return False
        self._seen_hashes[entry_hash] = True
        self._result.unique_entry_hashes_seen += 1
        return True

    # ── Lifecycle helpers ──────────────────────────────────────────────────

    async def _sleep_or_abort(self, seconds: float, adapter: _LifecycleAdapter) -> None:
        """
        Sleep in short chunks so wind-down can be detected promptly.
        Calls adapter.tick() during sleep to advance phase machine.
        """
        elapsed = 0.0
        step = min(seconds, 1.0)
        while elapsed < seconds:
            await asyncio.sleep(step)
            elapsed += step
            # Advance lifecycle phase machine via adapter
            adapter.tick()
            # Check abort frequently
            if adapter._abort_requested or adapter.is_terminal():
                return

    def _final_phase(self, lifecycle) -> None:
        """Mark teardown on lifecycle."""
        try:
            if lifecycle._current_phase == lifecycle._current_phase.WINDUP:
                lifecycle.mark_export_started()
                lifecycle.mark_teardown_started()
            elif lifecycle._current_phase not in (
                lifecycle._current_phase.EXPORT,
                lifecycle._current_phase.TEARDOWN,
            ):
                lifecycle.request_abort("scheduler_final_phase")
                lifecycle.mark_teardown_started()
        except Exception:
            pass  # teardown is best-effort

    # ── Export ────────────────────────────────────────────────────────────

    async def _run_export(self, lifecycle) -> None:
        """Run all three exporters; failure is fail-soft."""
        rend_md, rend_jsonld, rend_stix = _import_exporters()

        # Build minimal diagnostic report from result
        report = self._build_diagnostic_report(lifecycle)

        export_dir = self._config.export_dir

        for render_fn, suffix in [
            (rend_md, "md"),
            (rend_jsonld, "jsonld"),
            (rend_stix, "stix.json"),
        ]:
            try:
                path = render_fn(report, export_dir or None)
                self._result.export_paths.append(str(path))
            except Exception as exc:
                # Fail-soft: export error must not prevent teardown
                # but we still record it
                self._result.export_paths.append(f"EXPORT_ERROR:{suffix}:{exc}")

    def _build_diagnostic_report(self, lifecycle) -> dict:
        """Build a diagnostic report dict for exporters."""
        report = {
            "run_id": f"8bk_sprint_{int(_time.time())}",
            "phase": lifecycle._current_phase.name,
            "cycles_started": self._result.cycles_started,
            "cycles_completed": self._result.cycles_completed,
            "unique_entry_hashes": self._result.unique_entry_hashes_seen,
            "duplicates_skipped": self._result.duplicate_entry_hashes_skipped,
            "pattern_hits": self._result.total_pattern_hits,
            "accepted_findings": self._result.accepted_findings,
            "aborted": self._result.aborted,
            "abort_reason": self._result.abort_reason,
            "stop_requested": self._result.stop_requested,
            "lifecycle_snapshot": lifecycle.snapshot(),
            "entries_per_source": dict(self._entries_per_source),
            "hits_per_source": dict(self._hits_per_source),
        }
        # Sprint 8VM: Append shadow pre-decision readiness preview (read-only, diagnostic)
        shadow_preview = self._build_shadow_readiness_preview()
        if shadow_preview:
            report["shadow_pre_decision"] = shadow_preview
        return report

    # ── Sprint 8RC: IOC-aware prioritisation ───────────────────────────────

    # Base tier weights (B.1 invariant)
    _BASE_TIER_WEIGHTS: dict[str, float] = {
        "structured_ti": 1.0,
        "clearnet": 0.8,
        "academic": 0.6,
        "dark": 1.2,
    }

    async def load_source_weights(self, store: Any) -> None:
        """
        Load hit-rate history from DuckDB and set source weights.

        Bounds: 0.3 – 2.5 (30% floor, 250% ceiling, B.6).
        Falls back to defaults on any error.
        """
        try:
            rows = await store.async_query_sprint_source_stats()
            if not rows:
                return
            max_rate = max(r["avg_hit_rate"] for r in rows) or 1.0
            for row in rows:
                src = row["source_type"]
                raw = row["avg_hit_rate"] / max_rate * 1.5
                # B.6: ±20% per sprint cap → clamp to [0.3, 2.5]
                clipped = max(0.3, min(2.5, raw))
                self._source_weights[src] = clipped
                log.debug(f"Source weight {src}: {clipped:.2f}")
        except Exception as e:
            log.warning(f"Source weight load failed: {e} — using defaults")

    def score_source(
        self, source_type: str, ioc_graph_stats: dict | None = None
    ) -> float:
        """
        Compute priority score per B.1 formula.

        score(source) = base_tier_weight(source)
                      × hit_rate_multiplier(source)
                      × novelty_bonus(source)
        """
        base = self._BASE_TIER_WEIGHTS.get(source_type, 0.7)
        hit_mult = self._source_weights.get(source_type, 1.0)
        novelty = self._novelty_bonuses.get(source_type, 1.0)
        return base * hit_mult * novelty

    def prioritize_sources(
        self, candidates: list[str], ioc_graph_stats: dict | None = None
    ) -> list[str]:
        """
        Sort candidates by score — highest first.
        Returns list of source_type strings ordered by priority.
        """
        scored = [
            (src, self.score_source(src, ioc_graph_stats))
            for src in candidates
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        log.debug(
            f"Source priorities: {[(s, f'{sc:.2f}') for s, sc in scored[:5]]}"
        )
        return [s for s, _ in scored]

    def set_novelty_bonus(self, source_type: str, has_bonus: bool) -> None:
        """Set novelty bonus: 1.5 if source added new IOC types this sprint."""
        self._novelty_bonuses[source_type] = 1.5 if has_bonus else 1.0

    # ── Sprint 8VB: Adaptive Timeout ───────────────────────────────────

    def _update_latency_ema(self, domain: str, latency: float) -> None:
        """Update EMA for domain fetch latency."""
        prev = self._fetch_latency_ema.get(domain, latency)
        self._fetch_latency_ema[domain] = (
            0.3 * latency + 0.7 * prev
        )

    def get_adaptive_timeout(self, domain: str) -> float:
        """Get adaptive timeout based on EMA latency. Clamped to [5, 30]s."""
        ema = self._fetch_latency_ema.get(domain, 10.0)
        return max(5.0, min(30.0, ema * 3.0))

    async def log_source_hit(
        self,
        store: Any,
        sprint_id: str,
        source_type: str,
        findings_count: int,
        ioc_count: int,
    ) -> None:
        """Record a source hit for hit-rate tracking."""
        hit_rate = findings_count / max(1, findings_count + 1)
        try:
            await store.async_record_source_hit(
                sprint_id, _time.time(), source_type,
                findings_count, ioc_count, hit_rate,
            )
        except Exception as e:
            log.warning(f"source_hit_log insert failed: {e}")

    # ── Sprint 8TB: Agentic Pivot Loop ──────────────────────────────────

    def inject_ioc_graph(self, ioc_graph: Any) -> None:
        """Inject IOCGraph reference for pivot operations."""
        self._pivot_ioc_graph = ioc_graph

    def enqueue_pivot(
        self,
        ioc_value: str,
        ioc_type: str,
        confidence: float,
        degree: float = 1.0,
        task_type: str | None = None,
    ) -> None:
        """
        Enqueue a pivot task. Called on every new IOC hit from buffer_ioc.
        Silently drops if queue is full (M1 8GB constraint).

        Sprint 8VI §B.4: RL-adaptive priority — for generic_pivot task types,
        blend EMA reward with base priority.
        """
        if self._pivot_queue.full():
            return
        # Multi-pivot: enqueue ALL applicable task types per IOC
        task_types_list: list[str]
        if task_type is not None:
            # Single explicit task type
            task_types_list = [task_type]
        else:
            task_types_list = {
                # Sprint 8TB original
                "cve": ["cve_to_github", "cve_to_academic"],
                "ipv4": ["ip_to_ct", "ip_to_greynoise", "shodan_enrich"],
                "ipv6": ["ip_to_ct"],
                "domain": ["domain_to_dns", "domain_to_wayback", "domain_to_pdns",
                           "domain_to_ct", "ahmia_search", "rdap_lookup"],
                "md5": ["hash_to_mb"],
                "sha256": ["hash_to_mb"],
                "sha1": ["hash_to_mb"],
                # Sprint 8VB: Maximum OSINT Coverage
                "url": ["wayback_search", "commoncrawl_search", "paste_keyword_search",
                        "github_dork", "multi_engine_search"],
                # Sprint 8VI §C: hypothesis feedback
                "hypothesis": ["multi_engine_search", "rdap_lookup"],
            }.get(ioc_type, [])
        if not task_types_list:
            return

        base_priority = confidence * max(1.0, float(degree))
        for tt in task_types_list:
            # Sprint 8VI §B.4: RL-adaptive priority blend
            effective = self._get_adaptive_priority(tt, base_priority=base_priority)
            priority = -effective
            task = PivotTask(priority, ioc_type, ioc_value, tt)
            try:
                self._pivot_queue.put_nowait(task)
                self._pivot_stats["total"] += 1
            except asyncio.QueueFull:
                pass

    async def _drain_pivot_queue(self, max_tasks: int = 5) -> int:
        """
        Drain up to max_tasks from pivot queue. Max 8s total deadline.
        Called at end of each ACTIVE cycle.
        """
        processed = 0
        deadline = asyncio.get_event_loop().time() + 8.0
        while processed < max_tasks:
            if asyncio.get_event_loop().time() > deadline:
                break
            try:
                task = self._pivot_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            try:
                await asyncio.wait_for(
                    self._execute_pivot(task),
                    timeout=6.0,
                )
                self._pivot_stats["processed"] += 1
            except (asyncio.TimeoutError, Exception) as e:
                self._pivot_stats["errors"] += 1
                log.debug(f"pivot {task.task_type} {task.ioc_value}: {e}")
            processed += 1
        return processed

    async def _execute_pivot(self, task: PivotTask) -> None:
        """Dispatch pivot task to appropriate intelligence client."""
        import aiohttp
        from hledac.universal.intelligence.exposure_clients import (
            GitHubCodeSearchClient,
            MalwareBazaarClient,
        )
        from hledac.universal.intelligence.network_reconnaissance import (
            PassiveDNSClient,
        )
        from hledac.universal.paths import CACHE_ROOT
        from hledac.universal.tool_registry import get_task_handler

        session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15),
            headers={"User-Agent": "curl/7.0"},
        )
        try:
            # Sprint 8VF: Registry dispatch — OSINT handlers registered via @register_task
            handler = get_task_handler(task.task_type)
            if handler is not None:
                await handler(task, self)
                return

            # Sprint 8VF: Inline lifecycle handlers only (max 5 branches)
            # Sprint 8VF §E.3: hypothesis_probe — keyword extraction from natural language
            # Sprint 8VI §C: Hypothesis → DuckPGQ confirmed_by feedback
            elif task.task_type == "hypothesis_probe":
                words = task.ioc_value.split()
                queries = sorted(
                    {w.lower() for w in words if len(w) > 5},
                    key=len, reverse=True
                )[:3]
                count_before = getattr(self, "_finding_count", 0)
                for sq in queries:
                    self.enqueue_pivot(
                        ioc_value=sq,
                        ioc_type="url",
                        confidence=0.7,
                    )
                count_after = getattr(self, "_finding_count", 0)
                hyp_found = count_after - count_before
                # Sprint 8VI §C: Feedback — successful hypotheses strengthen edges
                if hyp_found > 0 and hasattr(self, "_ioc_graph") and self._ioc_graph is not None:
                    try:
                        for ioc_entry in self._recent_iocs[-hyp_found:]:
                            ioc_val = ioc_entry.get("value") or ioc_entry.get("ioc", "")
                            if ioc_val:
                                self._ioc_graph.add_relation(
                                    task.ioc_value[:100],
                                    ioc_val,
                                    rel_type="confirmed_by",
                                    weight=0.8,
                                    evidence="hypothesis_probe",
                                )
                    except Exception:
                        pass

            # Sprint 8VF §C: Sprint lifecycle inline handlers (only these stay as elif)
            elif task.task_type == "sprint_windup":
                # Signal windup — nothing to do in pivot
                pass

            else:
                # Sprint 8VF: OSINT handlers moved to @register_task registry
                # (ti_feed_adapter, duckduckgo_adapter). Remaining types are either
                # unregistered or lifecycle-only.
                log.debug(f"[DISPATCH] Unknown task type: {task.task_type}")
        finally:
            await session.close()

    async def _buffer_ioc_pivot(
        self, ioc_type: str, ioc_value: str, confidence: float
    ) -> None:
        """Wrapper: buffer IOC to graph and enqueue for further pivoting."""
        # Sprint 8VE B.3: Lazy IOC graph init
        if not hasattr(self, "_ioc_graph"):
            from hledac.universal.graph.quantum_pathfinder import DuckPGQGraph
            self._ioc_graph = DuckPGQGraph()

        entry = {"ioc": ioc_value, "ioc_type": ioc_type, "source": "pivot"}
        domain = None
        try:
            from urllib.parse import urlparse
            domain = urlparse(ioc_value).netloc
        except Exception:
            pass
        if domain:
            entry["domain"] = domain
            entry["rel_type"] = "seen_at"
        if entry.get("ioc"):
            self._ioc_graph.add_relation(
                entry["ioc"], domain or ioc_value,
                rel_type=entry.get("rel_type", "pivot"),
                evidence=entry.get("source", "")
            )

        # Also buffer to pivot_ioc_graph if set
        if self._pivot_ioc_graph is not None:
            await self._pivot_ioc_graph.buffer_ioc(ioc_type, ioc_value, confidence)
            # Re-enqueue for further pivot (with degree+1)
            degree = 2
            self.enqueue_pivot(ioc_value, ioc_type, confidence * 0.9, degree)

    # ── Sprint 8UC B.4: Speculative prefetch ─────────────────────────────

    async def _speculative_prefetch(
        self,
        session,  # aiohttp.ClientSession
        n: int = 3,
    ) -> None:
        """Spustit top-n pivot tasků spekulativně jako background tasks."""
        if self._pivot_queue.empty():
            return

        # Sprint 8RA: Bound _speculative_results to prevent unbounded growth
        if len(self._speculative_results) > 500:
            keys = list(self._speculative_results.keys())
            for k in keys[:250]:
                del self._speculative_results[k]

        # Peek top-n z heap (min-heap: nejnižší = nejvyšší priorita)
        peeked = []
        try:
            with self._pivot_queue.mutex:
                peeked = list(self._pivot_queue.queue)[:n]
        except AttributeError:
            # Fallback for queues without mutex
            peeked = []
            for _ in range(min(n, self._pivot_queue.qsize())):
                try:
                    peeked.append(self._pivot_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break

        for pivot_task in peeked[:n]:
            task_key = f"{pivot_task.task_type}:{pivot_task.ioc_value}"
            if task_key in self._speculative_results:
                continue

            async def _speculative_run(pt=pivot_task, key=task_key):
                try:
                    result = await self._execute_pivot(pt, session)
                    self._speculative_results[key] = result or {}
                    log.debug(f"Speculative hit: {key}")
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    log.debug(f"Speculative miss {key}: {e}")

            task = asyncio.create_task(_speculative_run())
            self._bg_tasks.add(task)
            task.add_done_callback(self._bg_tasks.discard)

    # ── Sprint 8UC B.5: OODA agentic loop ────────────────────────────────

    async def _run_ooda_cycle(
        self,
        ioc_graph,
        session,
    ) -> None:
        """Jeden OODA cyklus — 60s interval."""
        log.info("OODA: cycle start")

        # OBSERVE
        try:
            node_count = ioc_graph.node_count() if ioc_graph and hasattr(ioc_graph, "node_count") else 0
            log.debug(f"OODA Observe: {node_count} IOC nodes")
        except Exception:
            node_count = 0

        # ORIENT — PageRank top-k
        top_nodes: list = []
        try:
            if ioc_graph and hasattr(ioc_graph, "pagerank"):
                top_nodes = await asyncio.get_running_loop().run_in_executor(
                    None, ioc_graph.pagerank, 10)
            elif ioc_graph and hasattr(ioc_graph, "get_top_nodes"):
                top_nodes = ioc_graph.get_top_nodes(10)
        except Exception as e:
            log.debug(f"OODA Orient PageRank: {e}")

        # DECIDE — nodes s pr_score > 0.05 dostávají priority boost
        decided_seeds: list = []
        for node in top_nodes[:5]:
            if len(node) >= 3:
                value, ioc_type, pr_score = node[0], node[1], float(node[2])
            else:
                continue
            if pr_score > 0.05:
                confidence = min(0.95, 0.75 + pr_score)
                decided_seeds.append((value, ioc_type, confidence))

        # ACT — enqueue pivot tasks (sync, no await needed)
        acted = 0
        for value, ioc_type, confidence in decided_seeds:
            try:
                self.enqueue_pivot(value, ioc_type, confidence, degree=2)
                acted += 1
            except Exception as e:
                log.debug(f"OODA Act enqueue {value}: {e}")

        self._pivot_stats["ooda_cycles"] = self._pivot_stats.get("ooda_cycles", 0) + 1
        self._pivot_stats["ooda_last_acted"] = acted
        log.info(f"OODA: acted on {acted} nodes")

    # ── Sprint 8VD §B: Arrow / Parquet columnar buffer ────────────────────

    async def _maybe_flush_to_parquet(self) -> None:
        """Flush Arrow batch to Parquet when N or S threshold is hit."""
        import time as _time
        now = _time.monotonic()
        if (
            len(self._arrow_batch) < self._ARROW_FLUSH_N
            and now - self._arrow_last_flush < self._ARROW_FLUSH_S
        ):
            return
        if not self._arrow_batch:
            return

        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            log.warning("[8VD-PARQUET] pyarrow not available — skipping flush")
            return

        batch = self._arrow_batch[:]
        self._arrow_batch.clear()
        self._arrow_last_flush = now

        schema = pa.schema([
            ("url",        pa.string()),
            ("title",      pa.string()),
            ("snippet",    pa.string()),
            ("source",     pa.string()),
            ("ioc",        pa.string()),
            ("ioc_type",   pa.string()),
            ("confidence", pa.float32()),
            ("timestamp",  pa.timestamp("ms", tz="UTC")),
            ("sprint_id",  pa.string()),
        ])
        rows = {k: [r.get(k) for r in batch] for k in schema.names}
        table = pa.table(rows, schema=schema)

        from hledac.universal.paths import get_sprint_parquet_dir
        sid = self.sprint_id or getattr(self, "sprint_id", "unknown")
        path = get_sprint_parquet_dir(sid) / f"batch_{int(now * 1000)}.parquet"

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, lambda: pq.write_table(table, path, compression="snappy")
        )
        log.info(f"[8VD-PARQUET] flushed {len(batch)} rows → {path}")

    def buffer_finding(self, finding: dict) -> None:
        """Buffer a finding into the Arrow batch."""
        self._arrow_batch.append(finding)
        # Kick off async flush without awaiting
        try:
            _t = asyncio.create_task(self._maybe_flush_to_parquet())
            self._bg_tasks.add(_t)
            _t.add_done_callback(self._bg_tasks.discard)
        except RuntimeError:
            pass  # No running loop in sync context
        # Sprint 8VF §B.3: IOC extraction — regex PRIMARY, spaCy SECONDARY
        _text = " ".join(filter(None, [
            finding.get("snippet", ""),
            finding.get("content", ""),
            finding.get("title", ""),
        ])).strip()
        if len(_text) > 10:
            try:
                from hledac.universal.brain.ane_embedder import extract_iocs_from_text
                for ioc in extract_iocs_from_text(_text[:2_000]):
                    ioc_entry = {
                        **ioc,
                        "source": "ner_extracted",
                        "parent_url": finding.get("url", ""),
                    }
                    self.buffer_ioc(ioc_entry)
            except Exception:
                pass  # NER is enrichment — never crashes the pipeline

    def buffer_ioc(self, ioc: dict) -> None:
        """
        Buffer an IOC into the Arrow batch.

        Sprint 8VI §D: IOCScorer final_score zapojeno.
        Sprint 8VI §C: Recent IOC ring buffer pro hypothesis feedback.
        """
        # Sprint 8VI §D: IOCScorer zapojení
        ioc_entry = dict(ioc)
        if hasattr(self, "_ioc_scorer") and self._ioc_scorer is not None:
            try:
                score = self._ioc_scorer.final_score(ioc_entry)
                ioc_entry["confidence"] = score
            except Exception:
                pass

        # Sprint 8VI §C: Ring buffer — max 100 recent IOCs
        recent = getattr(self, "_recent_iocs", [])
        recent.append(ioc_entry)
        self._recent_iocs = recent[-100:]

        # Sprint 8VI §C: Hypothesis → DuckPGQ confirmed_by hrany
        # (handled in _execute_pivot after finding confirmation)

        self._arrow_batch.append(ioc_entry)
        try:
            _t = asyncio.create_task(self._maybe_flush_to_parquet())
            self._bg_tasks.add(_t)
            _t.add_done_callback(self._bg_tasks.discard)
        except RuntimeError:
            pass

    # ── Sprint 8VD §B.5: DuckDB singleton helpers ───────────────────────────

    def _get_duckdb_con(self):
        """Singleton DuckDB connection — initialized once."""
        if self._duckdb_read_con is None:
            import duckdb
            self._duckdb_read_con = duckdb.connect()
        return self._duckdb_read_con

    def query_sprint_results(self, sql: str) -> list[dict]:
        """DuckDB vectorized query over Parquet files. Zero-copy style."""
        return self._get_duckdb_con().execute(sql).fetchdf().to_dict("records")

    # ── Sprint 8VD §D: Polars lazy dedup + ranking ────────────────────────

    def deduplicate_and_rank_findings(self, sprint_id: str | None = None) -> str:
        """
        Polars LazyFrame streaming dedup — M1 8GB RAM safe.
        Uses Polars 1.x .collect(engine='streaming') API.
        """
        import polars as pl
        from hledac.universal.paths import get_sprint_parquet_dir
        sid = sprint_id or self.sprint_id or "*"
        store_dir = get_sprint_parquet_dir(sid)
        glob = str(store_dir / "batch_*.parquet")
        out = str(store_dir / "ranked.parquet")

        (
            pl.scan_parquet(glob)
            .filter(
                pl.col("url").is_not_null() | pl.col("ioc").is_not_null()
            )
            .with_columns([
                pl.col("confidence").fill_null(0.5),
                pl.col("source").cast(pl.Categorical),
            ])
            .group_by(["url", "ioc"])
            .agg([
                pl.col("title").first(),
                pl.col("source").first(),
                pl.col("confidence").max(),
                pl.len().alias("hit_count"),
            ])
            .sort("hit_count", descending=True)
            .collect(engine="streaming")
            .write_parquet(out, compression="snappy")
        )
        return out

    # ── Sprint 8VD §C: Memory pressure loop ────────────────────────────────

    async def _memory_pressure_loop(self) -> None:
        """Background task — adjusts concurrency based on memory pressure."""
        from hledac.universal.resource_allocator import get_recommended_concurrency
        import asyncio as _asyncio

        while True:
            try:
                limits = get_recommended_concurrency()
                self._fetch_semaphore = _asyncio.Semaphore(limits["fetch"])
                log.info(
                    f"[MEM] fetch_limit={limits['fetch']} "
                    f"ml_jobs={limits['ml_jobs']}"
                )
                interval = 10 if limits["fetch"] <= 2 else 30
            except Exception as e:
                log.warning(f"[MEM] pressure check failed: {e}")
                interval = 30
            await _asyncio.sleep(interval)

    # ── Sprint 8VM: Shadow Pre-Decision Consumer ───────────────────────────
    # Read-only seam: consumes existing shadow/pre-decision layer
    # WITHOUT creating new scheduler framework, mutable state, or execution path

    def consume_shadow_pre_decision(self) -> Any:
        """
        Sprint 8VM: Read-only shadow pre-decision consumer.

        Collects shadow inputs from current scheduler state,
        runs parity check and pre-decision composition,
        and returns PreDecisionSummary.

        Caching: stores result in _shadow_pd_summary to avoid recomputation.
        Cache is cleared in _reset_result().

        THIS IS DIAGNOSTIC ONLY — all hard boundaries enforced:
        - Does NOT execute any tools (no execute_with_limits calls)
        - Does NOT activate any providers
        - Does NOT write to any ledgers as runtime truth
        - Does NOT modify scheduler mutable state
        - Does NOT create new scheduler framework
        - Does NOT dispatch or enqueue work
        - Returns PreDecisionSummary artifact, NOT a truth store

        Injection point: called from _build_diagnostic_report() at export time.
        The method is also available for ad-hoc calls during sprint for
        diagnostic purposes only.

        Returns None if shadow mode is not active.
        """
        from hledac.universal.runtime.shadow_inputs import RuntimeMode

        # Only run when shadow mode is explicitly enabled
        if not RuntimeMode.is_shadow_mode():
            return None

        # Return cached value if already computed this sprint
        if self._shadow_pd_summary is not None:
            return self._shadow_pd_summary

        lc = None
        if self._lc_adapter is not None:
            lc = self._lc_adapter._lc
        if lc is None:
            return None

        # Collect lifecycle snapshot
        try:
            now_mono = _time.monotonic()
            # Derive thermal state from latency EMA (read-only heuristic)
            thermal = "nominal"
            if self._fetch_latency_ema:
                max_ema = max(self._fetch_latency_ema.values()) if self._fetch_latency_ema else 10.0
                if max_ema > 20.0:
                    thermal = "critical"
                elif max_ema > 15.0:
                    thermal = "throttled"
                elif max_ema > 10.0:
                    thermal = "fair"

            lifecycle_bundle = collect_lifecycle_snapshot(
                lc, now_mono, thermal,
                windup_synthesis_mode="synthesis",
                windup_error=False,
                windup_engine=self._synthesis_engine or "unknown",
            )
        except Exception:
            return None

        # Collect graph summary (may be None if no graph injected yet)
        try:
            graph_bundle = collect_graph_summary(self._ioc_graph)
        except Exception:
            from hledac.universal.runtime.shadow_inputs import GraphSummaryBundle
            graph_bundle = GraphSummaryBundle()

        # Collect model/control facts from scheduler config
        try:
            mc_bundle = collect_model_control_facts(
                analyzer_result=None,
                raw_profile={
                    "tools": [],
                    "sources": list(self._config.source_tier_map.keys()),
                    "privacy_level": "STANDARD",
                    "use_tor": False,
                    "depth": "STANDARD",
                    "use_tot": False,
                    "tot_mode": "standard",
                    "models_needed": [],
                },
            )
        except Exception:
            from hledac.universal.runtime.shadow_inputs import ModelControlFactsBundle
            mc_bundle = ModelControlFactsBundle()

        # Export handoff facts (synthesized from scheduler state)
        export_facts = {
            "sprint_id": self.sprint_id or "unknown",
            "synthesis_engine": self._synthesis_engine or "unknown",
            "gnn_predictions": 0,
            "top_nodes_count": 0,
            "ranked_parquet_present": False,
            "phase_durations": {},
        }

        try:
            parity = run_shadow_parity(
                lifecycle_bundle=lifecycle_bundle,
                graph_bundle=graph_bundle,
                model_control_bundle=mc_bundle,
                export_handoff_facts=export_facts,
                branch_decision=None,
                provider_recommend=None,
                correlation=None,
                runtime_mode=RuntimeMode.get_current(),
            )
        except Exception:
            return None

        try:
            pd_summary = compose_pre_decision(parity)
        except Exception:
            return None

        # Tool readiness preview — DIAGNOSTIC ONLY, no dispatch, no execute_with_limits
        # Lazily access ToolRegistry to avoid cold-import cost in non-shadow mode
        try:
            registry = None
            # Try to get default registry (read-only inspection)
            from hledac.universal.tool_registry import create_default_registry
            registry = create_default_registry()
            all_tools = registry.list_tools()
            tool_names = [t.name for t in all_tools]
            tool_cards = registry.get_tool_cards_for_hermes()
            # Attach as read-only diagnostic annotations to pd_summary
            pd_summary._tool_readiness_preview = {
                "tool_count": len(all_tools),
                "tool_names": tool_names,
                "has_network_tools": bool(registry.get_network_tools()),
                "has_high_memory_tools": bool(registry.get_high_memory_tools()),
                "tool_cards_sample": tool_cards[:3] if tool_cards else [],
            }
        except Exception:
            # ToolRegistry unavailable — skip, this is diagnostic only
            pass

        # Cache for repeated calls within the same sprint
        self._shadow_pd_summary = pd_summary
        return pd_summary

    def evaluate_advisory_gate(self) -> None:
        """
        Sprint 8VQ: Evaluate advisory gate at WINDUP entry — DIAGNOSTIC ONLY.

        Reads from cached PreDecisionSummary (computed by consume_shadow_pre_decision)
        and composes AdvisoryGateSnapshot. Does NOT:
        - Influence dispatch or source ordering
        - Activate providers or tools
        - Write to any ledgers as runtime truth
        - Create new scheduler framework

        Stores ephemeral result in _advisory_gate_snapshot (cleared in _reset_result).
        Output goes into diagnostic report via _build_shadow_readiness_preview().
        """
        from hledac.universal.runtime.shadow_pre_decision import compose_advisory_gate

        pd = self.consume_shadow_pre_decision()
        if pd is None:
            self._advisory_gate_snapshot = None
            return

        try:
            self._advisory_gate_snapshot = compose_advisory_gate(pd)
        except Exception:
            self._advisory_gate_snapshot = None

    def _build_shadow_readiness_preview(self) -> dict[str, Any]:
        """
        Sprint 8VM + 8VQ: Build a machine-readable shadow readiness preview dict.

        Called from _build_diagnostic_report() when shadow mode is active.
        This is a READ-ONLY summary extracted from PreDecisionSummary
        for diagnostic/logging purposes — NOT a truth store.
        """
        pd = self.consume_shadow_pre_decision()
        if pd is None:
            return {}

        result: dict[str, Any] = {
            "runtime_mode": pd.runtime_mode,
            "parity_timestamp_monotonic": pd.parity_timestamp_monotonic,
            "lifecycle_readiness": {
                "phase": pd.lifecycle.workflow_phase,
                "is_active": pd.lifecycle.is_active,
                "is_windup": pd.lifecycle.is_windup,
                "can_accept_work": pd.lifecycle.can_accept_work,
                "should_prune": pd.lifecycle.should_prune,
                "phase_conflict": pd.lifecycle.phase_conflict,
            },
            "graph_readiness": {
                "backend": pd.graph.backend,
                "readiness": pd.graph.readiness,
                "nodes": pd.graph.nodes,
                "edges": pd.graph.edges,
            },
            "export_readiness": {
                "readiness": pd.export_readiness.readiness,
                "synthesis_engine": pd.export_readiness.synthesis_engine,
            },
            "model_control_readiness": {
                "readiness": pd.model_control.readiness,
                "tools_count": pd.model_control.tools_count,
            },
            "diff_taxonomy": [d.name for d in pd.diff_taxonomy],
            "blockers": pd.blockers,
            "unknowns": pd.unknowns,
            "compat_seams": pd.compat_seams,
        }

        # Sprint 8VQ: Decision gate readiness
        if pd.decision_gate is not None:
            result["decision_gate"] = {
                "gate_status": pd.decision_gate.gate_status,
                "blocker_count": pd.decision_gate.blocker_count,
                "unknown_count": pd.decision_gate.unknown_count,
                "compat_seam_count": pd.decision_gate.compat_seam_count,
                "is_proceed_allowed": pd.decision_gate.is_proceed_allowed,
                "defer_to_provider": pd.decision_gate.defer_to_provider,
                "blocker_categories": pd.decision_gate.blocker_categories,
                "unknown_categories": pd.decision_gate.unknown_categories,
            }

        # Sprint 8VQ: Tool readiness preview (read-only, no dispatch)
        if pd.tool_readiness is not None:
            result["tool_readiness"] = {
                "readiness": pd.tool_readiness.readiness,
                "tool_count": pd.tool_readiness.tool_count,
                "has_network_tools": pd.tool_readiness.has_network_tools,
                "has_high_memory_tools": pd.tool_readiness.has_high_memory_tools,
                "control_mode": pd.tool_readiness.control_mode,
                "pruned_tool_count": pd.tool_readiness.pruned_tool_count,
                "resource_constraint": pd.tool_readiness.resource_constraint,
                "can_execute": pd.tool_readiness.can_execute,
                "defer_reason": pd.tool_readiness.defer_reason,
            }

        # Sprint 8VQ: Windup readiness preview
        if pd.windup_readiness is not None:
            result["windup_readiness"] = {
                "readiness": pd.windup_readiness.readiness,
                "is_windup_phase": pd.windup_readiness.is_windup_phase,
                "synthesis_mode": pd.windup_readiness.synthesis_mode,
                "synthesis_engine": pd.windup_readiness.synthesis_engine,
                "has_export_data": pd.windup_readiness.has_export_data,
                "export_data_quality": pd.windup_readiness.export_data_quality,
                "defer_reason": pd.windup_readiness.defer_reason,
            }

        # Sprint 8VQ: Provider activation note (deferred/unknown only)
        if pd.provider_note is not None:
            result["provider_activation_note"] = {
                "status": pd.provider_note.status,
                "deferral_reason": pd.provider_note.deferral_reason,
                "has_recommendation": pd.provider_note.has_recommendation,
                "recommendation": pd.provider_note.recommendation,
                "next_phase_hint": pd.provider_note.next_phase_hint,
            }

        # Legacy: tool_readiness_preview from consumer seam (if still attached)
        if hasattr(pd, "_tool_readiness_preview"):
            result["tool_readiness_preview"] = pd._tool_readiness_preview

        # Sprint 8VQ: Advisory gate snapshot (computed at WINDUP entry, diagnostic only)
        if self._advisory_gate_snapshot is not None:
            ag = self._advisory_gate_snapshot
            result["advisory_gate"] = {
                "gate_outcome": ag.gate_outcome,
                "gate_status": ag.gate_status,
                "blocker_count": ag.blocker_count,
                "unknown_count": ag.unknown_count,
                "compat_seam_count": ag.compat_seam_count,
                "blocker_reasons": ag.blocker_reasons,
                "unknown_reasons": ag.unknown_reasons,
                "compat_seam_reasons": ag.compat_seam_reasons,
                "defer_to_provider": ag.defer_to_provider,
                "gate_evaluated_at_monotonic": ag.gate_evaluated_at_monotonic,
                "gate_evaluated_at_wall": ag.gate_evaluated_at_wall,
            }

        return result

    # ── Internal reset ────────────────────────────────────────────────────

    def _reset_result(self) -> None:
        self._seen_hashes.clear()
        self._entries_per_source.clear()
        self._hits_per_source.clear()
        self._stop_requested = False
        self._result = SprintSchedulerResult()
        # Sprint 8VD: Clear Arrow batch state
        self._arrow_batch.clear()
        self._arrow_last_flush = 0.0
        # Sprint 8RA: Close DuckDB read connection
        if self._duckdb_read_con is not None:
            try:
                self._duckdb_read_con.close()
            except Exception:
                pass
            self._duckdb_read_con = None
        # Sprint 8VM: Clear shadow pre-decision summary
        self._shadow_pd_summary = None
        # Sprint 8VQ: Clear advisory gate snapshot
        self._advisory_gate_snapshot = None


# ---------------------------------------------------------------------------
# Convenience top-level function
# ---------------------------------------------------------------------------

async def async_run_tiered_feed_sprint_once(
    sources: Sequence[str],
    config: Optional[SprintSchedulerConfig] = None,
    lifecycle: Optional[object] = None,
    now_monotonic: Optional[float] = None,
) -> SprintSchedulerResult:
    """
    One-shot tiered feed sprint.

    Creates its own lifecycle if none provided.
    """
    if config is None:
        config = SprintSchedulerConfig()
    if lifecycle is None:
        from hledac.universal.runtime.sprint_lifecycle import SprintLifecycleManager
        lifecycle = SprintLifecycleManager(
            sprint_duration_s=config.sprint_duration_s,
            windup_lead_s=config.windup_lead_s,
        )

    scheduler = SprintScheduler(config)
    return await scheduler.run(lifecycle, sources, now_monotonic)
