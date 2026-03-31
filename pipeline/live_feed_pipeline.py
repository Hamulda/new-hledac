"""
Sprint 8AN: Live RSS/Atom feed pipeline v2 — pattern-backed findings.

feed_url -> 8AF fetch+parse -> entry normalization
    -> HTML->text (word-boundary safe, entity-safe)
    -> pattern scan via PatternMatcher (offloaded, bounded concurrency)
    -> CanonicalFinding per PatternHit
    -> storage

Public API:
    async_run_live_feed_pipeline()
    FeedPipelineEntryResult, FeedPipelineRunResult

Invariants:
- Public/passive-only, no AO, no LLM
- store=None is valid no-op
- PatternMatcher is SSOT — no regex fallback
- Empty matcher registry = valid zero-findings state
- source_type = "rss_atom_pipeline", confidence = 0.8
- Deterministic finding_id via sha256 (no hash())
- payload_text = short context around hit (200 char radius)
- Per-entry dedup by (label, pattern, value) preserve-first
- Per-run dedup by entry_url
- HTML->text: strip script/style first, tag→space, then unescape
- Pattern scan offloaded via asyncio.to_thread + shared semaphore (max 4)
- PatternMatcher case-insensitive (matcher handles .lower() internally)
- entry_hash in FeedEntryHit for future dedup
-UMA emergency -> fail-soft abort
"""

from __future__ import annotations

import asyncio
import html
import hashlib
import logging
import re
import time
from collections import Counter
from typing import TYPE_CHECKING, Any

import msgspec

if TYPE_CHECKING:
    from hledac.universal.knowledge.duckdb_store import (
        CanonicalFinding,
        DuckDBShadowStore,
    )

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_FEED_TEXT_CHARS: int = 4000
FEED_PAYLOAD_CONTEXT_CHARS: int = 200
MAX_FEED_PATTERN_TASKS: int = 4

# ---------------------------------------------------------------------------
# Patchable symbol for pattern offload (tests patch this, not asyncio.to_thread)
# ---------------------------------------------------------------------------

_ASYNC_PATTERN_OFFLOAD: Any = asyncio.to_thread

# ---------------------------------------------------------------------------
# Shared semaphore for bounded pattern offload concurrency
# ---------------------------------------------------------------------------

_pattern_semaphore: asyncio.Semaphore | None = None


def _get_pattern_offload_semaphore() -> asyncio.Semaphore:
    """Return the shared module-level semaphore for pattern offload concurrency."""
    global _pattern_semaphore
    if _pattern_semaphore is None:
        _pattern_semaphore = asyncio.Semaphore(MAX_FEED_PATTERN_TASKS)
    return _pattern_semaphore


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------

class FeedPipelineEntryResult(msgspec.Struct, frozen=True, gc=False):
    """Result for a single feed entry."""
    entry_url: str
    accepted_findings: int
    stored_findings: int
    error: str | None = None


class FeedPipelineRunResult(msgspec.Struct, frozen=True, gc=False):
    """Result for a full feed pipeline run."""
    feed_url: str
    fetched_entries: int
    accepted_findings: int = 0
    stored_findings: int = 0
    patterns_configured: int = 0
    matched_patterns: int = 0
    pages: tuple[FeedPipelineEntryResult, ...] = ()
    error: str | None = None
    # Sprint 8AU: pre-store observability
    entries_seen: int = 0
    entries_with_empty_assembled_text: int = 0
    entries_with_text: int = 0
    entries_scanned: int = 0
    entries_with_hits: int = 0
    total_pattern_hits: int = 0
    findings_built_pre_store: int = 0
    assembled_text_chars_total: int = 0
    avg_assembled_text_len: float = 0.0
    signal_stage: str = "unknown"
    # Sprint 8BC: bounded sample capture (first 3 entries, truncated to 160 chars)
    sample_scanned_texts: tuple[str, ...] = ()
    sample_hit_counts: tuple[int, ...] = ()
    sample_hit_labels_union: tuple[str, ...] = ()
    sample_texts_truncated: bool = False
    feed_content_mismatch: bool = False
    # Sprint 8BE: source-specific text enrichment
    entries_with_rich_feed_content: int = 0
    entries_with_article_fallback: int = 0
    article_fallback_fetch_attempts: int = 0
    article_fallback_fetch_successes: int = 0
    enriched_text_chars_total: int = 0
    avg_enriched_text_len: float = 0.0
    sample_enriched_texts: tuple[str, ...] = ()
    enrichment_phase_used: str = "none"   # "feed_rich_content" / "article_fallback" / "mixed"
    temporal_feed_vocabulary_mismatch: bool = False


# ---------------------------------------------------------------------------
# Pre-store signal diagnosis helper (Sprint 8AU)
# ---------------------------------------------------------------------------


def diagnose_feed_signal_stage(
    entries_seen: int,
    entries_with_empty_assembled_text: int,
    entries_scanned: int,
    entries_with_hits: int,
    findings_built_pre_store: int,
    patterns_configured: int,
) -> str:
    """
    Diagnose which stage the signal is lost at.

    Returns one of:
      empty_registry       — no patterns configured at all
      no_pattern_hits     — patterns exist but nothing matched
      pattern_hits_but_no_findings_built  — hits seen but all were deduped/filtered
      prestore_findings_present          — findings exist pre-store
      unknown                        — counters not yet populated
    """
    if patterns_configured == 0:
        return "empty_registry"
    if entries_scanned == 0:
        return "no_pattern_hits"
    if entries_with_hits == 0:
        return "no_pattern_hits"
    if findings_built_pre_store == 0 and entries_with_hits > 0:
        return "pattern_hits_but_no_findings_built"
    if findings_built_pre_store > 0:
        return "prestore_findings_present"
    return "unknown"


