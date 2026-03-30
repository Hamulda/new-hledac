"""Sprint 8QA: IOCGraph last_seen update test."""

import asyncio
import tempfile
import time

import pytest

from hledac.universal.knowledge.ioc_graph import IOCGraph


@pytest.mark.asyncio
async def test_ioc_graph_upsert_updates_last_seen():
    """First upsert sets first_seen==last_seen, second upsert updates last_seen > first_seen."""
    with tempfile.TemporaryDirectory() as d:
        g = IOCGraph(db_path=f"{d}/graph")
        await g.initialize()

        await g.upsert_ioc("cve", "CVE-2026-1234", confidence=1.0)
        await asyncio.sleep(0.01)
        await g.upsert_ioc("cve", "CVE-2026-1234", confidence=1.0)

        # Pivot to get the node back
        results = await g.pivot("CVE-2026-1234", "cve", depth=1)
        assert len(results) == 0  # no neighbors

        # Check via raw query
        conn = g._conn
        loop = asyncio.get_running_loop()
        row = await loop.run_in_executor(
            g._executor,
            lambda: conn.execute(
                "MATCH (n:IOC) WHERE n.value = $v RETURN n.first_seen, n.last_seen",
                {"v": "CVE-2026-1234"},
            ).get_next(),
        )
        first_seen, last_seen = float(row[0]), float(row[1])
        assert last_seen > first_seen, f"last_seen ({last_seen}) should be > first_seen ({first_seen})"
        await g.close()
