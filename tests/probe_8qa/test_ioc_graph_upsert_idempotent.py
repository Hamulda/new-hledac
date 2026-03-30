"""Sprint 8QA: IOCGraph upsert idempotency tests."""

import asyncio
import tempfile

import pytest

from hledac.universal.knowledge.ioc_graph import IOCGraph


@pytest.mark.asyncio
async def test_ioc_graph_upsert_idempotent():
    """upsert_ioc twice -> one node, no exception."""
    with tempfile.TemporaryDirectory() as d:
        g = IOCGraph(db_path=f"{d}/graph")
        await g.initialize()

        id1 = await g.upsert_ioc("cve", "CVE-2026-1234")
        id2 = await g.upsert_ioc("cve", "CVE-2026-1234")

        assert id1 == id2
        stats = await g.graph_stats()
        assert stats["nodes"] == 1
        await g.close()
