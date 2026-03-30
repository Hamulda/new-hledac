"""
Sprint 8C3: Schema stability and disabled-default tests.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
import threading

import pytest


@pytest.fixture(autouse=True)
def fresh_trace_env(monkeypatch, tmp_path):
    """Each test gets fresh trace module state."""
    # Force re-import with fresh state
    if "hledac.universal.utils.flow_trace" in sys.modules:
        mod = sys.modules["hledac.universal.utils.flow_trace"]
        # Reset ALL relevant state
        mod.TRACE_ENABLED = False
        mod.TRACE_SAMPLE_RATE = 1.0
        mod._event_count = 0
        mod._drop_count = 0
        mod._counters = {}
        mod._span_stack = {}
        mod._trace_jsonl_file = None
        mod._trace_jsonl_path = None
        mod._trace_summary_path = None
        mod._run_id = None
        mod._trace_lock = threading.Lock()
        mod._event_buffer = __import__("collections").deque(maxlen=100)
    yield
    # Cleanup
    if "hledac.universal.utils.flow_trace" in sys.modules:
        mod = sys.modules["hledac.universal.utils.flow_trace"]
        mod.TRACE_ENABLED = False


class TestDisabledDefault:
    """Tests for disabled-default behavior."""

    def test_disabled_no_events_recorded(self, fresh_trace_env):
        """When disabled, no events are recorded."""
        import hledac.universal.utils.flow_trace as ft
        ft.TRACE_ENABLED = False

        ft.trace_event("comp", "stage", "test_event", status="ok")
        ft.trace_fetch_start("http://example.com", "curl")
        ft.trace_challenge_issued("http://example.com", "direct_web", "captcha", "curl")
        ft.trace_source_accepted("http://example.com", "indexed_search", "search")

        summary = ft.get_summary()
        assert summary == {}, f"Expected empty dict when disabled, got {summary}"
        assert ft.is_enabled() is False


class TestEnums:
    """Tests for canonical enums."""

    def test_enums_are_frozensets(self, fresh_trace_env):
        """Canonical enums are exposed and are frozensets."""
        import hledac.universal.utils.flow_trace as ft
        assert hasattr(ft, "SOURCE_FAMILY_ENUM")
        assert hasattr(ft, "ACQUISITION_MODE_ENUM")
        assert hasattr(ft, "CHALLENGE_OUTCOME_ENUM")
        assert hasattr(ft, "CHALLENGE_TYPE_ENUM")

        assert "indexed_search" in ft.SOURCE_FAMILY_ENUM
        assert "direct_web" in ft.SOURCE_FAMILY_ENUM
        assert "search" in ft.ACQUISITION_MODE_ENUM
        assert "none" in ft.CHALLENGE_OUTCOME_ENUM
        assert "captcha" in ft.CHALLENGE_TYPE_ENUM

        with pytest.raises(AttributeError):
            ft.SOURCE_FAMILY_ENUM.add("new")


class TestCoreSchema:
    """Tests for core trace_event schema preservation."""

    def test_basic_trace_event_schema_preserved(self, fresh_trace_env, tmp_path):
        """Base trace_event field names are unchanged."""
        import hledac.universal.utils.flow_trace as ft
        ft.TRACE_ENABLED = True

        jsonl_path = str(tmp_path / "test_schema.jsonl")
        summary_path = str(tmp_path / "test_schema_summary.json")

        original_get = ft._get_trace_paths
        ft._get_trace_paths = lambda: (Path(jsonl_path), Path(summary_path))
        ft._trace_jsonl_file = None
        ft._trace_jsonl_path = None
        ft.set_run_id("schema_test")

        ft.trace_event(
            component="fetch_coordinator",
            stage="fetch",
            event_type="fetch_start",
            url="http://example.com",
            target="curl",
            status="ok",
            duration_ms=5.0,
        )
        ft.flush()
        ft._get_trace_paths = original_get

        with open(jsonl_path, "r") as f:
            line = f.readline()
        event = json.loads(line)

        assert "ts" in event
        assert "run_id" in event
        assert "component" in event
        assert "stage" in event
        assert "event_type" in event
        assert "url" in event
        assert "target" in event
        assert "status" in event
        assert "elapsed_ms" in event
        assert "metadata" in event


class TestBoundedMetadata:
    """Tests for bounded metadata behavior."""

    def test_list_bounded_to_20(self, fresh_trace_env, tmp_path):
        """Oversized lists are bounded to 20 items."""
        import hledac.universal.utils.flow_trace as ft
        ft.TRACE_ENABLED = True

        jsonl_path = str(tmp_path / "bounded_list.jsonl")
        summary_path = str(tmp_path / "bounded_list_summary.json")

        original_get = ft._get_trace_paths
        ft._get_trace_paths = lambda: (Path(jsonl_path), Path(summary_path))
        ft._trace_jsonl_file = None
        ft._trace_jsonl_path = None
        ft.set_run_id("list_bounded")

        ft.trace_event("comp", "stage", "test", metadata={"data": list(range(100))})
        ft.flush()
        ft._get_trace_paths = original_get

        with open(jsonl_path, "r") as f:
            event = json.loads(f.readline())

        assert len(event["metadata"]["data"]) <= 20

    def test_nested_dict_bounded_to_10(self, fresh_trace_env, tmp_path):
        """Oversized nested dicts inside metadata are bounded to 10 items."""
        import hledac.universal.utils.flow_trace as ft
        ft.TRACE_ENABLED = True

        jsonl_path = str(tmp_path / "bounded_dict.jsonl")
        summary_path = str(tmp_path / "bounded_dict_summary.json")

        original_get = ft._get_trace_paths
        ft._get_trace_paths = lambda: (Path(jsonl_path), Path(summary_path))
        ft._trace_jsonl_file = None
        ft._trace_jsonl_path = None
        ft.set_run_id("dict_bounded")

        ft.trace_event("comp", "stage", "test", metadata={"nested": {f"key_{i}": i for i in range(50)}})
        ft.flush()
        ft._get_trace_paths = original_get

        with open(jsonl_path, "r") as f:
            event = json.loads(f.readline())

        assert len(event["metadata"]["nested"]) <= 10


class TestFailOpen:
    """Tests for fail-open behavior."""

    def test_file_error_does_not_crash(self, fresh_trace_env):
        """Tracing errors never crash runtime."""
        import hledac.universal.utils.flow_trace as ft
        ft.TRACE_ENABLED = True
        call_count = [0]

        def failing_ensure():
            call_count[0] += 1
            raise OSError("Simulated disk error")

        original_ensure = ft._ensure_file_open
        ft._ensure_file_open = failing_ensure
        ft.set_run_id("fail_open")

        ft.trace_event("comp", "stage", "test", status="ok")
        ft.trace_challenge_issued("http://x.com", "direct_web", "captcha", "curl")

        ft._ensure_file_open = original_ensure
        assert call_count[0] > 0, "Should have attempted to write"


class TestCounters:
    """Tests for counter accumulation."""

    def test_counters_accumulate(self, fresh_trace_env):
        """Counters accumulate correctly."""
        import hledac.universal.utils.flow_trace as ft
        ft.TRACE_ENABLED = True

        ft.trace_counter("test_counter", 1)
        ft.trace_counter("test_counter", 2)
        ft.trace_counter("another", 5)

        summary = ft.get_summary()
        assert summary["counters"].get("test_counter", 0) == 3
        assert summary["counters"].get("another", 0) == 5


class TestSourceAccepted:
    """Tests for trace_source_accepted with Sprint 8C3 flags."""

    def test_all_flags(self, fresh_trace_env, tmp_path):
        """trace_source_accepted accepts all Sprint 8C3 flags."""
        import hledac.universal.utils.flow_trace as ft
        ft.TRACE_ENABLED = True

        jsonl_path = str(tmp_path / "source_accepted.jsonl")
        summary_path = str(tmp_path / "source_accepted_summary.json")

        original_get = ft._get_trace_paths
        ft._get_trace_paths = lambda: (Path(jsonl_path), Path(summary_path))
        ft._trace_jsonl_file = None
        ft._trace_jsonl_path = None
        ft.set_run_id("source_accepted_test")

        ft.trace_source_accepted(
            url="http://example.com",
            source_family="indexed_search",
            acquisition_mode="search",
            content_type="text/html",
            bytes_in=5000,
            bytes_out=200,
            is_hidden_service=True,
            is_archive_hit=True,
            is_passive_hit=False,
            is_unindexed_candidate=True,
            is_decentralized_hit=False,
        )
        ft.flush()
        ft._get_trace_paths = original_get

        with open(jsonl_path, "r") as f:
            event = json.loads(f.readline())

        assert event["event_type"] == "source_accepted"
        assert event["target"] == "indexed_search"
        assert event["metadata"]["content_type"] == "text/html"
        assert event["metadata"]["bytes_in"] == 5000
        assert event["metadata"]["bytes_out"] == 200
        assert event["metadata"]["is_hidden_service"] == 1
        assert event["metadata"]["is_archive_hit"] == 1
        assert event["metadata"]["is_unindexed_candidate"] == 1


class TestChallengeFunnel:
    """Tests for challenge funnel events."""

    def test_challenge_events_emitted(self, fresh_trace_env, tmp_path):
        """Challenge funnel events are correctly emitted."""
        import hledac.universal.utils.flow_trace as ft
        ft.TRACE_ENABLED = True

        jsonl_path = str(tmp_path / "challenge.jsonl")
        summary_path = str(tmp_path / "challenge_summary.json")

        original_get = ft._get_trace_paths
        ft._get_trace_paths = lambda: (Path(jsonl_path), Path(summary_path))
        ft._trace_jsonl_file = None
        ft._trace_jsonl_path = None
        ft.set_run_id("challenge_test")

        ft.trace_challenge_issued("http://x.com", "indexed_search", "captcha", "curl")
        ft.trace_challenge_passed("http://x.com", "indexed_search", "captcha", "curl")
        ft.trace_challenge_failed("http://x.com", "indexed_search", "js_challenge", "curl")
        ft.trace_challenge_loop_detected("http://x.com", "direct_web", "curl")
        ft.trace_clearance_reused("http://x.com", "indexed_search", "curl")
        ft.flush()
        ft._get_trace_paths = original_get

        with open(jsonl_path, "r") as f:
            events = [json.loads(line) for line in f.readlines()]

        event_types = {e["event_type"] for e in events}
        assert "challenge_issued" in event_types
        assert "challenge_passed" in event_types
        assert "challenge_failed" in event_types
        assert "challenge_loop_detected" in event_types
        assert "clearance_reused" in event_types

        for e in events:
            assert e["stage"] == "challenge_funnel"


class TestFallbackEvents:
    """Tests for provider fallback events."""

    def test_fallback_events_emitted(self, fresh_trace_env, tmp_path):
        """Provider fallback events include from/to transport info."""
        import hledac.universal.utils.flow_trace as ft
        ft.TRACE_ENABLED = True

        jsonl_path = str(tmp_path / "fallback.jsonl")
        summary_path = str(tmp_path / "fallback_summary.json")

        original_get = ft._get_trace_paths
        ft._get_trace_paths = lambda: (Path(jsonl_path), Path(summary_path))
        ft._trace_jsonl_file = None
        ft._trace_jsonl_path = None
        ft.set_run_id("fallback_test")

        ft.trace_provider_fallback(
            url="http://x.com",
            source_family="indexed_search",
            from_transport="curl",
            to_transport="lightpanda",
            fallback_reason="403 forbidden",
        )
        ft.trace_fallback_after_403("http://x.com", "indexed_search", "curl")
        ft.trace_fallback_after_429("http://x.com", "direct_web", "curl", retry_after=60)
        ft.flush()
        ft._get_trace_paths = original_get

        with open(jsonl_path, "r") as f:
            events = [json.loads(line) for line in f.readlines()]

        types = {e["event_type"] for e in events}
        assert "provider_fallback" in types
        assert "fallback_after_403" in types
        assert "fallback_after_429" in types

        for e in events:
            if e["event_type"] == "fallback_after_429":
                assert e["metadata"].get("retry_after") == 60


class TestEvidenceFunnel:
    """Tests for extended evidence funnel events."""

    def test_evidence_events_emitted(self, fresh_trace_env, tmp_path):
        """Extended evidence funnel events with quality tiers."""
        import hledac.universal.utils.flow_trace as ft
        ft.TRACE_ENABLED = True

        jsonl_path = str(tmp_path / "evidence.jsonl")
        summary_path = str(tmp_path / "evidence_summary.json")

        original_get = ft._get_trace_paths
        ft._get_trace_paths = lambda: (Path(jsonl_path), Path(summary_path))
        ft._trace_jsonl_file = None
        ft._trace_jsonl_path = None
        ft.set_run_id("evidence_test")

        ft.trace_evidence_append_ext("finding", 5, "ok", "indexed_search", "high", "corr_key_123")
        ft.trace_evidence_emitted("fid1", "indexed_search", "high")
        ft.trace_evidence_corroborated("fid1", "archive", "corr_key_123")
        ft.trace_evidence_rejected_low_quality("fid2", "direct_web", "low_similarity")
        ft.trace_evidence_flush_persisted(10, 5.0, "ok", rows_persisted=10, bytes_written=1024)
        ft.flush()
        ft._get_trace_paths = original_get

        with open(jsonl_path, "r") as f:
            events = [json.loads(line) for line in f.readlines()]

        event_types = {e["event_type"] for e in events}
        assert "evidence_emitted" in event_types
        assert "evidence_corroborated" in event_types
        assert "evidence_rejected_low_quality" in event_types
        assert "evidence_flush_persisted" in event_types


class TestSnapshotEvents:
    """Tests for periodic snapshot events."""

    def test_snapshot_events_emitted(self, fresh_trace_env, tmp_path):
        """Periodic snapshot events are emitted correctly."""
        import hledac.universal.utils.flow_trace as ft
        ft.TRACE_ENABLED = True

        jsonl_path = str(tmp_path / "snapshots.jsonl")
        summary_path = str(tmp_path / "snapshots_summary.json")

        original_get = ft._get_trace_paths
        ft._get_trace_paths = lambda: (Path(jsonl_path), Path(summary_path))
        ft._trace_jsonl_file = None
        ft._trace_jsonl_path = None
        ft.set_run_id("snapshot_test")

        ft.trace_periodic_flow_snapshot(queue_depth=5, frontier_size=20, active_fetches=3, rss_mb=1024.5)
        ft.trace_queue_snapshot("evidence_queue", depth=5, enqueue_rate=1.5, dequeue_rate=1.2)
        ft.trace_transport_mix_snapshot({"curl": 10, "tor": 2, "lightpanda": 3})
        ft.trace_source_family_counts({"indexed_search": 5, "archive": 2})
        ft.flush()
        ft._get_trace_paths = original_get

        with open(jsonl_path, "r") as f:
            events = [json.loads(line) for line in f.readlines()]

        event_types = {e["event_type"] for e in events}
        assert "periodic_flow_snapshot" in event_types
        assert "queue_snapshot" in event_types
        assert "transport_mix_snapshot" in event_types
        assert "source_family_counts" in event_types

        for e in events:
            if e["event_type"] == "periodic_flow_snapshot":
                assert e["metadata"]["rss_mb"] == 1024.5
                assert e["metadata"]["queue_depth"] == 5


class TestBootRegression:
    """Tests for boot performance regression."""

    def test_import_is_fast(self, fresh_trace_env):
        """Importing flow_trace should be fast."""
        import time

        start = time.time()
        import hledac.universal.utils.flow_trace as ft_fresh
        elapsed = time.time() - start

        assert elapsed < 0.5, f"Import took {elapsed:.3f}s, possible heavy import regression"
        ft_fresh.is_enabled()
        ft_fresh.get_summary()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
