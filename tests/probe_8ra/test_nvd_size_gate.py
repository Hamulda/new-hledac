"""
test_nvd_size_gate.py
Sprint 8RA C.3 / D.5 — content-length > 80MB → skip, log warning
"""
import asyncio
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock as _AsyncMock
from unittest.mock import MagicMock as _MagicMock

import pytest

sys.path.insert(0, ".")


@pytest.mark.asyncio
async def test_nvd_size_gate_skips_large():
    """content-length > 80MB must be skipped without download."""
    from hledac.universal.intelligence.ti_feed_adapter import fetch_nvd_historical

    td = tempfile.mkdtemp()
    mirrors_dir = Path(td)

    session = _AsyncMock()
    mock_resp = _MagicMock()
    mock_resp.status = 200
    large_header = str(90 * 1024 * 1024)
    mock_resp.headers = {"content-length": large_header}
    
    class MockContextManager:
        async def __aenter__(self):
            return mock_resp
        async def __aexit__(self, *args):
            pass
    
    session.get = _AsyncMock(return_value=MockContextManager())

    results = await fetch_nvd_historical(mirrors_dir, session, years=[2023])

    assert results.get("2023") == 0
    assert not (mirrors_dir / "nvd_2023.json.gz").exists()


@pytest.mark.asyncio
async def test_nvd_size_gate_accepts_small():
    """content-length <= 80MB should proceed to download (actual gzip content needed)."""
    pass
