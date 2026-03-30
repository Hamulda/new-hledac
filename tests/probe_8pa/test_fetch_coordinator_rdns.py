"""
Sprint 8PA — D.4: fetch_coordinator SocksConnector rdns=True
"""
import asyncio
from unittest.mock import patch, MagicMock

import pytest


class TestFetchCoordinatorRdns:
    """D.4: SocksConnector created with rdns=True (DNS leak prevention)."""

    def test_tor_session_connector_has_rdns_true(self):
        """_get_tor_session creates SocksConnector with rdns=True."""
        from hledac.universal.coordinators.fetch_coordinator import FetchCoordinator

        # Create minimal instance and set required attributes
        fc = FetchCoordinator.__new__(FetchCoordinator)
        fc._tor_sessions = {}
        fc._tor_last_used = {}
        fc._tor_max_sessions = 5
        fc._tor_lock = asyncio.Lock()

        # Capture the call to SocksConnector.from_url
        captured_params = {}

        class MockProxyConnector:
            @classmethod
            def from_url(cls, url, rdns=False):
                captured_params['url'] = url
                captured_params['rdns'] = rdns
                return MagicMock()

        mock_aiohttp_socks = MagicMock(SocksConnector=MockProxyConnector)
        mock_aiohttp = MagicMock()
        mock_aiohttp.ClientSession = MagicMock()
        mock_aiohttp.ClientTimeout = MagicMock()

        with patch.dict('sys.modules', {'aiohttp_socks': mock_aiohttp_socks, 'aiohttp': mock_aiohttp}):
            asyncio.run(fc._get_tor_session('example.onion'))

        assert captured_params.get('rdns') is True, \
            f"rdns must be True, got {captured_params.get('rdns')}"
        assert 'socks5://127.0.0.1:9050' in captured_params.get('url', ''), \
            f"Expected socks5:// URL, got {captured_params.get('url')}"

    def test_tor_proxy_manager_is_running(self):
        """TorProxyManager.is_running() returns bool."""
        from hledac.universal.intelligence.stealth_crawler import TorProxyManager
        result = TorProxyManager.is_running()
        assert isinstance(result, bool)

    def test_tor_transport_available_is_bool(self):
        """TorTransport.available must be a bool."""
        from hledac.universal.transport.tor_transport import TorTransport
        assert isinstance(TorTransport.available, bool)
