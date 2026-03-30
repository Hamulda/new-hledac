from unittest.mock import AsyncMock, patch
import asyncio

def test_search_multi_engine_deduplicates():
    dup = [{"url": "http://x.com", "title": "T",
            "snippet": "S", "source": "mojeek_scrape"}]
    with patch("discovery.duckduckgo_adapter.async_search_public_web",
               new_callable=AsyncMock) as mock_ddg, \
         patch("discovery.duckduckgo_adapter._scrape_mojeek",
               new_callable=AsyncMock) as mock_mj:
        from discovery.duckduckgo_adapter import search_multi_engine
        mock_ddg.return_value = type("R", (), {"hits": ()})()
        mock_mj.return_value = dup
        r = asyncio.run(search_multi_engine("test"))
        assert sum(1 for x in r if x["url"] == "http://x.com") == 1
