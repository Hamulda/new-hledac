"""
Sprint 8AE: First live public OSINT pipeline wiring.

query -> discovery (8AC duckduckgo) -> fetch (8AD public_fetcher) ->
lightweight HTML extraction -> PatternMatcher (8X) -> quality gate (8W) ->
CanonicalFinding -> storage (8S/8R DuckDBShadowStore).

No LLM calls. No AO. No new storage schema.
All heavy I/O (HTML parsing, pattern scanning) offloaded via asyncio.to_thread().
"""

from __future__ import annotations

import asyncio
import hashlib
import html.parser
import re
import sys
import time
from typing import TYPE_CHECKING, Any

import msgspec

if TYPE_CHECKING:
    from hledac.universal.knowledge.duckdb_store import DuckDBShadowStore

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

MAX_EXTRACTED_TEXT_CHARS: int = 200_000
"""Hard cap on extracted text size per page."""

MAX_METADATA_PREPEND_CHARS: int = 500
"""Max chars of title+snippet prepended to extracted text for pattern scan context."""

_SOURCE_TYPE: str = "live_public_pipeline"
"""source_type value for all findings produced by this pipeline."""

_DEFAULT_CONFIDENCE: float = 0.8
"""Confidence for pipeline findings — executed but unverified."""

_FINDING_ID_CONTEXT_RADIUS: int = 100
"""Character radius around pattern hit for payload_text context window."""

# Sprint F150I: tier thresholds (additive, no new framework)
_QUALITY_TIER_VERY_GOOD = "very_good"
_QUALITY_TIER_GOOD = "good"
_QUALITY_TIER_OK = "ok"
_QUALITY_TIER_WEAK = "weak_low_signal"
_QUALITY_TIER_SKIP = "SKIP_WEAK"

# Discovery signal threshold — hit with score >= this is considered informative
_DISCOVERY_SIGNAL_SCORE_THRESHOLD: float = 0.3

# Adaptive fetch budget tiers: multiplier on base fetch_timeout_s
_FETCH_BUDGET_STRONG: float = 1.25   # very_good or discovery_score >= 0.7
_FETCH_BUDGET_NORMAL: float = 1.0    # ok, good
_FETCH_BUDGET_WEAK: float = 0.65     # weak_low_signal, low discovery score
_FETCH_BUDGET_SKIP: float = 0.0       # SKIP_WEAK — dead until Fix A in F150J

# Sprint F150J: pre-fetch skip threshold — below this score with no strong signal → SKIP tier
_DISCOVERY_SKIP_THRESHOLD: float = 0.15
"""If discovery_score is below this AND no strong signal, skip fetch entirely."""

# -----------------------------------------------------------------------------
# DTOs
# -----------------------------------------------------------------------------


class PipelinePageResult(msgspec.Struct, frozen=True, gc=False):
    """Result of processing a single discovered page."""

    url: str
    fetched: bool
    matched_patterns: int
    accepted_findings: int
    stored_findings: int
    error: str | None = None
    quality_reason: str | None = None  # why page was good/weak/skipped
    discovery_score: float | None = None  # signal strength from discovery hit
    discovery_reason: str | None = None  # reason from discovery hit
    discovery_signal: bool = False  # True if hit had score >= 0.3 or reason


class PipelineRunResult(msgspec.Struct, frozen=True, gc=False):
    """Top-level result of a full pipeline run."""

    query: str
    discovered: int
    fetched: int
    matched_patterns: int
    accepted_findings: int
    stored_findings: int
    patterns_configured: int
    pages: tuple[PipelinePageResult, ...]
    error: str | None = None
    # Sprint F150I: branch economics observability (additive)
    strong_pages: int = 0  # very_good tier, high yield
    weak_pages_skipped: int = 0  # SKIP_WEAK early exits (Fix B: was error-based, now quality_reason-based)
    low_value_fetches: int = 0  # fetched but matched nothing + poor quality
    # Sprint F150J: derived value counters
    discovery_strong_content_weak: int = 0  # discovery signal but zero pattern yield
    discovery_and_content_strong: int = 0  # both discovery signal and pattern yield
    # Sprint F150J: condensed public-branch verdict (additive dict)
    public_branch_verdict: dict = {}


# -----------------------------------------------------------------------------
# UMA helpers
# -----------------------------------------------------------------------------


