"""Sprint 8QA: IOCGraph schema initialization tests."""

import asyncio
import tempfile

import pytest

from hledac.universal.knowledge.ioc_graph import IOCGraph


@pytest.mark.asyncio
async def test_ioc_graph_schema_init():
    """IOCGraph.initialize() creates schema, second call is no-op."""
    with tempfile.TemporaryDirectory() as d:
        g = IOCGraph(db_path=f"{d}/graph")
        await g.initialize()
        await g.initialize()  # idempotent — no exception
        stats = await g.graph_stats()
        assert stats["nodes"] == 0
        assert stats["edges"] == 0
        await g.close()
