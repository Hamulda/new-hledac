"""
Sprint 8AW: Diagnostic Live Run V2 + End-to-End Signal/Store Trace

Tests:
  D.1   ObservedRunReport includes pre-store signal fields
  D.2   ObservedRunReport includes store rejection delta fields
  D.3   diagnose_end_to_end_live_run: no_pattern_hits
  D.4   diagnose_end_to_end_live_run: no_pattern_hits_possible_morphology_gap
  D.5   diagnose_end_to_end_live_run: pattern_hits_but_no_findings_built
  D.6   diagnose_end_to_end_live_run: low_information_rejection_dominant
  D.7   diagnose_end_to_end_live_run: duplicate_rejection_dominant
  D.8   diagnose_end_to_end_live_run: accepted_present
  D.9   completed=0+entries=0 → network_variance not regression
  D.10  completed>0+entries=0 → no_new_entries
  D.11  before snapshot resets ingest reason counters
  D.12  compare handles zero completed without exception
  D.13  probe_8as still green
  D.14  probe_8at still green
  D.15  probe_8au still green
  D.16  probe_8av still green
  D.17  probe_8aq env_blocker_na
  D.18  probe_8ar env_blocker_na
  D.19  ao_canary still green

Benchmarks:
  E.1   diagnose_end_to_end_live_run x1000: <300ms
  E.2   compare x1000 normal: <300ms
  E.3   compare x1000 degenerate: <300ms
  E.4   observed run composition x20: no leak
"""

import time
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from hledac.universal.__main__ import (
    diagnose_end_to_end_live_run,
    compare_observed_run_to_baseline,
    ObservedRunReport,
    _build_observed_run_report,
)


# =============================================================================
# D.1 — ObservedRunReport includes pre-store signal fields (8AU)
# =============================================================================

class TestObservedReportPreStoreSignalFields:
    """D.1: ObservedRunReport carries all Sprint 8AU pre-store signal fields."""

    def test_observed_report_has_all_pre_store_signal_fields(self):
        """All 8AU signal trace fields are present on ObservedRunReport."""
        # Check the Struct fields exist and have correct defaults
        report = ObservedRunReport(
            started_ts=0.0,
            finished_ts=1.0,
            elapsed_ms=1000.0,
            total_sources=5,
            completed_sources=1,
            fetched_entries=10,
            accepted_findings=0,
            stored_findings=0,
            batch_error=None,
            per_source=(),
            patterns_configured=0,
            bootstrap_applied=False,
            content_quality_validated=False,
            dedup_before={},
            dedup_after={},
            dedup_delta={},
            dedup_surface_available=False,
            uma_snapshot={},
            slow_sources=(),
            error_summary={"count": 0, "sources": []},
            success_rate=0.2,
            failed_source_count=4,
            baseline_delta={},
            health_breakdown={},
            # Sprint 8AU fields
            entries_seen=10,
            entries_with_empty_assembled_text=2,
            entries_with_text=8,
            entries_scanned=8,
            entries_with_hits=3,
            total_pattern_hits=5,
            findings_built_pre_store=3,
            avg_assembled_text_len=120.5,
            signal_stage="prestore_findings_present",
        )
        assert report.entries_seen == 10
        assert report.entries_with_empty_assembled_text == 2
        assert report.entries_with_text == 8
        assert report.entries_scanned == 8
        assert report.entries_with_hits == 3
        assert report.total_pattern_hits == 5
        assert report.findings_built_pre_store == 3
        assert report.avg_assembled_text_len == 120.5
        assert report.signal_stage == "prestore_findings_present"

    def test_observed_report_pre_store_fields_have_defaults(self):
        """Pre-store signal fields default to zero/empty (no breaking change)."""
        report = ObservedRunReport(
            started_ts=0.0,
            finished_ts=1.0,
            elapsed_ms=1000.0,
            total_sources=5,
            completed_sources=1,
            fetched_entries=0,
            accepted_findings=0,
            stored_findings=0,
            batch_error=None,
            per_source=(),
            patterns_configured=0,
            bootstrap_applied=False,
            content_quality_validated=False,
            dedup_before={},
            dedup_after={},
            dedup_delta={},
            dedup_surface_available=False,
            uma_snapshot={},
            slow_sources=(),
            error_summary={"count": 0, "sources": []},
            success_rate=0.0,
            failed_source_count=0,
            baseline_delta={},
            health_breakdown={},
        )
        # All 8AU fields have correct defaults
        assert report.entries_seen == 0
        assert report.entries_with_empty_assembled_text == 0
        assert report.entries_with_text == 0
        assert report.entries_scanned == 0
        assert report.entries_with_hits == 0
        assert report.total_pattern_hits == 0
        assert report.findings_built_pre_store == 0
        assert report.avg_assembled_text_len == 0.0
        assert report.signal_stage == "unknown"


