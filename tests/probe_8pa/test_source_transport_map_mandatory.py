"""
Sprint 8PA — D.5: SourceTransportMap mandatory Tor for .onion
"""
import pytest
from hledac.universal.transport.transport_resolver import (
    SourceTransportMap, Transport, TransportResolver
)


class TestSourceTransportMapMandatory:
    """D.5: .onion is mandatory Tor — cannot be overridden to DIRECT."""

    def test_onion_is_tor_mandatory(self):
        """SourceTransportMap[.onion] == Transport.TOR, always."""
        assert SourceTransportMap.get('.onion') == Transport.TOR

    def test_resolve_url_respects_mandatory_tor(self):
        """resolve_url() never returns DIRECT for .onion URLs."""
        r = TransportResolver()
        # Use correct .onion domains (not onion-like subdomains like mirror.onion.hiddenservice.com)
        onion_urls = [
            'https://example.onion/',
            'http://sub.domain.onion:8080/path',
            'https://3g2upl4pq6kufc4m.onion/',
            'https://onionmirror.onion/wiki',
        ]
        for url in onion_urls:
            result = r.resolve_url(url)
            assert result == Transport.TOR, \
                f"{url} must resolve to TOR, got {result}"
            assert result != Transport.DIRECT, \
                f"{url} must NEVER resolve to DIRECT (mandatory Tor)"

    def test_is_tor_mandatory_true_for_onion(self):
        """is_tor_mandatory() returns True for all onion domains."""
        r = TransportResolver()
        assert r.is_tor_mandatory('https://example.onion/') is True
        assert r.is_tor_mandatory('http://sub.domain.onion/') is True
        assert r.is_tor_mandatory('https://3g2upl4pq6kufc4m.onion/') is True

    def test_is_tor_mandatory_false_for_clearnet(self):
        """is_tor_mandatory() returns False for clearnet domains."""
        r = TransportResolver()
        assert r.is_tor_mandatory('https://example.com/') is False
        assert r.is_tor_mandatory('https://example.i2p/') is False
        # This is NOT a .onion domain — it's a subdomain of onion.hiddenservice.com
        assert r.is_tor_mandatory('https://mirror.hiddenservice.com/') is False

    def test_i2p_not_mandatoryT_or(self):
        """I2P is not mandatory Tor — it has its own transport."""
        r = TransportResolver()
        assert r.resolve_url('https://example.i2p/') == Transport.I2P
        assert r.is_tor_mandatory('https://example.i2p/') is False

    def test_mandatory_tor_cannot_be_overridden(self):
        """SourceTransportMap always maps .onion to Transport.TOR."""
        # Direct check: onion suffix always returns TOR from SourceTransportMap
        assert SourceTransportMap.get('.onion') == Transport.TOR
        # is_mandatory_tor always returns True for .onion
        assert SourceTransportMap.is_mandatory_tor('.onion') is True
