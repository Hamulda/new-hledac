"""Sprint 8TC B.1: rrf_rank_findings — empty sprint returns []"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_duckdb_store():
    """Vytvoří mock DuckDBShadowStore s async initialize."""
    with patch("hledac.universal.knowledge.duckdb_store.DuckDBShadowStore") as cls:
        instance = MagicMock()
        instance._initialized = True
        instance._closed = False
        instance._executor = MagicMock()
        instance._db_path = None
        instance._persistent_conn = MagicMock()
        cls.return_value = instance
        yield instance


@pytest.mark.asyncio
async def test_rrf_rank_empty_sprint():
    """rrf_rank_findings('nonexistent_sprint_xyz') → [] (no exception)"""
    from hledac.universal.knowledge.duckdb_store import DuckDBShadowStore

    store = DuckDBShadowStore.__new__(DuckDBShadowStore)
    store._initialized = False  # not initialized → early return
    store._closed = False

    result = await store.rrf_rank_findings("nonexistent_sprint_xyz")
    assert result == []