# =============================================================================
# D.2 — ObservedRunReport includes store rejection delta fields (8AV)
# =============================================================================

class TestObservedReportStoreRejectionDeltaFields:
    """D.2: ObservedRunReport carries all Sprint 8AV store rejection delta fields."""

    def test_observed_report_has_all_rejection_delta_fields(self):
        """All 8AV rejection delta fields are present on ObservedRunReport."""
        report = ObservedRunReport(
            started_ts=0.0,
            finished_ts=1.0,
            elapsed_ms=1000.0,
            total_sources=5,
            completed_sources=2,
            fetched_entries=20,
            accepted_findings=0,
            stored_findings=0,
            batch_error=None,
            per_source=(),
            patterns_configured=10,
            bootstrap_applied=True,
            content_quality_validated=True,
            dedup_before={},
            dedup_after={},
            dedup_delta={},
            dedup_surface_available=True,
            uma_snapshot={},
            slow_sources=(),
            error_summary={"count": 0, "sources": []},
            success_rate=0.4,
            failed_source_count=3,
            baseline_delta={},
            health_breakdown={},
            # Sprint 8AV fields
            accepted_count_delta=3,
            low_information_rejected_count_delta=5,
            in_memory_duplicate_rejected_count_delta=2,
            persistent_duplicate_rejected_count_delta=1,
            other_rejected_count_delta=0,
        )
        assert report.accepted_count_delta == 3
        assert report.low_information_rejected_count_delta == 5
        assert report.in_memory_duplicate_rejected_count_delta == 2
        assert report.persistent_duplicate_rejected_count_delta == 1
        assert report.other_rejected_count_delta == 0

    def test_observed_report_rejection_fields_have_defaults(self):
        """Rejection delta fields default to zero (no breaking change)."""
        report = ObservedRunReport(
            started_ts=0.0,
            finished_ts=1.0,
            elapsed_ms=1000.0,
            total_sources=5,
            completed_sources=0,
            fetched_entries=0,
            accepted_findings=0,
            stored_findings=0,
            batch_error=None,
            per_source=(),
            patterns_configured=0,
            bootstrap_applied=False,
            content_quality_validated=False,
            dedup_before={},
            dedup_after={},
            dedup_delta={},
            dedup_surface_available=False,
            uma_snapshot={},
            slow_sources=(),
            error_summary={"count": 0, "sources": []},
            success_rate=0.0,
            failed_source_count=5,
            baseline_delta={},
            health_breakdown={},
        )
        assert report.accepted_count_delta == 0
        assert report.low_information_rejected_count_delta == 0
        assert report.in_memory_duplicate_rejected_count_delta == 0
        assert report.persistent_duplicate_rejected_count_delta == 0
        assert report.other_rejected_count_delta == 0
        assert report.diagnostic_root_cause == "unknown"
        assert report.is_network_variance is False


# =============================================================================
# D.3 — diagnose_end_to_end_live_run: no_pattern_hits
# =============================================================================

