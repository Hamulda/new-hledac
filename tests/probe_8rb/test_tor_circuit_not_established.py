"""Sprint 8RB — Tor circuit NOT established: SOCKS port timeout → False."""
import asyncio
from unittest.mock import patch


async def test_tor_circuit_not_established():
    """Mock socket.connect timeout (OSError) → is_circuit_established() returns False."""
    from hledac.universal.transport.tor_transport import TorTransport

    def fake_sock_fail(*_args, **_kwargs):
        raise OSError("Connection refused")  # noqa: OSError is builtin

    with patch("socket.socket", fake_sock_fail):
        t = TorTransport()
        result = await t.is_circuit_established()
        assert result is False, f"Expected False, got {result}"


if __name__ == "__main__":
    asyncio.run(test_tor_circuit_not_established())
    print("test_tor_circuit_not_established: PASS")
