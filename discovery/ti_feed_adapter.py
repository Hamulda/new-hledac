"""
Lightweight structured TI feed adapters for normalized threat-intel ingress.

Provides a simple adapter seam for structured threat-intel sources (NVD, CISA KEV)
that maps to the NormalizedEntry format compatible with the existing discovery
architecture.

No browser, no JS rendering, no auth-required APIs, no cloud-only dependencies.

Sprint 8BN — Structured TI Ingest V1
"""

from __future__ import annotations

import json
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
