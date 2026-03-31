import asyncio
from hledac.universal.transport.circuit_breaker import get_breaker, get_transport_for_domain


def test_transport_resolver_fallback_chain():
    cb = get_breaker("test-fallback.onion")
    for _ in range(5):
        cb.record_failure()
    transport = asyncio.run(get_transport_for_domain("test-fallback.onion"))
    assert transport in ("tor", "nym")
