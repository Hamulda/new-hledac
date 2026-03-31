"""Test: _distill_findings never throws, even with empty input."""
import asyncio
from hledac.universal.brain.synthesis_runner import _distill_findings


def test_distill_findings_empty():
    result = asyncio.run(_distill_findings([]))
    assert isinstance(result, str)


def test_distill_findings_large():
    findings = [{"title": f"T{i}", "snippet": "x" * 500, "source": "test"}
                for i in range(200)]
    result = asyncio.run(_distill_findings(findings, max_tokens=1000))
    assert isinstance(result, str) and len(result) > 0
