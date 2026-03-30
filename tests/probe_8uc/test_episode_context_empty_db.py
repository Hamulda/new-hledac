"""Sprint 8UC: Episode context building."""
import pytest
from hledac.universal.brain.synthesis_runner import SynthesisRunner


@pytest.mark.asyncio
async def test_build_episode_context_empty_store():
    """With no store, returns empty string."""
    runner = SynthesisRunner.__new__(SynthesisRunner)
    result = await runner._build_episode_context(None, "test query")
    assert result == ""


@pytest.mark.asyncio
async def test_build_episode_context_store_without_method():
    """With store missing recall_episodes, returns empty string."""
    runner = SynthesisRunner.__new__(SynthesisRunner)
    fake_store = object()
    result = await runner._build_episode_context(fake_store, "test query")
    assert result == ""
