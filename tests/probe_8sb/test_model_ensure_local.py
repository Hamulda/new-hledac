"""D.12: _ensure_model local — returns Path when model exists on disk."""
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from hledac.universal.brain.synthesis_runner import SynthesisRunner
from hledac.universal.brain.model_lifecycle import ModelLifecycle


@pytest.mark.asyncio
async def test_model_ensure_local():
    """Mock glob hit → _ensure_model returns Path (not None)."""
    runner = SynthesisRunner(ModelLifecycle())

    mock_config = MagicMock()
    mock_config.parent.name = "Qwen2.5-0.5B-Instruct-4bit"
    mock_config.parent.exists.return_value = True
    mock_config.parent.__truediv__ = lambda self, x: Path("/mock/cache") / x

    def glob_side_effect(pattern):
        if "config.json" in pattern:
            return [mock_config.parent / "config.json"]
        return []

    with patch.object(Path, "glob", side_effect=glob_side_effect):
        with patch.object(Path, "exists", return_value=True):
            result = await runner._ensure_model()

    assert result is not None
    assert isinstance(result, Path)