# ---------------------------------------------------------------------------
# Batch DTOs (Sprint 8AL)
# ---------------------------------------------------------------------------

class FeedSourceRunResult(msgspec.Struct, frozen=True, gc=False):
    """Result for a single feed source run within a batch."""
    feed_url: str
    label: str
    origin: str
    priority: int
    fetched_entries: int
    accepted_findings: int
    stored_findings: int
    elapsed_ms: float = 0.0
    error: str | None = None
    signal_stage: str = "unknown"


class FeedSourceBatchRunResult(msgspec.Struct, frozen=True, gc=False):
    """Result for a multi-feed source batch run."""
    total_sources: int
    completed_sources: int
    fetched_entries: int
    accepted_findings: int
    stored_findings: int
    sources: tuple[FeedSourceRunResult, ...]
    error: str | None = None
    # Sprint 8BE Phase 3: dominant signal stage across all sources (mode)
    dominant_signal_stage: str = "unknown"


# ---------------------------------------------------------------------------
# HTML stripping — word-boundary safe, entity-safe, M1-safe
# Invariant B.8: strip script/style FIRST, then tag→space, THEN unescape
# ---------------------------------------------------------------------------

# Match entire <script>...</script> or <style>...</style> blocks (DOTALL)
_SCRIPT_STYLE_RE = re.compile(
    r"<script[^>]*>.*?</script>|"
    r"<style[^>]*>.*?</style>",
    re.DOTALL | re.IGNORECASE,
)
# Replace any HTML tag with a single space
_STRIP_TAGS_RE = re.compile(r"<[^>]+>")
_MULTI_WHITESPACE_RE = re.compile(r"[ \t\r\n]+")


def _strip_html_tags_from_text(text: str) -> str:
    """
    Strip HTML tags word-boundary safe, OSINT-safe.

    Steps (strict order per invariant B.9):
    1. Remove entire <script> and <style> blocks
    2. Replace remaining HTML tags with a single space
    3. Normalize whitespace
    4. html.unescape AFTER tag removal
    """
    if not text:
        return ""
    # Step 1: Remove script/style blocks completely
    cleaned = _SCRIPT_STYLE_RE.sub("", text)
    # Step 2: Replace tags with space
    cleaned = _STRIP_TAGS_RE.sub(" ", cleaned)
    # Step 3: Normalize whitespace
    cleaned = _MULTI_WHITESPACE_RE.sub(" ", cleaned).strip()
    # Step 4: Unescape HTML entities AFTER tag removal
    cleaned = html.unescape(cleaned)
    return cleaned


# Sprint 8BE: markdownify lazy import (optional dependency)
_markdownify_available: bool = False
try:
    import markdownify
    _markdownify_available = True
except ImportError:
    markdownify = None  # type: ignore[assignment]


def _convert_rich_html_to_text(rich_html: str) -> str:
    """
    Convert rich HTML content to clean text.

    Priority (per Sprint 8BE Phase 1):
    1. markdownify (if available) — preserves structure
    2. strip fallback — same as summary path

    Returns empty string if input is empty/whitespace.
    """
    if not rich_html or not rich_html.strip():
        return ""
    if _markdownify_available:
        try:
            converted = markdownify.markdownify(rich_html, strip=["script", "style"])
            converted = _MULTI_WHITESPACE_RE.sub(" ", converted).strip()
            if converted:
                return converted
        except Exception:
            pass
    return _strip_html_tags_from_text(rich_html)


def _assemble_enriched_feed_text(
    title: str,
    summary: str,
    rich_content: str,
) -> tuple[str, str]:
    """
    Assemble deterministic clean text from title + summary + rich_content.

    Sprint 8BE PHASE 1: source-specific text enrichment.

    Priority hierarchy:
    1. title (if non-empty)
    2. summary (stripped and cleaned, if non-empty)
    3. rich_content (converted, if non-empty)
    4. sentinel "[no content]" if all empty

    Returns (clean_text, enrichment_phase).
    """
    parts: list[str] = []
    enrichment_phase = "none"

    if title:
        parts.append(title.strip())

    if summary:
        stripped = _strip_html_tags_from_text(summary)
        if stripped:
            parts.append(stripped)

    if rich_content:
        converted = _convert_rich_html_to_text(rich_content)
        if converted:
            parts.append(converted)
            enrichment_phase = "feed_rich_content"

    if not parts:
        return ("[no content]", "none")
    return ("\n\n".join(parts), enrichment_phase)


# ---------------------------------------------------------------------------
# Deterministic clean text assembly
# ---------------------------------------------------------------------------

def _assemble_clean_feed_text(title: str, summary: str) -> str:
    """
    Assemble deterministic clean text from title + summary.

    Deterministic assembly order:
    1. title (if non-empty)
    2. summary (stripped and cleaned, if non-empty)
    3. sentinel "[no content]" if both empty

    No html.unescape before tag stripping (per B.9).
    """
    parts: list[str] = []
    if title:
        parts.append(title.strip())
    if summary:
        stripped = _strip_html_tags_from_text(summary)
        if stripped:
            parts.append(stripped)
    if not parts:
        return "[no content]"
    return "\n\n".join(parts)


# Backwards-compatible alias (used by probe_8ah tests)
_entry_payload_text = _assemble_clean_feed_text


