"""
Sprint 8PA — D.2: TransportResolver onion routing
"""
import pytest
from hledac.universal.transport.transport_resolver import (
    TransportResolver, SourceTransportMap, Transport
)


class TestTransportResolverOnionRouting:
    """D.2: .onion → TOR, .i2p → I2P, clearnet → DIRECT."""

    def test_onion_url_resolves_to_tor(self):
        r = TransportResolver()
        assert r.resolve_url('https://example.onion/') == Transport.TOR
        assert r.resolve_url('http://sub.domain.onion:8080/path') == Transport.TOR
        assert r.resolve_url('https://3g2upl4pq6kufc4m.onion/') == Transport.TOR

    def test_i2p_url_resolves_to_i2p(self):
        r = TransportResolver()
        assert r.resolve_url('https://example.i2p/') == Transport.I2P
        assert r.resolve_url('http://proxy.i2p/test') == Transport.I2P

    def test_clearnet_url_resolves_to_direct(self):
        r = TransportResolver()
        assert r.resolve_url('https://example.com/') == Transport.DIRECT
        assert r.resolve_url('http://example.org/path?q=1') == Transport.DIRECT
        assert r.resolve_url('https://api.example.net/v1/') == Transport.DIRECT

    def test_onion_with_port_resolves_to_tor(self):
        r = TransportResolver()
        assert r.resolve_url('https://example.onion:8443/') == Transport.TOR
        assert r.resolve_url('http://onion镜子.onion:80/path') == Transport.TOR

    def test_resolve_url_fast_sync(self):
        """resolve_url() is a fast synchronous dict lookup."""
        import time
        r = TransportResolver()
        t0 = time.monotonic()
        for _ in range(1000):
            r.resolve_url('https://example.onion/')
            r.resolve_url('https://example.com/')
        elapsed_ms = (time.monotonic() - t0) * 1000
        assert elapsed_ms < 50, f"resolve_url 1000x took {elapsed_ms:.2f}ms, expected <50ms"

    def test_is_tor_mandatory_onion(self):
        r = TransportResolver()
        assert r.is_tor_mandatory('https://example.onion/') is True
        assert r.is_tor_mandatory('http://sub.domain.onion:8080/') is True

    def test_is_tor_mandatory_clearnet(self):
        r = TransportResolver()
        assert r.is_tor_mandatory('https://example.com/') is False
        assert r.is_tor_mandatory('https://example.i2p/') is False

    def test_source_transport_map_onion_mandatory(self):
        """B6: .onion is mandatory Tor — cannot be overridden."""
        assert SourceTransportMap.get('.onion') == Transport.TOR
        assert SourceTransportMap.is_mandatory_tor('.onion') is True
        assert SourceTransportMap.is_mandatory_tor('.com') is False

    def test_source_transport_map_i2p_not_mandatory(self):
        """I2P is not mandatory Tor (it has its own transport)."""
        assert SourceTransportMap.get('.i2p') == Transport.I2P
        assert SourceTransportMap.is_mandatory_tor('.i2p') is False
