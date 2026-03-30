"""D.7: semantic_pivot on empty table — returns empty list, no exception."""
import asyncio
import tempfile
from pathlib import Path

import pytest

from hledac.universal.knowledge.semantic_store import SemanticStore


@pytest.mark.asyncio
async def test_semantic_pivot_empty_table():
    """Empty LanceDB table → semantic_pivot returns [] (not exception)."""
    with tempfile.TemporaryDirectory() as d:
        store = SemanticStore(db_path=Path(d) / "lancedb")
        await store.initialize()
        # Never flush any data

        results = await store.semantic_pivot("test query", top_k=5)

        assert results == []
        assert isinstance(results, list)

        await store.close()