def _get_uma_state() -> tuple[str, bool]:
    """
    Read UMA status via 8AB surface.
    Returns (state_str, io_only_hint).
    Raises: propagates any exception from resource_governor.

    Sprint 8AK: Uses SSOT labels from resource_governor — no localUMA interpretation.
    """
    # Sprint 8AB surface — lazy import to avoid module-level side effects
    from hledac.universal.core.resource_governor import (
        evaluate_uma_state,
        sample_uma_status,
        UMA_STATE_EMERGENCY,
    )

    status = sample_uma_status()
    state = evaluate_uma_state(status.system_used_gib)
    io_only = status.io_only
    return state, io_only


# -----------------------------------------------------------------------------
# HTML extraction helpers
# -----------------------------------------------------------------------------


class _HTMLTextExtractor(html.parser.HTMLParser):
    """
    Lightweight HTMLParser that collects only text from body-level tags
    and collapses whitespace. Fail-soft: never raises on malformed HTML.
    """

    __slots__ = ("_in_body", "_chunks", "_last_end")

    def __init__(self) -> None:
        super().__init__()
        self._in_body = False
        self._chunks: list[str] = []
        self._last_end = 0

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]  # noqa: ARG002
    ) -> None:
        if tag in ("body", "div", "p", "tr", "li", "article", "section", "main"):
            if not self._chunks or self._chunks[-1] != " ":
                self._chunks.append(" ")
        elif tag in ("br", "hr"):
            if self._chunks and self._chunks[-1] != " ":
                self._chunks.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in (
            "body", "div", "p", "tr", "li", "article", "section", "main", "h1",
            "h2", "h3", "h4", "h5", "h6", "ul", "ol",
        ):
            if self._chunks and self._chunks[-1] != " ":
                self._chunks.append(" ")

    def handle_data(self, data: str) -> None:
        stripped = data.strip()
        if stripped:
            self._chunks.append(stripped)
            if self._chunks[-1] != " ":
                self._chunks.append(" ")

    def get_text(self) -> str:
        result = "".join(self._chunks)
        # Collapse any runs of whitespace to single space
        result = re.sub(r"\s+", " ", result).strip()
        return result


def _html_to_text(html_content: str) -> str:
    """
    Convert HTML to plain text using stdlib HTMLParser.
    Runs in calling thread (caller is responsible for asyncio.to_thread).
    """
    try:
        parser = _HTMLTextExtractor()
        parser.feed(html_content)
        text = parser.get_text()
    except Exception:
        # Defensive: fall back to stripping tags via regex
        text = re.sub(r"<[^>]+>", " ", html_content)
        text = re.sub(r"\s+", " ", text).strip()
    return text


# -----------------------------------------------------------------------------
# Finding ID helper
# -----------------------------------------------------------------------------

def _make_finding_id(
    query: str, url: str, label: str, pattern: str, value: str
) -> str:
    """
    Deterministic finding ID via SHA-256 hash of pipeline inputs.
    hash() is forbidden (non-deterministic across processes).
    """
    key = f"{query}\x00{url}\x00{label}\x00{pattern}\x00{value}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


# -----------------------------------------------------------------------------
# Context window helper
# -----------------------------------------------------------------------------
# Sentinel: use a private module-level constant so the call site is self-explanatory
_NO_HIT_START = object()


def _pattern_context(
    text: str,
    start: int,
    end: int,
    radius: int = _FINDING_ID_CONTEXT_RADIUS,
) -> str:
    """
    Extract a context window around a pattern hit.
    Runs in calling thread (caller is responsible for asyncio.to_thread).
    """
    if start is _NO_HIT_START or end is _NO_HIT_START:
        return text[:MAX_EXTRACTED_TEXT_CHARS]
    lo = max(0, start - radius)
    hi = min(len(text), end + radius)
    return text[lo:hi]


# -----------------------------------------------------------------------------
# Text enrichment with discovery metadata (Sprint F150I)
# Prepend title/snippet to extracted text so pattern scanner gets better signal.
# Hard-capped, M1-safe, no new dependency.
# -----------------------------------------------------------------------------


