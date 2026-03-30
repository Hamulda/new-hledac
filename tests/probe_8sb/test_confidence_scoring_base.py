"""D.9: _compute_confidence base — empty report scores 0.3."""
import pytest

from hledac.universal.brain.synthesis_runner import OSINTReport, SynthesisRunner
from hledac.universal.brain.model_lifecycle import ModelLifecycle


def test_confidence_scoring_base():
    """Empty OSINTReport → _compute_confidence returns 0.3 (base only)."""
    runner = SynthesisRunner(ModelLifecycle())
    report = OSINTReport(
        query="",
        ioc_entities=[],
        threat_summary="",
        threat_actors=[],
        confidence=0.0,
        sources_count=0,
        timestamp=0.0,
    )
    score = runner._compute_confidence(report, used_outlines=True)
    assert score == 0.3
