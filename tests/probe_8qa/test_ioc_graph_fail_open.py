"""Sprint 8QA: IOCGraph fail-open test."""

import asyncio
import tempfile

import pytest

from hledac.universal.knowledge.ioc_graph import IOCGraph


@pytest.mark.asyncio
async def test_ioc_graph_fail_open():
    """Invalid db path: graph operations return gracefully without raising."""
    g = IOCGraph(db_path="/nonexistent/path/that/cant/be/created")
    await g.initialize()  # should not raise

    # Operations should return None/empty without raising
    result = await g.upsert_ioc("cve", "CVE-2026-1234")
    assert result is None

    stats = await g.graph_stats()
    assert stats["nodes"] == 0
    assert stats["edges"] == 0

    await g.close()
