"""
Sprint 8PB: test_shodan_client_cache_hit
D.6: Zapsat mock data do LMDB → query_host() vrátí data bez HTTP volání
"""

import asyncio
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest


def test_shodan_client_cache_hit():
    """With cached data, query_host returns cached result without HTTP."""
    from hledac.universal.intelligence.exposure_clients import (
        ShodanClient,
        ExposureCache,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "test_cache.lmdb"

        # Pre-populate cache
        cache = ExposureCache(prefix="shodan", cache_path=cache_path)
        mock_data = {
            "ip": "8.8.8.8",
            "country": "US",
            "org": "Google",
            "_cached_at": time.monotonic(),
        }
        cache.set("8.8.8.8", mock_data)

        # Create client with pre-filled cache
        with patch.dict("os.environ", {}, clear=True):
            client = ShodanClient()
            # Inject the cache
            client._cache = cache

            # Query should hit cache
            result = asyncio.run(client.query_host("8.8.8.8"))

            # Should return cached data
            assert result is not None
            assert result["ip"] == "8.8.8.8"
            assert result["country"] == "US"
            assert result["org"] == "Google"

            asyncio.run(client.close())


if __name__ == "__main__":
    test_shodan_client_cache_hit()