def _enrich_text_with_metadata(
    title: str,
    snippet: str,
    extracted_text: str,
) -> str:
    """
    Build a bounded scan text from: [title] [snippet] [extracted_content].

    Rationale: title + snippet contain query-aware signal that raw HTML→text
    loses (e.g. search engine bolded terms). Prepending them gives pattern
    matcher better context without any LLM or external call.

    The result is hard-capped at MAX_EXTRACTED_TEXT_CHARS.
    """
    # Build metadata prefix bounded to MAX_METADATA_PREPEND_CHARS
    meta_parts: list[str] = []
    remaining_meta = MAX_METADATA_PREPEND_CHARS

    if title:
        title_trunc = title[:remaining_meta]
        meta_parts.append(title_trunc)
        remaining_meta -= len(title_trunc)

    if snippet and remaining_meta > 20:
        snippet_trunc = snippet[:remaining_meta]
        meta_parts.append(snippet_trunc)

    meta_prefix = "\n".join(meta_parts) + "\n---\n"

    # Hard cap: meta_prefix + extracted_text capped at MAX_EXTRACTED_TEXT_CHARS
    max_content = MAX_EXTRACTED_TEXT_CHARS - len(meta_prefix)
    if max_content < 0:
        # meta_prefix alone exceeds cap — truncate it
        meta_prefix = meta_prefix[:MAX_EXTRACTED_TEXT_CHARS]
        max_content = 0

    content = extracted_text[:max_content] if max_content > 0 else ""

    return meta_prefix + content


# -----------------------------------------------------------------------------
# Page quality scoring (Sprint F150I)
# Query-aware heuristic for fetch budget prioritization.
# Bounded, no ML, no external calls.
# -----------------------------------------------------------------------------


def _score_page_quality(
    *,
    hit_url: str,
    hit_title: str,
    hit_snippet: str,
    hit_rank: int,
    query: str,
    extracted_text: str,
    discovery_score: float | None = None,
    discovery_reason: str | None = None,
) -> str:
    """
    Return a short quality tier string for a discovered page.

    Signals (compositional, no ML):
    - query-term density in title/snippet
    - URL structural depth
    - text richness (avg word len + word count)
    - discovery hit score / reason (if present)
    - rank priority (top-5 benefit of doubt)
    - pre-filter: skip extremely thin pages

    Returns one of:
      SKIP_WEAK: below minimum — skip immediately
      weak_low_signal: poor signals even after fetch
      ok: acceptable but not exceptional
      good: strong multi-dimensional signals
      very_good: exceptional signals, full investment warranted
    """
    # --- Discovery signal blend (additive, fail-soft) ------------
    has_discovery_signal = (
        (discovery_score is not None and discovery_score >= _DISCOVERY_SIGNAL_SCORE_THRESHOLD)
        or (discovery_reason is not None and discovery_reason.strip() != "")
    )
    strong_discovery = (
        discovery_score is not None and discovery_score >= 0.7
    )

    query_lower = query.lower()
    query_terms = frozenset(query_lower.split())

    # --- Pre-filter: skip pages with almost no content ------------
    if len(extracted_text) < 200:
        return "SKIP_WEAK:very_low_text"

    # --- Title query-term density --------------------------------
    title_words = frozenset(hit_title.lower().split())
    title_query_hits = len(query_terms & title_words)
    title_has_query = title_query_hits > 0

    # --- Snippet query-term density -----------------------------
    snippet_words = frozenset(hit_snippet.lower().split())
    snippet_query_hits = len(query_terms & snippet_words)
    snippet_has_query = snippet_query_hits > 0

    # --- URL structural signal -----------------------------------
    url_has_path = "/" in hit_url and len(hit_url.split("/")) > 3

    # --- Text richness -----------------------------------------
    text_len = len(extracted_text)
    word_count = len(extracted_text.split())
    avg_word_len = text_len / max(word_count, 1)
    text_is_meaningful = avg_word_len >= 3.5 and word_count >= 50

    # --- Composite scoring --------------------------------------
    signals_good = sum([
        title_has_query,
        snippet_has_query,
        url_has_path,
        text_is_meaningful,
    ])
    if strong_discovery:
        signals_good += 1  # discovery bonus

    rank_bonus = hit_rank < 5

    # --- Tier determination -------------------------------------
    if signals_good >= 4 or (signals_good >= 3 and (rank_bonus or strong_discovery)):
        return "very_good"
    elif signals_good >= 3:
        return "good"
    elif signals_good >= 2:
        return "ok"
    elif signals_good >= 1:
        return "ok"
    elif has_discovery_signal and text_is_meaningful and text_len > 1000:
        return "ok:no_query_signal"
    else:
        return "weak_low_signal"


