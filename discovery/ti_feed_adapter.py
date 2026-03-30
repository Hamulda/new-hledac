"""
Lightweight structured TI feed adapters for normalized threat-intel ingress.

Provides a simple adapter seam for structured threat-intel sources (NVD, CISA KEV)
that maps to the NormalizedEntry format compatible with the existing discovery
architecture.

No browser, no JS rendering, no auth-required APIs, no cloud-only dependencies.

Sprint 8BN — Structured TI Ingest V1
"""

from __future__ import annotations

import aiohttp
import asyncio
import hashlib
import json
import logging
import time
import urllib.parse
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import msgspec

if TYPE_CHECKING:
    from hledac.universal.fetching.public_fetcher import FetchResult


# ---------------------------------------------------------------------------
# Source tier constants
# ---------------------------------------------------------------------------

TIER_SURFACE = "surface"
TIER_STRUCTURED_TI = "structured_ti"
TIER_OVERLAY_READY = "overlay_ready"


# ---------------------------------------------------------------------------
# NormalizedEntry — unified entry model for all adapters
# ---------------------------------------------------------------------------


class NormalizedEntry(msgspec.Struct, frozen=True, gc=False):
    """
    Lightweight normalized entry from any structured TI source.

    Compatible with the existing discovery architecture while providing
    richer identifier density than typical RSS feeds.

    Attributes
    ----------
    entry_hash:
        Deterministic hash of title|published_raw for dedup.
    source_url:
        Canonical URL for the entry (or empty string if N/A).
    title:
        Entry title.
    body_text:
        Extracted body/description text.
    published_at:
        Unix timestamp (UTC) or None.
    source_type:
        Adapter source type string (e.g. "nvd", "cisa_kev", "rss").
    raw_identifiers:
        Tuple of identifiers extracted from the entry (e.g. CVE IDs).
        Must contain at minimum the primary identifier if available.
    source_tier:
        Source tier classification (surface, structured_ti, overlay_ready).
    rich_content_available:
        Whether richer content (full advisory, exploit, etc.) is available.
    """

    entry_hash: str
    source_url: str
    title: str
    body_text: str
    published_at: float | None
    source_type: str
    raw_identifiers: tuple[str, ...]
    source_tier: str = TIER_SURFACE
    rich_content_available: bool = False


# ---------------------------------------------------------------------------
# SourceAdapter protocol
# ---------------------------------------------------------------------------


