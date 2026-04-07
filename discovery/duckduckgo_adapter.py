"""
DuckDuckGo public web discovery adapter.

Backend: duckduckgo_search v8.1.1 (sync-only; async via asyncio.to_thread compatibility fallback)

INVARIANTS (Sprint 8AC):
- Public/passive-only; no auth, no cookies, no credentials
- No AO imports; no storage writes; no pattern matcher calls
- No import-time network side effects
- max_results hard cap = 50; default = 10
- asyncio.timeout() for timeout; CancelledError re-raised
- fail-soft for RatelimitException / TimeoutException / generic backend errors
- Per-call URL dedup with preserve-first ordering
- msgspec.Struct(frozen=True, gc=False) for all DTOs
"""

from __future__ import annotations

import asyncio
import logging
import time
import urllib.parse as urlparse
from typing import TYPE_CHECKING

import aiohttp
import msgspec

if TYPE_CHECKING:
    from duckduckgo_search import DDGS  # noqa: F401


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SOURCE_NAME: str = "duckduckgo"
DEFAULT_MAX_RESULTS: int = 10
HARD_MAX_RESULTS: int = 50
DEFAULT_TIMEOUT_S: float = 35.0

# ---------------------------------------------------------------------------
# DTO contracts
# ---------------------------------------------------------------------------


class DiscoveryHit(msgspec.Struct, frozen=True, gc=False):
    """
    Single web discovery result.

    All string fields are never None — None is normalized to "".
    """

    query: str
    title: str
    url: str
    snippet: str
    source: str  # always "duckduckgo"
    rank: int
    retrieved_ts: float


class DiscoveryBatchResult(msgspec.Struct, frozen=True, gc=False):
    """
    Result surface for a single discovery call.

    On any backend error the hits tuple is empty and error is set.
    On cancel (asyncio.CancelledError) the error is NOT swallowed —
    the exception is re-raised after the call unwinds.
    """

    hits: tuple[DiscoveryHit, ...]
    error: str | None = None


# ---------------------------------------------------------------------------
# Status helpers (O(1), no network calls)
# ---------------------------------------------------------------------------

_backend_name: str = "duckduckgo_search"
_backend_version: str | None = None
_last_error: str | None = None


def backend_name() -> str:
    return _backend_name


def backend_version() -> str:  # noqa: D102
    global _backend_version
    if _backend_version is None:
        try:
            import duckduckgo_search

            _backend_version = getattr(duckduckgo_search, "__version__", "unknown")
        except Exception:  # pragma: no cover — defensive
            _backend_version = "unknown"
    return _backend_version  # type: ignore[return-value]


def last_error() -> str | None:
    return _last_error


# ---------------------------------------------------------------------------
# URL normalisation for per-call dedup
# ---------------------------------------------------------------------------


def _normalize_url_for_dedup(raw_url: str) -> str:
    """
    Minimal URL normalisation for deduplication only.

    Rules:
    1. Lower-case scheme + host
    2. Strip trailing slash from path only (keep root-only "http://host/")
    3. Remove solitary trailing "?"
    4. Preserve fragment (user may want #section anchors)
    """
    if not raw_url:
        return ""

    try:
        parsed = urlparse.urlparse(raw_url)
        scheme = parsed.scheme.lower() if parsed.scheme else "https"
        netloc = parsed.netloc.lower() if parsed.netloc else ""

        path = parsed.path
        # strip trailing slash only when path is non-empty (avoids "http://host/" -> "http://host")
        if path.endswith("/") and len(path) > 1:
            path = path.rstrip("/")

        query = parsed.query
        # drop lone "?" with no real query params
        if query == "?":
            query = ""

        fragment = parsed.fragment

        return urlparse.urlunsplit((scheme, netloc, path, query, fragment))
    except Exception:  # pragma: no cover — defensive, malformed URL
        # Fallback: lowercase as much as reasonably possible
        lower = raw_url.lower()
        if lower.endswith("/") and len(lower) > 1:
            lower = lower.rstrip("/")
        return lower


