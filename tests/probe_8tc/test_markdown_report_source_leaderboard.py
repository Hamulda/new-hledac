"""Sprint 8TC B.4: Markdown report source leaderboard"""
import pytest
from unittest.mock import MagicMock, patch
import tempfile
from pathlib import Path


def test_markdown_report_source_leaderboard():
    """scorecard s source_yield → .md obsahuje '## Source Leaderboard'"""
    from hledac.universal.__main__ import _export_markdown_report

    mock_report = MagicMock()
    mock_report.summary = "Test"
    mock_report.threat_actors = []
    mock_report.findings = []
    mock_report.confidence = 0.5

    mock_scorecard = {
        "findings_per_minute": 5.0,
        "ioc_density": 0.5,
        "semantic_novelty": 1.0,
        "outlines_used": False,
        "source_yield_json": '{"wexit_content": 15, "feed": 8, "document": 3}',
        "phase_timings_json": "{}",
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("pathlib.Path.home", return_value=Path(tmpdir)):
            path = _export_markdown_report(mock_report, mock_scorecard, "s8tc_src")
            content = path.read_text()

            assert "## Source Leaderboard" in content
            assert "wexit_content" in content
            assert "feed" in content
