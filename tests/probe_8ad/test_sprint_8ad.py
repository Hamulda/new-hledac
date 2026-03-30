"""
Sprint 8AD — First Live Public Text Fetch Adapter v1
======================================================

Tests for public_fetcher.py — aiohttp/shared-session, chunked, size-safe, passive-only.
"""

import asyncio
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# CORRECT mock helpers (aiohttp async context manager pattern)
# ---------------------------------------------------------------------------


class FakeResponse:
    """Fake aiohttp.ClientResponse with async chunk iterator."""

    def __init__(self, url: str, status: int, ct: str, body_bytes: bytes):
        self.url = url
        self.status = status
        self._ct = ct
        self._body = body_bytes
        self.headers = {"Content-Type": ct}
        if body_bytes:
            self.headers["Content-Length"] = str(len(body_bytes))

    class _Content:
        def __init__(self, body: bytes):
            self._body = body

        async def iter_chunked(self, size: int):
            """Async generator — the ONLY pattern that works with aiohttp."""
            yield self._body

    @property
    def content(self):
        return self._Content(self._body)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None


class FakeSession:
    """Fake aiohttp.ClientSession whose .get() returns an async context manager."""

    def __init__(self, url: str, status: int, ct: str, body_bytes: bytes):
        self._url = url
        self._status = status
        self._ct = ct
        self._body = body_bytes

    def get(self, url: str, *, headers=None, allow_redirects=True):
        return FakeResponse(
            url=self._url or url,
            status=self._status,
            ct=self._ct,
            body_bytes=self._body,
        )


async def _make_fake_session(url: str, status: int, ct: str, body_bytes: bytes):
    """Async factory for FakeSession — matches async_get_aiohttp_session() signature."""
    return FakeSession(url=url, status=status, ct=ct, body_bytes=body_bytes)


def _make_patch(get_session_fn):
    """Return a context manager that patches async_get_aiohttp_session."""
    return patch(
        "hledac.universal.fetching.public_fetcher.async_get_aiohttp_session",
        get_session_fn,
    )


# ---------------------------------------------------------------------------
# G1: Module surface
# ---------------------------------------------------------------------------