# ---------------------------------------------------------------------------
# Internal backend wrapper
# ---------------------------------------------------------------------------


async def _ddgs_text_search(
    query: str,
    max_results: int,
    timeout_s: float,
    proxy: str | None,
) -> list[dict]:
    """
    Compatibility async wrapper around synchronous DDGS.text().

    Uses asyncio.to_thread() because duckduckgo_search v8.1.1 does NOT
    provide an AsyncDDGS class — only a sync DDGS class.

    Raises:
        CancelledError: propagated from the cancelled task.
        DuckDuckGoSearchException (subclasses): translated to error strings.
    """
    global _last_error

    def _sync_search() -> list[dict]:
        # Lazy import so that import-time of this module has zero network effect
        from duckduckgo_search import DDGS  # noqa: T1009

        backend: DDGS = DDGS()
        try:
            results = list(
                backend.text(query, max_results=max_results, proxy=proxy)
            )
            return results
        finally:
            try:
                backend.client.close()
            except Exception:  # pragma: no cover — best-effort
                pass

    hits: list[dict] = await asyncio.to_thread(_sync_search)
    return hits


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def async_search_public_web(
    query: str,
    max_results: int = DEFAULT_MAX_RESULTS,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    proxy: str | None = None,
) -> DiscoveryBatchResult:
    """
    Public web discovery via DuckDuckGo.

    Args:
        query:        Search query string (stripped; empty -> fail-soft no call).
        max_results:  Number of results to return (default 10, hard cap 50).
        timeout_s:    Per-request timeout in seconds (default 35).
        proxy:        Optional proxy URL (passed to backend if supported).

    Returns:
        DiscoveryBatchResult with hits tuple and optional error string.

    Fail-soft errors:
        - "empty_query"     : query was blank after strip
        - "rate_limited"    : RatelimitException from backend
        - "timeout"         : TimeoutException / asyncio.TimeoutError
        - "backend_error"   : Any other DuckDuckGoSearchException

    Note: max_results is silently clamped to [1, HARD_MAX_RESULTS] — no error is returned.

    CancelledError is always re-raised (not swallowed).

    Per-call URL dedup is applied after normalisation, preserving first-seen rank.
    """
    global _last_error

    # ---- input validation ---------------------------------------------------
    if query is None:
        _last_error = "empty_query"
        return DiscoveryBatchResult(hits=(), error="empty_query")
    trimmed = query.strip() if isinstance(query, str) else str(query).strip()
    if not trimmed:
        _last_error = "empty_query"
        return DiscoveryBatchResult(hits=(), error="empty_query")

    # ---- bounds + type guard ----------------------------------------------
    try:
        max_results = max(1, min(int(max_results), HARD_MAX_RESULTS))
    except (TypeError, ValueError):
        max_results = DEFAULT_MAX_RESULTS

    # ---- timeout wrapper ---------------------------------------------------
    try:
        async with asyncio.timeout(timeout_s):
            raw_hits: list[dict] = await _ddgs_text_search(
                trimmed, max_results, timeout_s, proxy
            )
    except asyncio.CancelledError:
        _last_error = "cancelled"
        raise  # always re-raise — do NOT swallow
    except asyncio.TimeoutError:
        _last_error = "timeout"
        return DiscoveryBatchResult(hits=(), error="timeout")
    except Exception as e:
        # ---- fail-soft for all backend errors ---------------------------------
        err_str = str(e)
        error_tag: str
        if "ratelimit" in err_str.lower() or "RatelimitException" in type(e).__name__:
            error_tag = "rate_limited"
        elif "timeout" in err_str.lower() or "TimeoutException" in type(e).__name__:
            error_tag = "timeout"
        else:
            error_tag = "backend_error"

        _last_error = error_tag
        return DiscoveryBatchResult(hits=(), error=error_tag)

    # ---- normalise + dedup -------------------------------------------------
    # URL -> (original_rank, DiscoveryHit) — preserve first-seen
    seen_urls: dict[str, int] = {}
    retrieved_ts = time.time()
    hits_list: list[DiscoveryHit] = []

    for _rank, raw in enumerate(raw_hits):
        raw_url = raw.get("url") or ""
        title = raw.get("title") or ""
        snippet = raw.get("body") or raw.get("snippet") or ""

        norm = _normalize_url_for_dedup(raw_url)
        if not norm or norm in seen_urls:
            continue

        seen_urls[norm] = len(hits_list)
        hits_list.append(
            DiscoveryHit(
                query=trimmed,
                title=title,
                url=raw_url,
                snippet=snippet,
                source=SOURCE_NAME,
                rank=len(hits_list),
                retrieved_ts=retrieved_ts,
            )
        )

    # Enforce final max_results cap after dedup
    final_hits = tuple(hits_list[:max_results])

    # Re-rank to reflect final slice order
    final_hits = tuple(
        DiscoveryHit(
            query=h.query,
            title=h.title,
            url=h.url,
            snippet=h.snippet,
            source=h.source,
            rank=i,
            retrieved_ts=h.retrieved_ts,
        )
        for i, h in enumerate(final_hits)
    )

    return DiscoveryBatchResult(hits=final_hits, error=None)


