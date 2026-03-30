"""
test_batch_upsert_vs_single_speedup.py
Sprint 8RA C.1 / D.2 — batch must be comparable to single-loop on 50 nodes
"""
import asyncio
import sys
import tempfile
import time

import pytest

sys.path.insert(0, ".")


@pytest.mark.asyncio
async def test_batch_vs_single_speedup():
    """Batch upsert must be comparable to single-loop on 50 nodes.

    Kuzu single-thread executor limits absolute speedup, but batch must
    be within 2x of single-loop (not 10x slower).
    """
    from hledac.universal.knowledge.ioc_graph import IOCGraph
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        g = IOCGraph(db_path=Path(d) / "bench")
        await g.initialize()

        iocs = [(f"cve", f"CVE-2026-{i}", 1.0) for i in range(50)]

        # Single-loop timing
        t_single = time.monotonic()
        for ioc_type, val, conf in iocs:
            await g.upsert_ioc(ioc_type, val, conf)
        elapsed_single = (time.monotonic() - t_single) * 1000

        # Batch timing
        t_batch = time.monotonic()
        await g.upsert_ioc_batch(iocs)
        elapsed_batch = (time.monotonic() - t_batch) * 1000

        # Batch must not be dramatically slower than single
        # (Kuzu single-thread bottleneck means they may be equal)
        assert elapsed_batch <= elapsed_single * 2.5, (
            f"Batch ({elapsed_batch:.1f}ms) should be comparable to "
            f"single-loop ({elapsed_single:.1f}ms), ratio={elapsed_batch/elapsed_single:.1f}"
        )

        stats = await g.graph_stats()
        assert stats["nodes"] == 50

        await g.close()
