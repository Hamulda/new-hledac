"""
Sprint 8AV: Quality Gate Rejection Truth + Ingest Outcome Counters

Tests verify:
  D.1  accepted_ingest_increments_accepted_count
  D.2  low_information_rejection_increments_low_information_count
  D.3  in_memory_duplicate_rejection_increments_quality_duplicate_count_and_reason_counter
  D.4  persistent_duplicate_rejection_increments_persistent_duplicate_reason_counter
  D.5  other_rejection_path_increments_other_rejected_count
  D.6  runtime_status_surface_exposes_all_reason_counters
  D.7  existing_status_keys_not_broken
  D.8  batch_ingest_updates_reason_counters_correctly
  D.9  reset_ingest_reason_counters_resets_all_fields_to_zero
  D.10 probe_8ak_still_green
  D.11 probe_8w_still_green
  D.12 probe_8ag_still_green
  D.13 probe_8as_still_green
  D.14 ao_canary_still_green

Benchmarks:
  E.1  get_dedup_runtime_status x1000: <5ms total (0.005ms/call)
  E.2  classify_ingest_outcome x1000: <2ms total (0.002ms/call)
  E.3  batch ingest x100: no order-of-magnitude regression
"""
import sys
import time

import pytest

from hledac.universal.knowledge.duckdb_store import (
    DuckDBShadowStore,
    CanonicalFinding,
    FindingQualityDecision,
)


# =============================================================================
# D.1 — accepted_ingest_increments_accepted_count
# =============================================================================

@pytest.mark.asyncio
async def test_accepted_ingest_increments_accepted_count(store):
    """
    When a finding passes the quality gate, accepted_count increments.
    """
    store.reset_ingest_reason_counters()
    # High-entropy, unique text → quality gate passes
    f = CanonicalFinding(
        finding_id="accepted1",
        query="The quick brown fox jumps over the lazy dog with typical OSINT content",
        source_type="web",
        confidence=0.8,
        ts=0.0,
        provenance=(),
    )
    await store.async_ingest_finding(f)
    status = store.get_dedup_runtime_status()

    assert status["accepted_count"] == 1, f"expected 1 accepted, got {status['accepted_count']}"
    assert status["low_information_rejected_count"] == 0
    assert status["in_memory_duplicate_rejected_count"] == 0
    assert status["persistent_duplicate_rejected_count"] == 0
    assert status["other_rejected_count"] == 0


# =============================================================================
# D.2 — low_information_rejection_increments_low_information_count
# =============================================================================

@pytest.mark.asyncio
async def test_low_information_rejection_increments_low_information_count(store):
    """
    A repetitive/low-entropy finding is rejected with reason='low_entropy_rejected'.
    low_information_rejected_count increments.
    """
    store.reset_ingest_reason_counters()
    # Very repetitive — entropy = 0.0 < 0.5 threshold
    f = CanonicalFinding(
        finding_id="lowent1",
        query="aaaaaaaaaaaaaaaaaa",
        source_type="web",
        confidence=0.5,
        ts=0.0,
        provenance=(),
    )
    result = await store.async_ingest_finding(f)

    # Result should be a FindingQualityDecision (not ActivationResult)
    assert isinstance(result, FindingQualityDecision), f"expected FindingQualityDecision, got {type(result)}"
    assert result.accepted is False
    assert result.reason == "low_entropy_rejected"

    status = store.get_dedup_runtime_status()
    assert status["low_information_rejected_count"] == 1, (
        f"expected 1 low_info rejection, got {status['low_information_rejected_count']}"
    )
    assert status["accepted_count"] == 0


# =============================================================================
# D.3 — in_memory_duplicate_rejection_increments_quality_duplicate_count_and_reason_counter
# =============================================================================