# ── Sprint 8VB: Multi-Engine Search ───────────────────────────────────────────

logger = logging.getLogger(__name__)


async def _scrape_mojeek(
    query: str, n: int = 10
) -> list[dict]:
    """Mojeek independent crawler, no CAPTCHA policy."""
    from bs4 import BeautifulSoup
    _UA = (
        "Mozilla/5.0 (Macintosh; ARM Mac OS X 14_0) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.0 Safari/605.1.15"
    )
    results = []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://www.mojeek.com/search",
                params={"q": query},
                headers={"User-Agent": _UA,
                         "Accept-Language": "en-US,en;q=0.9"},
                timeout=aiohttp.ClientTimeout(total=12)
            ) as r:
                if r.status != 200:
                    return []
                soup = BeautifulSoup(await r.text(), "html.parser")
                for li in soup.select("ul.results-standard li")[:n]:
                    a = li.select_one("a.ob")
                    p = li.select_one("p.s")
                    if a and a.get("href"):
                        results.append({
                            "title":   a.get_text(strip=True),
                            "url":     a["href"],
                            "snippet": p.get_text(strip=True) if p else "",
                            "source":  "mojeek_scrape"
                        })
    except Exception as e:
        logger.debug(f"[Mojeek] {e}")
    return results


async def _search_wayback_cdx(
    url_pattern: str, max_results: int = 20
) -> list[dict]:
    """Wayback CDX API — historical snapshots of URL.
    COMPAT: Tato funkce je dočasný compat wrapper.
    AUTHORITY: archive_discovery.wayback_cdx_lookup() je search-shaped canonical.
    REMOVAL CONDITION: po přechodu všech call-sites na archive_discovery.wayback_cdx_lookup().
    """
    from hledac.universal.intelligence.archive_discovery import wayback_cdx_lookup

    snapshots = await wayback_cdx_lookup(url_pattern, limit=max_results, timeout_s=20.0)
    # Převod z wayback_cdx_lookup format na _search_wayback_cdx format
    results = []
    for snap in snapshots:
        results.append({
            "title":        snap.get("title", ""),
            "url":          snap.get("url", ""),
            "snapshot_url": snap.get("url", ""),
            "timestamp":    snap.get("timestamp", ""),
            "mimetype":     "",
            "source":       "wayback_cdx"
        })
    return results