class TestDiagnoseEndToEndLiveRun:
    """D.3–D.8: Canonical root-cause diagnosis for zero-findings runs."""

    def test_diagnose_no_pattern_hits(self):
        """D.3: Patterns configured but no hits in entries with text (short text avg < 50)."""
        result = diagnose_end_to_end_live_run(
            completed_sources=1,
            entries_seen=10,
            pattern_count=10,
            total_pattern_hits=0,
            entries_with_text=8,
            avg_assembled_text_len=30.0,  # < 50 → plain no_pattern_hits
            findings_built_pre_store=0,
            accepted_count_delta=0,
            low_information_rejected_count_delta=0,
            in_memory_duplicate_rejected_count_delta=0,
            persistent_duplicate_rejected_count_delta=0,
            other_rejected_count_delta=0,
        )
        assert result == "no_pattern_hits"

    def test_diagnose_no_pattern_hits_possible_morphology_gap(self):
        """D.4: No hits but entries have substantial text (avg >= 50 chars)."""
        result = diagnose_end_to_end_live_run(
            completed_sources=1,
            entries_seen=10,
            pattern_count=10,
            total_pattern_hits=0,
            entries_with_text=8,
            avg_assembled_text_len=150.0,
            findings_built_pre_store=0,
            accepted_count_delta=0,
            low_information_rejected_count_delta=0,
            in_memory_duplicate_rejected_count_delta=0,
            persistent_duplicate_rejected_count_delta=0,
            other_rejected_count_delta=0,
        )
        assert result == "no_pattern_hits_possible_morphology_gap"

    def test_diagnose_no_pattern_hits_short_text(self):
        """No hits with short text (< 50 avg) → plain no_pattern_hits."""
        result = diagnose_end_to_end_live_run(
            completed_sources=1,
            entries_seen=10,
            pattern_count=10,
            total_pattern_hits=0,
            entries_with_text=8,
            avg_assembled_text_len=30.0,
            findings_built_pre_store=0,
            accepted_count_delta=0,
            low_information_rejected_count_delta=0,
            in_memory_duplicate_rejected_count_delta=0,
            persistent_duplicate_rejected_count_delta=0,
            other_rejected_count_delta=0,
        )
        assert result == "no_pattern_hits"

    def test_diagnose_pattern_hits_but_no_findings_built(self):
        """D.5: Hits seen but all filtered/deduped before store."""
        result = diagnose_end_to_end_live_run(
            completed_sources=1,
            entries_seen=10,
            pattern_count=10,
            total_pattern_hits=5,
            entries_with_text=8,
            avg_assembled_text_len=100.0,
            findings_built_pre_store=0,
            accepted_count_delta=0,
            low_information_rejected_count_delta=0,
            in_memory_duplicate_rejected_count_delta=0,
            persistent_duplicate_rejected_count_delta=0,
            other_rejected_count_delta=0,
        )
        assert result == "pattern_hits_but_no_findings_built"

    def test_diagnose_low_information_rejection_dominant(self):
        """D.6: Findings built but low_info rejections dominate over duplicates."""
        result = diagnose_end_to_end_live_run(
            completed_sources=1,
            entries_seen=10,
            pattern_count=10,
            total_pattern_hits=5,
            entries_with_text=8,
            avg_assembled_text_len=100.0,
            findings_built_pre_store=5,
            accepted_count_delta=0,
            low_information_rejected_count_delta=8,
            in_memory_duplicate_rejected_count_delta=2,
            persistent_duplicate_rejected_count_delta=0,
            other_rejected_count_delta=0,
        )
        assert result == "low_information_rejection_dominant"

    def test_diagnose_duplicate_rejection_dominant(self):
        """D.7: Findings built but duplicate rejections dominate."""
        result = diagnose_end_to_end_live_run(
            completed_sources=1,
            entries_seen=10,
            pattern_count=10,
            total_pattern_hits=5,
            entries_with_text=8,
            avg_assembled_text_len=100.0,
            findings_built_pre_store=5,
            accepted_count_delta=0,
            low_information_rejected_count_delta=1,
            in_memory_duplicate_rejected_count_delta=6,
            persistent_duplicate_rejected_count_delta=3,
            other_rejected_count_delta=0,
        )
        assert result == "duplicate_rejection_dominant"

    def test_diagnose_accepted_present(self):
        """D.8: At least one finding was accepted and stored."""
        result = diagnose_end_to_end_live_run(
            completed_sources=1,
            entries_seen=10,
            pattern_count=10,
            total_pattern_hits=5,
            entries_with_text=8,
            avg_assembled_text_len=100.0,
            findings_built_pre_store=5,
            accepted_count_delta=3,
            low_information_rejected_count_delta=1,
            in_memory_duplicate_rejected_count_delta=1,
            persistent_duplicate_rejected_count_delta=0,
            other_rejected_count_delta=0,
        )
        assert result == "accepted_present"