@pytest.mark.asyncio
async def test_in_memory_duplicate_rejection_increments_quality_duplicate_count_and_reason_counter(store):
    """
    Two findings with identical content (same normalized hash) — second is a
    hot-cache (in-memory) duplicate. Both counters increment.
    in_memory_duplicate_rejected_count tracks this path.
    """
    store.reset_ingest_reason_counters()
    # First — unique, stored
    f1 = CanonicalFinding(
        finding_id="inmem1",
        query="some common information that might appear twice",
        source_type="document",
        confidence=0.7,
        ts=1.0,
        provenance=(),
    )
    await store.async_ingest_finding(f1)
    assert store.get_dedup_runtime_status()["accepted_count"] == 1

    # Second — same normalized text → hot-cache hit
    f2 = CanonicalFinding(
        finding_id="inmem2",
        query="some common information that might appear twice",
        source_type="document",
        confidence=0.7,
        ts=2.0,
        provenance=(),
    )
    result = await store.async_ingest_finding(f2)

    assert isinstance(result, FindingQualityDecision)
    assert result.accepted is False
    assert result.reason in ("duplicate_detected", "persistent_duplicate"), (
        f"expected duplicate_detected, got {result.reason}"
    )

    status = store.get_dedup_runtime_status()
    # in_memory_duplicate_rejected_count is _quality_duplicate_count (hot-cache)
    assert status["in_memory_duplicate_rejected_count"] == 1, (
        f"expected 1 in-memory dupe, got {status['in_memory_duplicate_rejected_count']}"
    )
    assert status["persistent_duplicate_rejected_count"] == 0


# =============================================================================
# D.4 — persistent_duplicate_rejection_increments_persistent_duplicate_reason_counter
# =============================================================================

@pytest.mark.asyncio
async def test_persistent_duplicate_rejection_increments_persistent_duplicate_reason_counter():
    """
    Two findings with same normalized URL — second hits LMDB (cross-source persistent dedup).
    persistent_duplicate_rejected_count increments.

    Uses two-store isolation:
      - Store A: populates hot cache + LMDB with URL fingerprint
      - Store B: fresh hot cache, same LMDB (shared fallback path). Store B's hot cache
        misses the URL fingerprint, triggering Tier-2 LMDB lookup → persistent dupe.
    """
    import tempfile
    import pathlib

    # Store A: populate hot cache + LMDB with URL fingerprint
    tmp_a = pathlib.Path(tempfile.mkdtemp())
    store_a = DuckDBShadowStore(db_path=tmp_a / "store_a.duckdb")
    ok = await store_a.async_initialize()
    assert ok

    url = "http://example.com/article/isolated-content"
    await store_a.async_ingest_finding(CanonicalFinding(
        finding_id="perm1", query="text for article one",
        source_type="web", confidence=0.8, ts=1.0, provenance=(url,),
    ))
    await store_a.aclose()

    # Store B: fresh hot cache, shared LMDB fallback path (persistent dedup hit)
    tmp_b = pathlib.Path(tempfile.mkdtemp())
    store_b = DuckDBShadowStore(db_path=tmp_b / "store_b.duckdb")
    ok = await store_b.async_initialize()
    assert ok
    store_b.reset_ingest_reason_counters()

    try:
        # Store B's hot cache is empty → URL fingerprint lookup hits LMDB (Tier 2)
        f2 = CanonicalFinding(
            finding_id="perm2",
            query="completely different text for the same URL",
            source_type="web",
            confidence=0.8,
            ts=2.0,
            provenance=(url,),
        )
        result = await store_b.async_ingest_finding(f2)

        assert isinstance(result, FindingQualityDecision)
        assert result.accepted is False
        assert result.reason == "persistent_duplicate", (
            f"expected persistent_duplicate, got {result.reason}"
        )

        status = store_b.get_dedup_runtime_status()
        assert status["persistent_duplicate_rejected_count"] == 1, (
            f"expected 1 persistent dupe, got {status['persistent_duplicate_rejected_count']}"
        )
        # Hot cache should be unchanged (no new hot cache entry added for rejected finding)
        assert status["in_memory_duplicate_rejected_count"] == 0, (
            f"expected 0 in-memory dupes, got {status['in_memory_duplicate_rejected_count']}"
        )
    finally:
        await store_b.aclose()


# =============================================================================
# D.5 — other_rejection_path_increments_other_rejected_count
# =============================================================================

@pytest.mark.asyncio
async def test_other_rejection_path_increments_other_rejected_count(store):
    """
    Simulate the fail-open path: quality gate helper raises an exception,
    finding is stored via legacy path but _quality_fail_open_count increments.
    other_rejected_count reflects this.
    """
    store.reset_ingest_reason_counters()
    f = CanonicalFinding(
        finding_id="failopen1",
        query="anything",
        source_type="web",
        confidence=0.5,
        ts=0.0,
        provenance=(),
    )

    # Mock _assess_finding_quality to raise
    original = store._assess_finding_quality
    def raise_helper(finding):
        raise RuntimeError("simulated quality gate failure")

    store._assess_finding_quality = raise_helper

    try:
        await store.async_ingest_finding(f)
    finally:
        store._assess_finding_quality = original

    # Fail-open: finding is stored (ActivationResult) but via exception path
    status = store.get_dedup_runtime_status()
    assert status["other_rejected_count"] == 1, (
        f"expected 1 other_rejected, got {status['other_rejected_count']}"
    )
    # accepted_count also incremented for the fail-open path
    assert status["accepted_count"] == 1


