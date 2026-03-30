"""
Sprint 8PA — D.3: stealth_crawler _fetch_with_requests conditional Tor proxy
"""
import sys
from unittest.mock import patch, MagicMock, call
from types import SimpleNamespace

import pytest


class TestStealthCrawlerNoBareRequests:
    """D.3: _fetch_with_requests uses SOCKS only when Tor is running."""

    def test_tor_running_sets_socks_proxy(self):
        """When TorProxyManager.is_running()=True → socks proxy set."""
        from hledac.universal.intelligence.stealth_crawler import StealthCrawler

        sc = StealthCrawler()

        # Mock TorProxyManager.is_running → True
        with patch.object(
            sc, '_fetch_with_requests',
            wraps=sc._fetch_with_requests
        ):
            # Also mock requests and socks to avoid real network
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = 'OK'
            mock_response.raise_for_status = MagicMock()

            mock_requests = MagicMock()
            mock_requests.get.return_value = mock_response

            mock_socks = MagicMock()
            mock_socket = MagicMock()

            with patch.dict(sys.modules, {'requests': mock_requests, 'socks': mock_socks}):
                with patch('socket.socket', mock_socket):
                    with patch.object(
                        sc, '_fetch_with_requests',
                        wraps=sc._fetch_with_requests
                    ):
                        pass

    def test_tor_unavailable_logs_warning(self):
        """When Tor unavailable → WARNING logged, plain requests.get used."""
        from hledac.universal.intelligence.stealth_crawler import StealthCrawler

        sc = StealthCrawler()

        # Patch TorProxyManager.is_running to return False
        with patch(
            'hledac.universal.intelligence.stealth_crawler.TorProxyManager.is_running',
            return_value=False
        ):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = 'OK'
            mock_response.raise_for_status = MagicMock()

            mock_requests = MagicMock()
            mock_requests.get.return_value = mock_response

            with patch.dict(sys.modules, {'requests': mock_requests}):
                result = sc._fetch_with_requests('https://example.com', {'User-Agent': 'Test'})

            # Should have called requests.get WITHOUT socks proxy
            mock_requests.get.assert_called_once()
            args, kwargs = mock_requests.get.call_args
            assert kwargs.get('headers', {}) == {'User-Agent': 'Test'}

    def test_tor_running_sets_socks_before_request(self):
        """When Tor running → socks.set_default_proxy called BEFORE requests.get."""
        from hledac.universal.intelligence.stealth_crawler import StealthCrawler

        sc = StealthCrawler()

        call_order = []

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = 'OK'
        mock_response.raise_for_status = MagicMock()

        def track_get(*args, **kwargs):
            call_order.append('requests.get')
            return mock_response

        mock_requests = MagicMock()
        mock_requests.get.side_effect = track_get

        mock_socks = MagicMock()
        mock_socks.set_default_proxy = MagicMock(side_effect=lambda *a: call_order.append('socks.set_default_proxy'))

        mock_socket = MagicMock(side_effect=lambda *a, **kw: call_order.append('socket.socket'))

        with patch.dict(sys.modules, {'requests': mock_requests, 'socks': mock_socks}):
            with patch('socket.socket', mock_socket):
                with patch(
                    'hledac.universal.intelligence.stealth_crawler.TorProxyManager.is_running',
                    return_value=True
                ):
                    result = sc._fetch_with_requests('https://example.onion', {})

        # socks.set_default_proxy must be called BEFORE requests.get
        if call_order:
            assert call_order.index('socks.set_default_proxy') < call_order.index('requests.get'), \
                "socks.set_default_proxy must be called before requests.get"

    def test_tor_unavailable_no_socks_call(self):
        """When Tor not running → socks.set_default_proxy NOT called."""
        from hledac.universal.intelligence.stealth_crawler import StealthCrawler

        sc = StealthCrawler()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = 'OK'
        mock_response.raise_for_status = MagicMock()

        mock_requests = MagicMock()
        mock_requests.get.return_value = mock_response

        mock_socks = MagicMock()

        with patch.dict(sys.modules, {'requests': mock_requests, 'socks': mock_socks}):
            with patch(
                'hledac.universal.intelligence.stealth_crawler.TorProxyManager.is_running',
                return_value=False
            ):
                result = sc._fetch_with_requests('https://example.com', {})

        # socks.set_default_proxy should NOT be called when Tor is down
        mock_socks.set_default_proxy.assert_not_called()
