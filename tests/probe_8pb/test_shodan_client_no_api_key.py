"""
Sprint 8PB: test_shodan_client_no_api_key
D.5: ShodanClient bez env var → query_host() vrátí None, žádná HTTP volání (mock urllib)
"""

import asyncio
from unittest.mock import patch, MagicMock

import pytest


def test_shodan_client_no_api_key():
    """Without SHODAN_API_KEY, query_host returns None without HTTP calls."""
    from hledac.universal.intelligence.exposure_clients import ShodanClient

    # Ensure no API key in environment
    with patch.dict("os.environ", {}, clear=True):
        client = ShodanClient()

        # Run query
        result = asyncio.run(client.query_host("1.2.3.4"))

        # Should return None (cache miss + no API key)
        assert result is None

        # Close
        asyncio.run(client.close())


def test_shodan_client_no_http_calls_without_key():
    """Verify no HTTP session is created when no API key."""
    from hledac.universal.intelligence.exposure_clients import ShodanClient

    with patch.dict("os.environ", {}, clear=True):
        client = ShodanClient()

        # Patch aiohttp to verify no calls
        with patch("aiohttp.ClientSession") as mock_session:
            result = asyncio.run(client.query_host("1.2.3.4"))
            assert result is None
            # Session should NOT have been created
            mock_session.assert_not_called()

        asyncio.run(client.close())


if __name__ == "__main__":
    test_shodan_client_no_api_key()
    test_shodan_client_no_http_calls_without_key()
