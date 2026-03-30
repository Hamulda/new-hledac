"""Sprint 8TC B.2: JARM fingerprint timeout safety"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio


@pytest.mark.asyncio
async def test_jarm_fingerprint_timeout_safe():
    """Mock asyncio.open_connection → TimeoutError → jarm_fingerprint → str (ne None, ne raise)"""
    from hledac.universal.transport.tor_transport import jarm_fingerprint

    async def mock_open_connection_raise(*args, **kwargs):
        raise asyncio.TimeoutError("connection timeout")

    with patch("asyncio.open_connection", side_effect=mock_open_connection_raise):
        result = await jarm_fingerprint("example.com", 443)
        # Mělo by vrátit string (MD5), ne None ani exception
        assert isinstance(result, str)
        assert len(result) == 32  # MD5 hex


@pytest.mark.asyncio
async def test_jarm_fingerprint_length():
    """Mock ssl → returns string of length 32 (MD5 hex)"""
    from hledac.universal.transport.tor_transport import jarm_fingerprint
    import ssl

    mock_ssl_socket = MagicMock()
    mock_ssl_socket.cipher.return_value = ("TLS_AES_256_GCM_SHA384", "TLSv1.3", 256)
    mock_ssl_socket.version.return_value = "TLSv1.3"

    mock_writer = MagicMock()
    mock_writer.get_extra_info.return_value = mock_ssl_socket
    mock_writer.close = MagicMock()
    mock_writer.wait_closed = AsyncMock()

    async def mock_open_connection(*args, **kwargs):
        reader = MagicMock()
        return reader, mock_writer

    with patch("asyncio.open_connection", side_effect=mock_open_connection):
        result = await jarm_fingerprint("example.com", 443)

    assert isinstance(result, str)
    assert len(result) == 32  # MD5 hash length