# -----------------------------------------------------------------------------
# PatternMatcher helpers
# -----------------------------------------------------------------------------


def _get_patterns_configured_count() -> int:
    """Return current pattern count from singleton registry (0 if dirty/empty)."""
    state = sys.modules["hledac.universal.patterns.pattern_matcher"]._matcher_state
    return len(state._registry_snapshot) if state._registry_snapshot else 0


# -----------------------------------------------------------------------------
# Per-page finding extraction
# -----------------------------------------------------------------------------


async def _extract_live_public_findings_from_page(
    *,
    query: str,
    url: str,
    hit_label: str,
    hit_pattern: str,
    hit_value: str,
    hit_start: int,
    hit_end: int,
    page_text: str,
) -> tuple:  # CanonicalFinding — imported lazily to satisfy runtime
    """
    Construct CanonicalFinding for a single PatternHit.
    All heavy work (context extraction) offloaded to thread executor.
    """
    # Lazy import to avoid TYPE_CHECKING-only circular issues at runtime
    from hledac.universal.knowledge.duckdb_store import CanonicalFinding

    loop = asyncio.get_running_loop()

    # Extract context in thread to avoid blocking event loop
    context: str = await loop.run_in_executor(
        None, _pattern_context, page_text, hit_start, hit_end
    )

    # Truncate to hard cap (double-check since context is already bounded)
    if len(context) > MAX_EXTRACTED_TEXT_CHARS:
        context = context[:MAX_EXTRACTED_TEXT_CHARS]

    finding_id = _make_finding_id(query, url, hit_label, hit_pattern, hit_value)

    # provenance: (source, url, hit_label, hit_pattern)
    provenance: tuple[str, ...] = ("duckduckgo", url, hit_label or "", hit_pattern)

    finding = CanonicalFinding(
        finding_id=finding_id,
        query=query,
        source_type=_SOURCE_TYPE,
        confidence=_DEFAULT_CONFIDENCE,
        ts=time.time(),
        provenance=provenance,
        payload_text=context,
    )
    return (finding,)


# -----------------------------------------------------------------------------
# Single-page fetch + extract + match + store
# -----------------------------------------------------------------------------


