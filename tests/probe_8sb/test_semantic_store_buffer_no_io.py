"""D.2: buffer_finding() — no I/O, buffers only."""
import asyncio
import tempfile
from pathlib import Path

import pytest

from hledac.universal.knowledge.semantic_store import SemanticStore


@pytest.mark.asyncio
async def test_semantic_store_buffer_no_io():
    """buffer_finding() accumulates without creating LanceDB table."""
    with tempfile.TemporaryDirectory() as d:
        store = SemanticStore(db_path=Path(d) / "lancedb")
        await store.initialize()

        for i in range(10):
            store.buffer_finding(
                text=f"CVE-2026-{i} LockBit ransomware",
                source_type="cisa_kev",
                finding_id=f"f{i}",
                ts=float(i),
                ioc_types=["cve", "ransomware"],
            )

        # No I/O yet — pending only
        assert len(store._pending_texts) == 10
        assert len(store._pending_meta) == 10
        # Table still not created
        assert store._table is None

        await store.close()
