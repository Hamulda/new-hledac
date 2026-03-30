"""Common Crawl adapter pro archivní web data."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RawFinding:
    """Nalezený výsledek z OSINT zdroje."""
    text: str
    source: str
    url: str
    confidence: float = 0.5
    entities: List[str] = None
    metadata: dict = None

    def __post_init__(self):
        if self.entities is None:
            self.entities = []
        if self.metadata is None:
            self.metadata = {}


class CommonCrawlAdapter:
    """Common Crawl API adapter."""

    COLLINFO_URL = "https://index.commoncrawl.org/collinfo.json"
    _latest_index: Optional[str] = None

    def __init__(self, stealth):
        """
        Args:
            stealth: StealthManager instance for HTTP requests
        """
        self._stealth = stealth
        self._session = None

    async def _get_latest_index(self) -> str:
        """Získat nejnovější Common Crawl index."""
        if CommonCrawlAdapter._latest_index is None:
            text = await self._stealth.get(self.COLLINFO_URL)
            import orjson
            colls = orjson.loads(text)
            CommonCrawlAdapter._latest_index = colls[0]['cdx-api']
        return CommonCrawlAdapter._latest_index

    async def fetch(self, domain: str, max_results: int = 50) -> List[RawFinding]:
        """
        Fetch snapshots pro domain z Common Crawl.

        Args:
            domain: Cílová doména
            max_results: Maximální počet výsledků

        Returns:
            List[RawFinding]: Nalezené snapshoty
        """
        index = await self._get_latest_index()
        url = f"{index}?url=*.{domain}&output=json&limit={max_results}&filter=statuscode:200"

        findings = []
        try:
            text = await self._stealth.get(url)
            lines = text.strip().split('\n')
            for line in lines:
                if not line.strip():
                    continue
                try:
                    import orjson
                    data = orjson.loads(line)
                    findings.append(RawFinding(
                        text=data.get('url', ''),
                        source='commoncrawl',
                        url=data.get('url'),
                        metadata={'timestamp': data.get('timestamp')}
                    ))
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"CommonCrawl fetch failed: {e}")

        return findings

    async def close(self):
        """Zavřít session."""
        pass
