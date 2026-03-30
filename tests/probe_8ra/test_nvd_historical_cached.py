"""
test_nvd_historical_cached.py
Sprint 8RA C.3 / D.10 — if nvd_2023.json.gz exists, refresh_if_stale skips it
"""
import asyncio
import sys
import tempfile
import gzip
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, ".")


@pytest.mark.asyncio
async def test_nvd_historical_skips_cached():
    """Existing nvd_{year}.json.gz must not be re-downloaded."""
    from hledac.universal.intelligence.ti_feed_adapter import fetch_nvd_historical

    with tempfile.TemporaryDirectory() as td:
        mirrors_dir = Path(td)

        # Pre-create cached mirror
        fake_gzip = gzip.compress(json.dumps({"CVE_Items": []}).encode())
        cached_path = mirrors_dir / "nvd_2023.json.gz"
        cached_path.write_bytes(fake_gzip)

        session = AsyncMock()
        # If called, would fail
        session.get = AsyncMock(side_effect=RuntimeError("Should not be called"))

        results = await fetch_nvd_historical(
            mirrors_dir, session, years=[2023]
        )

        # Cached → -1
        assert results.get("2023") == -1
        # No HTTP call made
        session.get.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_if_stale_skips_fresh_nvd():
    """refresh_if_stale must not re-download fresh NVD modified feed."""
    from hledac.universal.intelligence.ti_feed_adapter import refresh_if_stale

    with tempfile.TemporaryDirectory() as td:
        mirrors_dir = Path(td)

        # Pre-create fresh modified feed (1h old < 12h)
        fresh_path = mirrors_dir / "nvd_modified.json.gz"
        fresh_path.write_bytes(gzip.compress(b"{}"))

        session = AsyncMock()
        get_called = False

        class MockContextManager:
            async def __aenter__(self):
                nonlocal get_called
                get_called = True
                raise RuntimeError("Should not be called")
            async def __aexit__(self, *args):
                pass

        session.get = AsyncMock(return_value=MockContextManager())

        # Should not raise, should not call get
        await refresh_if_stale(mirrors_dir, session)

        assert not get_called, "HTTP GET was called for fresh mirror"
