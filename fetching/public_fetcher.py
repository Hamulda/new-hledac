# hledac/universal/fetching/public_fetcher.py
# Sprint 8AD — First live public text fetch adapter v1
# aiohttp/shared-session, chunked size-safe, timeout-safe, passive-only
"""
Public-passive text/HTML fetcher using shared aiohttp session runtime.
Always-on, bounded, fail-soft, typed via msgspec.Struct.
"""
from __future__ import annotations

import asyncio
import re
import time
import urllib.parse
from typing import Final

import msgspec

from hledac.universal.network.session_runtime import async_get_aiohttp_session
from hledac.universal.patterns.pattern_matcher import match_text, configure_patterns, get_default_bootstrap_patterns

# ---------------------------------------------------------------------------
# Public API — single entry point
# ---------------------------------------------------------------------------

DEFAULT_UA: Final[str] = (
    "Mozilla/5.0 (compatible; research-bot/1.0; +passive-public-fetch)"
)

MAX_BYTES_DEFAULT: Final[int] = 2_000_000
MAX_BYTES_HARD: Final[int] = 10_000_000

# ---------------------------------------------------------------------------
# Typed result DTO
# ---------------------------------------------------------------------------


class FetchResult(msgspec.Struct, frozen=True, gc=False):
    """Frozen msgspec result — no mutations after construction."""

    url: str
    final_url: str
    status_code: int
    content_type: str
    text: str | None
    fetched_bytes: int  # actual bytes read
    declared_length: int  # Content-Length header value, -1 if absent
    elapsed_ms: float
    error: str | None = None


# ---------------------------------------------------------------------------
# Content-type whitelist (text-ish only)
# ---------------------------------------------------------------------------

ACCEPTED_CONTENT_TYPES: Final[frozenset[str]] = frozenset({
    "text/html",
    "text/plain",
    "text/xml",
    "application/xhtml+xml",
    "application/xml",
    "application/rss+xml",
    "application/atom+xml",
})


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------


def _validate_url(url: str) -> str | None:
    """
    Validate URL is http/https and well-formed.
    Returns None on success, error string on failure.
    """
    if not url or not isinstance(url, str):
        return "url_empty"
    url = url.strip()
    if not url:
        return "url_empty"
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return "url_malformed"
    scheme = parsed.scheme.lower()
    if not scheme:
        return "url_malformed"
    if scheme not in ("http", "https"):
        return f"url_unsupported_scheme:{scheme}"
    if not parsed.netloc:
        return "url_no_netloc"
    return None


# ---------------------------------------------------------------------------
# Main fetch function
# ---------------------------------------------------------------------------