async def _search_commoncrawl_cdx(
    url_pattern: str, max_results: int = 20
) -> list[dict]:
    """CommonCrawl CDX index — petabytes of crawl data, free.
    COMPAT: Tato funkce je dočasný compat wrapper.
    AUTHORITY: archive_discovery.commondrawl_cdx_lookup() je search-shaped canonical.
    REMOVAL CONDITION: po přechodu všech call-sites na archive_discovery."""
    import json as _json
    results = []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://index.commoncrawl.org/CC-MAIN-2024-51-index",
                params={
                    "url":    url_pattern,
                    "output": "json",
                    "limit":  max_results,
                    "fl":     "url,timestamp,filename,offset,length"
                },
                timeout=aiohttp.ClientTimeout(total=25)
            ) as r:
                if r.status != 200:
                    return []
                for line in (await r.text()).strip().split("\n")[:max_results]:
                    try:
                        rec = _json.loads(line)
                        results.append({
                            "title":        f"CommonCrawl: {rec.get('url','')}",
                            "url":          rec.get("url", ""),
                            "timestamp":    rec.get("timestamp", ""),
                            "warc_filename":rec.get("filename", ""),
                            "warc_offset":  rec.get("offset", 0),
                            "warc_length":  rec.get("length", 0),
                            "source":       "commoncrawl_cdx"
                        })
                    except Exception:
                        continue
    except Exception as e:
        logger.warning(f"[CommonCrawl CDX] {e}")
    return results


async def _query_shodan_internetdb(ip: str) -> dict:
    """Shodan InternetDB — open ports, CVEs, hostnames. Free, no API key.
    COMPAT: Tato funkce je dočasný compat wrapper.
    AUTHORITY: registry/shodan_internetdb_lookup() je search-shaped canonical.
    REMOVAL CONDITION: po přechodu všech call-sites na registry/shodan_internetdb_lookup()."""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://internetdb.shodan.io/{ip}",
                timeout=aiohttp.ClientTimeout(total=8)
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    return {
                        "ip":        ip,
                        "ports":     data.get("ports", []),
                        "cves":      data.get("cves", []),
                        "hostnames": data.get("hostnames", []),
                        "tags":      data.get("tags", []),
                        "source":    "shodan_internetdb"
                    }
    except Exception as e:
        logger.debug(f"[ShodanInternetDB] {e}")
    return {}


async def _query_rdap(target: str) -> dict:
    """RDAP — structured WHOIS successor, free without key.
    COMPAT: Tato funkce je dočasný compat wrapper.
    AUTHORITY: registry/rdap_lookup() je search-shaped canonical.
    REMOVAL CONDITION: po přechodu všech call-sites na registry/rdap_lookup()."""
    is_ip = target.replace(".", "").isdigit() or ":" in target
    base  = "https://rdap.org"
    endpoint = f"{base}/ip/{target}" if is_ip else f"{base}/domain/{target}"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                endpoint,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    return {
                        "target": target,
                        "rdap":   data,
                        "source": "rdap_org"
                    }
    except Exception as e:
        logger.debug(f"[RDAP] {e}")
    return {}


async def search_multi_engine(
    query: str, max_results: int = 30
) -> list[dict]:
    """
    Parallel search: DDG + Mojeek with URL deduplication.
    Bing excluded — actively blocks + CAPTCHA.
    """
    ddg_task    = async_search_public_web(query, max_results=max_results // 2)
    mojeek_task = _scrape_mojeek(query, max_results // 2)

    all_results: list[dict] = []
    for batch in await asyncio.gather(
        ddg_task, mojeek_task,
        return_exceptions=True
    ):
        if isinstance(batch, DiscoveryBatchResult) and batch.hits:
            all_results.extend([
                {"title": h.title, "url": h.url, "snippet": h.snippet, "source": h.source}
                for h in batch.hits
            ])
        elif isinstance(batch, list):
            all_results.extend(batch)

    seen: set[str] = set()
    deduped: list[dict] = []
    for r in all_results:
        raw_u = r.get("url", "")
        if not raw_u:
            continue
        norm = _normalize_url_for_dedup(raw_u)
        if norm and norm not in seen:
            seen.add(norm)
            deduped.append(r)
    return deduped[:max_results]
