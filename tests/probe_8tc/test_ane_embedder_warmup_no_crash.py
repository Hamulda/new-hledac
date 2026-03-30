"""Sprint 8TC B.5: ANEEmbedder warmup no crash"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio


@pytest.mark.asyncio
async def test_ane_embedder_warmup_no_crash():
    """ANEEmbedder s mock embed → warmup() → no exception"""
    from hledac.universal.brain.ane_embedder import ANEEmbedder

    # Mock ANE_AVAILABLE = True a model loaded
    with patch("hledac.universal.brain.ane_embedder.ANE_AVAILABLE", True):
        embedder = ANEEmbedder()
        embedder._loaded = True
        embedder.model = MagicMock()
        embedder._fallback_embedder = None

        # embed() throws NotImplementedError — warmup by to měl odchytit
        embedder.embed = MagicMock(side_effect=NotImplementedError("not implemented"))

        # warmup() by neměl vyhodit exception
        await embedder.warmup()  # Should not raise