async def async_fetch_public_text(
    url: str,
    timeout_s: float = 35.0,
    max_bytes: int = MAX_BYTES_DEFAULT,
) -> FetchResult:
    """
    Fetch a public URL using the shared aiohttp session.

    Passive-only: no auth, no cookies, no stealth.
    Chunked streaming with hard size cap.
    CancelledError propagates (not swallowed).

    Parameters
    ----------
    url : str
        Target URL (http or https only).
    timeout_s : float
        Per-request timeout in seconds (default 35 s).
    max_bytes : int
        Maximum bytes to read from body (default 2 MB, hard cap 10 MB).

    Returns
    -------
    FetchResult
        Typed result with final_url, status, content_type, text (or None),
        byte counts, elapsed_ms, and optional error.
    """
    t0 = time.monotonic()
    url = url.strip()

    # --- URL validation ---
    validation_error = _validate_url(url)
    if validation_error is not None:
        elapsed_ms = (time.monotonic() - t0) * 1000
        return FetchResult(
            url=url,
            final_url=url,
            status_code=0,
            content_type="",
            text=None,
            fetched_bytes=0,
            declared_length=-1,
            elapsed_ms=elapsed_ms,
            error=validation_error,
        )

    # --- Size cap enforcement ---
    if max_bytes > MAX_BYTES_HARD:
        max_bytes = MAX_BYTES_HARD

    # --- Session from shared runtime ---
    session = await async_get_aiohttp_session()

    headers = {"User-Agent": DEFAULT_UA}

    try:
        # Use asyncio.timeout() for deadline awareness
        async with asyncio.timeout(timeout_s):
            async with session.get(url, headers=headers, allow_redirects=True) as resp:
                final_url = str(resp.url)
                status_code = resp.status
                content_type = resp.headers.get("Content-Type", "")
                raw_content_type = content_type.split(";")[0].strip().lower()

                # --- Content-type gate ---
                if raw_content_type not in ACCEPTED_CONTENT_TYPES:
                    elapsed_ms = (time.monotonic() - t0) * 1000
                    return FetchResult(
                        url=url,
                        final_url=final_url,
                        status_code=status_code,
                        content_type=content_type,
                        text=None,
                        fetched_bytes=0,
                        declared_length=-1,
                        elapsed_ms=elapsed_ms,
                        error=f"content_type_rejected:{raw_content_type}",
                    )

                # --- Chunked body read with size cap ---
                body_chunks: list[bytes] = []
                total_read = 0
                accumulated_ok = True

                # declared length from header (may be -1 / absent)
                raw_declared = resp.headers.get("Content-Length")
                try:
                    declared_length = int(raw_declared) if raw_declared else -1
                except (ValueError, TypeError):
                    declared_length = -1

                async for chunk in resp.content.iter_chunked(8192):
                    chunk_len = len(chunk)
                    if total_read + chunk_len > max_bytes:
                        # Truncate at cap — take only what fits
                        remaining = max_bytes - total_read
                        if remaining > 0:
                            body_chunks.append(chunk[:remaining])
                            total_read += remaining
                        accumulated_ok = False
                        elapsed_ms = (time.monotonic() - t0) * 1000
                        return FetchResult(
                            url=url,
                            final_url=final_url,
                            status_code=status_code,
                            content_type=content_type,
                            text=None,
                            fetched_bytes=total_read,
                            declared_length=declared_length,
                            elapsed_ms=elapsed_ms,
                            error="size_cap_exceeded",
                        )
                    body_chunks.append(chunk)
                    total_read += chunk_len

                # --- Decode ---
                if accumulated_ok and body_chunks:
                    try:
                        body_bytes = b"".join(body_chunks)
                        text = body_bytes.decode("utf-8", errors="replace")
                    except Exception:
                        text = None
                else:
                    text = None

                elapsed_ms = (time.monotonic() - t0) * 1000
                return FetchResult(
                    url=url,
                    final_url=final_url,
                    status_code=status_code,
                    content_type=content_type,
                    text=text,
                    fetched_bytes=total_read,
                    declared_length=declared_length,
                    elapsed_ms=elapsed_ms,
                    error=None,
                )

    except asyncio.TimeoutError:
        elapsed_ms = (time.monotonic() - t0) * 1000
        return FetchResult(
            url=url,
            final_url=url,
            status_code=0,
            content_type="",
            text=None,
            fetched_bytes=0,
            declared_length=-1,
            elapsed_ms=elapsed_ms,
            error="timeout",
        )
    except asyncio.CancelledError:
        # Never swallow CancelledError — re-raise so the cancellation propagates
        elapsed_ms = (time.monotonic() - t0) * 1000
        raise
    except Exception as exc:
        elapsed_ms = (time.monotonic() - t0) * 1000
        return FetchResult(
            url=url,
            final_url=url,
            status_code=0,
            content_type="",
            text=None,
            fetched_bytes=0,
            declared_length=-1,
            elapsed_ms=elapsed_ms,
            error=f"fetch_error:{type(exc).__name__}:{exc}",
        )


__all__ = [
    "async_fetch_public_text",
    "process_html_payload",
    "DEFAULT_UA",
    "MAX_BYTES_DEFAULT",
    "MAX_BYTES_HARD",
    "FetchResult",
]

# ---------------------------------------------------------------------------
# HTML → text + pattern matching (CPU-bound, runs in shared CPU_EXECUTOR)
# ---------------------------------------------------------------------------
from hledac.universal.utils.executors import CPU_EXECUTOR


def _sync_process_html(html: str) -> tuple[str, list]:
    """Synchronous CPU-bound HTML parsing + pattern matching.

    Runs in CPU_EXECUTOR thread pool — never blocks the async event loop.
    Fail-safe: malformed HTML returns empty text, never raises.
    """
    # Bootstrap patterns on first use (idempotent, thread-safe)
    configure_patterns(get_default_bootstrap_patterns())

    # markdownify with plaintext fallback
    try:
        import markdownify as _md

        text = _md.markdownify(html, strip=["script", "style"], heading_style="ATX")
    except Exception:
        import html as _html

        text = re.sub(r"<[^>]+>", " ", _html.unescape(html))
        text = re.sub(r"\s{2,}", " ", text).strip()

    # Pattern scan
    matches = match_text(text)
    return (text, matches)


async def process_html_payload(html: str, url: str) -> tuple[str, list]:
    """Offload HTML→text+pattern matching to shared CPU_EXECUTOR.

    Args:
        html: Raw HTML content.
        url: Source URL (for context in errors; not used for fetching).

    Returns:
        Tuple of (markdown-stripped text, pattern match list).
        Never raises — malformed HTML returns (stripped_text, []) on fallback.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(CPU_EXECUTOR, _sync_process_html, html)
