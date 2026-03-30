"""
D.10: flush_buffers() dvakrát → druhý call vrací 0 (prázdný buffer).
"""
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")


async def test_ioc_buffer_idempotent_flush():
    from hledac.universal.knowledge.ioc_graph import IOCGraph

    with tempfile.TemporaryDirectory() as d:
        g = IOCGraph(db_path=Path(d) / "b")
        await g.initialize()

        # Buffer 5 IOCs
        for i in range(5):
            await g.buffer_ioc("cve", f"CVE-IDEM-{i}", 1.0)

        # First flush
        r1 = await g.flush_buffers()
        assert r1["ioc_flushed"] == 5

        # Second flush — idempotent, no-op
        r2 = await g.flush_buffers()
        assert r2["ioc_flushed"] == 0, f"Second flush should be 0, got {r2['ioc_flushed']}"

        stats = await g.graph_stats()
        assert stats["nodes"] == 5
        print(f"PASS: double flush_buffers() → first=5, second=0 (idempotent)")
        await g.close()


if __name__ == "__main__":
    asyncio.run(test_ioc_buffer_idempotent_flush())
