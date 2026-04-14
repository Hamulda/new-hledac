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
    """Frozen msgspec result — no mutations after construction.

    Backward-compatible: added fields have defaults so existing callers are unaffected.
    """

    url: str
    final_url: str
    status_code: int
    content_type: str
    text: str | None
    fetched_bytes: int  # actual bytes read
    declared_length: int  # Content-Length header value, -1 if absent
    elapsed_ms: float
    error: str | None = None
    # Added in F164A — feed ingress hardening
    xml_recovered: bool = False  # True: body was XML-ish but Content-Type was wrong, body is now text
    decode_replaced: bool = False  # True: UTF-8 decode used replacement chars
    body_read_error: bool = False  # True: headers were OK but body stream failed mid-read


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
# Retry constants — bounded, M1-safe
# ---------------------------------------------------------------------------

MAX_RETRIES: Final[int] = 1  # exactly one retry; no infinite loops
_RETRYABLE_STATUS_CODES: Final[frozenset[int]] = frozenset({429, 502, 503, 504, 520})


def _is_retryable_status(status_code: int) -> bool:
    return status_code in _RETRYABLE_STATUS_CODES


def _extract_retry_after(headers) -> float | None:
    """Parse Retry-After header, return seconds or None."""
    ra = headers.get("Retry-After") or headers.get("retry-after")
    if ra is None:
        return None
    try:
        return float(ra)
    except (ValueError, TypeError):
        return None


def _compute_backoff_seconds(retry_after: float | None, attempt: int) -> float:
    """Return bounded backoff in seconds.

    Uses Retry-After if available, otherwise exponential backoff capped at 8 s.
    Attempt 0 = no backoff (first failure already counted).
    """
    if retry_after is not None and retry_after > 0:
        return min(retry_after, 60.0)  # cap at 60 s to bound pause
    return min(2.0 ** (attempt + 1), 8.0)  # 4 s, capped at 8 s


def _build_retry_error(status_code: int, retry_after: float | None) -> str:
    """Build retry error string with : separator between code and details.

    Adapter uses .split(":", 2) — first two parts are always prefix+code,
    any additional colons in the message body are preserved in part[2].
    """
    parts = [f"retryable:{status_code}"]
    if retry_after is not None:
        parts.append(f"retry_after={retry_after:.1f}s")
    else:
        parts.append("backoff=exp")
    return "|".join(parts)


# ---------------------------------------------------------------------------
# XML-ish body sniffing helper — bounded, fail-safe
# ---------------------------------------------------------------------------

_XML_MARKER = b"<?xml"
_XML_TAG_RE = re.compile(rb"^\s*<[a-zA-Z]", re.IGNORECASE)


def _looks_xmlish(body: bytes) -> bool:
    """Return True if body starts like XML (<?xml or <tag).

    Strips leading ASCII whitespace so servers that prepend newlines
    before the XML declaration are correctly identified.
    """
    stripped = body.lstrip()
    if stripped.startswith(_XML_MARKER):
        return True
    return bool(_XML_TAG_RE.match(stripped))


# ---------------------------------------------------------------------------
# Decode helper — fail-soft, truth-bearing
# ---------------------------------------------------------------------------

