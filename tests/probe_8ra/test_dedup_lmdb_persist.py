"""
test_dedup_lmdb_persist.py
Sprint 8RA C.4 / D.6 — mark_seen + flush + new instance → is_duplicate=True
"""
import asyncio
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, ".")


@pytest.mark.asyncio
async def test_dedup_lmdb_persist():
    """Dedup hash survives flush + new instance."""
    from hledac.universal.runtime.sprint_scheduler import SprintScheduler, SprintSchedulerConfig

    with tempfile.TemporaryDirectory() as td:
        # Patch _get_dedup_lmdb_path to use temp dir
        import hledac.universal.runtime.sprint_scheduler as ss

        original_fn = ss._get_dedup_lmdb_path

        def temp_dedup_path():
            return Path(td) / "test_dedup.lmdb"

        ss._get_dedup_lmdb_path = temp_dedup_path

        try:
            config = SprintSchedulerConfig(sprint_duration_s=60.0)
            scheduler1 = SprintScheduler(config)

            # Simulate boot
            await scheduler1._load_dedup()

            # Mark some entries
            scheduler1.mark_seen("web", "https://test.com", "Test Title")
            scheduler1.mark_seen("web", "https://example.com", "")

            # Flush
            await scheduler1._flush_dedup()
            await scheduler1._close_dedup()

            # New instance — loads from same LMDB
            scheduler2 = SprintScheduler(config)
            await scheduler2._load_dedup()

            assert scheduler2.is_duplicate("web", "https://test.com", "Test Title")
            assert scheduler2.is_duplicate("web", "https://example.com", "")
            assert not scheduler2.is_duplicate("web", "https://new.com", "")

            await scheduler2._close_dedup()

        finally:
            ss._get_dedup_lmdb_path = original_fn
