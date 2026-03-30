"""D.6: semantic_pivot score range — all scores in [0.0, 1.0]."""
import asyncio
import tempfile
from pathlib import Path

import pytest

from hledac.universal.knowledge.semantic_store import SemanticStore


@pytest.mark.asyncio
async def test_semantic_pivot_score_range():
    """All scores from semantic_pivot are in [0.0, 1.0]."""
    with tempfile.TemporaryDirectory() as d:
        store = SemanticStore(db_path=Path(d) / "lancedb")
        await store.initialize()

        for i in range(10):
            store.buffer_finding(
                f"CVE-2026-{i} ransomware", "cisa_kev", f"f{i}", float(i), ["cve"]
            )

        await store.flush()
        results = await store.semantic_pivot("ransomware", top_k=10)

        assert len(results) > 0
        for r in results:
            assert 0.0 <= r["score"] <= 1.0, f"score {r['score']} out of range"

        await store.close()
