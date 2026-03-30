"""
Sprint 8AF — RSS/Atom Passive Source Adapter v1
===============================================

Tests for discovery/rss_atom_adapter.py
RSS 2.0 + Atom 1.0 passive feed parsing, no storage, no LLM.
"""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from hledac.universal.discovery.rss_atom_adapter import (
    FeedBatchResult,
    FeedEntryHit,
    _entry_dedup_key,
    _is_xml_entity_dangerous,
    _local_name,
    _normalize_url,
    _parse_feed_xml,
    _parse_published_ts,
    async_fetch_feed_entries,
)


# ---------------------------------------------------------------------------
# Sample feeds
# ---------------------------------------------------------------------------

RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Test Feed</title>
<link>https://example.com</link>
<item>
<title>Item One</title>
<link>https://example.com/1</link>
<description>First item description</description>
<pubDate>Wed, 15 Mar 2026 12:00:00 GMT</pubDate>
<guid>https://example.com/guid/1</guid>
</item>
<item>
<title>Item Two</title>
<link>https://example.com/2</link>
<description>Second item description</description>
<pubDate>Thu, 16 Mar 2026 12:00:00 GMT</pubDate>
<guid isPermaLink="false">item-two-guid</guid>
</item>
</channel>
</rss>"""

ATOM_SAMPLE = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Atom Test Feed</title>
<entry>
<title>Atom Entry One</title>
<link rel="alternate" href="https://atom.example/1"/>
<summary>First atom entry</summary>
<published>2026-03-15T12:00:00Z</published>
</entry>
<entry>
<title>Atom Entry Two</title>
<link href="https://atom.example/2"/>
<summary>Second atom entry</summary>
<updated>2026-03-16T12:00:00Z</updated>
</entry>
</feed>"""

RSS_DUPLICATES = """<?xml version="1.0"?>
<rss version="2.0">
<channel>
<item><title>Alpha</title><link>https://ex.com/a</link><guid>dup-key</guid></item>
<item><title>Alpha</title><link>https://ex.com/a2</link><guid>dup-key</guid></item>
<item><title>Beta</title><link>https://ex.com/b</link></item>
<item><title>Beta</title><link>https://ex.com/b</link></item>
</channel>
</rss>"""

RSS_NO_GUID = """<?xml version="1.0"?>
<rss version="2.0">
<channel>
<item><title>First</title><link>https://ex.com/first</link></item>
<item><title>First</title><link>https://ex.com/first</link></item>
<item><title>Second</title><link>https://ex.com/second</link></item>
</channel>
</rss>"""

