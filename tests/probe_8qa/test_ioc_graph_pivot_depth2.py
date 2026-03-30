"""Sprint 8QA: IOCGraph pivot depth 2 test."""

import asyncio
import tempfile

import pytest

from hledac.universal.knowledge.ioc_graph import IOCGraph


@pytest.mark.asyncio
async def test_ioc_graph_pivot_depth2():
    """Chain CVE->malware->IP: pivot from CVE depth=2 returns IP node."""
    with tempfile.TemporaryDirectory() as d:
        g = IOCGraph(db_path=f"{d}/graph")
        await g.initialize()

        id_cve = await g.upsert_ioc("cve", "CVE-2026-1234")
        id_mal = await g.upsert_ioc("malware", "cobalt_strike")
        id_ip = await g.upsert_ioc("ip", "1.2.3.4")

        await g.record_observation(id_cve, id_mal, "f1", 1000.0, "test")
        await g.record_observation(id_mal, id_ip, "f2", 1001.0, "test")

        # Pivot from CVE, depth=2 -> should reach IP through malware
        results = await g.pivot("CVE-2026-1234", "cve", depth=2)
        values = {r["value"] for r in results}
        assert "1.2.3.4" in values, f"Expected IP in results, got: {values}"
        await g.close()
