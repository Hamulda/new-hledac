"""D.10: _compute_confidence full — all signals → 1.0."""
import pytest

from hledac.universal.brain.synthesis_runner import IOCEntity, OSINTReport, SynthesisRunner
from hledac.universal.brain.model_lifecycle import ModelLifecycle


def test_confidence_scoring_full():
    """Full OSINTReport (threat_actors, CVE IOC, all fields, outlines=True) → 1.0."""
    runner = SynthesisRunner(ModelLifecycle())
    report = OSINTReport(
        query="LockBit ransomware 2026",
        ioc_entities=[
            IOCEntity(
                value="CVE-2026-1234",
                ioc_type="cve",
                severity="critical",
                context="LockBit exploits SMB vulnerability",
            )
        ],
        threat_summary="LockBit ransomware campaign targeting healthcare.",
        threat_actors=["LockBit"],
        confidence=0.0,
        sources_count=3,
        timestamp=1234567890.0,
    )
    score = runner._compute_confidence(report, used_outlines=True)
    assert score == 1.0