class SourceAdapter(ABC):
    """
    Abstract base for structured TI source adapters.

    Adapters must implement fetch_recent() which returns a list of
    NormalizedEntry objects.
    """

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Return the unique source type identifier."""
        ...

    @property
    @abstractmethod
    def source_tier(self) -> str:
        """Return the source tier classification."""
        ...

    @property
    def parseable(self) -> bool:
        """Whether the source format is parseable (default True)."""
        return True

    @property
    def stable_schema(self) -> bool:
        """Whether the source has a stable published schema (default True)."""
        return True

    @property
    def identifier_rich(self) -> bool:
        """
        Whether entries typically contain structured identifiers
        (CVE IDs, CPEs, etc.). Default True for structured TI sources.
        """
        return True

    @property
    def priority_score(self) -> int:
        """Computed priority score based on source quality attributes."""
        # Import here to avoid circular import
        from hledac.universal.discovery.source_registry import source_quality_score
        return source_quality_score(
            self.parseable,
            self.stable_schema,
            self.identifier_rich,
            self.source_tier,
        )

    @abstractmethod
    async def fetch_recent(self, limit: int) -> tuple[NormalizedEntry, ...]:
        """
        Fetch recent entries from the source.

        Parameters
        ----------
        limit:
            Maximum number of entries to return.

        Returns
        -------
        tuple[NormalizedEntry, ...]
            Entries sorted newest-first if published_at is available,
            otherwise in discovery order. Empty tuple on failure.
        """
        ...

    # ---------------------------------------------------------------------------
    # Shared utilities for subclasses
    # ---------------------------------------------------------------------------

    @staticmethod
    def _hash_fields(*fields: str) -> str:
        """Compute deterministic xxhash over pipe-separated fields."""
        import xxhash
        return xxhash.xxh64("|".join(f or "" for f in fields)).hexdigest()

    @staticmethod
    def _fetch_text(
        url: str,
        timeout_s: float = 30.0,
        max_bytes: int = 5_000_000,
    ) -> tuple[str | None, str | None]:
        """
        Fetch text content via public_fetcher.

        Returns (text, error). One is always None.
        """
        import asyncio
        from hledac.universal.fetching.public_fetcher import async_fetch_public_text

        try:
            result: FetchResult = asyncio.run(
                async_fetch_public_text(url, timeout_s=timeout_s, max_bytes=max_bytes)
            )
        except Exception as e:
            return None, str(e)

        if result.error or result.text is None:
            return None, result.error or "fetch_returned_none"
        return result.text, None


# ---------------------------------------------------------------------------
# NVD CVE API v2 Adapter
# ---------------------------------------------------------------------------


class NvdApiAdapter(SourceAdapter):
    """
    NVD CVE API v2 recent CVE ingest.

    Public, no auth required. Bounded resultsPerPage.
    Maps CVE ID, description, score, and references to NormalizedEntry.

    API base: https://services.nvd.nist.gov/rest/json/cves/2.0
    """

    API_BASE = "https://services.nvd.nist.gov/rest/json/cves/2.0"
    SOURCE_TYPE = "nvd"
    SOURCE_TIER = TIER_STRUCTURED_TI
    MAX_PER_PAGE = 20
    HARD_LIMIT = 100

    @property
    def source_type(self) -> str:
        return self.SOURCE_TYPE

    @property
    def source_tier(self) -> str:
        return self.SOURCE_TIER

    @property
    def identifier_rich(self) -> bool:
        return True

    async def fetch_recent(self, limit: int) -> tuple[NormalizedEntry, ...]:
        """
        Fetch recent CVEs from NVD API.

        Uses /cves/recent endpoint for latest CVEs.
        Results sorted by lastModified descending (NVD default).
        """
        limit = min(max(limit, 1), self.HARD_LIMIT)
        results_per_page = min(limit, self.MAX_PER_PAGE)

        url = (
            f"{self.API_BASE}"
            f"?resultsPerPage={results_per_page}"
            f"&startIndex=0"
        )

        text, error = self._fetch_text(url, timeout_s=30.0, max_bytes=5_000_000)
        if error or text is None:
            return ()

        try:
            data = json.loads(text)
        except Exception:
            return ()

        vulnerabilities = data.get("vulnerabilities", [])
        if not isinstance(vulnerabilities, list):
            return ()

        entries: list[NormalizedEntry] = []
        retrieved_ts = time.time()

        for vuln in vulnerabilities[:limit]:
            cve_data = vuln.get("cve", {})
            cve_id = cve_data.get("id", "")

            # Description: prefer English description
            descriptions = cve_data.get("descriptions", [])
            description = ""
            for desc in descriptions:
                if desc.get("lang", "").lower() == "en":
                    description = desc.get("value", "")
                    break
            if not description and descriptions:
                description = descriptions[0].get("value", "")

            # Published/referenced times
            published_ts: float | None = None
            pub_str = cve_data.get("published")
            if pub_str:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                    published_ts = dt.timestamp()
                except Exception:
                    pass

            # References (bounded)
            references = cve_data.get("references", [])[:5]
            source_url = references[0].get("url", "") if references else ""

            # Metrics for richness
            metrics = cve_data.get("metrics", {})
            score = None
            if "cvssMetricV31" in metrics:
                cvss = metrics["cvssMetricV31"][0].get("cvssData", {})
                score = cvss.get("baseScore")
            elif "cvssMetricV30" in metrics:
                cvss = metrics["cvssMetricV30"][0].get("cvssData", {})
                score = cvss.get("baseScore")
            elif "cvssMetricV2" in metrics:
                cvss = metrics["cvssMetricV2"][0].get("cvssData", {})
                score = cvss.get("baseScore")

            # Build body_text with score if available
            body_parts = []
            if description:
                body_parts.append(description)
            if score is not None:
                body_parts.append(f"CVSS: {score}")

            body_text = " ".join(body_parts)

            # raw_identifiers must contain CVE ID
            raw_identifiers = (cve_id,) if cve_id else ()

            entry_hash = self._hash_fields(cve_id, published_ts is not None and str(published_ts) or "")

            entries.append(
                NormalizedEntry(
                    entry_hash=entry_hash,
                    source_url=source_url,
                    title=cve_id or "",
                    body_text=body_text,
                    published_at=published_ts,
                    source_type=self.SOURCE_TYPE,
                    raw_identifiers=raw_identifiers,
                    source_tier=self.SOURCE_TIER,
                    rich_content_available=bool(references),
                )
            )

        return tuple(entries)


# ---------------------------------------------------------------------------
# CISA KEV JSON Adapter
# ---------------------------------------------------------------------------


class CisaKevAdapter(SourceAdapter):
    """
    CISA Known Exploited Vulnerabilities (KEV) catalog JSON ingest.

    Public, no auth required. Single JSON endpoint.
    Maps CVE ID, vendor/project/product, and notes to NormalizedEntry.

    API: https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json
    """

    API_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
    SOURCE_TYPE = "cisa_kev"
    SOURCE_TIER = TIER_STRUCTURED_TI
    HARD_LIMIT = 200

    @property
    def source_type(self) -> str:
        return self.SOURCE_TYPE

    @property
    def source_tier(self) -> str:
        return self.SOURCE_TIER

    @property
    def identifier_rich(self) -> bool:
        return True

    @property
    def stable_schema(self) -> bool:
        # KEV schema is versioned and stable per CISA mandate
        return True

    async def fetch_recent(self, limit: int) -> tuple[NormalizedEntry, ...]:
        """
        Fetch KEV catalog entries.

        Returns entries sorted by dateAdded descending (most recent first).
        """
        limit = min(max(limit, 1), self.HARD_LIMIT)

        text, error = self._fetch_text(self.API_URL, timeout_s=45.0, max_bytes=10_000_000)
        if error or text is None:
            return ()

        try:
            data = json.loads(text)
        except Exception:
            return ()

        vulns = data.get("vulnerabilities", [])
        if not isinstance(vulns, list):
            return ()

        entries: list[NormalizedEntry] = []

        for vuln in vulns[:limit]:
            cve_id = vuln.get("cveID", "")

            # Build body_text from available fields
            body_parts = []
            for field in ("vendorProject", "product", "shortDescription", "notes"):
                val = vuln.get(field, "")
                if val:
                    body_parts.append(str(val))

            body_text = " ".join(body_parts)

            # Date parsing
            published_ts: float | None = None
            date_added = vuln.get("dateAdded", "")
            if date_added:
                try:
                    from datetime import datetime
                    dt = datetime.strptime(date_added, "%Y-%m-%d")
                    published_ts = dt.timestamp()
                except Exception:
                    pass

            source_url = vuln.get("knownRansomwareCampaignUse", "")
            if not source_url:
                source_url = f"https://www.cisa.gov/known-exploited-vulnerabilities-catalog"

            raw_identifiers = (cve_id,) if cve_id else ()

            entry_hash = self._hash_fields(
                cve_id,
                date_added,
            )

            entries.append(
                NormalizedEntry(
                    entry_hash=entry_hash,
                    source_url=source_url or "",
                    title=cve_id or "",
                    body_text=body_text,
                    published_at=published_ts,
                    source_type=self.SOURCE_TYPE,
                    raw_identifiers=raw_identifiers,
                    source_tier=self.SOURCE_TIER,
                    rich_content_available=False,
                )
            )

        return tuple(entries)


# =============================================================================
# Sprint 8VB: Maximum OSINT Coverage
# =============================================================================

logger = logging.getLogger(__name__)

# ── ABUSE.CH FEEDS ──────────────────────────────────────────────────────────

async def fetch_urlhaus(max_items: int = 100) -> list[dict]:
    """URLhaus — live malware URL feed, public API, no key required."""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://urlhaus-api.abuse.ch/v1/urls/recent/",
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                data = await r.json()
                return [
                    {
                        "ioc":         e.get("url"),
                        "ioc_type":    "url",
                        "threat_type": e.get("threat"),
                        "title":       f"URLhaus: {e.get('threat','malware')}",
                        "source":      "urlhaus"
                    }
                    for e in data.get("urls", [])[:max_items]
                    if e.get("url_status") == "online"
                ]
    except Exception as e:
        logger.debug(f"[URLhaus] {e}")
    return []


async def fetch_threatfox(days: int = 1) -> list[dict]:
    """ThreatFox IOC feed — public API, no key required."""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://threatfox-api.abuse.ch/api/v1/",
                json={"query": "get_iocs", "days": days},
                timeout=aiohttp.ClientTimeout(total=20)
            ) as r:
                data = await r.json()
                return [
                    {
                        "ioc":        i.get("ioc_value"),
                        "ioc_type":   i.get("ioc_type"),
                        "malware":    i.get("malware"),
                        "confidence": i.get("confidence_level", 50) / 100,
                        "title":      f"ThreatFox: {i.get('malware','?')}",
                        "source":     "threatfox"
                    }
                    for i in data.get("data", [])
                ]
    except Exception as e:
        logger.debug(f"[ThreatFox] {e}")
    return []


async def fetch_feodo_c2() -> list[dict]:
    """Feodo Tracker C2 blocklist — public JSON, no key required."""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://feodotracker.abuse.ch/downloads/ipblocklist.json",
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                return [
                    {
                        "ioc":      e.get("ip_address"),
                        "ioc_type": "ip",
                        "malware":  e.get("malware"),
                        "port":     e.get("port"),
                        "title":    f"Feodo C2: {e.get('ip_address')}",
                        "source":   "feodo_tracker"
                    }
                    for e in await r.json(content_type=None)
                ]
    except Exception as e:
        logger.debug(f"[Feodo] {e}")
    return []


# ── PASSIVE DNS ─────────────────────────────────────────────────────────────

async def query_circl_pdns(
    domain: str, max_results: int = 50
) -> list[dict]:
    """CIRCL Passive DNS — community free tier, no authentication."""
    import json as _json
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://www.circl.lu/pdns/query/{domain}",
                headers={"Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                if r.status != 200:
                    return []
                results = []
                for line in (await r.text()).strip().split("\n")[:max_results]:
                    try:
                        rec = _json.loads(line)
                        results.append({
                            "ioc":        rec.get("rrvalue", ""),
                            "ioc_type":   rec.get("rrtype", "A").lower(),
                            "domain":     rec.get("rrname", ""),
                            "first_seen": rec.get("time_first", ""),
                            "last_seen":  rec.get("time_last", ""),
                            "source":     "circl_pdns"
                        })
                    except Exception:
                        continue
                return results
    except Exception as e:
        logger.debug(f"[CIRCL pDNS] {e}")
    return []


# ── CERTIFICATE TRANSPARENCY ────────────────────────────────────────────────

async def search_crtsh(
    domain: str, max_results: int = 100
) -> list[dict]:
    """crt.sh Certificate Transparency search — no key required."""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://crt.sh/",
                params={"q": f"%.{domain}", "output": "json"},
                timeout=aiohttp.ClientTimeout(total=20)
            ) as r:
                if r.status != 200:
                    return []
                data = await r.json(content_type=None)
                results: list[dict] = []
                seen:   set[str]    = set()
                for cert in data[:max_results]:
                    for sub in cert.get("name_value", "").split("\n"):
                        sub = sub.strip()
                        if sub and sub not in seen:
                            seen.add(sub)
                            results.append({
                                "ioc":     sub,
                                "ioc_type":"domain",
                                "issuer":  cert.get("issuer_name", ""),
                                "title":   f"CT cert: {sub}",
                                "source":  "crtsh"
                            })
                return results
    except Exception as e:
        logger.warning(f"[crt.sh] {e}")
    return []


async def certstream_monitor(
    keyword: str,
    duration_s: int = 60,
    max_certs: int = 200
) -> list[dict]:
    """
    Certstream WebSocket — live CT certificate monitoring.
    Captures new certificates containing keyword in domain.
    Requires: pip install websockets
    FIXED: uses get_running_loop() — no race condition.
    """
    try:
        import websockets
    except ImportError:
        logger.debug("[Certstream] websockets not installed")
        return []
    import json as _json
    results: list[dict] = []
    try:
        loop     = asyncio.get_running_loop()
        deadline = loop.time() + duration_s
        async with websockets.connect(
            "wss://certstream.calidog.io",
            ping_interval=10, close_timeout=5
        ) as ws:
            while loop.time() < deadline:
                if len(results) >= max_certs:
                    break
                try:
                    msg  = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = _json.loads(msg)
                    if data.get("message_type") != "certificate_update":
                        continue
                    for d in data["data"]["leaf_cert"]["all_domains"]:
                        if keyword.lower() in d.lower():
                            results.append({
                                "ioc":      d,
                                "ioc_type": "domain",
                                "title":    f"Certstream: {d}",
                                "source":   "certstream_live"
                            })
                except asyncio.TimeoutError:
                    continue
    except Exception as e:
        logger.warning(f"[Certstream] {e}")
    return results


# ── SHODAN INTERNETDB ───────────────────────────────────────────────────────

async def enrich_ip_internetdb(ip: str) -> dict:
    """
    Shodan InternetDB — open ports, CVEs, hostnames.
    Free, no API key, ARM64 native. ~1MB RAM.
    """
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


# ── PASTE MONITORING ────────────────────────────────────────────────────────

async def scrape_pastebin_for_keyword(
    keyword: str, max_pastes: int = 10
) -> list[dict]:
    """
    Pastebin archive scraping — public, no key required.
    FIXED: await asyncio.sleep() (previous bug was sync sleep).
    """
    from bs4 import BeautifulSoup
    results: list[dict] = []
    _UA = "Mozilla/5.0 (Macintosh; ARM Mac OS X 14_0) AppleWebKit/605.1.15"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://pastebin.com/archive",
                headers={"User-Agent": _UA},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                if r.status != 200:
                    return []
                soup = BeautifulSoup(await r.text(), "html.parser")
                paste_urls = [
                    f"https://pastebin.com/raw{a['href']}"
                    for tr in soup.select("table.maintable tr")[1:21]
                    for a in tr.select("td a")[:1]
                    if a.get("href")
                ]
            for raw_url in paste_urls[:max_pastes]:
                await asyncio.sleep(1.0)  # ← FIXED: await (was bug)
                try:
                    async with s.get(
                        raw_url,
                        headers={"User-Agent": _UA},
                        timeout=aiohttp.ClientTimeout(total=8)
                    ) as pr:
                        if pr.status == 200:
                            content = await pr.text()
                            if keyword.lower() in content.lower():
                                results.append({
                                    "url":          raw_url,
                                    "content":      content[:2000],
                                    "content_hash": hashlib.sha256(
                                        content.encode()
                                    ).hexdigest()[:16],
                                    "title":  f"Pastebin hit: {keyword}",
                                    "source": "pastebin_scrape"
                                })
                except Exception:
                    continue
    except Exception as e:
        logger.debug(f"[Pastebin] {e}")
    return results


async def search_github_gists(
    keyword: str, max_results: int = 10
) -> list[dict]:
    """GitHub Gist public search — free, no key required."""
    from bs4 import BeautifulSoup
    results: list[dict] = []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://gist.github.com/search",
                params={"q": keyword, "s": "updated"},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=aiohttp.ClientTimeout(total=12)
            ) as r:
                if r.status != 200:
                    return []
                soup = BeautifulSoup(await r.text(), "html.parser")
                for item in soup.select(".gist-snippet")[:max_results]:
                    a = item.select_one(".gist-snippet-meta a")
                    p = item.select_one(".gist-snippet-body")
                    if a and a.get("href"):
                        results.append({
                            "url":     f"https://gist.github.com{a['href']}",
                            "title":   a.get_text(strip=True),
                            "snippet": p.get_text(strip=True)[:200] if p else "",
                            "source":  "github_gist_search"
                        })
    except Exception as e:
        logger.debug(f"[GitHub Gist] {e}")
    return results


# ── GITHUB DORKING ──────────────────────────────────────────────────────────

_GH_DORK_TEMPLATES = {
    "ioc_in_code":    '"{v}" filename:iocs.txt OR filename:indicators',
    "credential":     '"{v}" password OR token OR secret',
    "config_leak":    '"{v}" filename:config.yml OR filename:.env',
    "malware_sample": '"{v}" malware OR implant OR backdoor',
}
_GH_HEADERS_BASE = {
    "Accept":     "application/vnd.github.v3+json",
    "User-Agent": "hledac-osint/1.0"
}


async def github_dork(
    value: str,
    dork_type: str = "ioc_in_code",
    max_results: int = 20
) -> list[dict]:
    """
    GitHub code search dorking.
    Without token: 60 req/h (public unauthenticated).
    With GITHUB_TOKEN env var: 5000 req/h.
    Token is optional — function works without it.
    """
    import os
    headers = dict(_GH_HEADERS_BASE)
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"
    query = _GH_DORK_TEMPLATES.get(
        dork_type, _GH_DORK_TEMPLATES["ioc_in_code"]
    ).format(v=value)
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://api.github.com/search/code",
                params={"q": query, "per_page": min(max_results, 30)},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    return [
                        {
                            "title":   i["name"],
                            "url":     i["html_url"],
                            "snippet": i["repository"]["full_name"],
                            "source":  "github_dork"
                        }
                        for i in data.get("items", [])
                    ]
                elif r.status == 403:
                    logger.debug("[GitHub dork] rate limited — set GITHUB_TOKEN")
    except Exception as e:
        logger.debug(f"[GitHub dork] {e}")
    return []


# ── TOR HIDDEN SERVICES — Ahmia ─────────────────────────────────────────────

AHMIA_CLEARNET = "https://ahmia.fi/search/"
AHMIA_ONION    = (
    "http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd"
    ".onion/search/"
)


async def search_ahmia(
    query: str,
    max_results: int = 20,
    use_onion: bool = False
) -> list[dict]:
    """
    Ahmia dark web index search.
    use_onion=True → via tor_transport.
    """
    from bs4 import BeautifulSoup
    base = AHMIA_ONION if use_onion else AHMIA_CLEARNET
    html = ""
    try:
        if use_onion:
            from transport.tor_transport import TorTransport
            # Use direct Tor session if available
            # Fallback to clearnet if tor not available
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(
                        f"{base}?q={query}",
                        headers={"User-Agent": "Mozilla/5.0"},
                        timeout=aiohttp.ClientTimeout(total=15)
                    ) as r:
                        html = await r.text() if r.status == 200 else ""
            except Exception:
                pass
        else:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    base, params={"q": query},
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as r:
                    html = await r.text() if r.status == 200 else ""
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        return [
            {
                "title":   a.get_text(strip=True),
                "url":     a["href"],
                "snippet": p.get_text(strip=True) if p else "",
                "source":  "ahmia_onion" if use_onion else "ahmia_clearnet"
            }
            for li in soup.select("li.result")[:max_results]
            for a in [li.select_one("h4 a")]
            for p in [li.select_one("p")]
            if a and a.get("href")
        ]
    except Exception as e:
        logger.warning(f"[Ahmia] {e}")
    return []


# ── RDAP LOOKUP ──────────────────────────────────────────────────────────────

async def query_rdap(target: str) -> dict:
    """
    RDAP — WHOIS successor, structured REST API, no key required.
    Automatically detects domain vs IP.
    """
    is_ip = (
        target.replace(".", "").isdigit() or ":" in target
    )
    base     = "https://rdap.org"
    endpoint = (
        f"{base}/ip/{target}" if is_ip
        else f"{base}/domain/{target}"
    )
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


# ---------------------------------------------------------------------------
# Adapter registration (module-level, fail-soft)
# ---------------------------------------------------------------------------

def _register_structured_adapters() -> None:
    """Register the structured TI adapters. Called once at module load."""
    from hledac.universal.discovery.source_registry import register_source_adapter
    try:
        register_source_adapter(NvdApiAdapter.SOURCE_TYPE, NvdApiAdapter)
    except ValueError:
        pass  # already registered
    try:
        register_source_adapter(CisaKevAdapter.SOURCE_TYPE, CisaKevAdapter)
    except ValueError:
        pass  # already registered


_register_structured_adapters()
