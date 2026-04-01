"""
test_upsert_canonical_semantics.py
Sprint 8TD — Lock the CREATED-ONLY semantics of upsert_ioc_batch.

CANONICAL SEMANTICS (Sprint 8TD):
  upsert_ioc_batch(iocs) -> list of NEWLY CREATED node IDs only.
  - First call with N new IOCs: returns N IDs
  - Second call with same IOCs: returns [] (all already exist)
  - Idempotency: total node count never exceeds N unique IOCs
  - Use graph_stats() if you need total node count (not this method)

flush_buffers() uses this to report 'ioc_flushed' = newly created count.
"""
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")


async def test_upsert_returns_created_only():
    """First call returns created IDs; second call returns []."""
    from hledac.universal.knowledge.ioc_graph import IOCGraph

    with tempfile.TemporaryDirectory() as d:
        g = IOCGraph(db_path=Path(d) / "sem")
        await g.initialize()

        iocs = [(f"cve", f"CVE-2026-{i}", 1.0) for i in range(20)]

        # First call — should return 20 created IDs
        ids1 = await g.upsert_ioc_batch(iocs)
        assert len(ids1) == 20, f"First call: expected 20, got {len(ids1)}"

        # Second call — should return [] (all already exist)
        ids2 = await g.upsert_ioc_batch(iocs)
        assert len(ids2) == 0, f"Second call: expected 0, got {len(ids2)}"

        # Total node count must be exactly 20 (idempotency)
        stats = await g.graph_stats()
        assert stats["nodes"] == 20, f"Expected 20 nodes total, got {stats['nodes']}"

        print("PASS: upsert_ioc_batch CREATED-ONLY semantics locked")
        await g.close()


async def test_flush_buffers_reports_created_count():
    """flush_buffers ioc_flushed == newly created, not total buffered."""
    from hledac.universal.knowledge.ioc_graph import IOCGraph

    with tempfile.TemporaryDirectory() as d:
        g = IOCGraph(db_path=Path(d) / "flush_sem")
        await g.initialize()

        # Buffer 15 IOCs
        for i in range(15):
            await g.buffer_ioc("cve", f"CVE-FLUSH-{i}", 1.0)

        # First flush — all 15 are new
        result1 = await g.flush_buffers()
        assert result1["ioc_flushed"] == 15, f"First flush: expected 15, got {result1['ioc_flushed']}"

        # Second flush — buffer empty, nothing new
        result2 = await g.flush_buffers()
        assert result2["ioc_flushed"] == 0, f"Second flush: expected 0, got {result2['ioc_flushed']}"

        # Total nodes still 15 (not 30)
        stats = await g.graph_stats()
        assert stats["nodes"] == 15, f"Expected 15 nodes total, got {stats['nodes']}"

        print("PASS: flush_buffers reports CREATED count correctly")
        await g.close()


async def test_mixed_new_and_existing():
    """Partial overlap: 10 new + 10 existing = 10 created returned."""
    from hledac.universal.knowledge.ioc_graph import IOCGraph

    with tempfile.TemporaryDirectory() as d:
        g = IOCGraph(db_path=Path(d) / "mixed")
        await g.initialize()

        # First batch: 10 unique
        batch1 = [(f"cve", f"CVE-MIXED-{i}", 1.0) for i in range(10)]
        ids1 = await g.upsert_ioc_batch(batch1)
        assert len(ids1) == 10

        # Second batch: 5 old + 5 new
        batch2 = [(f"cve", f"CVE-MIXED-{i}", 1.0) for i in range(5)]  # existing
        batch2 += [(f"cve", f"CVE-MIXED-{i}", 1.0) for i in range(10, 15)]  # new
        ids2 = await g.upsert_ioc_batch(batch2)
        assert len(ids2) == 5, f"Second batch: expected 5 created, got {len(ids2)}"

        stats = await g.graph_stats()
        assert stats["nodes"] == 15, f"Expected 15 nodes total, got {stats['nodes']}"

        print("PASS: Mixed new/existing — CREATED-only semantics holds")
        await g.close()


if __name__ == "__main__":
    asyncio.run(test_upsert_returns_created_only())
    asyncio.run(test_flush_buffers_reports_created_count())
    asyncio.run(test_mixed_new_and_existing())
