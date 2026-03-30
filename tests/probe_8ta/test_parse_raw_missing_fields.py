"""Sprint 8TA B.1: _parse_raw_to_osintreport with missing fields uses defaults."""
import pytest
import time
from unittest.mock import MagicMock


def test_parse_raw_missing_fields():
    """raw = {'title':'x'} -> _parse_raw_to_osintreport -> no exception, defaults filled."""
    from hledac.universal.brain.synthesis_runner import SynthesisRunner

    runner = SynthesisRunner(MagicMock())

    # Only title provided
    raw = {"title": "ransomware report"}
    result = runner._parse_raw_to_osintreport(raw)

    assert result is not None
    assert result.query == "ransomware report"
    assert result.threat_summary == ""
    assert result.threat_actors == []
    assert result.ioc_entities == []
    assert result.confidence == 0.0
    assert result.sources_count == 0
    assert result.timestamp > 0


def test_parse_raw_full_fields():
    """raw with all fields -> properly mapped."""
    from hledac.universal.brain.synthesis_runner import SynthesisRunner

    runner = SynthesisRunner(MagicMock())
    raw = {
        "title": "APT Report",
        "summary": "North Korean APT activity",
        "threat_actors": ["Lazarus", "APT38"],
        "findings": ["192.168.1.1", "evil.exe"],
        "confidence": 0.85,
        "timestamp": 1710000000.0,
    }
    result = runner._parse_raw_to_osintreport(raw)

    assert result is not None
    assert result.query == "APT Report"
    assert result.threat_summary == "North Korean APT activity"
    assert result.threat_actors == ["Lazarus", "APT38"]
    assert len(result.ioc_entities) == 2
    assert result.confidence == 0.85
    assert result.sources_count == 2
    assert result.timestamp == 1710000000.0