async def _fetch_and_process_page(
    *,
    semaphore: asyncio.Semaphore,
    query: str,
    hit_url: str,
    hit_title: str,
    hit_snippet: str,
    hit_rank: int,
    fetch_timeout_s: float,
    fetch_max_bytes: int,
    store: Any | None,
    discovery_score: float | None = None,
    discovery_reason: str | None = None,
) -> PipelinePageResult:
    """
    Fetch one URL, extract text, scan patterns, optionally store findings.
    Discovery signal (score/reason) is propagated for observability and
    used for adaptive budget selection — fail-soft when absent.
    """
    # --- Adaptive budget tier ----------------------------------------
    has_signal = (
        (discovery_score is not None and discovery_score >= _DISCOVERY_SIGNAL_SCORE_THRESHOLD)
        or (discovery_reason is not None and discovery_reason.strip() != "")
    )
    strong_signal = discovery_score is not None and discovery_score >= 0.7

    # Sprint F150J Fix A: wire SKIP tier — was dead code before
    low_discovery = (
        discovery_score is not None
        and discovery_score < _DISCOVERY_SKIP_THRESHOLD
        and not strong_signal
    )
    if low_discovery:
        budget_mult = _FETCH_BUDGET_SKIP  # 0.0 → true skip
    elif discovery_score is not None and discovery_score >= 0.85:
        budget_mult = _FETCH_BUDGET_STRONG
    elif strong_signal or has_signal:
        budget_mult = _FETCH_BUDGET_NORMAL
    else:
        budget_mult = _FETCH_BUDGET_WEAK

    effective_timeout = fetch_timeout_s * budget_mult
    # Don't call fetch at all for SKIP tier (budget_mult == 0)
    skip_fetch = budget_mult <= 0

    async with semaphore:
        # ---- Fetch -----------------------------------------------------------
        if skip_fetch:
            return PipelinePageResult(
                url=hit_url,
                fetched=False,
                matched_patterns=0,
                accepted_findings=0,
                stored_findings=0,
                error="skipped:weak_discovery",
                quality_reason="SKIP_WEAK:weak_discovery",
                discovery_score=discovery_score,
                discovery_reason=discovery_reason,
                discovery_signal=has_signal,
            )

        try:
            result = await asyncio.wait_for(
                _ASYNC_FETCH_PUBLIC_TEXT(hit_url, effective_timeout, fetch_max_bytes),
                timeout=effective_timeout + 5.0,
            )
        except asyncio.TimeoutError:
            return PipelinePageResult(
                url=hit_url, fetched=False, matched_patterns=0,
                accepted_findings=0, stored_findings=0,
                error=f"fetch_timeout_after_{effective_timeout:.1f}s",
                discovery_score=discovery_score,
                discovery_reason=discovery_reason,
                discovery_signal=has_signal,
            )
        except asyncio.CancelledError:
            raise  # [I6] propagate, never swallow
        except Exception as exc:
            return PipelinePageResult(
                url=hit_url, fetched=False, matched_patterns=0,
                accepted_findings=0, stored_findings=0,
                error=f"fetch_exception:{type(exc).__name__}:{exc}",
                discovery_score=discovery_score,
                discovery_reason=discovery_reason,
                discovery_signal=has_signal,
            )

        # Unpack fetch result (FetchResult frozen struct)
        fetched_text: str | None
        if hasattr(result, "text"):
            fetched_text = result.text
        else:
            fetched_text = None

        if not fetched_text:
            return PipelinePageResult(
                url=hit_url, fetched=True, matched_patterns=0,
                accepted_findings=0, stored_findings=0,
                error="fetch_text_none_or_empty",
                discovery_score=discovery_score,
                discovery_reason=discovery_reason,
                discovery_signal=has_signal,
            )

        # ---- Extract ---------------------------------------------------------
        loop = asyncio.get_running_loop()
        try:
            extracted_text: str = await loop.run_in_executor(
                None, _html_to_text, fetched_text
            )
        except Exception as exc:
            return PipelinePageResult(
                url=hit_url, fetched=True, matched_patterns=0,
                accepted_findings=0, stored_findings=0,
                error=f"html_extract_failed:{exc}",
                discovery_score=discovery_score,
                discovery_reason=discovery_reason,
                discovery_signal=has_signal,
            )

        # Hard cap
        if len(extracted_text) > MAX_EXTRACTED_TEXT_CHARS:
            extracted_text = extracted_text[:MAX_EXTRACTED_TEXT_CHARS]

        # Build quality signal from discovery metadata + text metrics
        # Sprint F150I: query-aware page selection, bounded signal scoring
        quality_reason = _score_page_quality(
            hit_url=hit_url,
            hit_title=hit_title or "",
            hit_snippet=hit_snippet or "",
            hit_rank=hit_rank,
            query=query,
            extracted_text=extracted_text,
            discovery_score=discovery_score,
            discovery_reason=discovery_reason,
        )

        # Skip very-low-quality pages early — preserve fetch budget
        if quality_reason.startswith("SKIP_WEAK"):
            return PipelinePageResult(
                url=hit_url, fetched=True, matched_patterns=0,
                accepted_findings=0, stored_findings=0,
                error=None, quality_reason=quality_reason,
                discovery_score=discovery_score,
                discovery_reason=discovery_reason,
                discovery_signal=has_signal,
            )

        # Sprint F150I: enrich extracted text with discovery metadata
        # This gives pattern scanner better signal (title/snippet hints present)
        scan_text = _enrich_text_with_metadata(
            hit_title or "", hit_snippet or "", extracted_text
        )

        # Free raw HTML reference early
        del fetched_text

        # ---- Pattern scan ----------------------------------------------------
        # 8X surface — run in thread executor; use enriched text
        try:
            loop = asyncio.get_running_loop()
            hits: list = await loop.run_in_executor(
                None, _SYNC_MATCH_TEXT, scan_text
            )
        except Exception:
            hits = []

        matched_count = len(hits)
        if matched_count == 0:
            return PipelinePageResult(
                url=hit_url, fetched=True, matched_patterns=0,
                accepted_findings=0, stored_findings=0,
                discovery_score=discovery_score,
                discovery_reason=discovery_reason,
                discovery_signal=has_signal,
            )

        # ---- Per-page dedup: (value, label, pattern) exact dedup -----------
        seen: set[tuple[str, str, str]] = set()
        unique_findings: list = []

        for hit in hits:
            key = (hit.value, hit.label if hit.label else "", hit.pattern)
            if key in seen:
                continue
            seen.add(key)

            findings_tuple = await _extract_live_public_findings_from_page(
                query=query,
                url=hit_url,
                hit_label=hit.label if hit.label else "",
                hit_pattern=hit.pattern,
                hit_value=hit.value,
                hit_start=hit.start,
                hit_end=hit.end,
                page_text=extracted_text,
            )
            unique_findings.append(findings_tuple[0])

        accepted_count = len(unique_findings)
        stored_count = 0

        # ---- Storage ---------------------------------------------------------
        if store is not None and unique_findings:
            try:
                # DuckDBShadowStore quality-gated ingest surface (8W + 8S)
                store_results = await store.async_ingest_findings_batch(unique_findings)
                # Count accepted (non-rejected) findings
                for sr in store_results:
                    if hasattr(sr, "accepted"):
                        if sr.accepted:
                            stored_count += 1
                    elif hasattr(sr, "lmdb_success"):
                        # ActivationResult — accepted if stored
                        if sr.lmdb_success:
                            stored_count += 1
                    # else: Fallback: unknown result type — do NOT overcount
            except asyncio.CancelledError:
                raise  # [I6]
            except Exception:
                # Fail-soft: storage error does not fail the page
                pass

        return PipelinePageResult(
            url=hit_url,
            fetched=True,
            matched_patterns=matched_count,
            accepted_findings=accepted_count,
            stored_findings=stored_count,
            quality_reason=quality_reason,
            discovery_score=discovery_score,
            discovery_reason=discovery_reason,
            discovery_signal=has_signal,
        )


