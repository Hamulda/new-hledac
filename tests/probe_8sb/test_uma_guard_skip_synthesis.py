"""D.11: UMA guard — RSS > 5.5GiB skips synthesis."""
import asyncio
from unittest.mock import patch, MagicMock

import pytest

from hledac.universal.brain.synthesis_runner import SynthesisRunner
from hledac.universal.brain.model_lifecycle import ModelLifecycle


@pytest.mark.asyncio
async def test_uma_guard_skip_synthesis():
    """Mock RSS=6.0 → synthesize_findings returns None (not crash)."""
    runner = SynthesisRunner(ModelLifecycle())

    mock_status = MagicMock()
    mock_status.rss_gib = 6.0

    findings = [
        {"source_type": "cisa_kev", "confidence": 0.95, "text": "CVE-2026 LockBit"},
    ]

    with patch(
        "hledac.universal.core.resource_governor.sample_uma_status",
        return_value=mock_status,
    ):
        result = await runner.synthesize_findings(
            "LockBit ransomware", findings, force_synthesis=True
        )

    assert result is None
