"""Sprint 8TC B.3: Streaming no stream_generate fallback"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio


@pytest.mark.asyncio
async def test_streaming_no_stream_generate():
    """Mock mlx_lm bez stream_generate attr → fallback returns (None, False)"""
    from hledac.universal.brain.synthesis_runner import SynthesisRunner

    runner = SynthesisRunner(MagicMock())

    mock_model = MagicMock()
    mock_tokenizer = MagicMock()
    mock_tokenizer.apply_chat_template = MagicMock(return_value="formatted_prompt")

    runner._lifecycle._ensure_loaded = AsyncMock(
        return_value=(mock_model, mock_tokenizer, None)
    )

    # Simulujeme, že mlx_lm nemá stream_generate
    with patch("mlx_lm.stream_generate", None):
        result = await runner._run_streaming_generation("test prompt")
        # Fallback vrací (None, False) protože accumulated je prázdný
        assert result == (None, False)
