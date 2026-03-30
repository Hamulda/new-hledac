"""Sprint 8TC B.3: Streaming fallback on exception"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio


@pytest.mark.asyncio
async def test_streaming_fallback_on_exception():
    """Mock stream_generate raises RuntimeError → fallback → no exception"""
    from hledac.universal.brain.synthesis_runner import SynthesisRunner

    runner = SynthesisRunner(MagicMock())

    mock_model = MagicMock()
    mock_tokenizer = MagicMock()
    mock_tokenizer.apply_chat_template = MagicMock(return_value="formatted_prompt")

    def raise_on_stream_generate(*args, **kwargs):
        raise RuntimeError("GPU error")

    runner._lifecycle._ensure_loaded = AsyncMock(
        return_value=(mock_model, mock_tokenizer, None)
    )

    with patch("mlx_lm.stream_generate", side_effect=raise_on_stream_generate):
        result = await runner._run_streaming_generation("test prompt")
        # Fallback vrací (None, False) — žádná exception se nešíří
        assert result == (None, False)