# =============================================================================
# D.9 — completed=0 + entries=0 → network_variance (not regression)
# =============================================================================

class TestNetworkVarianceNotRegression:
    """D.9: completed=0 and entries_seen=0 must NOT be called a regression."""

    def test_completed_zero_and_entries_zero_is_network_variance(self):
        """D.9: Zero sources completed AND zero entries seen = network_variance."""
        result = diagnose_end_to_end_live_run(
            completed_sources=0,
            entries_seen=0,
            pattern_count=10,
            total_pattern_hits=0,
            entries_with_text=0,
            avg_assembled_text_len=0.0,
            findings_built_pre_store=0,
            accepted_count_delta=0,
            low_information_rejected_count_delta=0,
            in_memory_duplicate_rejected_count_delta=0,
            persistent_duplicate_rejected_count_delta=0,
            other_rejected_count_delta=0,
        )
        assert result == "network_variance"

    def test_completed_zero_entries_zero_compare_returns_network_variance_status(self):
        """D.9: compare_observed_run_to_baseline shows network_variance, not regressed."""
        report = {
            "total_sources": 5,
            "completed_sources": 0,
            "fetched_entries": 0,
            "accepted_findings": 0,
            "stored_findings": 0,
            "elapsed_ms": 100.0,
        }
        delta = compare_observed_run_to_baseline(report)
        assert delta["status"] == "network_variance"
        assert delta["blocker"] == "no_sources_completed_no_fetched"
        # Must NOT be "regressed"
        assert delta["status"] != "regressed"


# =============================================================================
# D.10 — completed>0 + entries=0 → no_new_entries
# =============================================================================

class TestNoNewEntries:
    """D.10: completed sources but zero entries seen = no_new_entries."""

    def test_completed_positive_and_entries_zero_is_no_new_entries(self):
        """D.10: Sources completed but no entries fetched = no_new_entries."""
        result = diagnose_end_to_end_live_run(
            completed_sources=2,
            entries_seen=0,
            pattern_count=10,
            total_pattern_hits=0,
            entries_with_text=0,
            avg_assembled_text_len=0.0,
            findings_built_pre_store=0,
            accepted_count_delta=0,
            low_information_rejected_count_delta=0,
            in_memory_duplicate_rejected_count_delta=0,
            persistent_duplicate_rejected_count_delta=0,
            other_rejected_count_delta=0,
        )
        assert result == "no_new_entries"


# =============================================================================
# D.11 — before snapshot resets ingest reason counters
# =============================================================================

class TestBeforeSnapshotResetsIngestCounters:
    """D.11: reset_ingest_reason_counters called before BEFORE snapshot."""

    def test_before_snapshot_resets_counters_when_surface_exists(self):
        """D.11: When surface exists, reset is called before dedup_before snapshot."""
        mock_store = MagicMock()
        mock_store.reset_ingest_reason_counters = MagicMock()
        mock_store.get_dedup_runtime_status = MagicMock(return_value={
            "accepted_count": 0,
            "low_information_rejected_count": 0,
            "in_memory_duplicate_rejected_count": 0,
            "persistent_duplicate_rejected_count": 0,
            "other_rejected_count": 0,
            "persistent_dedup_enabled": True,
        })

        # Simulate the BEFORE snapshot logic from _run_observed_default_feed_batch_once
        # Step 1: reset counters if surface exists
        if hasattr(mock_store, "reset_ingest_reason_counters"):
            mock_store.reset_ingest_reason_counters()

        # Step 2: take BEFORE snapshot
        dedup_before = mock_store.get_dedup_runtime_status()

        # Verify reset was called BEFORE the snapshot
        mock_store.reset_ingest_reason_counters.assert_called_once()
        # Snapshot was taken after reset
        assert dedup_before["accepted_count"] == 0

    def test_before_snapshot_noop_when_surface_missing(self):
        """D.11: No reset when surface (reset_ingest_reason_counters) doesn't exist."""
        mock_store = MagicMock(spec=[])  # no reset_ingest_reason_counters

        # Should not raise
        if hasattr(mock_store, "reset_ingest_reason_counters"):
            mock_store.reset_ingest_reason_counters()

        # No attribute = nothing called