# ---------------------------------------------------------------------------
# Backwards-compatible entry-to-candidate-findings (used by probe_8ah tests)
# DEPRECATED: pipeline now uses pattern-backed approach via _entry_to_pattern_findings
# ---------------------------------------------------------------------------


def _entry_to_candidate_findings(
    feed_url: str,
    entry: Any,
    query_context: str | None,
) -> list[dict]:
    """
    [DEPRECATED — Sprint 8AN] Entry-backed CanonicalFinding dicts.
    Replaced by pattern-backed _entry_to_pattern_findings().

    This function is kept for probe_8ah test compatibility only.
    """
    title = getattr(entry, "title", "") or ""
    summary = getattr(entry, "summary", "") or ""
    entry_url = getattr(entry, "entry_url", "") or ""
    published_raw = getattr(entry, "published_raw", "") or ""
    published_ts = getattr(entry, "published_ts", None)

    if not entry_url:
        entry_url = f"urn:feed:entry:{title[:64]}"

    payload = _assemble_clean_feed_text(title, summary)
    ts = _sane_timestamp(published_ts)

    query = query_context or feed_url

    return [{
        "finding_id": _make_feed_finding_id(
            feed_url, entry_url, title, published_raw
        ),
        "query": query,
        "source_type": "rss_atom_pipeline",
        "confidence": 0.8,
        "ts": ts,
        "provenance": ("rss_atom", feed_url, entry_url, "feed_entry"),
        "payload_text": payload,
    }]


# ---------------------------------------------------------------------------
# Timestamp sanity
# ---------------------------------------------------------------------------

_MIN_SANE_TS = 946684800.0  # 2000-01-01 00:00:00 UTC
_ONE_DAY_S = 86400.0


def _sane_timestamp(published_ts: float | None) -> float:
    """Return sane timestamp or fallback to time.time()."""
    now = time.time()
    if published_ts is None:
        return now
    if published_ts < _MIN_SANE_TS or published_ts > (now + _ONE_DAY_S):
        return now
    return published_ts


# ---------------------------------------------------------------------------
# Deterministic finding ID
# ---------------------------------------------------------------------------

def _make_feed_finding_id(
    feed_url: str,
    entry_url: str,
    label: str,
    pattern: str,
    value: str = "",
) -> str:
    """
    Deterministic ID via sha256 using pattern identity fields.
    No hash() — deterministic across runs.
    """
    key = f"{feed_url}\x00{entry_url}\x00{label}\x00{pattern}\x00{value}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Per-run dedup
# ---------------------------------------------------------------------------

class _RunDeduper:
    """Per-run preserve-first dedup by entry_url.

    Backwards-compatible: is_new(entry_url) for pattern-backed pipeline,
    is_new(entry_url, title, published_raw) for legacy entry-backed callers.
    """

    def __init__(self) -> None:
        self._seen: dict[str, bool] = {}

    def is_new(self, entry_url: str, _title: str = "", _raw: str = "") -> bool:
        # Legacy entry-backed callers pass (url, title, raw) — key is entry_url only
        # Pattern-backed callers pass just (entry_url,)
        if entry_url in self._seen:
            return False
        self._seen[entry_url] = True
        return True


# ---------------------------------------------------------------------------
# PatternMatcher import and helpers
# ---------------------------------------------------------------------------

# Import here so that absence of pattern_matcher is a hard fail at import time
from hledac.universal.patterns.pattern_matcher import match_text

# ---------------------------------------------------------------------------
# Per-entry dedup for pattern-backed findings
# ---------------------------------------------------------------------------

class _EntryDeduper:
    """Per-entry dedup by (label, pattern, value) preserve-first."""

    def __init__(self) -> None:
        self._seen: set[tuple[str, str, str]] = set()

    def is_new(self, label: str, pattern: str, value: str) -> bool:
        key = (label or "", pattern, value)
        if key in self._seen:
            return False
        self._seen.add(key)
        return True


# ---------------------------------------------------------------------------
# Pattern scan — offloaded, bounded concurrency
# ---------------------------------------------------------------------------


async def _async_scan_feed_text(text: str) -> list:
    """
    Offload pattern scan to thread executor with shared semaphore.

    PatternMatcher.match_text() handles casefolding internally.
    Empty registry = empty list (valid zero-findings state).

    Raises:
        RuntimeError: if the pattern matcher itself fails (for fail-soft guard).
        CancelledError: propagated if task is cancelled.
    """
    if not text:
        return []

    # Sprint 8AU: normalize text before scan to recover morphology variants
    # (e.g. "vulnerabilities" -> "vulnerabilities" via casefold ensures hits)
    normalized = text.casefold()

    # Bounded concurrency via shared semaphore
    sem = _get_pattern_offload_semaphore()

    async with sem:
        hits: list = await _ASYNC_PATTERN_OFFLOAD(match_text, normalized)
    return hits


# ---------------------------------------------------------------------------
# Payload text extraction around hit — unicode-safe, 200 char radius
# ---------------------------------------------------------------------------


