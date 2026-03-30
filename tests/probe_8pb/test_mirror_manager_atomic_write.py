"""
Sprint 8PB: test_mirror_manager_atomic_write
D.2: Ověřit atomic write invariant - při selhaném downloadu je temp file vymazán
"""

import asyncio
import tempfile
from pathlib import Path


def test_mirror_manager_atomic_write():
    """
    Test invariant: if download fails mid-stream, temp file is cleaned up
    and dest file does not exist (not corrupted).

    This tests the fail-open cleanup path in download_mirror().
    """
    from hledac.universal.intelligence.ti_feed_adapter import MirrorManager

    with tempfile.TemporaryDirectory() as tmpdir:
        mirrors_root = Path(tmpdir)
        mm = MirrorManager(mirrors_root=mirrors_root)

        # Override _get_session to return a session that fails on request
        class FailingSession:
            """Session that fails when request is called."""
            async def request(self, method, url, **kwargs):
                # This simulates a network error during streaming
                raise ConnectionError("simulated network failure")

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        # Replace session via a simple assignment
        mm._session = FailingSession()

        dest_path = mirrors_root / "cisa_kev.json"
        tmp_path = dest_path.with_suffix(".tmp")

        # Run download - should return None (fail-open)
        result = asyncio.run(mm.download_mirror("cisa_kev"))

        # Should return None on failure
        assert result is None, f"Expected None, got {result}"

        # Dest should NOT exist (not corrupted)
        assert not dest_path.exists(), f"Dest exists: {dest_path}"
        # Temp should be cleaned up (not exist)
        assert not tmp_path.exists(), f"Temp still exists: {tmp_path}"


if __name__ == "__main__":
    test_mirror_manager_atomic_write()
