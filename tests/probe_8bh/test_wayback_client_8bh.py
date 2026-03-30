import asyncio
from hledac.universal.tools.deep_research_sources import wayback_cdx_lookup

def test_wayback_lookup_smoke():
    rows = asyncio.run(wayback_cdx_lookup("example.com", limit=3, timeout_s=8.0))
    assert isinstance(rows, list)