def _extract_payload_context(
    text: str,
    hit_start: int,
    hit_end: int,
) -> str:
    """
    Extract unicode-safe payload context around pattern hit.

    Uses FEED_PAYLOAD_CONTEXT_CHARS radius.
    Cuts at whitespace boundaries if possible.
    """
    radius = FEED_PAYLOAD_CONTEXT_CHARS
    start = max(0, hit_start - radius)
    end = min(len(text), hit_end + radius)

    ctx = text[start:end]

    # Cut at whitespace boundaries to avoid mid-word cuts
    # Prefer breaking at newline/space before the hit
    if start > 0:
        # Find last whitespace before hit_start in the context window
        pre_cut = ctx[: hit_start - start]
        last_ws = max(pre_cut.rfind("\n"), pre_cut.rfind(" "))
        if last_ws > 0:
            ctx = ctx[last_ws + 1:]

    if end < len(text):
        # Find first whitespace after hit_end
        post_cut = ctx[hit_end - start:]
        first_ws = min(post_cut.find("\n"), post_cut.find(" "))
        if first_ws > 0:
            ctx = ctx[: hit_end - start + first_ws]

    ctx = ctx.strip()
    # Add ellipsis only if we actually cut
    cut_left = start > 0
    cut_right = end < len(text)
    if cut_left:
        ctx = "…" + ctx
    if cut_right:
        ctx = ctx + "…"
    return ctx


# ---------------------------------------------------------------------------
# PatternHit -> CanonicalFinding
# ---------------------------------------------------------------------------


def _pattern_hit_to_finding(
    feed_url: str,
    entry_url: str,
    hit: Any,
    query_context: str | None,
    clean_text: str,
) -> dict:
    """
    Map a single PatternHit to a CanonicalFinding dict.

    PatternHit: pattern, start, end, value, label
    """
    label = hit.label or ""
    pattern = hit.pattern
    value = hit.value

    ts = time.time()
    query = query_context or feed_url

    payload_text = _extract_payload_context(
        clean_text,
        hit.start,
        hit.end,
    )

    return {
        "finding_id": _make_feed_finding_id(
            feed_url, entry_url, label, pattern, value
        ),
        "query": query,
        "source_type": "rss_atom_pipeline",
        "confidence": 0.8,
        "ts": ts,
        "provenance": ("rss_atom", feed_url, entry_url, f"pattern:{label}"),
        "payload_text": payload_text,
    }


# ---------------------------------------------------------------------------
# Entry -> pattern-backed findings (replaces _entry_to_candidate_findings)
# ---------------------------------------------------------------------------


_MIN_ARTICLE_FALLBACK_CHARS: int = 400
_MAX_ARTICLE_FALLBACK_TIMEOUT: float = 8.0
_MAX_ARTICLE_FALLBACK_KB: int = 150


