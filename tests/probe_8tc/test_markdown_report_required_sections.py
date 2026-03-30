"""Sprint 8TC B.4: Markdown report required sections"""
import pytest
from unittest.mock import MagicMock, patch
import tempfile
from pathlib import Path


def test_markdown_report_required_sections():
    """Výsledný .md obsahuje: '# Ghost Prime', '## Executive Summary', '## Threat Actors', '## Top Findings', '## Research Metrics'"""
    from hledac.universal.__main__ import _export_markdown_report

    mock_report = MagicMock()
    mock_report.summary = "Test summary"
    mock_report.threat_actors = ["APT29"]
    mock_report.findings = ["IOC: 192.168.1.1"]
    mock_report.confidence = 0.85

    mock_scorecard = {
        "findings_per_minute": 5.0,
        "ioc_density": 0.5,
        "semantic_novelty": 1.0,
        "outlines_used": False,
        "source_yield_json": "{}",
        "phase_timings_json": "{}",
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("pathlib.Path.home", return_value=Path(tmpdir)):
            path = _export_markdown_report(mock_report, mock_scorecard, "s8tc_test")
            content = path.read_text()

            required_sections = [
                "# Ghost Prime",
                "## Executive Summary",
                "## Threat Actors",
                "## Top Findings",
                "## Research Metrics",
            ]
            for section in required_sections:
                assert section in content, f"Missing section: {section}"
