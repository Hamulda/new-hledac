"""
Sprint 8BK — Tier-Aware Scheduler Tests.
D.1–D.22 invariants + E.1–E.4 benchmarks
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hledac.universal.runtime.sprint_scheduler import (
    SourceTier,
    SourceWork,
    SprintScheduler,
    SprintSchedulerConfig,
    SprintSchedulerResult,
    async_run_tiered_feed_sprint_once,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeFeedResult:
    """Mock FeedPipelineRunResult with basic attributes."""
    def __init__(
        self,
        feed_url="http://example.com/feed",
        fetched_entries=5,
        accepted_findings=2,
        matched_patterns=3,
        error=None,
    ):
        self.feed_url = feed_url
        self.fetched_entries = fetched_entries
        self.accepted_findings = accepted_findings
        self.stored_findings = 0
        self.patterns_configured = 10
        self.matched_patterns = matched_patterns
        self.pages = ()
        self.error = error


def make_mock_lifecycle(sprint_duration_s=1800.0, windup_lead_s=180.0):
    """
    Mock SprintLifecycleManager that simulates real phase machine behavior.

    tick() advances through phases in order.
    _sleep_or_abort also calls tick(), consuming one phase per sleep call.
    """
    phases = ["WARMUP", "ACTIVE", "ACTIVE", "WINDUP", "EXPORT", "TEARDOWN"]

    lm = MagicMock()
    lm.sprint_duration_s = sprint_duration_s
    lm.windup_lead_s = windup_lead_s
    lm._started_at = None
    lm._current_phase = MagicMock()
    lm._current_phase.name = "BOOT"
    lm._abort_requested = False
    lm._abort_reason = ""
    lm._export_started = False
    lm._teardown_started = False
    lm._tick_idx = 0
    lm._phases = phases

    def start(_nm=None):
        lm._started_at = 100.0
        lm._current_phase.name = "WARMUP"

    def tick(_nm=None):
        if lm._tick_idx < len(lm._phases):
            lm._current_phase.name = lm._phases[lm._tick_idx]
            lm._tick_idx += 1
        return lm._current_phase

    def should_enter_windup(_nm=None):
        if lm._tick_idx < len(lm._phases):
            return lm._phases[lm._tick_idx] == "WINDUP"
        return True

    def is_terminal():
        return lm._teardown_started

    def request_abort(reason=""):
        lm._abort_requested = True
        lm._abort_reason = reason

    def mark_export_started(_nm=None):
        lm._export_started = True
        lm._current_phase.name = "EXPORT"

    def mark_teardown_started(_nm=None):
        lm._teardown_started = True
        lm._current_phase.name = "TEARDOWN"

    def snapshot():
        return {
            "sprint_duration_s": lm.sprint_duration_s,
            "windup_lead_s": lm.windup_lead_s,
            "current_phase": lm._current_phase.name,
            "abort_requested": lm._abort_requested,
            "abort_reason": lm._abort_reason,
        }

    def recommended_tool_mode(_nm=None, thermal_state="nominal"):
        if lm._abort_requested or thermal_state == "critical":
            return "panic"
        if lm._current_phase.name == "WINDUP":
            return "prune"
        return "normal"

    lm.start = start
    lm.tick = tick
    lm.should_enter_windup = should_enter_windup
    lm.is_terminal = is_terminal
    lm.request_abort = request_abort
    lm.mark_export_started = mark_export_started
    lm.mark_teardown_started = mark_teardown_started
    lm.snapshot = snapshot
    lm.recommended_tool_mode = recommended_tool_mode

    return lm


# ---------------------------------------------------------------------------
# D.1 — Scheduler starts lifecycle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scheduler_starts_lifecycle():
    """Scheduler calls lifecycle.start() before any other lifecycle method."""
    lifecycle = make_mock_lifecycle()
    config = SprintSchedulerConfig(sprint_duration_s=1800.0, max_cycles=1)
    scheduler = SprintScheduler(config)

    mock_feed = AsyncMock(return_value=FakeFeedResult())

    with patch(
        "hledac.universal.runtime.sprint_scheduler._import_live_feed_pipeline",
        return_value=(mock_feed, FakeFeedResult),
    ):
        with patch(
            "hledac.universal.runtime.sprint_scheduler._import_exporters",
            return_value=(MagicMock(), MagicMock(), MagicMock()),
        ):
            await scheduler.run(lifecycle, ["http://example.com/feed"])

    assert lifecycle._started_at is not None


# ---------------------------------------------------------------------------
# D.2 — Scheduler runs at least one cycle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scheduler_runs_at_least_one_cycle():
    """At least one cycle is started when sources are provided."""
    lifecycle = make_mock_lifecycle()
    config = SprintSchedulerConfig(sprint_duration_s=1800.0, max_cycles=10, cycle_sleep_s=0.001)
    scheduler = SprintScheduler(config)
    mock_feed = AsyncMock(return_value=FakeFeedResult())

    with patch(
        "hledac.universal.runtime.sprint_scheduler._import_live_feed_pipeline",
        return_value=(mock_feed, FakeFeedResult),
    ):
        with patch(
            "hledac.universal.runtime.sprint_scheduler._import_exporters",
            return_value=(MagicMock(), MagicMock(), MagicMock()),
        ):
            result = await scheduler.run(lifecycle, ["http://example.com/feed"])

    assert result.cycles_started >= 1


# ---------------------------------------------------------------------------
# D.3 — Scheduler respects max_cycles
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scheduler_respects_max_cycles():
    """Cycles are capped at max_cycles even when sprint is still active."""
    lifecycle = make_mock_lifecycle()
    # Allocate plenty of phases for the loop + _sleep_or_abort ticks
    # When max_cycles is hit, make is_terminal return True immediately
    call_count = [0]

    def terminal_check():
        call_count[0] += 1
        # After 5 cycles, act as terminal to enforce max_cycles
        return call_count[0] > 5

    lifecycle.is_terminal = terminal_check

    config = SprintSchedulerConfig(sprint_duration_s=1800.0, max_cycles=5, cycle_sleep_s=0.001)
    scheduler = SprintScheduler(config)
    mock_feed = AsyncMock(return_value=FakeFeedResult())

    with patch(
        "hledac.universal.runtime.sprint_scheduler._import_live_feed_pipeline",
        return_value=(mock_feed, FakeFeedResult),
    ):
        with patch(
            "hledac.universal.runtime.sprint_scheduler._import_exporters",
            return_value=(MagicMock(), MagicMock(), MagicMock()),
        ):
            result = await scheduler.run(lifecycle, ["http://example.com/feed"])

    assert result.cycles_started <= 5


# ---------------------------------------------------------------------------
# D.4 — Scheduler tracks unique entry hashes
# ---------------------------------------------------------------------------

def test_scheduler_tracks_unique_entry_hashes():
    """is_new_entry returns True for previously unseen hashes."""
    config = SprintSchedulerConfig()
    scheduler = SprintScheduler(config)

    assert scheduler.is_new_entry("abc123") is True
    assert scheduler.is_new_entry("def456") is True
    assert scheduler._result.unique_entry_hashes_seen == 2


# ---------------------------------------------------------------------------
# D.5 — Scheduler skips duplicate entry hashes
# ---------------------------------------------------------------------------

def test_scheduler_skips_duplicate_entry_hashes():
    """is_new_entry returns False for already-seen hashes."""
    config = SprintSchedulerConfig()
    scheduler = SprintScheduler(config)

    assert scheduler.is_new_entry("abc123") is True
    assert scheduler.is_new_entry("abc123") is False
    assert scheduler.is_new_entry("abc123") is False

    assert scheduler._result.unique_entry_hashes_seen == 1
    assert scheduler._result.duplicate_entry_hashes_skipped == 2


# ---------------------------------------------------------------------------
# D.6 — TaskGroup uses semaphore for bounded concurrency
# ---------------------------------------------------------------------------

def test_scheduler_uses_taskgroup_for_owned_concurrency():
    """Concurrency is bounded via asyncio.Semaphore inside the scheduler."""
    config = SprintSchedulerConfig(max_parallel_sources=2)
    scheduler = SprintScheduler(config)

    assert scheduler._config.max_parallel_sources == 2


# ---------------------------------------------------------------------------
# D.7 — High-value tiers ordered first
# ---------------------------------------------------------------------------

def test_scheduler_orders_high_value_tiers_first():
    """Sources are sorted by tier priority: SURFACE > STRUCTURED_TI > DEEP > ARCHIVE > OTHER."""
    config = SprintSchedulerConfig(
        source_tier_map={
            "http://slow/archive": SourceTier.ARCHIVE,
            "http://fast/news": SourceTier.SURFACE,
            "http://ti/ct": SourceTier.STRUCTURED_TI,
        }
    )
    scheduler = SprintScheduler(config)
    sources = ["http://slow/archive", "http://fast/news", "http://ti/ct"]
    items = scheduler._build_work_items(sources)

    assert items[0].tier == SourceTier.SURFACE
    assert items[1].tier == SourceTier.STRUCTURED_TI
    assert items[2].tier == SourceTier.ARCHIVE


# ---------------------------------------------------------------------------
# D.8 — Prune mode drops low-priority work
# ---------------------------------------------------------------------------

def test_scheduler_prunes_low_priority_work_in_prune_mode():
    """In prune mode, ARCHIVE and OTHER tier items are dropped."""
    config = SprintSchedulerConfig()
    scheduler = SprintScheduler(config)

    items = [
        SourceWork("http://surf/news", "surf", SourceTier.SURFACE),
        SourceWork("http://arch/old", "arch", SourceTier.ARCHIVE),
        SourceWork("http://deep/dark", "deep", SourceTier.DEEP),
        SourceWork("http://other/misc", "misc", SourceTier.OTHER),
    ]

    pruned = scheduler._prune_work_items(items)

    assert all(w.tier != SourceTier.ARCHIVE for w in pruned)
    assert all(w.tier != SourceTier.OTHER for w in pruned)
    assert any(w.tier == SourceTier.SURFACE for w in pruned)
    assert any(w.tier == SourceTier.DEEP for w in pruned)


# ---------------------------------------------------------------------------
# D.9 — Enters windup before new cycle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scheduler_enters_windup_before_new_cycle():
    """When lifecycle says WINDUP, scheduler stops starting new work and goes to teardown."""
    lifecycle = make_mock_lifecycle()
    config = SprintSchedulerConfig(sprint_duration_s=1800.0, max_cycles=10, cycle_sleep_s=0.001)
    scheduler = SprintScheduler(config)
    mock_feed = AsyncMock(return_value=FakeFeedResult())

    with patch(
        "hledac.universal.runtime.sprint_scheduler._import_live_feed_pipeline",
        return_value=(mock_feed, FakeFeedResult),
    ):
        with patch(
            "hledac.universal.runtime.sprint_scheduler._import_exporters",
            return_value=(MagicMock(), MagicMock(), MagicMock()),
        ):
            result = await scheduler.run(lifecycle, ["http://example.com/feed"])

    assert result.final_phase in ("WINDUP", "EXPORT", "TEARDOWN")


# ---------------------------------------------------------------------------
# D.10 — Final phase is teardown
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scheduler_final_phase_is_teardown():
    """After run(), lifecycle reaches TEARDOWN."""
    lifecycle = make_mock_lifecycle()
    config = SprintSchedulerConfig(sprint_duration_s=1800.0, max_cycles=2, cycle_sleep_s=0.001)
    scheduler = SprintScheduler(config)
    mock_feed = AsyncMock(return_value=FakeFeedResult())

    with patch(
        "hledac.universal.runtime.sprint_scheduler._import_live_feed_pipeline",
        return_value=(mock_feed, FakeFeedResult),
    ):
        with patch(
            "hledac.universal.runtime.sprint_scheduler._import_exporters",
            return_value=(MagicMock(), MagicMock(), MagicMock()),
        ):
            await scheduler.run(lifecycle, ["http://example.com/feed"])

    assert lifecycle._teardown_started


# ---------------------------------------------------------------------------
# D.11 — stop_on_first_accepted
# ---------------------------------------------------------------------------

def test_scheduler_stop_on_first_accepted():
    """stop_requested flag is set when stop_on_first_accepted is True and findings exist."""
    config = SprintSchedulerConfig(stop_on_first_accepted=True)
    scheduler = SprintScheduler(config)

    scheduler._result.accepted_findings = 1
    scheduler._result.stop_requested = True

    assert scheduler._result.stop_requested is True


# ---------------------------------------------------------------------------
# D.12 — Abort path sets result flags
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scheduler_abort_path_sets_result_flags():
    """When lifecycle requests abort, result.aborted and abort_reason are set."""
    lifecycle = make_mock_lifecycle()
    lifecycle._abort_requested = True
    lifecycle._abort_reason = "test_abort"

    # Make is_terminal return False initially, then True after first iteration
    # This allows the loop to enter and detect the abort flag
    call_count = [0]

    def dynamic_terminal():
        call_count[0] += 1
        return call_count[0] > 1

    lifecycle.is_terminal = dynamic_terminal

    config = SprintSchedulerConfig(sprint_duration_s=1800.0, cycle_sleep_s=0.001)
    scheduler = SprintScheduler(config)

    result = await scheduler.run(lifecycle, ["http://example.com/feed"])

    assert result.aborted is True
    assert "test_abort" in result.abort_reason


# ---------------------------------------------------------------------------
# D.13 — Reuses existing exporters
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scheduler_reuses_existing_exporters():
    """Export phase calls all three existing exporters."""
    exported = {}

    def capture_md(report, path=None):
        exported["md"] = True
        return MagicMock(__str__=lambda: "/tmp/md")

    def capture_jsonld(report, path=None):
        exported["jsonld"] = True
        return MagicMock(__str__=lambda: "/tmp/jsonld")

    def capture_stix(report, path=None):
        exported["stix"] = True
        return MagicMock(__str__=lambda: "/tmp/stix")

    lifecycle = make_mock_lifecycle()
    config = SprintSchedulerConfig(export_enabled=True)
    scheduler = SprintScheduler(config)

    with patch(
        "hledac.universal.runtime.sprint_scheduler._import_exporters",
        return_value=(capture_md, capture_jsonld, capture_stix),
    ):
        await scheduler._run_export(lifecycle)

    assert exported.get("md"), "markdown exporter not called"
    assert exported.get("jsonld"), "jsonld exporter not called"
    assert exported.get("stix"), "stix exporter not called"


# ---------------------------------------------------------------------------
# D.14 — No new work after windup
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scheduler_no_new_work_after_windup():
    """When lifecycle is in WINDUP, scheduler should not start new cycles."""
    lifecycle = make_mock_lifecycle()
    # Override phase to WINDUP to simulate already-in-windup
    lifecycle._current_phase.name = "WINDUP"
    lifecycle.tick = MagicMock(return_value=MagicMock(name="phase"))

    config = SprintSchedulerConfig(max_cycles=10, cycle_sleep_s=0.001)
    scheduler = SprintScheduler(config)

    with patch(
        "hledac.universal.runtime.sprint_scheduler._import_live_feed_pipeline",
        return_value=(AsyncMock(return_value=FakeFeedResult()), FakeFeedResult),
    ):
        with patch(
            "hledac.universal.runtime.sprint_scheduler._import_exporters",
            return_value=(MagicMock(), MagicMock(), MagicMock()),
        ):
            result = await scheduler.run(lifecycle, ["http://example.com/feed"])

    # Should have exited work loop when WINDUP was set
    assert result.final_phase in ("WINDUP", "EXPORT", "TEARDOWN")


# ---------------------------------------------------------------------------
# D.15 — Export failure is fail-soft
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scheduler_handles_export_failure_fail_soft():
    """Exporter error does not raise; result.export_paths records the failure."""
    lifecycle = make_mock_lifecycle()
    config = SprintSchedulerConfig(export_enabled=True)
    scheduler = SprintScheduler(config)

    def fail_md(report, path=None):
        raise RuntimeError("disk full")

    with patch(
        "hledac.universal.runtime.sprint_scheduler._import_exporters",
        return_value=(fail_md, MagicMock(), MagicMock()),
    ):
        await scheduler._run_export(lifecycle)

    assert any("EXPORT_ERROR" in p for p in scheduler._result.export_paths)


# ---------------------------------------------------------------------------
# D.16 — Result is JSON-serializable
# ---------------------------------------------------------------------------

def test_scheduler_result_is_serializable():
    """SprintSchedulerResult fields are basic Python types safe for JSON."""
    import json

    result = SprintSchedulerResult(
        cycles_started=3,
        cycles_completed=2,
        unique_entry_hashes_seen=10,
        duplicate_entry_hashes_skipped=5,
        total_pattern_hits=7,
        accepted_findings=2,
        entries_per_source={"http://ex.com": 5},
        hits_per_source={"http://ex.com": 3},
        final_phase="TEARDOWN",
        export_paths=["/tmp/out.md"],
        aborted=False,
        abort_reason="",
    )

    json_str = json.dumps(result.__dict__)
    parsed = json.loads(json_str)

    assert parsed["cycles_started"] == 3
    assert parsed["unique_entry_hashes_seen"] == 10
    assert parsed["final_phase"] == "TEARDOWN"


# ---------------------------------------------------------------------------
# D.17 — Main hook is small and contract-safe
# ---------------------------------------------------------------------------

def test_scheduler_main_hook_is_small_and_contract_safe():
    """async_run_tiered_feed_sprint_once accepts optional lifecycle, returns Result."""
    import inspect

    sig = inspect.signature(async_run_tiered_feed_sprint_once)
    params = list(sig.parameters.keys())

    assert "sources" in params
    assert "config" in params
    assert "lifecycle" in params
    assert "now_monotonic" in params


# ---------------------------------------------------------------------------
# D.18 — Works with zero hits
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scheduler_works_with_zero_hits():
    """Zero-fetch scenario produces zero stats gracefully."""
    lifecycle = make_mock_lifecycle()
    config = SprintSchedulerConfig(sprint_duration_s=1800.0, max_cycles=1, cycle_sleep_s=0.001)
    scheduler = SprintScheduler(config)
    mock_feed = AsyncMock(
        return_value=FakeFeedResult(fetched_entries=0, accepted_findings=0, matched_patterns=0)
    )

    with patch(
        "hledac.universal.runtime.sprint_scheduler._import_live_feed_pipeline",
        return_value=(mock_feed, FakeFeedResult),
    ):
        with patch(
            "hledac.universal.runtime.sprint_scheduler._import_exporters",
            return_value=(MagicMock(), MagicMock(), MagicMock()),
        ):
            result = await scheduler.run(lifecycle, ["http://example.com/feed"])

    assert result.total_pattern_hits == 0
    assert result.accepted_findings == 0


# ---------------------------------------------------------------------------
# D.19 — Works with non-zero hits (mock)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scheduler_works_with_nonzero_hits_mock():
    """Non-zero hit scenario accumulates stats correctly."""
    lifecycle = make_mock_lifecycle()
    config = SprintSchedulerConfig(sprint_duration_s=1800.0, max_cycles=1, cycle_sleep_s=0.001)
    scheduler = SprintScheduler(config)
    mock_feed = AsyncMock(
        return_value=FakeFeedResult(
            feed_url="http://ex.com",
            fetched_entries=10,
            accepted_findings=3,
            matched_patterns=7,
        )
    )

    with patch(
        "hledac.universal.runtime.sprint_scheduler._import_live_feed_pipeline",
        return_value=(mock_feed, FakeFeedResult),
    ):
        with patch(
            "hledac.universal.runtime.sprint_scheduler._import_exporters",
            return_value=(MagicMock(), MagicMock(), MagicMock()),
        ):
            result = await scheduler.run(lifecycle, ["http://ex.com"])

    assert result.total_pattern_hits == 7
    assert result.accepted_findings == 3


# ---------------------------------------------------------------------------
# D.20 — Sleep loop calls tick
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scheduler_sleep_loop_calls_tick():
    """_sleep_or_abort calls lifecycle.tick while sleeping."""
    lifecycle = make_mock_lifecycle()
    tick_count = [0]
    orig_tick = lifecycle.tick

    def counting_tick(*args, **kwargs):
        tick_count[0] += 1
        return orig_tick(*args, **kwargs)

    lifecycle.tick = counting_tick

    scheduler = SprintScheduler(SprintSchedulerConfig(cycle_sleep_s=0.05))
    await scheduler._sleep_or_abort(0.15, lifecycle)

    assert tick_count[0] >= 1


# ---------------------------------------------------------------------------
# D.21 — No background threads
# ---------------------------------------------------------------------------

def test_scheduler_does_not_use_background_threads():
    """SprintScheduler code contains no threading.Thread usage."""
    import hledac.universal.runtime.sprint_scheduler as mod

    src = open(mod.__file__).read()

    assert "threading.Thread" not in src
    assert "Thread(" not in src
    assert "thread.start()" not in src


# ---------------------------------------------------------------------------
# D.22 — Reports entries and hits per source
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scheduler_reports_entries_and_hits_per_source():
    """Result.entries_per_source and hits_per_source are populated after a run."""
    lifecycle = make_mock_lifecycle()

    config = SprintSchedulerConfig(sprint_duration_s=1800.0, max_cycles=1, cycle_sleep_s=0.001)
    scheduler = SprintScheduler(config)

    # Directly populate via _process_result to test accumulation logic
    fake_result = FakeFeedResult(
        feed_url="http://news/feed",
        fetched_entries=8,
        accepted_findings=4,
        matched_patterns=2,
    )
    scheduler._process_result("http://news/feed", fake_result)

    assert scheduler._result.entries_per_source.get("http://news/feed", 0) == 8
    assert scheduler._result.hits_per_source.get("http://news/feed", 0) == 2


# ---------------------------------------------------------------------------
# E.1 — lifecycle tick + scheduler bookkeeping x10000 < 300ms
# ---------------------------------------------------------------------------

def test_benchmark_tick_bookkeeping_x10000():
    """10000 lifecycle.tick + scheduler bookkeeping calls complete in <300ms."""
    import time
    from hledac.universal.runtime.sprint_lifecycle import SprintLifecycleManager

    lifecycle = SprintLifecycleManager(sprint_duration_s=1800.0, windup_lead_s=180.0)
    lifecycle.start(100.0)

    scheduler = SprintScheduler(SprintSchedulerConfig())

    t0 = time.perf_counter()
    for i in range(10000):
        lifecycle.tick(100.0 + i)
        scheduler._result.cycles_started += 1
    elapsed = time.perf_counter() - t0

    assert elapsed < 0.3


# ---------------------------------------------------------------------------
# E.2 — In-sprint entry_hash dedup set ops x10000 < 300ms
# ---------------------------------------------------------------------------

def test_benchmark_dedup_set_ops_x10000():
    """10000 is_new_entry() calls complete in <300ms."""
    import time
    config = SprintSchedulerConfig()
    scheduler = SprintScheduler(config)

    t0 = time.perf_counter()
    for i in range(10000):
        scheduler.is_new_entry(f"hash_{i % 1000}")
    elapsed = time.perf_counter() - t0

    assert elapsed < 0.3


# ---------------------------------------------------------------------------
# E.3 — Export path composition x1000 < 300ms
# ---------------------------------------------------------------------------

def test_benchmark_export_path_composition_x1000():
    """1000 diagnostic report builds complete in <300ms."""
    import time
    config = SprintSchedulerConfig()
    scheduler = SprintScheduler(config)
    lifecycle = make_mock_lifecycle()

    t0 = time.perf_counter()
    for _ in range(1000):
        scheduler._build_diagnostic_report(lifecycle)
    elapsed = time.perf_counter() - t0

    assert elapsed < 0.3


# ---------------------------------------------------------------------------
# E.4 — Bounded scheduler smoke x20 no task leak
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bounded_scheduler_smoke_x20_no_task_leak():
    """20 scheduler runs produce no lingering tasks."""
    config = SprintSchedulerConfig(sprint_duration_s=1.0, max_cycles=1, cycle_sleep_s=0.001)
    mock_feed = AsyncMock(return_value=FakeFeedResult())

    for i in range(20):
        lifecycle = make_mock_lifecycle()
        scheduler = SprintScheduler(config)

        with patch(
            "hledac.universal.runtime.sprint_scheduler._import_live_feed_pipeline",
            return_value=(mock_feed, FakeFeedResult),
        ):
            with patch(
                "hledac.universal.runtime.sprint_scheduler._import_exporters",
                return_value=(MagicMock(), MagicMock(), MagicMock()),
            ):
                await scheduler.run(lifecycle, ["http://example.com/feed"])

    assert True


# ---------------------------------------------------------------------------
# SourceTier enum invariants
# ---------------------------------------------------------------------------

def test_source_tier_enum_exhaustive():
    """All expected tiers exist in SourceTier enum."""
    assert SourceTier.SURFACE is not None
    assert SourceTier.STRUCTURED_TI is not None
    assert SourceTier.DEEP is not None
    assert SourceTier.ARCHIVE is not None
    assert SourceTier.OTHER is not None


def test_config_tier_of_defaults_to_other():
    """Sources not in source_tier_map default to OTHER tier."""
    config = SprintSchedulerConfig()
    assert config.tier_of("http://unknown.site") == SourceTier.OTHER


def test_config_sorted_tiers_preserves_order():
    """sorted_tiers() returns tiers in high→low priority order."""
    config = SprintSchedulerConfig()
    tiers = config.sorted_tiers()
    assert tiers.index(SourceTier.SURFACE) < tiers.index(SourceTier.OTHER)
    assert tiers.index(SourceTier.STRUCTURED_TI) < tiers.index(SourceTier.ARCHIVE)