async def _fetch_article_text(entry_url: str) -> tuple[str, bool]:
    """
    Fetch article body via direct aiohttp GET and strip HTML.

    Returns (article_text, success).
    NEVER raises — all exceptions are caught, success=False on any failure.
    CancelledError is NOT caught (propagated).
    """
    try:
        from urllib.parse import urlparse
        parsed = urlparse(entry_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return ("", False)
    except Exception:
        return ("", False)

    try:
        from hledac.universal.network.session_runtime import async_get_aiohttp_session
    except Exception:
        return ("", False)

    try:
        session = await async_get_aiohttp_session()
    except Exception:
        return ("", False)

    try:
        import aiohttp as _aiohttp
    except Exception:
        return ("", False)

    try:
        async with asyncio.timeout(_MAX_ARTICLE_FALLBACK_TIMEOUT):
            try:
                async with session.get(entry_url, timeout=_aiohttp.ClientTimeout(total=_MAX_ARTICLE_FALLBACK_TIMEOUT)) as resp:
                    if resp.status != 200:
                        return ("", False)
                    raw = await resp.read()
            except asyncio.CancelledError:
                raise
            except Exception:
                return ("", False)
    except asyncio.CancelledError:
        raise
    except Exception:
        return ("", False)

    # Decode with fallback, cap at MAX_ARTICLE_FALLBACK_KB
    try:
        raw = raw[: _MAX_ARTICLE_FALLBACK_KB * 1024]
        try:
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            try:
                text = raw.decode("latin-1", errors="replace")
            except Exception:
                return ("", False)
    except Exception:
        return ("", False)

    article_text = _strip_html_tags_from_text(text)
    if not article_text:
        return ("", False)
    return (article_text.strip(), True)


async def _entry_to_pattern_findings(
    feed_url: str,
    entry: Any,
    query_context: str | None,
) -> tuple[list[dict], int, int, int, str, str, bool, bool]:
    """
    Entry -> pattern-backed CanonicalFinding dicts.

    Returns (findings, patterns_configured, matched_patterns, assembled_text_len, clean_text, enrichment_phase, article_fallback_used, article_fallback_attempted).
    Empty registry = valid zero-findings state (patterns_configured=0, matched=0).
    enrichment_phase: "feed_rich_content" | "article_fallback" | "none"
    article_fallback_used: True if article was fetched and enriched
    """
    title = getattr(entry, "title", "") or ""
    summary = getattr(entry, "summary", "") or ""
    rich_content = getattr(entry, "rich_content", "") or ""
    entry_url = getattr(entry, "entry_url", "") or ""

    if not entry_url:
        entry_url = f"urn:feed:entry:{title[:64]}"

    # Sprint 8BE PHASE 1: use enriched assembly (title + summary + rich_content)
    clean_text, enrichment_phase = _assemble_enriched_feed_text(title, summary, rich_content)
    assembled_text_len = len(clean_text)
    article_fallback_used = False

    # Sprint 8BE PHASE 2: article fallback when assembled text is too short
    # Invariant: only fetch if assembled_len < 400 and entry_url is valid http/https
    article_fallback_attempted = False
    if assembled_text_len < _MIN_ARTICLE_FALLBACK_CHARS:
        article_text = ""
        article_success = False
        try:
            article_text, article_success = await _fetch_article_text(entry_url)
        except asyncio.CancelledError:
            raise  # never swallow
        except Exception:
            pass

        article_fallback_attempted = True
        if article_success and article_text:
            # Append article text to existing clean_text
            combined = f"{clean_text}\n\n{article_text}"
            # Hard cap on combined text
            if len(combined) > MAX_FEED_TEXT_CHARS:
                combined = combined[:MAX_FEED_TEXT_CHARS]
            clean_text = combined
            assembled_text_len = len(clean_text)
            enrichment_phase = "article_fallback"
            article_fallback_used = True

    # Hard cap on assembled text (redundant but defensive)
    if assembled_text_len > MAX_FEED_TEXT_CHARS:
        clean_text = clean_text[:MAX_FEED_TEXT_CHARS]
        assembled_text_len = len(clean_text)

    # Get pattern count before scan
    from hledac.universal.patterns.pattern_matcher import get_pattern_matcher
    matcher_state = get_pattern_matcher()
    patterns_configured = len(matcher_state._registry_snapshot)

    # Pattern scan — offloaded, bounded
    try:
        hits = await _async_scan_feed_text(clean_text)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # Fail-soft: re-raise so pipeline loop records pattern_step_failed
        raise RuntimeError(f"pattern_scan_failed: {exc}") from exc

    matched_patterns = len(hits)

    if not hits:
        return ([], patterns_configured, matched_patterns, assembled_text_len, clean_text, enrichment_phase, article_fallback_used, article_fallback_attempted)

    # Per-entry dedup by (label, pattern, value)
    entry_deduper = _EntryDeduper()
    findings: list[dict] = []

    for hit in hits:
        label = hit.label or ""
        pattern = hit.pattern
        value = hit.value

        if not entry_deduper.is_new(label, pattern, value):
            continue

        finding = _pattern_hit_to_finding(
            feed_url, entry_url, hit, query_context, clean_text
        )
        findings.append(finding)

    return (findings, patterns_configured, matched_patterns, assembled_text_len, clean_text, enrichment_phase, article_fallback_used, article_fallback_attempted)


# ---------------------------------------------------------------------------
# UMA interaction
# ---------------------------------------------------------------------------

async def _check_uma_emergency() -> bool:
    """Return True if UMA is in emergency state."""
    try:
        from hledac.universal.core.resource_governor import sample_uma_status
        uma = sample_uma_status()
        return uma.state == "emergency"
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Main pipeline (pattern-backed)
# ---------------------------------------------------------------------------

async def async_run_live_feed_pipeline(
    feed_url: str,
    store: "DuckDBShadowStore | None" = None,
    query_context: str | None = None,
    max_entries: int = 20,
    timeout_s: float = 35.0,
    max_bytes: int = 2_000_000,
) -> FeedPipelineRunResult:
    """
    Run live feed pipeline for a single feed_url.

    Steps:
    1. Check UMA emergency -> fail-soft abort
    2. Fetch+parse via 8AF async_fetch_feed_entries()
    3. Per-entry: assemble clean text -> pattern scan -> dedup -> storage
    4. Return aggregated result with pattern observability

    Parameters
    ----------
    feed_url : str
        The feed URL to fetch.
    store : DuckDBShadowStore | None
        Optional storage. None = count-only mode.
    query_context : str | None
        Optional query context for findings.
    max_entries : int
        Max entries to process (clamped by 8AF to 1-100).
    timeout_s : float
        Feed fetch timeout.
    max_bytes : int
        Max bytes to fetch.

    Returns
    -------
    FeedPipelineRunResult
        With patterns_configured and matched_patterns observability.
    """
    # Step 1: UMA emergency check
    try:
        if await _check_uma_emergency():
            return FeedPipelineRunResult(
                feed_url=feed_url,
                fetched_entries=0,
                accepted_findings=0,
                stored_findings=0,
                patterns_configured=0,
                matched_patterns=0,
                pages=(),
                error="uma_emergency_abort",
            )
    except Exception:
        pass  # UMA check is best-effort; continue with pipeline

    # Step 2: Fetch via 8AF
    from hledac.universal.discovery.rss_atom_adapter import async_fetch_feed_entries

    try:
        batch = await async_fetch_feed_entries(
            feed_url=feed_url,
            max_entries=max_entries,
            timeout_s=timeout_s,
            max_bytes=max_bytes,
        )
    except asyncio.CancelledError:
        raise  # never swallow
    except Exception as exc:
        return FeedPipelineRunResult(
            feed_url=feed_url,
            fetched_entries=0,
            accepted_findings=0,
            stored_findings=0,
            patterns_configured=0,
            matched_patterns=0,
            pages=(),
            error=f"fetch_exception:{type(exc).__name__}:{exc}",
        )

    # Handle fetch-level errors fail-soft
    if batch.error:
        return FeedPipelineRunResult(
            feed_url=feed_url,
            fetched_entries=0,
            accepted_findings=0,
            stored_findings=0,
            patterns_configured=0,
            matched_patterns=0,
            pages=(),
            error=f"fetch_error:{batch.error}",
        )

    entries = batch.entries
    fetched_count = len(entries)

    # Handle empty but valid response
    if fetched_count == 0:
        return FeedPipelineRunResult(
            feed_url=feed_url,
            fetched_entries=0,
            accepted_findings=0,
            stored_findings=0,
            patterns_configured=0,
            matched_patterns=0,
            pages=(),
            error=None,
            entries_seen=0,
            entries_with_empty_assembled_text=0,
            entries_with_text=0,
            entries_scanned=0,
            entries_with_hits=0,
            total_pattern_hits=0,
            findings_built_pre_store=0,
            assembled_text_chars_total=0,
            avg_assembled_text_len=0.0,
            signal_stage="unknown",
            # Sprint 8BE: enrichment
            entries_with_rich_feed_content=0,
            entries_with_article_fallback=0,
            article_fallback_fetch_attempts=0,
            article_fallback_fetch_successes=0,
            enriched_text_chars_total=0,
            avg_enriched_text_len=0.0,
            sample_enriched_texts=(),
            enrichment_phase_used="none",
            temporal_feed_vocabulary_mismatch=False,
        )

    # Step 3: Per-entry processing — pattern-backed
    run_deduper = _RunDeduper()
    pages: list[FeedPipelineEntryResult] = []
    total_accepted = 0
    total_stored = 0
    total_matched = 0
    total_patterns_configured = 0
    # Sprint 8AU: pre-store observability counters
    entries_seen = 0
    entries_with_empty_assembled_text = 0
    entries_with_text = 0
    entries_scanned = 0
    entries_with_hits = 0
    total_pattern_hits = 0
    findings_built_pre_store = 0
    assembled_text_chars_total = 0
    # Sprint 8BE: enrichment counters
    entries_with_rich_feed_content = 0
    entries_with_article_fallback = 0
    article_fallback_fetch_attempts = 0
    article_fallback_fetch_successes = 0
    enriched_text_chars_total = 0
    # Sprint 8BC: bounded sample capture (max 3 entries, max 160 chars per sample)
    _sample_texts: list[str] = []
    _sample_hit_counts: list[int] = []
    _sample_hit_labels: list[str] = []
    _sample_texts_truncated = False
    _entries_with_content_seen = 0
    _MAX_SAMPLE_ENTRIES = 3
    _MAX_SAMPLE_CHARS = 160

    for entry in entries:
        entry_url = getattr(entry, "entry_url", "") or f"urn:feed:entry:{getattr(entry, 'title', '')[:64]}"

        # Per-run dedup: skip if we've already seen this entry_url
        if not run_deduper.is_new(entry_url):
            pages.append(FeedPipelineEntryResult(
                entry_url=entry_url,
                accepted_findings=0,
                stored_findings=0,
                error=None,
            ))
            continue

        entries_seen += 1

        # Pattern scan + mapping — fail-soft per entry
        try:
            findings, patterns_cfg, matched, assembled_len, clean_text, enrichment_phase, article_fallback_used, article_fallback_attempted = await _entry_to_pattern_findings(
                feed_url, entry, query_context
            )
        except asyncio.CancelledError:
            raise  # never swallow
        except Exception:
            pages.append(FeedPipelineEntryResult(
                entry_url=entry_url,
                accepted_findings=0,
                stored_findings=0,
                error="pattern_step_failed",
            ))
            continue

        total_patterns_configured += patterns_cfg
        total_matched += matched

        # Sprint 8AU: update assembled text counters
        # "[no content]" sentinel means no real content (both title and summary were empty)
        is_empty_content = (assembled_len == 0) or (clean_text == "[no content]")
        assembled_text_chars_total += assembled_len
        if is_empty_content:
            entries_with_empty_assembled_text += 1
        else:
            entries_text = clean_text
            if len(entries_text) > _MAX_SAMPLE_CHARS:
                entries_text = entries_text[:_MAX_SAMPLE_CHARS]
                _sample_texts_truncated = True
            _entries_with_content_seen += 1
            if _entries_with_content_seen <= _MAX_SAMPLE_ENTRIES:
                _sample_texts.append(entries_text)
                _sample_hit_counts.append(matched)
                if matched > 0:
                    try:
                        from hledac.universal.patterns.pattern_matcher import match_text
                        hits_for_labels = match_text(entries_text)
                        seen_labels = set()
                        for h in hits_for_labels:
                            if h.label:
                                seen_labels.add(h.label)
                        _sample_hit_labels.extend(seen_labels)
                    except Exception:
                        pass
            entries_with_text += 1
            entries_scanned += 1
            total_pattern_hits += matched
            # Sprint 8BE: track enrichment phase
            if enrichment_phase == "feed_rich_content":
                entries_with_rich_feed_content += 1
            elif enrichment_phase == "article_fallback":
                entries_with_article_fallback += 1
            if article_fallback_attempted:
                article_fallback_fetch_attempts += 1
            if article_fallback_used:
                article_fallback_fetch_successes += 1
            enriched_text_chars_total += assembled_len
            if matched > 0:
                entries_with_hits += 1
                findings_built_pre_store += len(findings)

        if not findings:
            pages.append(FeedPipelineEntryResult(
                entry_url=entry_url,
                accepted_findings=0,
                stored_findings=0,
                error=None,
            ))
            continue

        # Step 4: Storage
        accepted_findings = 0
        stored_findings = 0

        if store is not None:
            try:
                from hledac.universal.knowledge.duckdb_store import CanonicalFinding

                canonicals: list[CanonicalFinding] = [
                    CanonicalFinding(**f) for f in findings
                ]

                results = await store.async_ingest_findings_batch(canonicals)

                accepted_findings = sum(
                    1 for r in results
                    if getattr(r, "activated", False) or getattr(r, "success", False)
                )
                stored_findings = accepted_findings

            except asyncio.CancelledError:
                raise
            except Exception:
                # Storage fail-soft: count as accepted but not stored
                accepted_findings = len(findings)
                stored_findings = 0
        else:
            # No store: count-only mode
            accepted_findings = len(findings)

        total_accepted += accepted_findings
        total_stored += stored_findings

        pages.append(FeedPipelineEntryResult(
            entry_url=entry_url,
            accepted_findings=accepted_findings,
            stored_findings=stored_findings,
            error=None,
        ))

    # Sprint 8AU: compute signal stage diagnosis
    signal_stage = diagnose_feed_signal_stage(
        entries_seen=entries_seen,
        entries_with_empty_assembled_text=entries_with_empty_assembled_text,
        entries_scanned=entries_scanned,
        entries_with_hits=entries_with_hits,
        findings_built_pre_store=findings_built_pre_store,
        patterns_configured=total_patterns_configured,
    )
    avg_text_len = (
        assembled_text_chars_total / entries_with_text
        if entries_with_text > 0
        else 0.0
    )

    return FeedPipelineRunResult(
        feed_url=feed_url,
        fetched_entries=fetched_count,
        accepted_findings=total_accepted,
        stored_findings=total_stored,
        patterns_configured=total_patterns_configured,
        matched_patterns=total_matched,
        pages=tuple(pages),
        error=None,
        entries_seen=entries_seen,
        entries_with_empty_assembled_text=entries_with_empty_assembled_text,
        entries_with_text=entries_with_text,
        entries_scanned=entries_scanned,
        entries_with_hits=entries_with_hits,
        total_pattern_hits=total_pattern_hits,
        findings_built_pre_store=findings_built_pre_store,
        assembled_text_chars_total=assembled_text_chars_total,
        avg_assembled_text_len=avg_text_len,
        signal_stage=signal_stage,
        # Sprint 8BC: bounded sample capture
        sample_scanned_texts=tuple(_sample_texts),
        sample_hit_counts=tuple(_sample_hit_counts),
        sample_hit_labels_union=tuple(dict.fromkeys(_sample_hit_labels)),
        sample_texts_truncated=_sample_texts_truncated,
        feed_content_mismatch=bool(_entries_with_content_seen > 0 and all(c == 0 for c in _sample_hit_counts)),
        # Sprint 8BE: enrichment
        entries_with_rich_feed_content=entries_with_rich_feed_content,
        entries_with_article_fallback=entries_with_article_fallback,
        article_fallback_fetch_attempts=article_fallback_fetch_attempts,
        article_fallback_fetch_successes=article_fallback_fetch_successes,
        enriched_text_chars_total=enriched_text_chars_total,
        avg_enriched_text_len=(
            enriched_text_chars_total / entries_with_text
            if entries_with_text > 0
            else 0.0
        ),
        sample_enriched_texts=tuple(_sample_texts),
        enrichment_phase_used="article_fallback" if entries_with_article_fallback > 0 else ("feed_rich_content" if entries_with_rich_feed_content > 0 else "none"),
        temporal_feed_vocabulary_mismatch=False,
    )


# ---------------------------------------------------------------------------
# Batch source coercion (Sprint 8AL — unchanged public signature)
# ---------------------------------------------------------------------------


def _coerce_source_to_tuple(
    source: object,
) -> tuple[str, str, str, int]:
    """
    Coerce FeedSeed / FeedDiscoveryHit / MergedFeedSource / plain str
    into a unified (feed_url, label, origin, priority) tuple.

    Label fallback = "" (never None -> "None" string).
    FeedSeed uses 'source' field for origin.
    FeedDiscoveryHit has no origin/priority — use "" and 0.
    MergedFeedSource has both origin and priority.
    """
    if isinstance(source, str):
        return (source, "", "unknown", 0)

    if hasattr(source, "source") and not hasattr(source, "origin"):
        feed_url = getattr(source, "feed_url", "") or ""
        label = getattr(source, "label", None)
        label = "" if label is None else label
        origin = getattr(source, "source", None)
        origin = "" if origin is None else origin
        priority = int(getattr(source, "priority", 0) or 0)
        return (feed_url, label, origin, priority)

    feed_url = getattr(source, "feed_url", "") or ""
    label = getattr(source, "label", None)
    label = "" if label is None else label
    origin = getattr(source, "origin", None)
    origin = "" if origin is None else origin
    priority = int(getattr(source, "priority", 0) or 0)
    return (feed_url, label, origin, priority)


# ---------------------------------------------------------------------------
# Batch runner (Sprint 8AL — unchanged public signature)
# ---------------------------------------------------------------------------


async def async_run_feed_source_batch(
    sources: tuple[object, ...],
    store: Any | None = None,
    max_entries_per_feed: int = 20,
    feed_concurrency: int = 3,
    query_context: str | None = None,
    per_feed_timeout_s: float = 45.0,
    batch_timeout_s: float = 300.0,
) -> FeedSourceBatchRunResult:
    """
    Run a one-shot batch over heterogeneous feed sources.

    Unchanged signature from 8AL — no breaking changes to public API.
    """
    if not sources:
        return FeedSourceBatchRunResult(
            total_sources=0,
            completed_sources=0,
            fetched_entries=0,
            accepted_findings=0,
            stored_findings=0,
            sources=(),
            error=None,
        )

    normalized: list[tuple[str, str, str, int]] = [
        _coerce_source_to_tuple(s) for s in sources
    ]
    normalized.sort(key=lambda x: -x[3])

    # UMA check at batch start
    emergency_abort = False
    critical_clamp = False
    try:
        from hledac.universal.core.resource_governor import sample_uma_status
        uma = sample_uma_status()
        if uma.state == "emergency":
            emergency_abort = True
        elif uma.state == "critical":
            critical_clamp = True
    except Exception:
        pass

    if emergency_abort:
        return FeedSourceBatchRunResult(
            total_sources=len(normalized),
            completed_sources=0,
            fetched_entries=0,
            accepted_findings=0,
            stored_findings=0,
            sources=(),
            error="uma_emergency_abort",
        )

    effective_concurrency = 1 if critical_clamp else feed_concurrency

    async def _run_single(
        feed_url: str,
        label: str,
        origin: str,
        priority: int,
    ) -> FeedSourceRunResult:
        start = time.monotonic()
        elapsed_ms = 0.0

        resolved_query = query_context
        if not resolved_query:
            resolved_query = label if label else feed_url

        try:
            async with asyncio.timeout(per_feed_timeout_s):
                result: FeedPipelineRunResult = await async_run_live_feed_pipeline(
                    feed_url=feed_url,
                    store=store,
                    query_context=resolved_query,
                    max_entries=max_entries_per_feed,
                    timeout_s=per_feed_timeout_s,
                )
        except asyncio.CancelledError:
            raise  # never swallow
        except asyncio.TimeoutError:
            elapsed_ms = (time.monotonic() - start) * 1000.0
            return FeedSourceRunResult(
                feed_url=feed_url,
                label=label,
                origin=origin,
                priority=priority,
                fetched_entries=0,
                accepted_findings=0,
                stored_findings=0,
                elapsed_ms=elapsed_ms,
                error="per_feed_timeout",
            )
        except BaseException as exc:
            elapsed_ms = (time.monotonic() - start) * 1000.0
            return FeedSourceRunResult(
                feed_url=feed_url,
                label=label,
                origin=origin,
                priority=priority,
                fetched_entries=0,
                accepted_findings=0,
                stored_findings=0,
                elapsed_ms=elapsed_ms,
                error=f"unexpected:{type(exc).__name__}:{exc}",
            )

        elapsed_ms = (time.monotonic() - start) * 1000.0
        return FeedSourceRunResult(
            feed_url=feed_url,
            label=label,
            origin=origin,
            priority=priority,
            fetched_entries=result.fetched_entries,
            accepted_findings=result.accepted_findings,
            stored_findings=result.stored_findings,
            elapsed_ms=elapsed_ms,
            error=result.error,
            signal_stage=result.signal_stage,
        )

    results: list[FeedSourceRunResult] = []

    try:
        async with asyncio.timeout(batch_timeout_s):
            for i in range(0, len(normalized), effective_concurrency):
                batch_slice = normalized[i : i + effective_concurrency]
                tasks = [
                    _run_single(url, lbl, org, pri)
                    for url, lbl, org, pri in batch_slice
                ]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                for res in batch_results:
                    if isinstance(res, asyncio.CancelledError):
                        raise res
                    elif isinstance(res, BaseException):
                        results.append(FeedSourceRunResult(
                            feed_url="<unknown>",
                            label="",
                            origin="unknown",
                            priority=0,
                            fetched_entries=0,
                            accepted_findings=0,
                            stored_findings=0,
                            error=f"gather_exception:{type(res).__name__}:{res}",
                        ))
                    else:
                        results.append(res)
    except asyncio.CancelledError:
        raise  # never swallow
    except asyncio.TimeoutError:
        pass

    total_fetched = sum(r.fetched_entries for r in results)
    total_accepted = sum(r.accepted_findings for r in results)
    total_stored = sum(r.stored_findings for r in results)
    completed = sum(1 for r in results if r.error is None)
    batch_error = "batch_timeout" if (
        len(results) < len(normalized) or
        any(r.error == "per_feed_timeout" for r in results)
    ) else None

    # Sprint 8BE Phase 3: dominant signal stage (mode) across all sources
    stage_counter: Counter[str] = Counter()
    for r in results:
        if r.signal_stage and r.signal_stage != "unknown":
            stage_counter[r.signal_stage] += 1
    dominant_stage = stage_counter.most_common(1)[0][0] if stage_counter else "unknown"

    _logger = logging.getLogger(__name__)
    _logger.info(f"[BATCH] dominant_signal_stage={dominant_stage}")

    return FeedSourceBatchRunResult(
        total_sources=len(normalized),
        completed_sources=completed,
        fetched_entries=total_fetched,
        accepted_findings=total_accepted,
        stored_findings=total_stored,
        sources=tuple(results),
        error=batch_error,
        dominant_signal_stage=dominant_stage,
    )


async def async_run_default_feed_batch(
    store: Any | None = None,
    max_entries_per_feed: int = 20,
    feed_concurrency: int = 3,
    query_context: str | None = None,
    per_feed_timeout_s: float = 45.0,
    batch_timeout_s: float = 300.0,
) -> FeedSourceBatchRunResult:
    """
    Run a one-shot batch over the default curated feed seeds (8AJ).

    Unchanged signature from 8AL.
    """
    from hledac.universal.discovery.rss_atom_adapter import get_default_feed_seeds

    seeds = get_default_feed_seeds()
    return await async_run_feed_source_batch(
        sources=seeds,
        store=store,
        max_entries_per_feed=max_entries_per_feed,
        feed_concurrency=feed_concurrency,
        query_context=query_context,
        per_feed_timeout_s=per_feed_timeout_s,
        batch_timeout_s=batch_timeout_s,
    )
