"""
D.7: Mock Kuzu — buffer_ioc() 50× → upsert_ioc_batch NENÍ volána.
"""
import asyncio
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, ".")


async def test_ioc_buffer_no_kuzu_calls():
    from hledac.universal.knowledge.ioc_graph import IOCGraph

    with tempfile.TemporaryDirectory() as d:
        g = IOCGraph(db_path=Path(d) / "b")
        await g.initialize()

        # Patch upsert_ioc_batch to track calls
        call_count = 0
        original_batch = g.upsert_ioc_batch

        async def mock_batch(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return []

        g.upsert_ioc_batch = mock_batch

        # Buffer 50 IOCs — no Kuzu calls
        for i in range(50):
            await g.buffer_ioc("cve", f"CVE-TEST-{i}", 1.0)

        assert call_count == 0, f"upsert_ioc_batch called {call_count} times (expected 0)"
        assert len(g._ioc_buffer) == 50
        print(f"PASS: buffer_ioc() 50× → upsert_ioc_batch called {call_count} times (0 expected)")
        await g.close()


if __name__ == "__main__":
    asyncio.run(test_ioc_buffer_no_kuzu_calls())
