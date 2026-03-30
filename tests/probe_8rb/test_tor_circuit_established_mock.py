"""Sprint 8RB — Tor circuit established: mock is_circuit_established → True."""
import asyncio
from unittest.mock import patch, AsyncMock


async def test_tor_circuit_established_mock():
    """Mock is_circuit_established() → returns True directly (socket.bind issue with module-level import)."""
    from hledac.universal.transport.tor_transport import TorTransport

    t = TorTransport()

    # Patch the method directly — socket module is bound at import time
    async def fake_circuit():
        return True

    t.is_circuit_established = fake_circuit
    result = await t.is_running()
    assert result is True, f"Expected True, got {result}"


if __name__ == "__main__":
    asyncio.run(test_tor_circuit_established_mock())
    print("test_tor_circuit_established_mock: PASS")
