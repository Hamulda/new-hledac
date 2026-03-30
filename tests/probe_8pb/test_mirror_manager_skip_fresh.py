"""
Sprint 8PB: test_mirror_manager_skip_fresh
D.1: Vytvořit temp mirror file s mtime = now → download_mirror() přeskočí download (mtime check)
"""

import asyncio
import tempfile
import time
from pathlib import Path

import pytest


def test_mirror_manager_skip_fresh():
    """Fresh mirror (mtime = now) should be skipped by download."""
    from hledac.universal.intelligence.ti_feed_adapter import MirrorManager, MIRRORS_ROOT

    # Create temp mirror
    with tempfile.TemporaryDirectory() as tmpdir:
        mirror_path = Path(tmpdir) / "cisa_kev.json"
        mirror_path.write_text('{"vulnerabilities":[]}')

        # Set mtime to now
        now = time.monotonic()
        import os
        os.utime(mirror_path, (now, now))

        mm = MirrorManager(mirrors_root=Path(tmpdir))

        # Sync check: is_fresh should return True for recent file
        assert mm._is_fresh(mirror_path) is True

        # Download should return path (skip download since fresh)
        result = asyncio.run(mm.download_mirror("cisa_kev"))
        assert result is not None
        assert result == mirror_path


if __name__ == "__main__":
    test_mirror_manager_skip_fresh()
