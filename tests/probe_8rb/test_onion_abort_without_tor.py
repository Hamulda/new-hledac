"""Sprint 8RB — Onion abort without Tor: is_running=False → TorUnavailableError."""
import pytest
from unittest.mock import patch


def test_onion_abort_without_tor():
    """Mock is_running()=False + .onion URL → _fetch_with_requests raises TorUnavailableError."""
    from hledac.universal.intelligence.stealth_crawler import StealthCrawler
    from hledac.universal.transport.tor_transport import TorUnavailableError

    sc = StealthCrawler(use_header_spoofer=False)

    with patch.object(sc, "_check_dependencies", lambda: None):
        with patch("hledac.universal.intelligence.stealth_crawler.TorProxyManager.is_running", return_value=False):
            with pytest.raises(TorUnavailableError):
                sc._fetch_with_requests(
                    "http://zqktlwiuavvvqqt4ybvgvi7tyo4hjl5xgfuvpdf6otjiycgwqbym2qad.onion/", {}
                )


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
