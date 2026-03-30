"""Sprint 8TC B.4: Markdown report file created"""
import pytest
from unittest.mock import MagicMock, patch
import tempfile
import os
from pathlib import Path


def test_markdown_report_file_created():
    """_export_markdown_report(mock_report, mock_scorecard, 'test_8tc') → path.exists()"""
    from hledac.universal.__main__ import _export_markdown_report

    mock_report = MagicMock()
    mock_report.summary = "Test summary"
    mock_report.threat_actors = ["APT29"]
    mock_report.findings = ["Finding 1", "Finding 2"]
    mock_report.confidence = 0.85

    mock_scorecard = {
        "findings_per_minute": 12.5,
        "ioc_density": 0.34,
        "semantic_novelty": 0.78,
        "outlines_used": True,
        "source_yield_json": '{"web": 10, "feed": 5}',
        "phase_timings_json": '{"BOOT": 1.0, "ACTIVE": 30.0}',
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("pathlib.Path.home", return_value=Path(tmpdir)):
            path = _export_markdown_report(mock_report, mock_scorecard, "test_8tc")
            assert os.path.exists(path), f"Report file not created at {path}"
            content = path.read_text()
            assert "# Ghost Prime" in content
            assert "test_8tc" in content