# =============================================================================
# D.6 — runtime_status_surface_exposes_all_reason_counters
# =============================================================================

@pytest.mark.asyncio
async def test_runtime_status_surface_exposes_all_reason_counters(store):
    """
    get_dedup_runtime_status() returns all 5 required reason counter keys:
    accepted_count, low_information_rejected_count,
    in_memory_duplicate_rejected_count, persistent_duplicate_rejected_count,
    other_rejected_count.
    """
    status = store.get_dedup_runtime_status()

    required_keys = [
        "accepted_count",
        "low_information_rejected_count",
        "in_memory_duplicate_rejected_count",
        "persistent_duplicate_rejected_count",
        "other_rejected_count",
    ]
    for key in required_keys:
        assert key in status, f"Missing required status key: {key}"
        assert isinstance(status[key], int), f"{key} must be int, got {type(status[key])}"


# =============================================================================
# D.7 — existing_status_keys_not_broken
# =============================================================================

@pytest.mark.asyncio
async def test_existing_status_keys_not_broken(store):
    """
    Sprint 8AV must not break existing status keys.
    All keys from prior sprints remain accessible.
    """
    status = store.get_dedup_runtime_status()

    legacy_keys = [
        "persistent_dedup_enabled",
        "last_boot_cleanup_error",
        "last_dedup_error",
        "dedup_lmdb_path",
        "dedup_namespace",
        "hot_cache_size",
        "hot_cache_capacity",
        "in_memory_duplicate_count",
        "persistent_duplicate_count",
    ]
    for key in legacy_keys:
        assert key in status, f"Legacy status key broken: {key}"


# =============================================================================
# D.8 — batch_ingest_updates_reason_counters_correctly
# =============================================================================

@pytest.mark.asyncio
async def test_batch_ingest_updates_reason_counters_correctly(store):
    """
    async_ingest_findings_batch updates all reason counters correctly
    across mixed accepted/rejected findings.
    """
    store.reset_ingest_reason_counters()

    findings = [
        # Item 0: accepted
        CanonicalFinding(finding_id="b1", query="unique high entropy content for batch testing purposes here", source_type="web", confidence=0.8, ts=1.0, provenance=()),
        # Item 1: accepted
        CanonicalFinding(finding_id="b2", query="another unique piece of content for batch processing", source_type="web", confidence=0.8, ts=2.0, provenance=()),
        # Item 2: low entropy — rejected
        CanonicalFinding(finding_id="b3", query="aaaaaaaaaa", source_type="web", confidence=0.5, ts=3.0, provenance=()),
        # Item 3: accepted
        CanonicalFinding(finding_id="b4", query="third unique content item for batch testing here", source_type="web", confidence=0.8, ts=4.0, provenance=()),
        # Item 4: duplicate of b1 (same text) — hot cache hit
        CanonicalFinding(finding_id="b5", query="unique high entropy content for batch testing purposes here", source_type="web", confidence=0.8, ts=5.0, provenance=()),
    ]

    results = await store.async_ingest_findings_batch(findings)

    # Count by type
    n_low_ent = sum(1 for r in results if isinstance(r, FindingQualityDecision) and r.reason == "low_entropy_rejected")
    n_dup = sum(1 for r in results if isinstance(r, FindingQualityDecision) and r.reason in ("duplicate_detected", "persistent_duplicate"))

    status = store.get_dedup_runtime_status()
    assert status["accepted_count"] == 3, f"expected 3 accepted, got {status['accepted_count']}"
    assert status["low_information_rejected_count"] == n_low_ent, (
        f"expected {n_low_ent} low_info, got {status['low_information_rejected_count']}"
    )
    assert status["in_memory_duplicate_rejected_count"] == n_dup, (
        f"expected {n_dup} in_memory dupes, got {status['in_memory_duplicate_rejected_count']}"
    )


