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
                    asyncio.create_task(self._speculative_prefetch(None, n=3))
                    self._last_speculative = now_mono

                # Sprint 8UC B.5: OODA cycle every 60s
                if (now_mono - self._last_ooda) >= self._ooda_interval:
                    asyncio.create_task(self._run_ooda_cycle(self._pivot_ioc_graph, None))
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
        return {
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
    ) -> None:
        """
        Enqueue a pivot task. Called on every new IOC hit from buffer_ioc.
        Silently drops if queue is full (M1 8GB constraint).
        """
        if self._pivot_queue.full():
            return
        # Multi-pivot: enqueue ALL applicable task types per IOC
        task_types = {
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
        }.get(ioc_type, [])
        if not task_types:
            return
        priority = -(confidence * max(1.0, float(degree)))
        for task_type in task_types:
            task = PivotTask(priority, ioc_type, ioc_value, task_type)
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

        session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15),
            headers={"User-Agent": "curl/7.0"},
        )
        try:
            if task.task_type == "cve_to_github":
                gh = GitHubCodeSearchClient(cache_dir=CACHE_ROOT / "github")
                results = await gh.search_cve(task.ioc_value, session)
                for r in results[:5]:
                    url = r.get("url", "")
                    if url:
                        await self._buffer_ioc_pivot("url", url, 0.65)
                    repo = r.get("repo", "")
                    if repo and "." in repo:
                        domain = repo.split("/")[0] + ".github.io"
                        await self._buffer_ioc_pivot("domain", domain, 0.50)
                await gh.close()

            elif task.task_type == "ip_to_ct":
                from hledac.universal.intelligence.ct_log_client import CTLogClient
                ct = CTLogClient(cache_dir=CACHE_ROOT / "ct")
                result = await ct.pivot_domain(task.ioc_value, session)
                for san in (result.get("san_names") or [])[:10]:
                    await self._buffer_ioc_pivot("domain", san, 0.70)
                await ct.close()

            elif task.task_type == "domain_to_dns":
                dns_client = PassiveDNSClient()
                ips = await dns_client.resolve_domain(task.ioc_value)
                for ip in ips[:5]:
                    await self._buffer_ioc_pivot("ipv4", ip, 0.72)
                await dns_client.close()

            elif task.task_type == "hash_to_mb":
                mb = MalwareBazaarClient(cache_dir=CACHE_ROOT / "mb")
                data = await mb.query_hash(task.ioc_value, session)
                for val, typ in mb.extract_iocs(data):
                    await self._buffer_ioc_pivot(typ, val, 0.80)
                await mb.close()

            elif task.task_type == "domain_to_wayback":
                from hledac.universal.intelligence.archive_discovery import WaybackCDXClient
                wb = WaybackCDXClient(cache_dir=CACHE_ROOT / "wayback")
                snaps = await wb.get_snapshots(task.ioc_value, session, limit=20)
                for snap in sorted(snaps, key=lambda x: x.get("timestamp", ""))[:5]:
                    text = await wb.fetch_snapshot_text(
                        snap["original"], snap["timestamp"], session
                    )
                    if text:
                        for hit in match_text(text[:8000]):
                            if hit.label and hit.value:
                                await self._buffer_ioc_pivot(hit.label, hit.value, 0.68)

            elif task.task_type == "cve_to_academic":
                from hledac.universal.intelligence.academic_search import SemanticScholarClient
                scholar = SemanticScholarClient(cache_dir=CACHE_ROOT / "scholar")
                papers = await scholar.search_ss(task.ioc_value, session)
                for p in papers[:5]:
                    text = f"{p['title']} {p['abstract']}"
                    for hit in match_text(text):
                        if hit.label and hit.value:
                            await self._buffer_ioc_pivot(hit.label, hit.value, 0.78)
                arxiv = await scholar.search_arxiv(task.ioc_value, session)
                for a in arxiv[:3]:
                    for hit in match_text(a.get("summary", "")):
                        if hit.label and hit.value:
                            await self._buffer_ioc_pivot(hit.label, hit.value, 0.75)

            elif task.task_type == "ip_to_greynoise":
                from hledac.universal.intelligence.exposure_clients import GreyNoiseClient
                gn = GreyNoiseClient(cache_dir=CACHE_ROOT / "greynoise")
                result = await gn.classify_ip(task.ioc_value, session)
                classification = result.get("classification", "unknown")
                if classification == "malicious":
                    await self._buffer_ioc_pivot("ipv4", task.ioc_value, 0.92)
                    log.info(
                        f"GreyNoise: {task.ioc_value} = MALICIOUS "
                        f"({result.get('name', '')})"
                    )

            # Sprint 8VB: Maximum OSINT Coverage dispatch
            elif task.task_type == "domain_to_pdns":
                from hledac.universal.discovery.ti_feed_adapter import query_circl_pdns
                for r in await query_circl_pdns(task.ioc_value):
                    await self._buffer_ioc_pivot(
                        r.get("ioc_type", "domain"), r.get("ioc", ""), 0.75
                    )

            elif task.task_type == "domain_to_ct":
                from hledac.universal.discovery.ti_feed_adapter import search_crtsh
                for r in await search_crtsh(task.ioc_value):
                    await self._buffer_ioc_pivot("domain", r.get("ioc", ""), 0.70)

            elif task.task_type == "ct_live_monitor":
                from hledac.universal.discovery.ti_feed_adapter import certstream_monitor
                for r in await certstream_monitor(task.ioc_value, duration_s=120):
                    await self._buffer_ioc_pivot("domain", r.get("ioc", ""), 0.65)

            elif task.task_type == "paste_keyword_search":
                from hledac.universal.discovery.ti_feed_adapter import scrape_pastebin_for_keyword
                for r in await scrape_pastebin_for_keyword(task.ioc_value):
                    await self._buffer_ioc_pivot("url", r.get("url", ""), 0.60)

            elif task.task_type == "github_dork":
                from hledac.universal.discovery.ti_feed_adapter import github_dork
                for r in await github_dork(task.ioc_value):
                    await self._buffer_ioc_pivot("url", r.get("url", ""), 0.70)
                await asyncio.sleep(2.0)

            elif task.task_type == "ahmia_search":
                from hledac.universal.discovery.ti_feed_adapter import search_ahmia
                for r in await search_ahmia(task.ioc_value, use_onion=False):
                    await self._buffer_ioc_pivot("url", r.get("url", ""), 0.65)

            elif task.task_type == "shodan_enrich":
                from hledac.universal.discovery.ti_feed_adapter import enrich_ip_internetdb
                r = await enrich_ip_internetdb(task.ioc_value)
                if r:
                    await self._buffer_ioc_pivot("ipv4", task.ioc_value, 0.80)

            elif task.task_type == "rdap_lookup":
                from hledac.universal.discovery.ti_feed_adapter import query_rdap
                r = await query_rdap(task.ioc_value)
                if r:
                    await self._buffer_ioc_pivot("domain", task.ioc_value, 0.75)

            elif task.task_type == "multi_engine_search":
                from hledac.universal.discovery.duckduckgo_adapter import search_multi_engine
                for r in await search_multi_engine(task.ioc_value):
                    await self._buffer_ioc_pivot("url", r.get("url", ""), 0.70)

            elif task.task_type == "wayback_search":
                from hledac.universal.discovery.duckduckgo_adapter import _search_wayback_cdx
                for r in await _search_wayback_cdx(task.ioc_value):
                    await self._buffer_ioc_pivot("url", r.get("url", ""), 0.65)

            elif task.task_type == "commoncrawl_search":
                from hledac.universal.discovery.duckduckgo_adapter import _search_commoncrawl_cdx
                for r in await _search_commoncrawl_cdx(task.ioc_value):
                    await self._buffer_ioc_pivot("url", r.get("url", ""), 0.65)

            elif task.task_type == "dht_lookup":
                # Sprint 8VB D.10: DHT integration via KademliaNode
                try:
                    from dht.kademlia_node import KademliaNode
                    from hledac.universal.core.resource_governor import ResourceGovernor
                    node = KademliaNode(
                        node_id=f"hledac-{task.ioc_value[:8]}",
                        governor=ResourceGovernor(),
                    )
                    result = await node.find_value(task.ioc_value)
                    if result:
                        await self._buffer_ioc_pivot("domain", task.ioc_value, 0.75)
                except Exception as e:
                    log.debug(f"[DHT lookup] {e}")

            elif task.task_type == "taxii_fetch":
                # TAXII 2.1 fetch via discovery.ti_feed_adapter
                try:
                    from hledac.universal.discovery.ti_feed_adapter import fetch_taxii
                    for entry in await fetch_taxii(task.ioc_value):
                        await self._buffer_ioc_pivot("url", entry.get("url", ""), 0.70)
                except ImportError:
                    pass  # TAXII not available
        finally:
            await session.close()

    async def _buffer_ioc_pivot(
        self, ioc_type: str, ioc_value: str, confidence: float
    ) -> None:
        """Wrapper: buffer IOC to graph and enqueue for further pivoting."""
        if self._pivot_ioc_graph is not None:
            await self._pivot_ioc_graph.buffer_ioc(ioc_type, ioc_value, confidence)
            # Re-enqueue for further pivot (with degree+1)
            degree = 2.0
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

        # Peek top-n z heap (min-heap: nejnižší = nejvyšší priorita)
        peeked = []
        with self._pivot_queue.mutex:
            peeked = list(self._pivot_queue.queue)[:n]

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

    async def _execute_pivot(self, task: PivotTask, session=None) -> dict:
        """Execute a single pivot task. Checks speculative cache first."""
        task_key = f"{task.task_type}:{task.ioc_value}"
        if task_key in self._speculative_results:
            result = self._speculative_results.pop(task_key)
            log.debug(f"Speculative cache hit: {task_key}")
            self._pivot_stats["speculative_hits"] = self._pivot_stats.get("speculative_hits", 0) + 1
            return result
        # Placeholder — real implementation would do actual pivot work
        return {"task_type": task.task_type, "ioc_value": task.ioc_value, "status": "executed"}

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

        # ACT — enqueue pivot tasks
        acted = 0
        for value, ioc_type, confidence in decided_seeds:
            try:
                await self.enqueue_pivot(value, ioc_type, confidence, degree=2)
                acted += 1
            except Exception as e:
                log.debug(f"OODA Act enqueue {value}: {e}")

        self._pivot_stats["ooda_cycles"] = self._pivot_stats.get("ooda_cycles", 0) + 1
        self._pivot_stats["ooda_last_acted"] = acted
        log.info(f"OODA: acted on {acted} nodes")

    async def enqueue_pivot(
        self,
        ioc_value: str,
        ioc_type: str,
        confidence: float = 0.7,
        degree: int = 1,
    ) -> None:
        """Enqueue a pivot task for agentic exploration."""
        task = PivotTask(
            priority=-(confidence * degree),
            ioc_type=ioc_type,
            ioc_value=ioc_value,
            task_type="generic_pivot",
        )
        await self._pivot_queue.put(task)
        self._pivot_stats["total"] = self._pivot_stats.get("total", 0) + 1

    # ── Internal reset ────────────────────────────────────────────────────

    def _reset_result(self) -> None:
        self._seen_hashes.clear()
        self._entries_per_source.clear()
        self._hits_per_source.clear()
        self._stop_requested = False
        self._result = SprintSchedulerResult()


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
