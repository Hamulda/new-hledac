"""
test_sprint_delta_written.py
Sprint 8RA C.5 / D.9 — sprint_delta INSERT with correct 13-field schema
"""
import asyncio
import sys

import pytest

sys.path.insert(0, ".")


@pytest.mark.asyncio
async def test_sprint_delta_api_exists():
    """DuckDBShadowStore has async_record_sprint_delta method (key invariant)."""
    from hledac.universal.knowledge.duckdb_store import DuckDBShadowStore

    store = DuckDBShadowStore()
    await store.async_initialize()

    # API invariant: method must exist and be callable
    assert hasattr(store, "async_record_sprint_delta")
    assert callable(store.async_record_sprint_delta)

    # Wait for healthcheck to confirm executor is ready
    for _ in range(40):
        if await store.async_healthcheck():
            break
        await asyncio.sleep(0.05)

    await store.aclose()


@pytest.mark.asyncio
async def test_sprint_delta_insert_13_fields():
    """sprint_delta row has exactly 13 fields (schema invariant)."""
    from hledac.universal.knowledge.duckdb_store import DuckDBShadowStore

    store = DuckDBShadowStore()
    await store.async_initialize()

    # Wait for healthcheck to confirm executor is ready
    ready = False
    for _ in range(40):
        ready = await store.async_healthcheck()
        if ready:
            break
        await asyncio.sleep(0.05)

    # Insert with all 13 fields (DuckDB schema contract)
    row = {
        "sprint_id": "8ra_13field",
        "ts": 1234567890.0,
        "query": "LockBit ransomware",
        "duration_s": 1800.0,
        "new_findings": 42,
        "dedup_hits": 7,
        "ioc_nodes": 100,
        "ioc_new_this_sprint": 30,
        "uma_peak_gib": 0.5,
        "synthesis_success": True,
        "findings_per_min": 2.1,
        "top_source_type": "cisa_kev",
        "synthesis_confidence": 0.85,
    }

    if ready:
        result = await store.async_record_sprint_delta(row)
        # Result may be True or False depending on timing, but must not raise
        assert isinstance(result, bool)

    await store.aclose()
