"""Sprint 8RB — Tor live clearnet (LIVE — requires Tor daemon).

SKIPPED if Tor circuit not established.
"""
import asyncio
import sys


async def test_tor_live_clearnet():
    """Tor live: is_circuit_established() → connect to clearnet check.torproject.org."""
    from hledac.universal.transport.tor_transport import TorTransport

    t = TorTransport()
    circuit_ok = await t.is_circuit_established()

    if not circuit_ok:
        # Tor not running — skip with explanation
        import pytest
        pytest.skip("Tor circuit not established — start Tor daemon first: brew services start tor")

    # Tor is up — verify routing
    import aiohttp
    from aiohttp_socks import ProxyConnector

    connector = ProxyConnector.from_url("socks5://127.0.0.1:9050", rdns=True)
    async with aiohttp.ClientSession(connector=connector) as sess:
        async with sess.get(
            "http://check.torproject.org/api/ip",
            timeout=aiohttp.ClientTimeout(total=30),
        ) as r:
            data = await r.json()
            assert data.get("IsTor") is True, f"Not routing through Tor! Got: {data}"
            print(f"Tor live OK: exit IP = {data['IP']}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(test_tor_live_clearnet())
    print("test_tor_live_clearnet: PASS")