# -----------------------------------------------------------------------------
# Placeholder fetch/match imports (patched in tests; real code uses 8AD/8X)
# -----------------------------------------------------------------------------

_ASYNC_FETCH_PUBLIC_TEXT: Any = None  # patched by tests
_SYNC_MATCH_TEXT: Any = None  # patched by tests


def _patch_fetcher_and_matcher(
    fetch_fn: Any, match_fn: Any
) -> None:
    global _ASYNC_FETCH_PUBLIC_TEXT, _SYNC_MATCH_TEXT
    _ASYNC_FETCH_PUBLIC_TEXT = fetch_fn
    _SYNC_MATCH_TEXT = match_fn


def _ensure_patched() -> None:
    """Ensure runtime fetch/matcher are patched from 8AD/8X modules."""
    global _ASYNC_FETCH_PUBLIC_TEXT, _SYNC_MATCH_TEXT
    if _ASYNC_FETCH_PUBLIC_TEXT is None:
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text
        _ASYNC_FETCH_PUBLIC_TEXT = async_fetch_public_text
    if _SYNC_MATCH_TEXT is None:
        from hledac.universal.patterns.pattern_matcher import match_text
        _SYNC_MATCH_TEXT = match_text


# -----------------------------------------------------------------------------
# Main pipeline
# -----------------------------------------------------------------------------


