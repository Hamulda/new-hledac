"""Sprint 8RB — Ahmia discovery: mock HTTP response with .onion links."""
import asyncio
from unittest.mock import MagicMock
from hledac.universal.intelligence.onion_seed_manager import OnionSeedManager


class AsyncCtxManager:
    """Minimal async context manager wrapping a mock response."""
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *args):
        return None


class MockGetResult:
    """aiohttp ClientSession.get() return value — async context manager."""
    def __init__(self, html):
        self._html = html
        self._resp = MagicMock()
        self._resp.status = 200

        async def _text():
            return self._html
        self._resp.text = _text
        self._ctx = AsyncCtxManager(self._resp)

    def __call__(self, *args, **kwargs):
        return self._ctx


async def test_ahmia_discovery_mock():
    """Mock HTTP response with .onion links → discover_from_ahmia() returns list of onion URLs."""
    mgr = OnionSeedManager()

    # V3 onion addresses are exactly 56 base32 chars before .onion
    # base32 charset for V3: a-z and 2-7 (no 0,1,8,9,h)
    v3_onion = "abcdef234567abcdef234567abcdef234567abcdef234567abcdef23"
    assert len(v3_onion) == 56, f"V3 onion must be 56 chars, got {len(v3_onion)}"
    v2_onion = "def567234567abcd"  # 16 chars, all valid base32 (no 0,1,8,9)
    assert len(v2_onion) == 16, f"V2 onion must be 16 chars, got {len(v2_onion)}"

    mock_html = (
        f'<html><body>'
        f'<a href="http://{v3_onion}.onion/">Link 1</a>'
        f'<a href="http://{v2_onion}.onion/">Link 2</a>'
        f'</body></html>'
    )

    mock_get = MockGetResult(mock_html)
    mock_session = MagicMock()
    mock_session.get = mock_get

    async def _close():
        return None
    mock_session.close = _close

    # Pass session directly — bypasses aiohttp import inside discover_from_ahmia
    discovered = await mgr.discover_from_ahmia("ransomware", session=mock_session)

    assert len(discovered) == 2, f"Expected 2 discovered seeds, got {len(discovered)}: {discovered}"
    assert any(v3_onion in d for d in discovered), f"V3 onion not found in {discovered}"
    assert any(v2_onion in d for d in discovered), f"V2 onion not found in {discovered}"


if __name__ == "__main__":
    asyncio.run(test_ahmia_discovery_mock())
    print("test_ahmia_discovery_mock: PASS")
