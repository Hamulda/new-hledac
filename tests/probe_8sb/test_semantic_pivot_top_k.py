"""D.5: semantic_pivot top_k — returns ≤ top_k results."""
import asyncio
import tempfile
from pathlib import Path

import pytest

from hledac.universal.knowledge.semantic_store import SemanticStore


@pytest.mark.asyncio
async def test_semantic_pivot_top_k():
    """Insert 20 findings → semantic_pivot(top_k=5) → returns list of length ≤ 5."""
    with tempfile.TemporaryDirectory() as d:
        store = SemanticStore(db_path=Path(d) / "lancedb")
        await store.initialize()

        for i in range(20):
            store.buffer_finding(
                f"CVE-2026-{i} ransomware infrastructure lateral movement cobalt strike",
                "clearnet",
                f"f{i}",
                float(i),
                ["cve", "malware"],
            )

        await store.flush()
        results = await store.semantic_pivot("ransomware CVE exploit", top_k=5)

        assert isinstance(results, list)
        assert len(results) <= 5
        for r in results:
            assert "text" in r
            assert "score" in r
            assert "source_type" in r

        await store.close()