async def async_run_live_public_pipeline(
    query: str,
    store: "DuckDBShadowStore | None" = None,
    max_results: int = 10,
    fetch_timeout_s: float = 35.0,
    fetch_max_bytes: int = 2_000_000,
    fetch_concurrency: int = 5,
) -> PipelineRunResult:
    """
    Sprint 8AE: Live public OSINT pipeline.

    Orchestration-only: wires existing 8AC/8AD/8X/8W/8S components.
    No LLM. No AO. No new storage schema.

    Parameters
    ----------
    query:
        Research query string (passed to CanonicalFinding.query).
    store:
        Optional DuckDBShadowStore instance. If None, storage is a no-op
        and only counting happens.
    max_results:
        Maximum discovery hits to process (default 10).
    fetch_timeout_s:
        Per-fetch operation timeout in seconds (applied per-page via 8AD API).
    fetch_max_bytes:
        Maximum bytes to fetch per page.
    fetch_concurrency:
        Maximum concurrent fetches in the batch.

    Returns
    -------
    PipelineRunResult with typed counts and per-page error breakdown.
    """
    # Ensure hot-path imports are resolved
    _ensure_patched()

    # ---- UMA check -----------------------------------------------------------
    # Sprint 8AK: SSOT labels from resource_governor — no local string literals
    from hledac.universal.core.resource_governor import (
        UMA_STATE_EMERGENCY,
        UMA_STATE_CRITICAL,
        UMA_STATE_OK,
    )

    uma_state = UMA_STATE_OK
    try:
        uma_state, _ = _get_uma_state()
    except Exception:
        pass  # Defensive: proceed with ok state

    if uma_state == UMA_STATE_EMERGENCY:
        return PipelineRunResult(
            query=query,
            discovered=0,
            fetched=0,
            matched_patterns=0,
            accepted_findings=0,
            stored_findings=0,
            patterns_configured=_get_patterns_configured_count(),
            pages=(),
            error="uma_emergency_abort",
        )

    effective_concurrency = fetch_concurrency
    if uma_state == UMA_STATE_CRITICAL or uma_state == UMA_STATE_EMERGENCY:
        effective_concurrency = 1

    semaphore = asyncio.Semaphore(effective_concurrency)

    # ---- Discovery (8AC) -----------------------------------------------------
    discovery_error: str | None = None
    hits: tuple = ()

    try:
        # 8AC surface — duckduckgo_search passive discovery
        discovery_result = await _ASYNC_DISCOVERY_SEARCH(query, max_results)
        if hasattr(discovery_result, "hits"):
            hits = discovery_result.hits
        elif isinstance(discovery_result, dict):
            hits = discovery_result.get("hits", ())

        err_val = discovery_result.get("error") if isinstance(discovery_result, dict) else getattr(discovery_result, "error", None)
        if err_val:
            discovery_error = str(err_val)
    except asyncio.CancelledError:
        raise  # [I6]
    except Exception as exc:
        discovery_error = f"discovery_exception:{type(exc).__name__}:{exc}"
        hits = ()

    if not hits:
        return PipelineRunResult(
            query=query,
            discovered=0,
            fetched=0,
            matched_patterns=0,
            accepted_findings=0,
            stored_findings=0,
            patterns_configured=_get_patterns_configured_count(),
            pages=(),
            error=discovery_error or "discovery_empty",
        )

    # ---- Fetch batch ---------------------------------------------------------
    # Per-call semaphore, no global batch timeout
    tasks: list[asyncio.Task] = []
    for hit in hits:
        # Sprint F150I: extract discovery score/reason if present (additive, fail-soft)
        hit_score: float | None = getattr(hit, "score", None)
        if hit_score is None and hasattr(hit, "__getitem__"):
            try:
                hit_score = float(hit[4]) if len(hit) > 4 else None
            except (ValueError, TypeError):
                hit_score = None

        hit_reason: str | None = getattr(hit, "reason", None)
        if hit_reason is None and hasattr(hit, "__getitem__"):
            try:
                hit_reason = str(hit[5]) if len(hit) > 5 else None
            except (ValueError, TypeError):
                hit_reason = None

        task = asyncio.create_task(
            _fetch_and_process_page(
                semaphore=semaphore,
                query=query,
                hit_url=hit.url if hasattr(hit, "url") else str(hit[2]),
                hit_title=hit.title if hasattr(hit, "title") else str(hit[1] if len(hit) > 1 else ""),
                hit_snippet=hit.snippet if hasattr(hit, "snippet") else str(hit[3] if len(hit) > 3 else ""),
                hit_rank=hit.rank if hasattr(hit, "rank") else 0,
                fetch_timeout_s=fetch_timeout_s,
                fetch_max_bytes=fetch_max_bytes,
                store=store,
                discovery_score=hit_score,
                discovery_reason=hit_reason,
            )
        )
        tasks.append(task)

    # asyncio.gather preserves order; _check_gathered enforces [I6][I7][I8]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    # _check_gathered propagates CancelledError [I6] and BaseException [I7]
    from hledac.universal.network.session_runtime import _check_gathered
    ok_results, error_results = _check_gathered(raw_results)

    # Assemble page results in discovery order (skipping exceptions)
    all_page_results: list[PipelinePageResult] = []
    for item in ok_results:
        if isinstance(item, PipelinePageResult):
            all_page_results.append(item)

    # ---- Aggregate -----------------------------------------------------------
    total_discovered = len(hits)
    total_fetched = sum(1 for p in all_page_results if p.fetched)
    total_matched = sum(p.matched_patterns for p in all_page_results)
    total_accepted = sum(p.accepted_findings for p in all_page_results)
    total_stored = sum(p.stored_findings for p in all_page_results)
    patterns_cfg = _get_patterns_configured_count()

    # Sprint F150J Fix B: branch economics counters
    # Fix weak_pages_skipped: SKIP_WEAK post-fetch pages have error=None (not error!=None)
    strong_pages = sum(
        1 for p in all_page_results
        if p.quality_reason == "very_good"
    )
    weak_pages_skipped = sum(
        1 for p in all_page_results
        if p.quality_reason is not None and p.quality_reason.startswith("SKIP_WEAK")
    )
    # low-value = fetched but poor quality + no matches
    low_value_fetches = sum(
        1 for p in all_page_results
        if p.fetched
        and p.matched_patterns == 0
        and p.quality_reason in ("weak_low_signal", "ok:no_query_signal")
    )
    # Sprint F150J: additive derived counters for public-branch value assessment
    # discovery_strong_content_weak: discovery signal but page yielded nothing
    discovery_strong_content_weak = sum(
        1 for p in all_page_results
        if (p.discovery_signal and p.matched_patterns == 0)
    )
    # discovery_and_content_strong: both discovery signal and pattern yield
    discovery_and_content_strong = sum(
        1 for p in all_page_results
        if p.discovery_signal and p.matched_patterns > 0
    )

    run_error: str | None = None
    if discovery_error:
        run_error = discovery_error
    elif error_results:
        # Surface first error
        err = error_results[0]
        run_error = f"batch_error:{type(err).__name__}:{err}"

    # Sprint F150J: build condensed public-branch verdict
    # waste_ratio = pages that consumed budget but yielded nothing
    fetched_pages = [p for p in all_page_results if p.fetched]
    fetched_count = len(fetched_pages)
    waste_ratio = (
        round(low_value_fetches / fetched_count, 3)
        if fetched_count > 0
        else 0.0
    )
    # value_ratio = pages with actual pattern yield vs total discovered
    value_ratio = (
        round(discovery_and_content_strong / total_discovered, 3)
        if total_discovered > 0
        else 0.0
    )
    # public_branch_hint: one-liner signal quality label
    if strong_pages >= 2 and discovery_and_content_strong >= 2:
        public_branch_hint = "high_value"
    elif discovery_and_content_strong >= 1:
        public_branch_hint = "some_value"
    elif discovery_strong_content_weak >= 1:
        public_branch_hint = "weak_signal"
    elif weak_pages_skipped > 0 and fetched_count == 0:
        public_branch_hint = "skipped_low_quality"
    else:
        public_branch_hint = "low_value"

    public_branch_verdict = {
        "waste_ratio": waste_ratio,
        "value_ratio": value_ratio,
        "public_branch_hint": public_branch_hint,
        "strong_pages": strong_pages,
        "weak_pages_skipped": weak_pages_skipped,
        "discovery_strong_content_weak": discovery_strong_content_weak,
        "discovery_and_content_strong": discovery_and_content_strong,
        "low_value_fetches": low_value_fetches,
    }

    return PipelineRunResult(
        query=query,
        discovered=total_discovered,
        fetched=total_fetched,
        matched_patterns=total_matched,
        accepted_findings=total_accepted,
        stored_findings=total_stored,
        patterns_configured=patterns_cfg,
        pages=tuple(all_page_results),
        error=run_error,
        strong_pages=strong_pages,
        weak_pages_skipped=weak_pages_skipped,
        low_value_fetches=low_value_fetches,
        discovery_strong_content_weak=discovery_strong_content_weak,
        discovery_and_content_strong=discovery_and_content_strong,
        public_branch_verdict=public_branch_verdict,
    )


# Placeholder for discovery (patched in tests)
_ASYNC_DISCOVERY_SEARCH: Any = None


def _patch_discovery(search_fn: Any) -> None:
    global _ASYNC_DISCOVERY_SEARCH
    _ASYNC_DISCOVERY_SEARCH = search_fn


def _ensure_discovery_patched() -> None:
    global _ASYNC_DISCOVERY_SEARCH
    if _ASYNC_DISCOVERY_SEARCH is None:
        from hledac.universal.discovery.duckduckgo_adapter import (
            async_search_public_web,
        )
        _ASYNC_DISCOVERY_SEARCH = async_search_public_web


# Ensure discovery is patched on module import
_ensure_discovery_patched()
