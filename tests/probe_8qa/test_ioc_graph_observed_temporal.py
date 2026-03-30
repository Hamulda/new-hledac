"""Sprint 8QA: IOCGraph OBSERVED edge temporal test."""

import asyncio
import tempfile

import pytest

from hledac.universal.knowledge.ioc_graph import IOCGraph


@pytest.mark.asyncio
async def test_ioc_graph_observed_temporal():
    """record_observation twice with different ts: last_seen > first_seen on edge."""
    with tempfile.TemporaryDirectory() as d:
        g = IOCGraph(db_path=f"{d}/graph")
        await g.initialize()

        id_a = await g.upsert_ioc("cve", "CVE-2026-A")
        id_b = await g.upsert_ioc("ip", "8.8.8.8")

        await g.record_observation(id_a, id_b, "finding1", 1000.0, "test")
        await asyncio.sleep(0.01)
        await g.record_observation(id_a, id_b, "finding1", 2000.0, "test")

        # Query edge properties directly
        conn = g._conn
        loop = asyncio.get_running_loop()
        row = await loop.run_in_executor(
            g._executor,
            lambda: conn.execute(
                "MATCH (a:IOC)-[r:OBSERVED]->(b:IOC) "
                "WHERE a.id = $ida AND b.id = $idb "
                "RETURN r.first_seen, r.last_seen",
                {"ida": id_a, "idb": id_b},
            ).get_next(),
        )
        first_seen = float(row[0])
        last_seen = float(row[1])
        assert last_seen > first_seen, f"last_seen ({last_seen}) should be > first_seen ({first_seen})"
        await g.close()