def _try_decode(body: bytes) -> tuple[str, bool]:
    """Decode bytes to str, return (text, replaced_bool).

    replaced_bool=True when UTF-8 decoder used replacement chars (U+FFFD).
    This tells the adapter that the body was garbled, not truly empty.
    """
    try:
        text = body.decode("utf-8", errors="strict")
        return (text, False)
    except UnicodeDecodeError:
        # Use replacement mode so we still get a usable string
        text = body.decode("utf-8", errors="replace")
        # Count how many replacement chars were inserted
        replaced = "\ufffd" in text
        return (text, replaced)


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

    # --- Type guard: non-string input fails fast, fail-soft ---
    if not isinstance(url, str):
        elapsed_ms = (time.monotonic() - t0) * 1000
        return FetchResult(
            url=str(url) if url is not None else "",
            final_url=str(url) if url is not None else "",
            status_code=0,
            content_type="",
            text=None,
            fetched_bytes=0,
            declared_length=-1,
            elapsed_ms=elapsed_ms,
            error="url_empty",
        )

    # --- URL validation (strip happens inside _validate_url) ---
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

    # --- Retryable status tracking ---
    retry_after: float | None = None
    last_status_code: int = 0
    last_error: str | None = None

    for attempt in range(MAX_RETRIES + 1):
        session = await async_get_aiohttp_session()
        headers = {"User-Agent": DEFAULT_UA}

        try:
            async with asyncio.timeout(timeout_s):
                async with session.get(url, headers=headers, allow_redirects=True) as resp:
                    final_url = str(resp.url)
                    last_status_code = resp.status
                    content_type = resp.headers.get("Content-Type", "")
                    raw_content_type = content_type.split(";")[0].strip().lower()

                    # --- Retryable status → wait and retry once ---
                    if _is_retryable_status(last_status_code):
                        last_error = _build_retry_error(last_status_code, retry_after)
                        if attempt < MAX_RETRIES:
                            retry_after = _extract_retry_after(resp.headers)
                            backoff = _compute_backoff_seconds(retry_after, attempt)
                            await asyncio.sleep(backoff)
                            continue
                        # Exhausted retries — return with error prefix
                        elapsed_ms = (time.monotonic() - t0) * 1000
                        return FetchResult(
                            url=url,
                            final_url=final_url,
                            status_code=last_status_code,
                            content_type=content_type,
                            text=None,
                            fetched_bytes=0,
                            declared_length=-1,
                            elapsed_ms=elapsed_ms,
                            error=last_error,
                        )

                    # --- Content-type gate with XML-ish body recovery (Feed ingress hardening F164A) ---
                    xml_recovered = False
                    rejected_ct = raw_content_type not in ACCEPTED_CONTENT_TYPES

                    raw_declared = resp.headers.get("Content-Length")
                    try:
                        declared_length = int(raw_declared) if raw_declared else -1
                    except (ValueError, TypeError):
                        declared_length = -1

                    # --- Chunked body read with size cap ---
                    body_chunks: list[bytes] = []
                    total_read = 0
                    accumulated_ok = True
                    first_chunk_peeked = False

                    async for chunk in resp.content.iter_chunked(8192):
                        chunk_len = len(chunk)

                        # Peek: check first chunk for XML-ish body when CT is wrong
                        if rejected_ct and not first_chunk_peeked:
                            first_chunk_peeked = True
                            if _looks_xmlish(chunk):
                                # Feed ingress recovery: wrong CT but XML body — accept it
                                xml_recovered = True
                            elif total_read == 0:
                                # First chunk is not XML-ish and we haven't accumulated anything —
                                # non-XML body under wrong CT: reject without reading remainder
                                elapsed_ms = (time.monotonic() - t0) * 1000
                                return FetchResult(
                                    url=url,
                                    final_url=final_url,
                                    status_code=last_status_code,
                                    content_type=content_type,
                                    text=None,
                                    fetched_bytes=0,
                                    declared_length=declared_length,
                                    elapsed_ms=elapsed_ms,
                                    error=f"content_type_rejected:{raw_content_type}",
                                )

                        if total_read + chunk_len > max_bytes:
                            remaining = max_bytes - total_read
                            if remaining > 0:
                                body_chunks.append(chunk[:remaining])
                                total_read += remaining
                            accumulated_ok = False
                            elapsed_ms = (time.monotonic() - t0) * 1000
                            return FetchResult(
                                url=url,
                                final_url=final_url,
                                status_code=last_status_code,
                                content_type=content_type,
                                text=None,
                                fetched_bytes=total_read,
                                declared_length=declared_length,
                                elapsed_ms=elapsed_ms,
                                error="size_cap_exceeded",
                            )
                        body_chunks.append(chunk)
                        total_read += chunk_len

                    if accumulated_ok and body_chunks:
                        try:
                            body_bytes = b"".join(body_chunks)
                            # Detect decode replacement chars for truth
                            text, decode_replaced = _try_decode(body_bytes)
                        except Exception:
                            text = None
                            decode_replaced = False
                    else:
                        text = None
                        decode_replaced = False

                    elapsed_ms = (time.monotonic() - t0) * 1000
                    return FetchResult(
                        url=url,
                        final_url=final_url,
                        status_code=last_status_code,
                        content_type=content_type,
                        text=text,
                        fetched_bytes=total_read,
                        declared_length=declared_length,
                        elapsed_ms=elapsed_ms,
                        error=None,
                        xml_recovered=xml_recovered,
                        decode_replaced=decode_replaced,
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
                error=f"fetch_error;{type(exc).__name__};{exc}",
                body_read_error=True,
            )

    # Should not reach here, but as safeguard:
    elapsed_ms = (time.monotonic() - t0) * 1000
    return FetchResult(
        url=url,
        final_url=url,
        status_code=last_status_code,
        content_type="",
        text=None,
        fetched_bytes=0,
        declared_length=-1,
        elapsed_ms=elapsed_ms,
        error=last_error or "retry_exhausted",
        body_read_error=True,
    )


__all__ = [
    "async_fetch_public_text",
    "process_html_payload",
    "DEFAULT_UA",
    "MAX_BYTES_DEFAULT",
    "MAX_BYTES_HARD",
    "MAX_RETRIES",
    "FetchResult",
    "_is_retryable_status",
    "_extract_retry_after",
    "_compute_backoff_seconds",
    "_try_decode",
    "_looks_xmlish",
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
