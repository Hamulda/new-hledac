"""D.8: semantic_pivot similarity ordering — related result scores higher."""
import asyncio
import tempfile
from pathlib import Path

import pytest

from hledac.universal.knowledge.semantic_store import SemanticStore


@pytest.mark.asyncio
async def test_semantic_pivot_similarity():
    """Insert ransomware + recipe → ransomware query → ransomware result score > recipe."""
    with tempfile.TemporaryDirectory() as d:
        store = SemanticStore(db_path=Path(d) / "lancedb")
        await store.initialize()

        store.buffer_finding(
            "LockBit ransomware CVE-2026-1234 exploiting Windows SMB",
            "cisa_kev",
            "ransomware_finding",
            1.0,
            ["ransomware", "cve"],
        )
        store.buffer_finding(
            "Classic carbonara pasta recipe with guanciale and pecorino romano",
            "clearnet",
            "recipe_finding",
            2.0,
            ["food"],
        )

        await store.flush()
        results = await store.semantic_pivot("ransomware exploit", top_k=2)

        assert len(results) == 2
        scores = {r["finding_id"]: r["score"] for r in results}
        assert scores["ransomware_finding"] > scores["recipe_finding"], (
            f"Ransomware score {scores['ransomware_finding']} should exceed "
            f"recipe score {scores['recipe_finding']}"
        )

        await store.close()
