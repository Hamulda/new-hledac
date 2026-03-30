"""
D.8: buffer_ioc() 500× → flush_buffers() volána automaticky.
"""
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")


async def test_ioc_buffer_flush_size():
    from hledac.universal.knowledge.ioc_graph import IOCGraph

    with tempfile.TemporaryDirectory() as d:
        g = IOCGraph(db_path=Path(d) / "b")
        await g.initialize()

        # Buffer 500 IOCs — should trigger auto-flush at 500
        for i in range(500):
            await g.buffer_ioc("cve", f"CVE-FLUSH-{i}", 1.0)

        # After auto-flush at exactly 500, buffer should be empty
        assert len(g._ioc_buffer) == 0, f"Buffer should be empty, has {len(g._ioc_buffer)}"

        # Final manual flush (should flush 0 since auto-triggered)
        result = await g.flush_buffers()
        assert result["ioc_flushed"] == 0

        stats = await g.graph_stats()
        assert stats["nodes"] == 500
        print(f"PASS: buffer_ioc() 500× → auto-flush triggered, buffer empty")
        await g.close()


if __name__ == "__main__":
    asyncio.run(test_ioc_buffer_flush_size())