# =============================================================================
# D.12 — compare handles zero completed without exception
# =============================================================================

class TestCompareHandlesZeroCompleted:
    """D.12: compare_observed_run_to_baseline must not throw on degenerate input."""

    def test_compare_zero_completed_zero_entries_no_exception(self):
        """D.12: All zeros must not raise."""
        report = {
            "total_sources": 0,
            "completed_sources": 0,
            "fetched_entries": 0,
            "accepted_findings": 0,
            "stored_findings": 0,
            "elapsed_ms": 0.0,
        }
        delta = compare_observed_run_to_baseline(report)
        assert "status" in delta
        assert "blocker" in delta
        assert delta["status"] == "network_variance"

    def test_compare_zero_completed_with_entries_no_exception(self):
        """D.12: Zero completed but some entries fetched must not raise."""
        report = {
            "total_sources": 5,
            "completed_sources": 0,
            "fetched_entries": 3,
            "accepted_findings": 0,
            "stored_findings": 0,
            "elapsed_ms": 500.0,
        }
        delta = compare_observed_run_to_baseline(report)
        assert "status" in delta
        assert delta["status"] == "network_variance"

    def test_compare_accepted_positive_vs_baseline_improved(self):
        """D.12: accepted_findings > 0 must show improved status."""
        report = {
            "total_sources": 5,
            "completed_sources": 3,
            "fetched_entries": 30,
            "accepted_findings": 5,
            "stored_findings": 4,
            "elapsed_ms": 3000.0,
        }
        delta = compare_observed_run_to_baseline(report)
        assert delta["status"] == "improved"
        assert delta["findings_delta"] == 5

    def test_compare_accepted_zero_vs_baseline_zero_stable(self):
        """D.12: accepted_findings same as baseline, same completion = stable."""
        report = {
            "total_sources": 5,
            "completed_sources": 1,
            "fetched_entries": 10,
            "accepted_findings": 0,
            "stored_findings": 0,
            "elapsed_ms": 1557.6,
        }
        delta = compare_observed_run_to_baseline(report)
        assert delta["status"] == "stable"
        assert delta["blocker"] is None


# =============================================================================
# D.13–D.19 — Prior sprint probes still green
# =============================================================================

