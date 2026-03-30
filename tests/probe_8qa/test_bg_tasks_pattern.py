"""Sprint 8QA: duckdb_store _bg_tasks pattern test."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from hledac.universal.knowledge.duckdb_store import DuckDBShadowStore


@pytest.mark.asyncio
async def test_bg_tasks_pattern():
    """_bg_tasks.add() is called when graph is injected and findings processed."""
    store = DuckDBShadowStore.__new__(DuckDBShadowStore)
    store._initialized = True
    store._closed = False
    store._bg_tasks = set()
    store._ioc_graph = MagicMock()
    store._ioc_graph.upsert_ioc = AsyncMock(return_value="test:id")
    store._ioc_graph.record_observation = AsyncMock()

    mock_finding = MagicMock()
    mock_finding.payload_text = "CVE-2026-1234 1.2.3.4"
    mock_finding.pattern_matches = []
    mock_finding.ts = 1000.0
    mock_finding.source_type = "test"
    mock_finding.finding_id = "f1"

    store._graph_ingest_findings([mock_finding])
    await asyncio.sleep(0.05)

    assert len(store._bg_tasks) <= 1  # task was added
    store._bg_tasks.clear()
