"""D.1: SemanticStore.initialize() — model loaded, db connected."""
import asyncio
import tempfile
from pathlib import Path

import pytest

from hledac.universal.knowledge.semantic_store import SemanticStore


@pytest.mark.asyncio
async def test_semantic_store_initialize():
    """initialize() loads FastEmbed model and connects to LanceDB."""
    with tempfile.TemporaryDirectory() as d:
        store = SemanticStore(db_path=Path(d) / "lancedb")
        await store.initialize()

        assert store._initialized is True
        assert store._model is not None
        assert store._db is not None
        # Table not created yet (no data flushed)
        assert store._table is None

        await store.close()