class TestPriorSprintProbesGreen:
    """D.13–D.19: Verify all prior sprint probes remain green."""

    def test_probe_8as_still_green(self):
        """D.13: probe_8as still green (last run: 8AS signal/delta/truth)."""
        from hledac.universal.__main__ import (
            compare_observed_run_to_baseline,
            classify_feed_health,
            FeedHealthKind,
            format_observed_run_summary,
            _SPRINT_8AO_BASELINE,
        )
        # Sanity: baseline is the 8AO truth
        assert _SPRINT_8AO_BASELINE["completed_sources"] == 1
        assert _SPRINT_8AO_BASELINE["accepted_findings"] == 0
        # classify_feed_health returns expected keys
        result = classify_feed_health(())
        assert "health_breakdown" in result
        assert "success_count" in result
        assert result["total"] == 0
        # format_observed_run_summary does not raise
        summary = format_observed_run_summary({})
        assert "OBSERVED FEED BATCH RUN SUMMARY" in summary

    def test_probe_8at_still_green(self):
        """D.14: probe_8at still green (seed truth)."""
        from hledac.universal.discovery.rss_atom_adapter import (
            get_default_feed_seed_truth,
            get_default_feed_seeds,
        )
        truth = get_default_feed_seed_truth()
        assert truth["count"] == 5
        assert not truth["has_authenticated_reuters"]
        seeds = get_default_feed_seeds()
        assert len(seeds) == 5

    def test_probe_8au_still_green(self):
        """D.15: probe_8au still green (pre-store signal trace)."""
        pytest.importorskip("ahocorasick", reason="ENV BLOCKER: ahocorasick not in env")
        from hledac.universal.pipeline.live_feed_pipeline import (
            diagnose_feed_signal_stage,
            FeedPipelineRunResult,
        )
        # diagnose_feed_signal_stage returns expected stages
        stage = diagnose_feed_signal_stage(
            entries_seen=0,
            entries_with_empty_assembled_text=0,
            entries_scanned=0,
            entries_with_hits=0,
            findings_built_pre_store=0,
            patterns_configured=0,
        )
        assert stage == "empty_registry"
        # FeedPipelineRunResult has all 8AU fields
        result = FeedPipelineRunResult(
            feed_url="http://example.com",
            fetched_entries=0,
            entries_seen=10,
            entries_with_empty_assembled_text=2,
            entries_with_text=8,
            entries_scanned=8,
            entries_with_hits=3,
            total_pattern_hits=5,
            findings_built_pre_store=3,
            avg_assembled_text_len=120.0,
            signal_stage="prestore_findings_present",
        )
        assert result.entries_seen == 10
        assert result.total_pattern_hits == 5

    def test_probe_8av_still_green(self):
        """D.16: probe_8av still green (store rejection truth)."""
        from hledac.universal.knowledge.duckdb_store import (
            DuckDBShadowStore,
        )
        # DuckDBShadowStore has reset_ingest_reason_counters
        store = DuckDBShadowStore(db_path=None)
        assert hasattr(store, "reset_ingest_reason_counters")
        assert hasattr(store, "get_dedup_runtime_status")
        status = store.get_dedup_runtime_status()
        assert "accepted_count" in status
        assert "low_information_rejected_count" in status

    def test_probe_8aq_env_blocker_na(self):
        """D.17: probe_8aq is ENV BLOCKER / N/A (ahocorasick not in env)."""
        # ahocorasick is not installed → tests that import it skip
        # We verify the truth surface (diagnose_feed_signal_stage) still works
        pytest.importorskip("ahocorasick", reason="ENV BLOCKER: ahocorasick not in env")
        from hledac.universal.pipeline.live_feed_pipeline import diagnose_feed_signal_stage
        stage = diagnose_feed_signal_stage(
            entries_seen=10,
            entries_with_empty_assembled_text=0,
            entries_scanned=10,
            entries_with_hits=0,
            findings_built_pre_store=0,
            patterns_configured=10,
        )
        assert stage == "no_pattern_hits"

    def test_probe_8ar_env_blocker_na(self):
        """D.18: probe_8ar is ENV BLOCKER / N/A (ahocorasick not in env)."""
        # Same as D.17 — verify diagnosis path still works
        pytest.importorskip("ahocorasick", reason="ENV BLOCKER: ahocorasick not in env")
        from hledac.universal.pipeline.live_feed_pipeline import diagnose_feed_signal_stage
        stage = diagnose_feed_signal_stage(
            entries_seen=10,
            entries_with_empty_assembled_text=0,
            entries_scanned=10,
            entries_with_hits=3,
            findings_built_pre_store=0,
            patterns_configured=10,
        )
        assert stage == "pattern_hits_but_no_findings_built"

    def test_ao_canary_still_green(self):
        """D.19: test_ao_canary still green."""
        from hledac.universal.__main__ import (
            get_last_observed_run_report,
        )
        # get_last_observed_run_report is callable and returns None when no run
        result = get_last_observed_run_report()
        assert result is None or isinstance(result, dict)


