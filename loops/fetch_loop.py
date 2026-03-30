"""
Fetch Loop - Data fetching phase
===============================

Async data fetching with selectolax parsing.
Part of the distributed processing pipeline.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# Try to import selectolax
try:
    from selectolax.parser import HTMLParser
    SELECTOLAX_AVAILABLE = True
except ImportError:
    SELECTOLAX_AVAILABLE = False

# Try to import aiohttp for async HTTP
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False


async def fetch_query(query: str, max_results: int = 10) -> Dict[str, Any]:
    """
    Fetch data for a research query.

    Args:
        query: Research query string
        max_results: Maximum number of results to fetch

    Returns:
        Dictionary with fetched data
    """
    logger.info(f"Fetching data for query: {query[:50]}...")

    # This is a placeholder - actual implementation would use HTTP client
    # The real fetch would be handled by FetchCoordinator in autonomous_orchestrator
    return {
        "query": query,
        "results": [],
        "status": "fetched",
        "source": "fetch_loop"
    }


def _extract_links_selectolax(html: str, base_url: str, max_links: int = 50) -> List[Dict]:
    """
    Extract links using selectolax (4x faster than lxml).

    Args:
        html: HTML content
        base_url: Base URL for resolving relative links
        max_links: Maximum number of links to extract

    Returns:
        List of link dictionaries
    """
    if not SELECTOLAX_AVAILABLE:
        return []

    try:
        parser = HTMLParser(html)
        links = []

        for node in parser.css('a'):
            href = node.attributes.get('href')
            if href and not href.startswith(('#', 'javascript:', 'mailto:')):
                # Resolve relative URLs
                if href.startswith('/'):
                    from urllib.parse import urljoin
                    href = urljoin(base_url, href)

                text = node.text(deep=True).strip()[:100] if node.text() else ""

                links.append({
                    "url": href,
                    "text": text,
                    "source": "selectolax"
                })

                if len(links) >= max_links:
                    break

        return links

    except Exception as e:
        logger.warning(f"selectolax extraction failed: {e}")
        return []


def _extract_links_regex(html: str, base_url: str, max_links: int = 50) -> List[Dict]:
    """
    Fallback: Extract links using regex.

    Args:
        html: HTML content
        base_url: Base URL
        max_links: Maximum links to extract

    Returns:
        List of link dictionaries
    """
    import re
    from urllib.parse import urljoin

    pattern = re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]*)</a>', re.IGNORECASE)
    links = []

    for match in pattern.finditer(html):
        href = match.group(1)
        text = match.group(2).strip()[:100]

        if href and not href.startswith(('#', 'javascript:', 'mailto:')):
            if href.startswith('/'):
                href = urljoin(base_url, href)

            links.append({
                "url": href,
                "text": text,
                "source": "regex"
            })

            if len(links) >= max_links:
                break

    return links


async def fetch_url(url: str, timeout: int = 30) -> Optional[str]:
    """
    Fetch a single URL.

    Args:
        url: URL to fetch
        timeout: Timeout in seconds

    Returns:
        HTML content or None
    """
    if not AIOHTTP_AVAILABLE:
        return None

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                if response.status == 200:
                    return await response.text()
                return None
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None