class TestModuleSurface:
    def test_module_importable(self):
        from hledac.universal.fetching import public_fetcher

        assert public_fetcher is not None

    def test_async_fetch_public_text_exists(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        assert asyncio.iscoroutinefunction(async_fetch_public_text)

    def test_default_ua_constant(self):
        from hledac.universal.fetching.public_fetcher import DEFAULT_UA

        assert isinstance(DEFAULT_UA, str)
        assert len(DEFAULT_UA) > 0
        assert "Mozilla" in DEFAULT_UA

    def test_max_bytes_constants(self):
        from hledac.universal.fetching.public_fetcher import (
            MAX_BYTES_DEFAULT,
            MAX_BYTES_HARD,
        )

        assert MAX_BYTES_DEFAULT == 2_000_000
        assert MAX_BYTES_HARD == 10_000_000
        assert MAX_BYTES_DEFAULT < MAX_BYTES_HARD


# ---------------------------------------------------------------------------
# G2: FetchResult contract
# ---------------------------------------------------------------------------

class TestFetchResultContract:
    def test_fetch_result_is_msgspec_struct(self):
        from hledac.universal.fetching.public_fetcher import FetchResult
        import msgspec

        assert issubclass(FetchResult, msgspec.Struct)

    def test_fetch_result_fields(self):
        from hledac.universal.fetching.public_fetcher import FetchResult

        r = FetchResult(
            url="https://example.com",
            final_url="https://example.com",
            status_code=200,
            content_type="text/html",
            text="<html>Hello</html>",
            fetched_bytes=20,
            declared_length=20,
            elapsed_ms=100.0,
        )
        assert r.url == "https://example.com"
        assert r.final_url == "https://example.com"
        assert r.status_code == 200
        assert r.content_type == "text/html"
        assert r.text == "<html>Hello</html>"
        assert r.fetched_bytes == 20
        assert r.declared_length == 20
        assert r.elapsed_ms == 100.0
        assert r.error is None

    def test_fetch_result_error_field_optional(self):
        from hledac.universal.fetching.public_fetcher import FetchResult

        r = FetchResult(
            url="https://example.com",
            final_url="https://example.com",
            status_code=200,
            content_type="text/html",
            text="<html>Hello</html>",
            fetched_bytes=20,
            declared_length=20,
            elapsed_ms=100.0,
        )
        assert r.error is None

    def test_fetch_result_frozen(self):
        from hledac.universal.fetching.public_fetcher import FetchResult

        r = FetchResult(
            url="https://example.com",
            final_url="https://example.com",
            status_code=200,
            content_type="text/html",
            text="<html>Hello</html>",
            fetched_bytes=20,
            declared_length=20,
            elapsed_ms=100.0,
        )
        with pytest.raises(Exception):
            r.url = "https://evil.com"


# ---------------------------------------------------------------------------
# G3: URL validation = fail-soft
# ---------------------------------------------------------------------------

class TestUrlValidation:
    @pytest.mark.asyncio
    async def test_empty_url_returns_fail_soft(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        result = await async_fetch_public_text("")
        assert result.error == "url_empty"
        assert result.status_code == 0
        assert result.text is None

    @pytest.mark.asyncio
    async def test_whitespace_only_url_returns_fail_soft(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        result = await async_fetch_public_text("   ")
        assert result.error == "url_empty"
        assert result.status_code == 0

    @pytest.mark.asyncio
    async def test_malformed_url_returns_fail_soft(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        result = await async_fetch_public_text("not-a-valid-url")
        assert result.error == "url_malformed"
        assert result.status_code == 0


# ---------------------------------------------------------------------------
# G4: non-http scheme = fail-soft
# ---------------------------------------------------------------------------

class TestNonHttpScheme:
    @pytest.mark.asyncio
    async def test_ftp_scheme_rejected(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        result = await async_fetch_public_text("ftp://example.com/file.txt")
        assert "unsupported_scheme" in result.error
        assert result.status_code == 0

    @pytest.mark.asyncio
    async def test_file_scheme_rejected(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        result = await async_fetch_public_text("file:///etc/passwd")
        assert "unsupported_scheme" in result.error
        assert result.status_code == 0

    @pytest.mark.asyncio
    async def test_javascript_scheme_rejected(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        result = await async_fetch_public_text("javascript:alert(1)")
        assert "unsupported_scheme" in result.error
        assert result.status_code == 0


# ---------------------------------------------------------------------------
# G5: Session integration
# ---------------------------------------------------------------------------

class TestSessionIntegration:
    @pytest.mark.asyncio
    async def test_session_obtained_from_runtime(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        body = b"<html>Test</html>"
        factory = lambda: _make_fake_session(
            url="https://example.com",
            status=200,
            ct="text/html",
            body_bytes=body,
        )
        with _make_patch(factory):
            result = await async_fetch_public_text("https://example.com")

        assert result.error is None
        assert result.status_code == 200


# ---------------------------------------------------------------------------
# G6-G8: Accepted content types
# ---------------------------------------------------------------------------

class TestAcceptedContentTypes:
    @pytest.mark.asyncio
    async def test_text_html_accepted(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        body = b"<html><body>Hello World</body></html>"
        factory = lambda: _make_fake_session(
            url="https://example.com",
            status=200,
            ct="text/html; charset=utf-8",
            body_bytes=body,
        )
        with _make_patch(factory):
            result = await async_fetch_public_text("https://example.com")

        assert result.status_code == 200
        assert result.text is not None
        assert "Hello World" in result.text
        assert result.error is None
        assert result.content_type == "text/html; charset=utf-8"

    @pytest.mark.asyncio
    async def test_text_plain_accepted(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        body = b"Plain text content here"
        factory = lambda: _make_fake_session(
            url="https://example.com",
            status=200,
            ct="text/plain",
            body_bytes=body,
        )
        with _make_patch(factory):
            result = await async_fetch_public_text("https://example.com")

        assert result.status_code == 200
        assert result.text == "Plain text content here"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_application_xml_accepted(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        body = b'<?xml version="1.0"?><root><item>Data</item></root>'
        factory = lambda: _make_fake_session(
            url="https://example.com/data.xml",
            status=200,
            ct="application/xml",
            body_bytes=body,
        )
        with _make_patch(factory):
            result = await async_fetch_public_text("https://example.com/data.xml")

        assert result.status_code == 200
        assert result.text is not None
        assert "Data" in result.text

    @pytest.mark.asyncio
    async def test_application_rss_xml_accepted(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        body = b'<?xml version="1.0"?><rss><channel><title>Test</title></channel></rss>'
        factory = lambda: _make_fake_session(
            url="https://example.com/feed.xml",
            status=200,
            ct="application/rss+xml",
            body_bytes=body,
        )
        with _make_patch(factory):
            result = await async_fetch_public_text("https://example.com/feed.xml")

        assert result.status_code == 200
        assert result.text is not None

    @pytest.mark.asyncio
    async def test_application_atom_xml_accepted(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        body = b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>Test</title></feed>'
        factory = lambda: _make_fake_session(
            url="https://example.com/atom.xml",
            status=200,
            ct="application/atom+xml",
            body_bytes=body,
        )
        with _make_patch(factory):
            result = await async_fetch_public_text("https://example.com/atom.xml")

        assert result.status_code == 200
        assert result.text is not None

    @pytest.mark.asyncio
    async def test_application_xhtml_xml_accepted(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        body = b'<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><body>Test</body></html>'
        factory = lambda: _make_fake_session(
            url="https://example.com/page.xhtml",
            status=200,
            ct="application/xhtml+xml",
            body_bytes=body,
        )
        with _make_patch(factory):
            result = await async_fetch_public_text("https://example.com/page.xhtml")

        assert result.status_code == 200
        assert result.text is not None


# ---------------------------------------------------------------------------
# G9: Binary content types rejected
# ---------------------------------------------------------------------------

class TestBinaryContentTypeRejected:
    @pytest.mark.asyncio
    async def test_image_png_rejected(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        factory = lambda: _make_fake_session(
            url="https://example.com/image.png",
            status=200,
            ct="image/png",
            body_bytes=b"\x89PNG\r\n\x1a\n",
        )
        with _make_patch(factory):
            result = await async_fetch_public_text("https://example.com/image.png")

        assert "content_type_rejected" in result.error
        assert result.text is None
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_application_pdf_rejected(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        factory = lambda: _make_fake_session(
            url="https://example.com/doc.pdf",
            status=200,
            ct="application/pdf",
            body_bytes=b"%PDF-1.4",
        )
        with _make_patch(factory):
            result = await async_fetch_public_text("https://example.com/doc.pdf")

        assert "content_type_rejected" in result.error
        assert result.text is None

    @pytest.mark.asyncio
    async def test_application_octet_stream_rejected(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        factory = lambda: _make_fake_session(
            url="https://example.com/binary",
            status=200,
            ct="application/octet-stream",
            body_bytes=b"\x00\x01\x02",
        )
        with _make_patch(factory):
            result = await async_fetch_public_text("https://example.com/binary")

        assert "content_type_rejected" in result.error
        assert result.text is None

    @pytest.mark.asyncio
    async def test_video_mp4_rejected(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        factory = lambda: _make_fake_session(
            url="https://example.com/video.mp4",
            status=200,
            ct="video/mp4",
            body_bytes=b"mp4data",
        )
        with _make_patch(factory):
            result = await async_fetch_public_text("https://example.com/video.mp4")

        assert "content_type_rejected" in result.error
        assert result.text is None


# ---------------------------------------------------------------------------
# G10: Size cap
# ---------------------------------------------------------------------------

class TestSizeCap:
    @pytest.mark.asyncio
    async def test_oversize_truncated_with_error(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        # Multi-chunk body: 8192 + rest = 100000 bytes total
        chunk1 = b"x" * 8192
        chunk2 = b"x" * (100_000 - 8192)

        class MultiChunkFakeResponse(FakeResponse):
            class _Content(FakeResponse._Content):
                async def iter_chunked(self, size: int):
                    yield chunk1
                    yield chunk2

        class MultiChunkFakeSession(FakeSession):
            def get(self, url: str, *, headers=None, allow_redirects=True):
                return MultiChunkFakeResponse(
                    url=self._url or url,
                    status=self._status,
                    ct=self._ct,
                    body_bytes=b"",  # not used
                )

        async def factory():
            s = MultiChunkFakeSession(
                url="https://example.com/large",
                status=200,
                ct="text/html",
                body_bytes=b"",
            )
            s._url = "https://example.com/large"
            return s

        with _make_patch(factory):
            result = await async_fetch_public_text(
                "https://example.com/large", max_bytes=10_000
            )

        assert result.error == "size_cap_exceeded"
        assert result.text is None
        assert result.fetched_bytes == 10_000
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_max_bytes_hard_cap_enforced(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        large_body = b"y" * 12_000_000

        class LargeChunkFakeResponse(FakeResponse):
            class _Content(FakeResponse._Content):
                async def iter_chunked(self, size: int):
                    yield large_body

        class LargeChunkFakeSession(FakeSession):
            def get(self, url: str, *, headers=None, allow_redirects=True):
                return LargeChunkFakeResponse(
                    url=self._url or url,
                    status=self._status,
                    ct=self._ct,
                    body_bytes=b"",  # not used
                )

        async def factory():
            s = LargeChunkFakeSession(
                url="https://example.com/page",
                status=200,
                ct="text/html",
                body_bytes=b"",
            )
            return s

        with _make_patch(factory):
            result = await async_fetch_public_text(
                "https://example.com/page", max_bytes=20_000_000
            )

        assert result.fetched_bytes <= 10_000_000

    @pytest.mark.asyncio
    async def test_exact_cap_no_error(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        body = b"z" * 5000
        factory = lambda: _make_fake_session(
            url="https://example.com/exact",
            status=200,
            ct="text/html",
            body_bytes=body,
        )
        with _make_patch(factory):
            result = await async_fetch_public_text(
                "https://example.com/exact", max_bytes=5000
            )

        assert result.error is None
        assert result.fetched_bytes == 5000
        assert result.text is not None


# ---------------------------------------------------------------------------
# G11-G16: Field propagation
# ---------------------------------------------------------------------------

class TestRedirectAndFields:
    @pytest.mark.asyncio
    async def test_redirect_updates_final_url(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        body = b"<html>Redirected</html>"
        factory = lambda: _make_fake_session(
            url="https://example.com/final-page",  # after redirect
            status=200,
            ct="text/html",
            body_bytes=body,
        )
        with _make_patch(factory):
            result = await async_fetch_public_text("https://example.com/redirect-me")

        assert result.final_url == "https://example.com/final-page"
        assert result.url == "https://example.com/redirect-me"

    @pytest.mark.asyncio
    async def test_status_code_propagated(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        body = b"Not Found"
        factory = lambda: _make_fake_session(
            url="https://example.com/missing",
            status=404,
            ct="text/html",
            body_bytes=body,
        )
        with _make_patch(factory):
            result = await async_fetch_public_text("https://example.com/missing")

        assert result.status_code == 404

    @pytest.mark.asyncio
    async def test_fetched_bytes_reflects_actual_read(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        body = b"<html><body>Small page</body></html>"
        factory = lambda: _make_fake_session(
            url="https://example.com",
            status=200,
            ct="text/html",
            body_bytes=body,
        )
        with _make_patch(factory):
            result = await async_fetch_public_text("https://example.com")

        assert result.fetched_bytes == len(body)

    @pytest.mark.asyncio
    async def test_declared_length_from_header(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        body = b"<html>Hello</html>"
        factory = lambda: _make_fake_session(
            url="https://example.com",
            status=200,
            ct="text/html",
            body_bytes=body,
        )
        with _make_patch(factory):
            result = await async_fetch_public_text("https://example.com")

        assert result.declared_length == len(body)

    @pytest.mark.asyncio
    async def test_declared_length_minus_one_when_missing(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        body = b"<html>Hello</html>"
        factory = lambda: _make_fake_session(
            url="https://example.com",
            status=200,
            ct="text/html",
            body_bytes=body,
        )
        with _make_patch(factory):
            result = await async_fetch_public_text("https://example.com")

        assert result.declared_length == len(body)

    @pytest.mark.asyncio
    async def test_elapsed_ms_is_non_negative(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        body = b"<html>Fast response</html>"
        factory = lambda: _make_fake_session(
            url="https://example.com",
            status=200,
            ct="text/html",
            body_bytes=body,
        )
        with _make_patch(factory):
            result = await async_fetch_public_text("https://example.com")

        assert result.elapsed_ms >= 0


# ---------------------------------------------------------------------------
# G17-G18: Timeout and cancellation
# ---------------------------------------------------------------------------

class TestTimeoutAndCancellation:
    @pytest.mark.asyncio
    async def test_timeout_returns_error(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        # Make response.sleep that never completes
        class NeverFinishesFakeResponse(FakeResponse):
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return None

            class _Content(FakeResponse._Content):
                async def iter_chunked(self, size: int):
                    await asyncio.sleep(10)  # longer than 1s timeout
                    yield self._body

        class NeverFinishesFakeSession(FakeSession):
            def get(self, url: str, *, headers=None, allow_redirects=True):
                return NeverFinishesFakeResponse(
                    url=self._url or url,
                    status=200,
                    ct=self._ct,
                    body_bytes=b"never",
                )

        async def factory():
            return NeverFinishesFakeSession(
                url="https://example.com",
                status=200,
                ct="text/html",
                body_bytes=b"never",
            )

        with _make_patch(factory):
            result = await async_fetch_public_text(
                "https://example.com", timeout_s=1.0
            )

        assert result.error == "timeout"
        assert result.status_code == 0
        assert result.text is None

    @pytest.mark.asyncio
    async def test_cancelled_error_raised_not_swallowed(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        async def cancelling_factory():
            raise asyncio.CancelledError("test cancellation")

        with _make_patch(cancelling_factory):
            with pytest.raises(asyncio.CancelledError):
                await async_fetch_public_text("https://example.com", timeout_s=5.0)

    @pytest.mark.asyncio
    async def test_generic_exception_returns_fail_soft(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        # Make session.get() itself raise the exception (inside the try block)
        class FailingSession(FakeSession):
            def get(self, url: str, *, headers=None, allow_redirects=True):
                raise RuntimeError("network failure")

        async def failing_factory():
            return FailingSession(
                url="https://example.com",
                status=200,
                ct="text/html",
                body_bytes=b"",
            )

        with _make_patch(failing_factory):
            result = await async_fetch_public_text(
                "https://example.com", timeout_s=5.0
            )

        assert result.error is not None
        assert "RuntimeError" in result.error
        assert result.status_code == 0


# ---------------------------------------------------------------------------
# G19: UTF-8 decode
# ---------------------------------------------------------------------------

class TestUtf8Decode:
    @pytest.mark.asyncio
    async def test_invalid_utf8_replaced_not_crashed(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        body = b"\xef\xbb\xbf\x80\x81\x82"  # BOM + invalid UTF-8
        factory = lambda: _make_fake_session(
            url="https://example.com",
            status=200,
            ct="text/html; charset=utf-8",
            body_bytes=body,
        )
        with _make_patch(factory):
            result = await async_fetch_public_text("https://example.com")

        assert result.text is not None
        assert result.error is None


# ---------------------------------------------------------------------------
# G20: No import-time side effects
# ---------------------------------------------------------------------------

class TestNoImportSideEffects:
    def test_no_import_time_network_calls(self):
        from hledac.universal.fetching import public_fetcher

        assert public_fetcher is not None
        assert public_fetcher.async_fetch_public_text is not None


# ---------------------------------------------------------------------------
# G26: Benchmarks
# ---------------------------------------------------------------------------

class TestBenchmark:
    @pytest.mark.asyncio
    async def test_benchmark_async_overhead(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        body = b"<html>Fast</html>"
        factory = lambda: _make_fake_session(
            url="https://example.com",
            status=200,
            ct="text/html",
            body_bytes=body,
        )
        with _make_patch(factory):
            t0 = time.perf_counter()
            result = await async_fetch_public_text("https://example.com")
            t1 = time.perf_counter()

        elapsed_ms = (t1 - t0) * 1000
        assert result.error is None
        assert elapsed_ms < 50

    @pytest.mark.asyncio
    async def test_benchmark_many_calls_stable(self):
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        body = b"<html>Hello</html>"
        factory = lambda: _make_fake_session(
            url="https://example.com",
            status=200,
            ct="text/html",
            body_bytes=body,
        )
        with _make_patch(factory):
            for i in range(100):
                result = await async_fetch_public_text(f"https://example.com/page{i}")
                assert result.error is None
                assert result.status_code == 200
