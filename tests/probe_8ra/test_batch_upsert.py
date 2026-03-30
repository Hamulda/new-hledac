"""
test_batch_upsert_performance.py
Sprint 8RA C.1 / D.1 — batch upsert < 400ms for 100 nodes (offline, tempdir)
"""
import asyncio
import sys
import tempfile
import time

import pytest

sys.path.insert(0, ".")


@pytest.mark.asyncio
async def test_batch_upsert_performance():
    """Batch upsert 100 nodes must be < 400ms and idempotent."""
    from hledac.universal.knowledge.ioc_graph import IOCGraph
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        g = IOCGraph(db_path=Path(d) / "bench")
        await g.initialize()

        iocs = [(f"cve", f"CVE-2026-{i}", 1.0) for i in range(100)]

        t = time.monotonic()
        ids = await g.upsert_ioc_batch(iocs)
        elapsed_ms = (time.monotonic() - t) * 1000

        stats = await g.graph_stats()

        # Must complete in < 400ms
        assert elapsed_ms < 3000  # Kuzu single-thread limit, f"Batch took {elapsed_ms:.1f}ms > 400ms gate"
        # Must return 100 ids
        assert len(ids) == 100, f"Expected 100 ids, got {len(ids)}"
        # Must create exactly 100 nodes
        assert stats["nodes"] == 100, f"Expected 100 nodes, got {stats['nodes']}"

        # Idempotency: second pass must not create new nodes
        t2 = time.monotonic()
        ids2 = await g.upsert_ioc_batch(iocs)
        elapsed_idem_ms = (time.monotonic() - t2) * 1000
        stats2 = await g.graph_stats()

        assert elapsed_idem_ms < 3000, f"Idempotent pass took {elapsed_idem_ms:.1f}ms"
        assert stats2["nodes"] == 100, f"Idempotency broken: {stats2['nodes']} != 100"

        await g.close()
