"""Sprint 8TC B.4: Markdown report graceful degradation when report is None"""
import pytest
from unittest.mock import MagicMock, patch
import tempfile
from pathlib import Path


def test_markdown_report_no_findings_graceful():
    """report=None → .md obsahuje '_Synthesis failed' (no exception)"""
    from hledac.universal.__main__ import _export_markdown_report

    mock_scorecard = {
        "findings_per_minute": 0.0,
        "ioc_density": 0.0,
        "semantic_novelty": 1.0,
        "outlines_used": False,
        "source_yield_json": "{}",
        "phase_timings_json": "{}",
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("pathlib.Path.home", return_value=Path(tmpdir)):
            # Nemělo by vyhodit exception
            path = _export_markdown_report(None, mock_scorecard, "s8tc_none")
            content = path.read_text()
            assert "_Synthesis failed" in content
