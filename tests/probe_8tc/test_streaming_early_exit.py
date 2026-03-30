"""Sprint 8TC B.3: Streaming early exit test"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio


@pytest.mark.asyncio
async def test_streaming_early_exit():
    """Mock stream_generate → yield '{...valid JSON with "title"...}' after 3 chunks → returns (dict, True)"""
    from hledac.universal.brain.synthesis_runner import SynthesisRunner

    runner = SynthesisRunner(MagicMock())

    # Simulovaný chunk s kompletním JSON po 3. chunku
    class MockChunk:
        def __init__(self, text):
            self.text = text

    chunks = [
        MockChunk('{"summ'),
        MockChunk('ary": "tes'),
        MockChunk('t", "title": "IOC Report", "findings": []}'),
    ]

    mock_model = MagicMock()
    mock_tokenizer = MagicMock()
    mock_tokenizer.apply_chat_template = MagicMock(return_value="formatted_prompt")

    # _ensure_loaded je async, vrací přímo tuple (model, tokenizer, path)
    runner._lifecycle._ensure_loaded = AsyncMock(
        return_value=(mock_model, mock_tokenizer, None)
    )

    with patch("mlx_lm.stream_generate", return_value=iter(chunks)):
        result = await runner._run_streaming_generation("test prompt")

    assert result is not None
    parsed_dict, used_outlines = result
    assert used_outlines is True
    assert parsed_dict["title"] == "IOC Report"
    assert parsed_dict["summary"] == "test"
