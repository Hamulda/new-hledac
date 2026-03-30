"""D.4: flush() idempotent — second flush returns 0."""
import asyncio
import tempfile
from pathlib import Path

import pytest

from hledac.universal.knowledge.semantic_store import SemanticStore


@pytest.mark.asyncio
async def test_semantic_store_flush_idempotent():
    """Two consecutive flushes — second returns 0."""
    with tempfile.TemporaryDirectory() as d:
        store = SemanticStore(db_path=Path(d) / "lancedb")
        await store.initialize()

        store.buffer_finding(
            "CVE-2026-1 LockBit ransomware", "cisa_kev", "f1", 1.0, ["cve"]
        )

        c1 = await store.flush()
        c2 = await store.flush()

        assert c1 == 1
        assert c2 == 0

        await store.close()
