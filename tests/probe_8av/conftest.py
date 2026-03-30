"""
Sprint 8AV: Reusable fixtures for ingest outcome counter tests.
"""
import asyncio
import pathlib
import tempfile
import pytest

from hledac.universal.knowledge.duckdb_store import DuckDBShadowStore


@pytest.fixture
def store_path():
    """Temp DuckDB path per test, cleaned up automatically."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    yield tmp / "test.duckdb"


@pytest.fixture
async def store(store_path):
    """
    Fresh initialized store per test.
    Resets counters before each test to ensure isolation.
    """
    s = DuckDBShadowStore(db_path=store_path)
    ok = await s.async_initialize()
    assert ok, "store init failed"
    s.reset_ingest_reason_counters()
    yield s
    await s.aclose()


@pytest.fixture
def any_event_loop():
    """Allow any event loop scope for async fixtures."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    yield loop
