"""
D.9: buffer_ioc() 10× → flush_buffers() → upsert_ioc_batch voláno s 10 iocs.
"""
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")


async def test_ioc_buffer_flush_windup():
    from hledac.universal.knowledge.ioc_graph import IOCGraph

    with tempfile.TemporaryDirectory() as d:
        g = IOCGraph(db_path=Path(d) / "b")
        await g.initialize()

        # Buffer 10 IOCs
        for i in range(10):
            await g.buffer_ioc("cve", f"CVE-WINDUP-{i}", 1.0)

        assert len(g._ioc_buffer) == 10

        # Flush
        result = await g.flush_buffers()
        assert result["ioc_flushed"] == 10, f"Expected 10, got {result['ioc_flushed']}"
        assert len(g._ioc_buffer) == 0, "Buffer should be empty after flush"

        stats = await g.graph_stats()
        assert stats["nodes"] == 10
        print(f"PASS: flush_buffers() → 10 IOCs flushed to Kuzu")
        await g.close()


if __name__ == "__main__":
    asyncio.run(test_ioc_buffer_flush_windup())
