import asyncio
from hledac.universal.transport.circuit_breaker import get_breaker, resilient_fetch


def test_nym_not_in_automatic_fallback():
    """Nym nesmí být v automatickém fallback chainu — pouze pro anonymity_required."""
    # Otevri CB pro clearnet i tor
    for prefix in ("", "tor:"):
        cb = get_breaker(f"{prefix}heavy-latency.onion")
        for _ in range(5):
            cb.record_failure()
    # Bez anonymity_required → vrátí None (ne Nym fetch)
    result = asyncio.run(resilient_fetch("http://heavy-latency.onion/test"))
    assert result is None
