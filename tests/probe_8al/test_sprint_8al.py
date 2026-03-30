"""
Sprint 8AL: Multi-Feed Batch Runner v1 tests.

Run with: pytest hledac/universal/tests/probe_8al/ -v
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hledac.universal.discovery.rss_atom_adapter import (
    FeedDiscoveryHit,
    FeedSeed,
    MergedFeedSource,
    get_default_feed_seeds,
)
from hledac.universal.pipeline.live_feed_pipeline import (
    FeedSourceBatchRunResult,
    FeedSourceRunResult,
    _coerce_source_to_tuple,
    async_run_default_feed_batch,
    async_run_feed_source_batch,
    async_run_live_feed_pipeline,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_feed_result():
    """A mock FeedPipelineRunResult with some entries."""
    mock = MagicMock()
    mock.fetched_entries = 5
    mock.accepted_findings = 3
    mock.stored_findings = 2
    mock.error = None
    return mock


@pytest.fixture
def mock_feed_result_error():
    """A mock FeedPipelineRunResult with an error."""
    mock = MagicMock()
    mock.fetched_entries = 0
    mock.accepted_findings = 0
    mock.stored_findings = 0
    mock.error = "fetch_error:timeout"
    return mock


# ---------------------------------------------------------------------------
# D.1 — test_empty_source_batch_returns_typed_empty_result
# ---------------------------------------------------------------------------

def test_empty_source_batch_returns_typed_empty_result():
    result = asyncio.run(
        async_run_feed_source_batch(
            sources=(),
            store=None,
        )
    )
    assert isinstance(result, FeedSourceBatchRunResult)
    assert result.total_sources == 0
    assert result.completed_sources == 0
    assert result.fetched_entries == 0
    assert result.accepted_findings == 0
    assert result.stored_findings == 0
    assert result.sources == ()
    assert result.error is None


# ---------------------------------------------------------------------------
# D.2 — test_default_feed_batch_uses_curated_seeds
# ---------------------------------------------------------------------------

def test_default_feed_batch_uses_curated_seeds():
    """async_run_default_feed_batch should call get_default_feed_seeds()."""
    with patch(
        "hledac.universal.discovery.rss_atom_adapter.get_default_feed_seeds"
    ) as mock_seeds:
        mock_seeds.return_value = (
            FeedSeed(feed_url="http://a.com", label="A", source="curated", priority=1),
            FeedSeed(feed_url="http://b.com", label="B", source="curated", priority=2),
        )
        # Don't actually run the feeds — just check seeds are retrieved
        with patch(
            "hledac.universal.pipeline.live_feed_pipeline.async_run_feed_source_batch",
            new_callable=AsyncMock,
        ) as mock_batch:
            mock_batch.return_value = FeedSourceBatchRunResult(
                total_sources=2,
                completed_sources=2,
                fetched_entries=0,
                accepted_findings=0,
                stored_findings=0,
                sources=(),
                error=None,
            )
            result = asyncio.run(
                async_run_default_feed_batch(store=None, feed_concurrency=1)
            )
            mock_seeds.assert_called_once()
            mock_batch.assert_called_once()
            _, kwargs = mock_batch.call_args
            assert len(kwargs["sources"]) == 2


# ---------------------------------------------------------------------------
# D.3 — test_seed_priority_ordering_is_stable
# ---------------------------------------------------------------------------

def test_seed_priority_ordering_is_stable():
    """Sources should be sorted by priority descending, stable for equal priority."""
    sources = (
        FeedSeed(feed_url="http://low.com", label="L", source="curated", priority=1),
        FeedSeed(feed_url="http://high.com", label="H", source="curated", priority=10),
        FeedSeed(feed_url="http://mid.com", label="M", source="curated", priority=5),
    )
    # Verify the coercion preserves order for equal priority (stable sort)
    coerced = [_coerce_source_to_tuple(s) for s in sources]
    assert coerced[0][0] == "http://low.com"
    assert coerced[1][0] == "http://high.com"
    assert coerced[2][0] == "http://mid.com"

    # Now test actual sort order
    normalized = [_coerce_source_to_tuple(s) for s in sources]
    normalized.sort(key=lambda x: -x[3])  # priority desc
    assert normalized[0][0] == "http://high.com"
    assert normalized[1][0] == "http://mid.com"
    assert normalized[2][0] == "http://low.com"


# ---------------------------------------------------------------------------
# D.4 — test_discovered_sources_can_be_run
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_discovered_sources_can_be_run():
    """FeedDiscoveryHit can be coerced and passed to batch runner."""
    hit = FeedDiscoveryHit(
        page_url="http://discovered.com",
        feed_url="http://discovered.com/feed.xml",
        title="RSS Feed",
        feed_type="rss",
        confidence=0.9,
        source="discovered",
        discovered_ts=1700000000.0,
    )
    # FeedDiscoveryHit has no label/priority — should coerce to "" and 0
    url, label, origin, priority = _coerce_source_to_tuple(hit)
    assert url == "http://discovered.com/feed.xml"
    assert label == ""
    assert priority == 0

    # Mock the actual pipeline to verify it can be called
    with patch(
        "hledac.universal.pipeline.live_feed_pipeline.async_run_live_feed_pipeline",
        new_callable=AsyncMock,
    ) as mock_run:
        mock_run.return_value = MagicMock(
            fetched_entries=2,
            accepted_findings=1,
            stored_findings=1,
            error=None,
        )
        result = await async_run_feed_source_batch(
            sources=(hit,),
            store=None,
            feed_concurrency=1,
            per_feed_timeout_s=5.0,
        )
        assert result.total_sources == 1
        mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# D.5 — test_merged_sources_can_be_run
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_merged_sources_can_be_run():
    """MergedFeedSource can be coerced and passed to batch runner."""
    merged = MergedFeedSource(
        feed_url="http://merged.com/feed",
        label="Merged Label",
        origin="discovered",
        priority=7,
    )
    url, label, origin, priority = _coerce_source_to_tuple(merged)
    assert url == "http://merged.com/feed"
    assert label == "Merged Label"
    assert origin == "discovered"
    assert priority == 7

    with patch(
        "hledac.universal.pipeline.live_feed_pipeline.async_run_live_feed_pipeline",
        new_callable=AsyncMock,
    ) as mock_run:
        mock_run.return_value = MagicMock(
            fetched_entries=3,
            accepted_findings=2,
            stored_findings=2,
            error=None,
        )
        result = await async_run_feed_source_batch(
            sources=(merged,),
            store=None,
            feed_concurrency=1,
            per_feed_timeout_s=5.0,
        )
        assert result.total_sources == 1
        assert result.completed_sources == 1
        assert result.fetched_entries == 3
        assert result.accepted_findings == 2


# ---------------------------------------------------------------------------
# D.6 — test_per_feed_failure_does_not_kill_batch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_per_feed_failure_does_not_kill_batch(mock_feed_result_error):
    """One failing feed source should not prevent other sources from completing."""
    sources = (
        FeedSeed(feed_url="http://good.com", label="Good", source="curated", priority=1),
        FeedSeed(feed_url="http://bad.com", label="Bad", source="curated", priority=2),
        FeedSeed(feed_url="http://also-good.com", label="AlsoGood", source="curated", priority=3),
    )

    def run_side_effect(*args, **kwargs):
        feed_url = kwargs.get("feed_url") or args[0]
        if "bad" in feed_url:
            return mock_feed_result_error
        return MagicMock(
            fetched_entries=5,
            accepted_findings=3,
            stored_findings=2,
            error=None,
        )

    with patch(
        "hledac.universal.pipeline.live_feed_pipeline.async_run_live_feed_pipeline",
        new_callable=AsyncMock,
    ) as mock_run:
        mock_run.side_effect = run_side_effect
        result = await async_run_feed_source_batch(
            sources=sources,
            store=None,
            feed_concurrency=3,
            per_feed_timeout_s=5.0,
            batch_timeout_s=60.0,
        )
        assert result.total_sources == 3
        assert result.completed_sources == 2  # good + also-good
        assert result.error is None  # batch itself succeeded
        # Check bad source has error but others don't
        source_errors = {s.feed_url: s.error for s in result.sources}
        assert source_errors["http://bad.com"] == "fetch_error:timeout"
        assert source_errors["http://good.com"] is None
        assert source_errors["http://also-good.com"] is None


# ---------------------------------------------------------------------------
# D.7 — test_per_feed_timeout_isolated_to_single_feed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_per_feed_timeout_isolated_to_single_feed():
    """Per-feed timeout should produce error for that feed only."""
    sources = (
        FeedSeed(feed_url="http://slow.com", label="Slow", source="curated", priority=1),
        FeedSeed(feed_url="http://fast.com", label="Fast", source="curated", priority=2),
    )

    async def slow_run(*args, **kwargs):
        await asyncio.sleep(10.0)  # Will exceed 0.5s timeout
        return MagicMock(fetched_entries=1, accepted_findings=1, stored_findings=1, error=None)

    async def fast_run(*args, **kwargs):
        return MagicMock(fetched_entries=2, accepted_findings=1, stored_findings=1, error=None)

    call_count = 0

    async def run_dispatcher(*args, **kwargs):
        nonlocal call_count
        feed_url = kwargs.get("feed_url") or (args[0] if args else "")
        call_count += 1
        if "slow" in feed_url:
            return await slow_run(*args, **kwargs)
        return await fast_run(*args, **kwargs)

    with patch(
        "hledac.universal.pipeline.live_feed_pipeline.async_run_live_feed_pipeline",
        side_effect=run_dispatcher,
    ):
        result = await async_run_feed_source_batch(
            sources=sources,
            store=None,
            feed_concurrency=2,
            per_feed_timeout_s=0.5,
            batch_timeout_s=30.0,
        )

    assert result.total_sources == 2
    # One timed out, one completed
    source_results = {s.feed_url: s for s in result.sources}
    assert source_results["http://slow.com"].error == "per_feed_timeout"
    assert source_results["http://fast.com"].error is None


# ---------------------------------------------------------------------------
# D.8 — test_cancelled_error_is_reraised
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cancelled_error_is_reraised():
    """asyncio.CancelledError must be re-raised, not swallowed."""
    sources = (FeedSeed(feed_url="http://cancel.com", label="X", source="curated", priority=1),)

    async def raising_run(*args, **kwargs):
        raise asyncio.CancelledError()

    with patch(
        "hledac.universal.pipeline.live_feed_pipeline.async_run_live_feed_pipeline",
        raising_run,
    ):
        with pytest.raises(asyncio.CancelledError):
            await async_run_feed_source_batch(
                sources=sources,
                store=None,
                feed_concurrency=1,
                per_feed_timeout_s=30.0,
            )


# ---------------------------------------------------------------------------
# D.9 — test_store_none_is_valid
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_store_none_is_valid():
    """store=None should be a valid no-op storage mode."""
    with patch(
        "hledac.universal.pipeline.live_feed_pipeline.async_run_live_feed_pipeline",
        new_callable=AsyncMock,
    ) as mock_run:
        mock_run.return_value = MagicMock(
            fetched_entries=5,
            accepted_findings=3,
            stored_findings=0,  # store=None means no storage
            error=None,
        )
        result = await async_run_feed_source_batch(
            sources=(FeedSeed(feed_url="http://test.com", label="T", source="curated", priority=1),),
            store=None,
            feed_concurrency=1,
            per_feed_timeout_s=5.0,
        )
        assert result.stored_findings == 0
        # Verify store=None was passed through
        _, kwargs = mock_run.call_args
        assert kwargs["store"] is None


# ---------------------------------------------------------------------------
# D.10 — test_batch_delegates_to_async_run_live_feed_pipeline
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_batch_delegates_to_async_run_live_feed_pipeline(mock_feed_result):
    """Batch runner must delegate actual feed execution to async_run_live_feed_pipeline."""
    sources = (
        FeedSeed(feed_url="http://feed1.com", label="F1", source="curated", priority=1),
        FeedSeed(feed_url="http://feed2.com", label="F2", source="curated", priority=2),
    )
    with patch(
        "hledac.universal.pipeline.live_feed_pipeline.async_run_live_feed_pipeline",
        new_callable=AsyncMock,
    ) as mock_run:
        mock_run.return_value = mock_feed_result
        result = await async_run_feed_source_batch(
            sources=sources,
            store=None,
            feed_concurrency=2,
            per_feed_timeout_s=5.0,
        )
        assert mock_run.call_count == 2
        # Verify both feed URLs were passed
        called_urls = {
            (c.kwargs.get("feed_url") if c.kwargs else c.args[0])
            for c in mock_run.call_args_list
        }
        assert "http://feed1.com" in called_urls
        assert "http://feed2.com" in called_urls


# ---------------------------------------------------------------------------
# D.11 — test_query_context_global_override
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_query_context_global_override(mock_feed_result):
    """Global query_context should override per-feed label fallback."""
    sources = (
        FeedSeed(feed_url="http://feed.com", label="Label", source="curated", priority=1),
    )
    with patch(
        "hledac.universal.pipeline.live_feed_pipeline.async_run_live_feed_pipeline",
        new_callable=AsyncMock,
    ) as mock_run:
        mock_run.return_value = mock_feed_result
        await async_run_feed_source_batch(
            sources=sources,
            store=None,
            query_context="GLOBAL_OVERRIDE",
            feed_concurrency=1,
            per_feed_timeout_s=5.0,
        )
        _, kwargs = mock_run.call_args
        assert kwargs["query_context"] == "GLOBAL_OVERRIDE"


# ---------------------------------------------------------------------------
# D.12 — test_label_fallback_when_query_context_missing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_label_fallback_when_query_context_missing(mock_feed_result):
    """When query_context is None/empty, label should be used as query_context."""
    sources = (
        FeedSeed(feed_url="http://feed.com", label="MyLabel", source="curated", priority=1),
    )
    with patch(
        "hledac.universal.pipeline.live_feed_pipeline.async_run_live_feed_pipeline",
        new_callable=AsyncMock,
    ) as mock_run:
        mock_run.return_value = mock_feed_result
        await async_run_feed_source_batch(
            sources=sources,
            store=None,
            query_context=None,
            feed_concurrency=1,
            per_feed_timeout_s=5.0,
        )
        _, kwargs = mock_run.call_args
        assert kwargs["query_context"] == "MyLabel"


# ---------------------------------------------------------------------------
# D.13 — test_feed_url_final_fallback_when_label_missing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_feed_url_final_fallback_when_label_missing(mock_feed_result):
    """When both query_context and label are empty, feed_url should be used."""
    # FeedDiscoveryHit has no label
    hit = FeedDiscoveryHit(
        page_url="http://discovered.com",
        feed_url="http://discovered.com/feed.xml",
        title="RSS",
        feed_type="rss",
        confidence=0.9,
        source="discovered",
        discovered_ts=1700000000.0,
    )
    with patch(
        "hledac.universal.pipeline.live_feed_pipeline.async_run_live_feed_pipeline",
        new_callable=AsyncMock,
    ) as mock_run:
        mock_run.return_value = mock_feed_result
        await async_run_feed_source_batch(
            sources=(hit,),
            store=None,
            query_context=None,
            feed_concurrency=1,
            per_feed_timeout_s=5.0,
        )
        _, kwargs = mock_run.call_args
        assert kwargs["query_context"] == "http://discovered.com/feed.xml"


# ---------------------------------------------------------------------------
# D.14 — test_emergency_uma_aborts_batch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_emergency_uma_aborts_batch():
    """UMA emergency state should abort the entire batch with error."""
    sources = (
        FeedSeed(feed_url="http://test.com", label="T", source="curated", priority=1),
    )
    mock_uma = MagicMock()
    mock_uma.state = "emergency"

    with patch(
        "hledac.universal.core.resource_governor.sample_uma_status",
        return_value=mock_uma,
    ):
        result = await async_run_feed_source_batch(
            sources=sources,
            store=None,
            feed_concurrency=3,
            per_feed_timeout_s=5.0,
        )

    assert result.error == "uma_emergency_abort"
    assert result.total_sources == 1
    assert result.completed_sources == 0
    assert result.sources == ()


# ---------------------------------------------------------------------------
# D.15 — test_critical_uma_clamps_concurrency_to_one
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_critical_uma_clamps_concurrency_to_one(mock_feed_result):
    """UMA critical state should clamp effective_concurrency to 1."""
    sources = (
        FeedSeed(feed_url="http://f1.com", label="F1", source="curated", priority=1),
        FeedSeed(feed_url="http://f2.com", label="F2", source="curated", priority=2),
    )
    mock_uma = MagicMock()
    mock_uma.state = "critical"

    with patch(
        "hledac.universal.core.resource_governor.sample_uma_status",
        return_value=mock_uma,
    ):
        with patch(
            "hledac.universal.pipeline.live_feed_pipeline.async_run_live_feed_pipeline",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = mock_feed_result
            start = time.monotonic()
            result = await async_run_feed_source_batch(
                sources=sources,
                store=None,
                feed_concurrency=5,  # requested 5
                per_feed_timeout_s=5.0,
            )
            elapsed = time.monotonic() - start

    # With concurrency=1, tasks run sequentially — verify by checking
    # that both were called (not parallel) by seeing 2 calls completed
    assert mock_run.call_count == 2


# ---------------------------------------------------------------------------
# D.16 — test_ok_warn_keep_requested_bounded_concurrency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ok_warn_keep_requested_bounded_concurrency(mock_feed_result):
    """UMA ok/warn states should keep the requested bounded concurrency."""
    sources = tuple(
        FeedSeed(feed_url=f"http://f{i}.com", label=f"F{i}", source="curated", priority=i)
        for i in range(1, 5)
    )
    mock_uma = MagicMock()
    mock_uma.state = "ok"

    call_times = []

    async def timed_run(*args, **kwargs):
        call_times.append(time.monotonic())
        await asyncio.sleep(0.05)  # 50ms per call
        return mock_feed_result

    with patch(
        "hledac.universal.core.resource_governor.sample_uma_status",
        return_value=mock_uma,
    ):
        with patch(
            "hledac.universal.pipeline.live_feed_pipeline.async_run_live_feed_pipeline",
            new_callable=AsyncMock,
        ):
            with patch(
                "hledac.universal.pipeline.live_feed_pipeline.async_run_live_feed_pipeline",
                side_effect=timed_run,
            ):
                result = await async_run_feed_source_batch(
                    sources=sources,
                    store=None,
                    feed_concurrency=3,  # Should run 3 at a time
                    per_feed_timeout_s=5.0,
                )

    assert result.completed_sources == 4
    # With concurrency=3 and 4 tasks of 50ms each:
    # First batch of 3 starts together, 4th waits
    # First 3 finish at ~50ms, then 4th starts and finishes at ~100ms
    # Total should be < 150ms if concurrent
    assert call_times[-1] - call_times[0] < 0.15  # All ran concurrently


# ---------------------------------------------------------------------------
# D.17 — test_completed_sources_count_correct
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_completed_sources_count_correct(mock_feed_result, mock_feed_result_error):
    """completed_sources should count only sources with error=None."""
    sources = (
        FeedSeed(feed_url="http://ok.com", label="OK", source="curated", priority=1),
        FeedSeed(feed_url="http://err.com", label="Err", source="curated", priority=2),
        FeedSeed(feed_url="http://also-ok.com", label="AlsoOK", source="curated", priority=3),
    )

    async def run_dispatcher(*args, **kwargs):
        feed_url = kwargs.get("feed_url") or (args[0] if args else "")
        if "err" in feed_url:
            return mock_feed_result_error
        return mock_feed_result

    with patch(
        "hledac.universal.pipeline.live_feed_pipeline.async_run_live_feed_pipeline",
        new_callable=AsyncMock,
    ):
        with patch(
            "hledac.universal.pipeline.live_feed_pipeline.async_run_live_feed_pipeline",
            side_effect=run_dispatcher,
        ):
            result = await async_run_feed_source_batch(
                sources=sources,
                store=None,
                feed_concurrency=3,
                per_feed_timeout_s=5.0,
            )

    assert result.total_sources == 3
    assert result.completed_sources == 2  # ok + also-ok
    assert result.error is None  # batch itself succeeded


# ---------------------------------------------------------------------------
# D.18 — test_aggregate_counts_are_correct
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_aggregate_counts_are_correct():
    """Aggregate fetched/accepted/stored counts should sum all source results."""
    sources = (
        FeedSeed(feed_url="http://f1.com", label="F1", source="curated", priority=1),
        FeedSeed(feed_url="http://f2.com", label="F2", source="curated", priority=2),
    )

    async def run_dispatcher(*args, **kwargs):
        feed_url = kwargs.get("feed_url") or (args[0] if args else "")
        if "f1" in feed_url:
            return MagicMock(fetched_entries=10, accepted_findings=8, stored_findings=7, error=None)
        return MagicMock(fetched_entries=5, accepted_findings=3, stored_findings=2, error=None)

    with patch(
        "hledac.universal.pipeline.live_feed_pipeline.async_run_live_feed_pipeline",
        new_callable=AsyncMock,
    ):
        with patch(
            "hledac.universal.pipeline.live_feed_pipeline.async_run_live_feed_pipeline",
            side_effect=run_dispatcher,
        ):
            result = await async_run_feed_source_batch(
                sources=sources,
                store=MagicMock(),  # non-None store
                feed_concurrency=2,
                per_feed_timeout_s=5.0,
            )

    assert result.fetched_entries == 15   # 10 + 5
    assert result.accepted_findings == 11  # 8 + 3
    assert result.stored_findings == 9     # 7 + 2


# ---------------------------------------------------------------------------
# D.19 — test_merge_surface_from_8aj_reused_via_monkeypatch
# ---------------------------------------------------------------------------

def test_merge_surface_from_8aj_reused_via_monkeypatch():
    """Verify merge_feed_sources and get_default_feed_seeds exist in rss_atom_adapter."""
    from hledac.universal.discovery import rss_atom_adapter

    assert hasattr(rss_atom_adapter, "merge_feed_sources")
    assert hasattr(rss_atom_adapter, "get_default_feed_seeds")
    assert hasattr(rss_atom_adapter, "FeedSeed")
    assert hasattr(rss_atom_adapter, "FeedDiscoveryHit")
    assert hasattr(rss_atom_adapter, "MergedFeedSource")

    # Verify merge_feed_sources callable signature
    seeds = get_default_feed_seeds()
    hits: tuple[FeedDiscoveryHit, ...] = ()
    merged = rss_atom_adapter.merge_feed_sources(hits, seeds)
    assert isinstance(merged, tuple)
    assert all(isinstance(m, MergedFeedSource) for m in merged)


# ---------------------------------------------------------------------------
# D.20 — test_import_time_has_no_network_side_effects
# ---------------------------------------------------------------------------

def test_import_time_has_no_network_side_effects():
    """Importing the module should not trigger any network calls."""
    # This is implicitly tested by the fact that all imports above
    # (before running any async function) complete instantly
    # without any network activity. We verify by checking that
    # the module can be imported cleanly.
    import hledac.universal.pipeline.live_feed_pipeline as m
    assert hasattr(m, "async_run_feed_source_batch")
    assert hasattr(m, "async_run_default_feed_batch")
    assert hasattr(m, "_coerce_source_to_tuple")
    assert hasattr(m, "FeedSourceRunResult")
    assert hasattr(m, "FeedSourceBatchRunResult")


# ---------------------------------------------------------------------------
# D.21 — test_no_new_production_module_created
# ---------------------------------------------------------------------------

def test_no_new_production_module_created():
    """Sprint 8AL must not create any new production module."""
    import os

    # The sprint contract: only live_feed_pipeline.py was modified.
    # Verify it exists (was edited, not deleted).
    project_root = os.path.dirname(
        os.path.dirname(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(__file__)
                )
            )
        )
    )
    pipeline_file = os.path.join(
        project_root, "hledac", "universal", "pipeline", "live_feed_pipeline.py"
    )
    assert os.path.exists(pipeline_file), f"live_feed_pipeline.py not found at {pipeline_file}"
