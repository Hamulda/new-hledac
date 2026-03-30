"""
test_dedup_cross_sprint.py
Sprint 8RA C.4 / D.7 — dedup persists across sprint instances
"""
import asyncio
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, ".")


@pytest.mark.asyncio
async def test_dedup_cross_sprint():
    """is_duplicate returns True for entry seen in previous sprint instance."""
    from hledac.universal.runtime.sprint_scheduler import SprintScheduler, SprintSchedulerConfig

    with tempfile.TemporaryDirectory() as td:
        import hledac.universal.runtime.sprint_scheduler as ss

        original_fn = ss._get_dedup_lmdb_path

        def temp_dedup_path():
            return Path(td) / "cross_sprint.lmdb"

        ss._get_dedup_lmdb_path = temp_dedup_path

        try:
            config = SprintSchedulerConfig(sprint_duration_s=60.0)

            # Sprint 1
            s1 = SprintScheduler(config)
            await s1._load_dedup()
            s1.mark_seen("web", "https://shared.com", "Shared")
            await s1._close_dedup()

            # Sprint 2 (new instance, same LMDB)
            s2 = SprintScheduler(config)
            await s2._load_dedup()

            assert s2.is_duplicate("web", "https://shared.com", "Shared")
            assert not s2.is_duplicate("web", "https://only-s2.com", "")

            await s2._close_dedup()

        finally:
            ss._get_dedup_lmdb_path = original_fn