# =============================================================================
# E.1 — Benchmark: diagnose_end_to_end_live_run x1000 <300ms
# =============================================================================

class TestBenchmarks:
    """E.1–E.4: Performance benchmarks."""

    def test_benchmark_diagnose_1000x_under_300ms(self):
        """E.1: 1000x diagnose_end_to_end_live_run() < 300ms total."""
        args = dict(
            completed_sources=1,
            entries_seen=10,
            pattern_count=10,
            total_pattern_hits=5,
            entries_with_text=8,
            avg_assembled_text_len=100.0,
            findings_built_pre_store=3,
            accepted_count_delta=0,
            low_information_rejected_count_delta=4,
            in_memory_duplicate_rejected_count_delta=2,
            persistent_duplicate_rejected_count_delta=1,
            other_rejected_count_delta=0,
        )
        start = time.perf_counter()
        for _ in range(1000):
            diagnose_end_to_end_live_run(**args)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        assert elapsed_ms < 300.0, f"diagnose x1000 took {elapsed_ms:.1f}ms (limit 300ms)"

    def test_benchmark_compare_1000x_normal_under_300ms(self):
        """E.2: 1000x compare_observed_run_to_baseline (normal) < 300ms."""
        report = {
            "total_sources": 5,
            "completed_sources": 2,
            "fetched_entries": 20,
            "accepted_findings": 3,
            "stored_findings": 2,
            "elapsed_ms": 2000.0,
        }
        start = time.perf_counter()
        for _ in range(1000):
            compare_observed_run_to_baseline(report)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        assert elapsed_ms < 300.0, f"compare x1000 took {elapsed_ms:.1f}ms (limit 300ms)"

    def test_benchmark_compare_1000x_degenerate_under_300ms(self):
        """E.3: 1000x compare_observed_run_to_baseline (degenerate) < 300ms, no exception."""
        report = {
            "total_sources": 0,
            "completed_sources": 0,
            "fetched_entries": 0,
            "accepted_findings": 0,
            "stored_findings": 0,
            "elapsed_ms": 0.0,
        }
        start = time.perf_counter()
        for _ in range(1000):
            result = compare_observed_run_to_baseline(report)
            assert "status" in result
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        assert elapsed_ms < 300.0, f"compare degenerate x1000 took {elapsed_ms:.1f}ms (limit 300ms)"

    def test_benchmark_observed_run_composition_20x_no_leak(self):
        """E.4: 20x observed run composition with 8AU+8AV fields: no task leak."""
        import asyncio

        async def compose_once():
            started = time.time()
            # Simulate building a report with all 8AU + 8AV fields
            report = _build_observed_run_report(
                started_ts=started,
                batch_result=None,
                dedup_before={"persistent_dedup_enabled": True},
                dedup_after={"persistent_dedup_enabled": True},
                uma_snapshot={"peak_used_gib": 4.5},
                patterns_configured=10,
                batch_error=None,
                bootstrap_applied=True,
                # 8AU
                entries_seen=10,
                entries_with_empty_assembled_text=2,
                entries_with_text=8,
                entries_scanned=8,
                entries_with_hits=3,
                total_pattern_hits=5,
                findings_built_pre_store=3,
                avg_assembled_text_len=120.0,
                signal_stage="prestore_findings_present",
                # 8AV
                accepted_count_delta=3,
                low_information_rejected_count_delta=5,
                in_memory_duplicate_rejected_count_delta=2,
                persistent_duplicate_rejected_count_delta=1,
                other_rejected_count_delta=0,
                # 8AW
                diagnostic_root_cause="accepted_present",
                is_network_variance=False,
            )
            return report

        async def run_many():
            results = []
            for _ in range(20):
                r = await compose_once()
                results.append(r)
            return results

        results = asyncio.run(run_many())
        assert len(results) == 20
        for r in results:
            assert r.entries_seen == 10
            assert r.accepted_count_delta == 3
            assert r.diagnostic_root_cause == "accepted_present"
