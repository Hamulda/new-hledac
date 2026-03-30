"""D.3: flush() — batch embed + LanceDB insert, returns row count."""
import asyncio
import tempfile
from pathlib import Path

import pytest

from hledac.universal.knowledge.semantic_store import SemanticStore


@pytest.mark.asyncio
async def test_semantic_store_flush():
    """buffer 5 findings → flush() → returns 5 and LanceDB table has 5 rows."""
    with tempfile.TemporaryDirectory() as d:
        store = SemanticStore(db_path=Path(d) / "lancedb")
        await store.initialize()

        for i in range(5):
            store.buffer_finding(
                text=f"CVE-2026-{i} LockBit ransomware lateral movement",
                source_type="cisa_kev",
                finding_id=f"f{i}",
                ts=float(i),
                ioc_types=["cve", "ransomware"],
            )

        count = await store.flush()
        assert count == 5
        n = await store.count()
        assert n == 5

        await store.close()