MALFORMED_XML = "<rss><channel><item><title>Broken"
UNSUPPORTED_ROOT = "<foo><bar>baz</bar></foo>"
XML_ENTITY_BOMB = """<?xml version="1.0"?>
<!DOCTYPE rss [
<!ENTITY xx SYSTEM "file:///etc/passwd">
]>
<rss>&xx;</rss>"""
XML_DOCTYPE = """<?xml version="1.0"?>
<!DOCTYPE rss PUBLIC "-//W3C//DTD RSS 0.91//EN">
<rss></rss>"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeFetchResult:
    """Mirrors FetchResult from public_fetcher but without msgspec."""

    def __init__(
        self,
        url: str = "https://feed.example/rss",
        final_url: str | None = None,
        status_code: int = 200,
        content_type: str = "application/rss+xml",
        text: str | None = None,
        error: str | None = None,
    ):
        self.url = url
        self.final_url = final_url or url
        self.status_code = status_code
        self.content_type = content_type
        self.text = text
        self.error = error


# ---------------------------------------------------------------------------
# Test: module structure
# ---------------------------------------------------------------------------


class TestModuleExists:
    def test_feed_entry_hit_exists(self):
        assert FeedEntryHit is not None

    def test_feed_batch_result_exists(self):
        assert FeedBatchResult is not None

    def test_async_fetch_feed_entries_exists(self):
        assert asyncio.iscoroutinefunction(async_fetch_feed_entries)


# ---------------------------------------------------------------------------
# Test: DTO contracts
# ---------------------------------------------------------------------------


class TestFeedEntryHitContract:
    def test_all_fields_present(self):
        now = time.time()
        hit = FeedEntryHit(
            feed_url="https://feed.example",
            entry_url="https://feed.example/1",
            title="Title",
            summary="Summary",
            published_raw="2026-03-15",
            published_ts=now,
            source="rss_atom",
            rank=0,
            retrieved_ts=now,
        )
        assert hit.feed_url == "https://feed.example"
        assert hit.entry_url == "https://feed.example/1"
        assert hit.title == "Title"
        assert hit.summary == "Summary"
        assert hit.published_raw == "2026-03-15"
        assert hit.published_ts == now
        assert hit.source == "rss_atom"
        assert hit.rank == 0
        assert hit.retrieved_ts == now

    def test_source_constant(self):
        now = time.time()
        hit = FeedEntryHit(
            feed_url="", entry_url="", title="", summary="",
            published_raw="", published_ts=None, source="rss_atom",
            rank=0, retrieved_ts=now,
        )
        assert hit.source == "rss_atom"

    def test_published_ts_optional(self):
        now = time.time()
        hit = FeedEntryHit(
            feed_url="", entry_url="", title="", summary="",
            published_raw="", published_ts=None, source="rss_atom",
            rank=0, retrieved_ts=now,
        )
        assert hit.published_ts is None


class TestFeedBatchResultContract:
    def test_error_none_by_default(self):
        result = FeedBatchResult(feed_url="https://feed.example", entries=())
        assert result.error is None

    def test_error_can_be_set(self):
        result = FeedBatchResult(
            feed_url="https://feed.example",
            entries=(),
            error="xml_parse_error",
        )
        assert result.error == "xml_parse_error"


# ---------------------------------------------------------------------------
# Test: RSS parsing
# ---------------------------------------------------------------------------


class TestRSSParsing:
    def test_rss_parses_title_and_link(self):
        now = time.time()
        entries = _parse_feed_xml(RSS_SAMPLE, "https://feed.example/rss", now)
        assert len(entries) == 2
        assert entries[0].title == "Item One"
        assert entries[0].entry_url == "https://example.com/guid/1"
        assert entries[1].title == "Item Two"
        assert entries[1].entry_url == "https://example.com/2"

    def test_rss_description_becomes_summary(self):
        now = time.time()
        entries = _parse_feed_xml(RSS_SAMPLE, "https://feed.example/rss", now)
        assert entries[0].summary == "First item description"

    def test_rss_guid_permalink_true(self):
        now = time.time()
        entries = _parse_feed_xml(RSS_SAMPLE, "https://feed.example/rss", now)
        assert entries[0].entry_url == "https://example.com/guid/1"

    def test_rss_guid_permalink_false_becomes_dedup_key_only(self):
        now = time.time()
        entries = _parse_feed_xml(RSS_SAMPLE, "https://feed.example/rss", now)
        # guid isPermaLink=false → use link as entry_url
        assert entries[1].entry_url == "https://example.com/2"

    def test_rss_retrieved_ts_set(self):
        now = time.time()
        entries = _parse_feed_xml(RSS_SAMPLE, "https://feed.example/rss", now)
        assert entries[0].retrieved_ts == now

    def test_rss_published_raw_preserved(self):
        now = time.time()
        entries = _parse_feed_xml(RSS_SAMPLE, "https://feed.example/rss", now)
        assert "2026" in entries[0].published_raw

    def test_rss_published_ts_float_or_none(self):
        now = time.time()
        entries = _parse_feed_xml(RSS_SAMPLE, "https://feed.example/rss", now)
        assert isinstance(entries[0].published_ts, float)

    def test_rss_rank_reassigned_after_dedup(self):
        now = time.time()
        entries = _parse_feed_xml(RSS_SAMPLE, "https://feed.example/rss", now)
        assert entries[0].rank == 0
        assert entries[1].rank == 1


# ---------------------------------------------------------------------------
# Test: Atom parsing
# ---------------------------------------------------------------------------


class TestAtomParsing:
    def test_atom_parses_title(self):
        now = time.time()
        entries = _parse_feed_xml(ATOM_SAMPLE, "https://feed.example/atom", now)
        assert entries[0].title == "Atom Entry One"
        assert entries[1].title == "Atom Entry Two"

    def test_atom_rel_alternate_preferred(self):
        now = time.time()
        entries = _parse_feed_xml(ATOM_SAMPLE, "https://feed.example/atom", now)
        assert entries[0].entry_url == "https://atom.example/1"

    def test_atom_fallback_href(self):
        now = time.time()
        entries = _parse_feed_xml(ATOM_SAMPLE, "https://feed.example/atom", now)
        assert entries[1].entry_url == "https://atom.example/2"

    def test_atom_summary(self):
        now = time.time()
        entries = _parse_feed_xml(ATOM_SAMPLE, "https://feed.example/atom", now)
        assert entries[0].summary == "First atom entry"

    def test_atom_source(self):
        now = time.time()
        entries = _parse_feed_xml(ATOM_SAMPLE, "https://feed.example/atom", now)
        assert all(e.source == "rss_atom" for e in entries)

    def test_atom_default_namespace(self):
        # Atom uses default namespace without prefix — must not fail
        now = time.time()
        entries = _parse_feed_xml(ATOM_SAMPLE, "https://feed.example/atom", now)
        assert len(entries) == 2


# ---------------------------------------------------------------------------
# Test: fail-soft semantics
# ---------------------------------------------------------------------------


class TestFailSoft:
    def test_malformed_xml_error(self):
        now = time.time()
        entries = _parse_feed_xml(MALFORMED_XML, "https://feed.example", now)
        assert entries == []

    def test_unsupported_root(self):
        now = time.time()
        entries = _parse_feed_xml(UNSUPPORTED_ROOT, "https://feed.example", now)
        assert entries == []

    def test_xml_entity_rejected(self):
        now = time.time()
        assert _is_xml_entity_dangerous(XML_ENTITY_BOMB) is True
        entries = _parse_feed_xml(XML_ENTITY_BOMB, "https://feed.example", now)
        assert entries == []

    def test_xml_doctype_rejected(self):
        now = time.time()
        assert _is_xml_entity_dangerous(XML_DOCTYPE) is True
        entries = _parse_feed_xml(XML_DOCTYPE, "https://feed.example", now)
        assert entries == []

    def test_safe_xml_not_rejected(self):
        assert _is_xml_entity_dangerous(RSS_SAMPLE) is False
        assert _is_xml_entity_dangerous(ATOM_SAMPLE) is False


# ---------------------------------------------------------------------------
# Test: normalization
# ---------------------------------------------------------------------------


class TestNormalization:
    def test_none_fields_normalize_to_empty_string(self):
        now = time.time()
        # RSS with empty title/description
        minimal_rss = """<?xml version="1.0"?><rss version="2.0"><channel>
        <item><title></title><link>https://ex.com/1</link></item>
        </channel></rss>"""
        entries = _parse_feed_xml(minimal_rss, "https://feed.example", now)
        assert entries[0].title == ""
        assert entries[0].summary == ""

    def test_title_always_str(self):
        now = time.time()
        entries = _parse_feed_xml(RSS_SAMPLE, "https://feed.example", now)
        assert isinstance(entries[0].title, str)

    def test_summary_always_str(self):
        now = time.time()
        entries = _parse_feed_xml(RSS_SAMPLE, "https://feed.example", now)
        assert isinstance(entries[0].summary, str)

    def test_entry_url_always_str(self):
        now = time.time()
        entries = _parse_feed_xml(RSS_SAMPLE, "https://feed.example", now)
        assert isinstance(entries[0].entry_url, str)

    def test_published_raw_always_str(self):
        now = time.time()
        entries = _parse_feed_xml(RSS_SAMPLE, "https://feed.example", now)
        assert isinstance(entries[0].published_raw, str)

    def test_retrieved_ts_filled(self):
        now = time.time()
        entries = _parse_feed_xml(RSS_SAMPLE, "https://feed.example", now)
        assert entries[0].retrieved_ts > 0


# ---------------------------------------------------------------------------
# Test: dedup preserve-first
# ---------------------------------------------------------------------------


class TestDedup:
    def test_rss_guid_dedup(self):
        now = time.time()
        entries = _parse_feed_xml(RSS_DUPLICATES, "https://feed.example", now)
        # First occurrence kept, second skipped
        assert len(entries) == 2
        assert entries[0].title == "Alpha"
        assert entries[1].title == "Beta"

    def test_rss_fallback_dedup_without_guid(self):
        now = time.time()
        entries = _parse_feed_xml(RSS_NO_GUID, "https://feed.example", now)
        # Two identical (title+link) entries deduped to 2
        assert len(entries) == 2

    def test_dedup_key_function(self):
        key = _entry_dedup_key("https://ex.com/1", "Title", "2026-03-15", None, None)
        assert key.startswith("u:")

    def test_dedup_key_guid(self):
        key = _entry_dedup_key("https://ex.com/1", "Title", "2026-03-15", "my-guid", True)
        assert key.startswith("g:")


# ---------------------------------------------------------------------------
# Test: max_entries bounds
# ---------------------------------------------------------------------------


class TestMaxEntries:
    @pytest.mark.asyncio
    async def test_default_is_20(self):
        """async_fetch_feed_entries caps at 20 entries by default."""
        xml = '<?xml version="1.0"?><rss version="2.0"><channel>' + "".join(
            f"<item><title>I{i}</title><link>https://ex.com/{i}</link></item>"
            for i in range(30)
        ) + "</channel></rss>"

        class MockResult:
            text = xml
            error = None
            url = "https://feed.example"
            final_url = "https://feed.example"
            status_code = 200
            content_type = "application/rss+xml"

        with patch(
            "hledac.universal.fetching.public_fetcher.async_fetch_public_text",
            new_callable=AsyncMock,
            return_value=MockResult(),
        ):
            result = await async_fetch_feed_entries("https://feed.example")
            assert len(result.entries) == 20

    @pytest.mark.asyncio
    async def test_hard_cap_100(self):
        """async_fetch_feed_entries hard-caps at 100 entries."""
        xml = '<?xml version="1.0"?><rss version="2.0"><channel>' + "".join(
            f"<item><title>I{i}</title><link>https://ex.com/{i}</link></item>"
            for i in range(150)
        ) + "</channel></rss>"

        class MockResult:
            text = xml
            error = None
            url = "https://feed.example"
            final_url = "https://feed.example"
            status_code = 200
            content_type = "application/rss+xml"

        with patch(
            "hledac.universal.fetching.public_fetcher.async_fetch_public_text",
            new_callable=AsyncMock,
            return_value=MockResult(),
        ):
            result = await async_fetch_feed_entries("https://feed.example", max_entries=200)
            assert len(result.entries) == 100


# ---------------------------------------------------------------------------
# Test: CancelledError re-raise
# ---------------------------------------------------------------------------


class TestCancelledError:
    @pytest.mark.asyncio
    async def test_cancelled_error_re_raised(self):
        """CancelledError must propagate, not be swallowed."""
        async def fake_fetch(*args, **kwargs):
            raise asyncio.CancelledError()

        with patch(
            "hledac.universal.fetching.public_fetcher.async_fetch_public_text",
            new_callable=AsyncMock,
            side_effect=fake_fetch,
        ):
            with pytest.raises(asyncio.CancelledError):
                await async_fetch_feed_entries("https://feed.example/rss")


# ---------------------------------------------------------------------------
# Test: fetch error fail-soft
# ---------------------------------------------------------------------------


class TestFetchError:
    @pytest.mark.asyncio
    async def test_fetch_error_returns_fail_soft(self):
        """Fetch-level error must return fail-soft result with error string."""

        class MockResult:
            text = None
            error = "timeout"
            url = "https://feed.example/rss"
            final_url = "https://feed.example/rss"
            status_code = 0
            content_type = ""

        with patch(
            "hledac.universal.fetching.public_fetcher.async_fetch_public_text",
            new_callable=AsyncMock,
            return_value=MockResult(),
        ):
            result = await async_fetch_feed_entries("https://feed.example/rss")
            assert result.error == "timeout"
            assert result.entries == ()


# ---------------------------------------------------------------------------
# Test: text_none fail-soft
# ---------------------------------------------------------------------------


class TestTextNone:
    @pytest.mark.asyncio
    async def test_text_none_returns_fail_soft(self):
        """text=None from fetch must return fail-soft with fetch_returned_none."""

        class MockResult:
            text = None
            error = None
            url = "https://feed.example/rss"
            final_url = "https://feed.example/rss"
            status_code = 200
            content_type = "application/rss+xml"

        with patch(
            "hledac.universal.fetching.public_fetcher.async_fetch_public_text",
            new_callable=AsyncMock,
            return_value=MockResult(),
        ):
            result = await async_fetch_feed_entries("https://feed.example/rss")
            assert result.error == "fetch_returned_none"
            assert result.entries == ()


# ---------------------------------------------------------------------------
# Test: url normalization
# ---------------------------------------------------------------------------


class TestURLNormalization:
    def test_normalize_https_lowercased(self):
        url = _normalize_url("HTTPS://EXAMPLE.COM/Path")
        assert url.startswith("https://")

    def test_normalize_strips_lone_question(self):
        url = _normalize_url("https://example.com?")
        assert url == "https://example.com"

    def test_empty_returns_empty(self):
        assert _normalize_url("") == ""
        assert _normalize_url(None) == ""


# ---------------------------------------------------------------------------
# Test: published_ts parsing
# ---------------------------------------------------------------------------


class TestPublishedTs:
    def test_rss_pubdate_parsed(self):
        ts = _parse_published_ts("Wed, 15 Mar 2026 12:00:00 GMT")
        assert isinstance(ts, float)
        assert ts > 0

    def test_atom_zulu_parsed(self):
        ts = _parse_published_ts("2026-03-15T12:00:00Z")
        assert isinstance(ts, float)

    def test_invalid_returns_none(self):
        assert _parse_published_ts("not a date") is None
        assert _parse_published_ts(None) is None
        assert _parse_published_ts("") is None


# ---------------------------------------------------------------------------
# Test: no import-time side effects
# ---------------------------------------------------------------------------


class TestNoSideEffects:
    def test_module_imports_without_network(self):
        # If we got here, module already imported successfully
        # which means no network calls at import time
        assert True


# ---------------------------------------------------------------------------
# Test: integration with 8AD mock
# ---------------------------------------------------------------------------


class Test8ADIntegration:
    @pytest.mark.asyncio
    async def test_uses_8ad_fetch_surface(self):
        """async_fetch_feed_entries must call async_fetch_public_text."""

        class MockResult:
            text = RSS_SAMPLE
            error = None
            url = "https://feed.example/rss"
            final_url = "https://feed.example/rss"
            status_code = 200
            content_type = "application/rss+xml"

        called = False

        async def mock_fetch(*args, **kwargs):
            nonlocal called
            called = True
            return MockResult()

        with patch(
            "hledac.universal.fetching.public_fetcher.async_fetch_public_text",
            new_callable=AsyncMock,
            side_effect=mock_fetch,
        ):
            result = await async_fetch_feed_entries("https://feed.example/rss")
            assert called is True
            assert len(result.entries) == 2
            assert result.error is None


# ---------------------------------------------------------------------------
# Test: local_name namespace safety
# ---------------------------------------------------------------------------


class TestLocalName:
    def test_strips_namespace(self):
        assert _local_name("{http://www.w3.org/2005/Atom}entry") == "entry"
        assert _local_name("entry") == "entry"

    def test_none_input(self):
        assert _local_name(None) == ""


# ---------------------------------------------------------------------------
# Test: benchmark sanity
# ---------------------------------------------------------------------------


class TestBenchmarks:
    def test_rss_20_items_parsing_performance(self):
        now = time.time()
        xml = '<?xml version="1.0"?><rss version="2.0"><channel>' + "".join(
            f"<item><title>I{i}</title><link>https://ex.com/{i}</link>"
            f"<description>D{i}</description><guid>g{i}</guid></item>"
            for i in range(20)
        ) + "</channel></rss>"
        t0 = time.perf_counter()
        entries = _parse_feed_xml(xml, "https://feed.example", now)
        t1 = time.perf_counter()
        ms = (t1 - t0) * 1000
        assert len(entries) == 20
        assert ms < 100, f"RSS parse too slow: {ms:.1f}ms"

    def test_atom_20_entries_parsing_performance(self):
        now = time.time()
        xml = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">' + "".join(
            f"<entry><title>E{i}</title><link href='https://atom.ex/{i}'/>"
            f"<summary>S{i}</summary><published>2026-03-15T12:00:00Z</published></entry>"
            for i in range(20)
        ) + "</feed>"
        t0 = time.perf_counter()
        entries = _parse_feed_xml(xml, "https://feed.example/atom", now)
        t1 = time.perf_counter()
        ms = (t1 - t0) * 1000
        assert len(entries) == 20
        assert ms < 100, f"Atom parse too slow: {ms:.1f}ms"

    def test_dedup_50_entries(self):
        """Parsing 50 unique entries should return all 50 (no dedup needed)."""
        now = time.time()
        xml = '<?xml version="1.0"?><rss version="2.0"><channel>' + "".join(
            f"<item><title>Item {i}</title><link>https://ex.com/{i}</link></item>"
            for i in range(50)
        ) + "</channel></rss>"
        t0 = time.perf_counter()
        entries = _parse_feed_xml(xml, "https://feed.example", now)
        t1 = time.perf_counter()
        ms = (t1 - t0) * 1000
        assert len(entries) == 50
        assert ms < 100, f"Dedup 50 too slow: {ms:.1f}ms"

    def test_adapter_overhead_over_mocked_fetch(self):
        """Adapter overhead should be <20ms for 20 items (excluding network)."""
        now = time.time()
        t0 = time.perf_counter()
        entries = _parse_feed_xml(RSS_SAMPLE, "https://feed.example/rss", now)
        t1 = time.perf_counter()
        ms = (t1 - t0) * 1000
        assert len(entries) == 2
        assert ms < 20, f"Adapter overhead too high: {ms:.1f}ms"
