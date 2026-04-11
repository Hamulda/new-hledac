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
) -> str:
    """
    Return a short quality reason string for a discovered page.

    Scoring signals (compositional, no ML):
    - query-term density in title/snippet (query-aware)
    - URL signal strength (structured URL > bare domain)
    - rank priority (top results get benefit of doubt)
    - text richness (content length vs noise ratio)
    - pre-filter: skip extremely weak candidates

    Returns one of:
      SKIP_WEAK: below minimum threshold — skip
      weak_low_text: fetched but very little text
      low_signal: title/snippet missing query terms
      ok: acceptable page
      good: strong signals across multiple dimensions
      very_good: exceptional title + URL + text quality
    """
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

    # --- Text richness: content chars / total chars ratio -------
    # Very low ratio = mostly boilerplate/nav, not useful
    text_len = len(extracted_text)
    word_count = len(extracted_text.split())
    # rough noise proxy: avg word len < 3.5 suggests heavy markup/boilerplate
    avg_word_len = text_len / max(word_count, 1)
    text_is_meaningful = avg_word_len >= 3.5 and word_count >= 50

    # --- Composite scoring --------------------------------------
    signals_good = sum([
        title_has_query,
        snippet_has_query,
        url_has_path,
        text_is_meaningful,
    ])

    rank_bonus = hit_rank < 5  # top-5 gets benefit of doubt

    if signals_good >= 3 and rank_bonus:
        return "very_good"
    elif signals_good >= 2:
        return "good"
    elif signals_good >= 1:
        return "ok"
    elif text_is_meaningful and text_len > 1000:
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
    hit_title: str,  # noqa: F841
    hit_snippet: str,  # noqa: F841
    hit_rank: int,  # noqa: F841
    fetch_timeout_s: float,
    fetch_max_bytes: int,
    store: Any | None,
) -> PipelinePageResult:
    """
    Fetch one URL, extract text, scan patterns, optionally store findings.
    Returns PipelinePageResult preserving hit metadata from discovery.
    """
    async with semaphore:
        # ---- Fetch -----------------------------------------------------------
        fetch_start = time.monotonic()
        try:
            # 8AD surface
            result = await asyncio.wait_for(
                _ASYNC_FETCH_PUBLIC_TEXT(hit_url, fetch_timeout_s, fetch_max_bytes),
                timeout=fetch_timeout_s + 5.0,  # hard outer cap slightly above per-call timeout
            )
        except asyncio.TimeoutError:
            return PipelinePageResult(
                url=hit_url, fetched=False, matched_patterns=0,
                accepted_findings=0, stored_findings=0,
                error=f"fetch_timeout_after_{fetch_timeout_s}s",
            )
        except asyncio.CancelledError:
            raise  # [I6] propagate, never swallow
        except Exception as exc:
            return PipelinePageResult(
                url=hit_url, fetched=False, matched_patterns=0,
                accepted_findings=0, stored_findings=0,
                error=f"fetch_exception:{type(exc).__name__}:{exc}",
            )

        # fetch_elapsed available for future telemetry
        # fetch_elapsed = time.monotonic() - fetch_start  # noqa: F841

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
        )

        # Skip very-low-quality pages early — preserve fetch budget
        if quality_reason.startswith("SKIP_WEAK"):
            return PipelinePageResult(
                url=hit_url, fetched=True, matched_patterns=0,
                accepted_findings=0, stored_findings=0,
                error=None, quality_reason=quality_reason,
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

    run_error: str | None = None
    if discovery_error:
        run_error = discovery_error
    elif error_results:
        # Surface first error
        err = error_results[0]
        run_error = f"batch_error:{type(err).__name__}:{err}"

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