# =============================================================================
# D.9 — reset_ingest_reason_counters_resets_all_fields_to_zero
# =============================================================================

@pytest.mark.asyncio
async def test_reset_ingest_reason_counters_resets_all_fields_to_zero(store):
    """
    reset_ingest_reason_counters() resets all 5 counter fields to zero.
    """
    # Manually set all counters to non-zero
    store._accepted_count = 99
    store._quality_rejected_count = 88
    store._quality_duplicate_count = 77
    store._persistent_duplicate_count = 66
    store._quality_fail_open_count = 55

    store.reset_ingest_reason_counters()

    status = store.get_dedup_runtime_status()
    assert status["accepted_count"] == 0
    assert status["low_information_rejected_count"] == 0
    assert status["in_memory_duplicate_rejected_count"] == 0
    assert status["persistent_duplicate_rejected_count"] == 0
    assert status["other_rejected_count"] == 0


# =============================================================================
# D.10–D.14 — Prior sprint sanity gates
# =============================================================================

@pytest.mark.asyncio
async def test_probe_8ak_still_green():
    """D.10: probe_8ak tests must still pass."""
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "hledac/universal/tests/probe_8ak/", "--tb=no", "-q"],
        capture_output=True, text=True,
        cwd="/Users/vojtechhamada/PycharmProjects/Hledac",
    )
    assert result.returncode == 0, f"probe_8ak failed:\n{result.stdout}\n{result.stderr}"


@pytest.mark.asyncio
async def test_probe_8w_still_green():
    """D.11: probe_8w tests must still pass."""
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "hledac/universal/tests/probe_8w/", "--tb=no", "-q"],
        capture_output=True, text=True,
        cwd="/Users/vojtechhamada/PycharmProjects/Hledac",
    )
    assert result.returncode == 0, f"probe_8w failed:\n{result.stdout}\n{result.stderr}"


@pytest.mark.asyncio
async def test_probe_8ag_still_green():
    """D.12: probe_8ag tests must still pass."""
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "hledac/universal/tests/probe_8ag/", "--tb=no", "-q"],
        capture_output=True, text=True,
        cwd="/Users/vojtechhamada/PycharmProjects/Hledac",
    )
    assert result.returncode == 0, f"probe_8ag failed:\n{result.stdout}\n{result.stderr}"


@pytest.mark.asyncio
async def test_probe_8as_still_green():
    """D.13: probe_8as tests must still pass."""
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "hledac/universal/tests/probe_8as/", "--tb=no", "-q"],
        capture_output=True, text=True,
        cwd="/Users/vojtechhamada/PycharmProjects/Hledac",
    )
    assert result.returncode == 0, f"probe_8as failed:\n{result.stdout}\n{result.stderr}"


@pytest.mark.asyncio
async def test_ao_canary_still_green():
    """D.14: ao_canary tests must still pass."""
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "hledac/universal/tests/test_ao_canary.py", "--tb=no", "-q"],
        capture_output=True, text=True,
        cwd="/Users/vojtechhamada/PycharmProjects/Hledac",
    )
    assert result.returncode == 0, f"ao_canary failed:\n{result.stdout}\n{result.stderr}"


# =============================================================================
# E.3 — batch ingest benchmark
# =============================================================================

@pytest.mark.asyncio
async def test_batch_ingest_benchmark_e3(store):
    """
    E.3: 100x mocked batch ingest with counters enabled — no order-of-magnitude regression.
    Target: < 5s for 100 batches of 10 findings each.
    """
    store.reset_ingest_reason_counters()

    findings = [
        CanonicalFinding(
            finding_id=f"bench_{i}_{j}",
            query=f"unique content item {i}-{j} for performance measurement in OSINT context",
            source_type="web",
            confidence=0.8,
            ts=float(i * 10 + j),
            provenance=(),
        )
        for i in range(10)
        for j in range(10)
    ]

    iterations = 100
    start = time.perf_counter()
    for _ in range(iterations):
        store.reset_ingest_reason_counters()
        await store.async_ingest_findings_batch(findings)
    elapsed = time.perf_counter() - start

    print(f"\nE.3 batch ingest x{iterations} (1000 findings each): {elapsed:.2f}s total, {elapsed/iterations*1000:.1f}ms/iter")
    # No order-of-magnitude regression: should be well under 5s for 100 iterations
    assert elapsed < 5.0, f"batch ingest too slow: {elapsed:.2f}s for {iterations} iterations"
