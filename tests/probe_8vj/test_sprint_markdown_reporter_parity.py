"""Sprint 8VJ §B: Sprint markdown reporter parity probes

Ověřuje:
1. Canonical renderer `render_sprint_markdown()` vrací správné sekce
2. Shell bridge `__main__._render_sprint_report_markdown()` deleguje správně
3. Výstupní path semantics je zachována (home/.hledac/reports/{sprint_id}.md)
4. Graceful degradation když report je None nebo má chybějící atributy
"""
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestCanonicalRendererOutput:
    """Přímé testy canonical rendereru."""

    def test_required_sections_present(self):
        """Canonical renderer obsahuje všechny požadované sekce."""
        from hledac.universal.export.sprint_markdown_reporter import render_sprint_markdown

        mock_report = MagicMock()
        mock_report.summary = "Test summary"
        mock_report.threat_actors = ["APT29", "UNC2452"]
        mock_report.findings = ["IOC: 192.168.1.1", "IOC: evil.com"]

        mock_scorecard = {
            "findings_per_minute": 5.0,
            "ioc_density": 0.5,
            "semantic_novelty": 1.0,
            "outlines_used": False,
            "source_yield_json": '{"feed:http://example.com": 10}',
            "phase_timings_json": '{"BOOT": 0.0, "ACTIVE": 10.5, "WINDUP": 20.0}',
        }

        result = render_sprint_markdown(mock_report, mock_scorecard, "s8vj_test")

        required = [
            "# Ghost Prime — Sprint Report",
            "**Sprint ID:** `s8vj_test`",
            "## Executive Summary",
            "## Research Metrics",
            "| Findings/min | 5.00 |",
            "| IOC density | 0.500 |",
            "## Threat Actors",
            "- `APT29`",
            "- `UNC2452`",
            "## Top Findings",
            "**1.** IOC: 192.168.1.1",
            "**2.** IOC: evil.com",
            "## Source Leaderboard",
            "`feed:http://example.com`",
            "## Phase Timings",
            "`BOOT`",
        ]
        for item in required:
            assert item in result, f"Missing in output: {item!r}"

    def test_graceful_no_findings(self):
        """Renderer degrades gracefully když nejsou findings."""
        from hledac.universal.export.sprint_markdown_reporter import render_sprint_markdown

        mock_report = MagicMock(spec=["summary"])
        mock_report.summary = "Empty sprint"
        mock_report.threat_actors = None
        mock_report.findings = None

        mock_scorecard = {
            "findings_per_minute": 0.0,
            "ioc_density": 0.0,
            "semantic_novelty": 1.0,
            "outlines_used": True,
            "source_yield_json": "{}",
            "phase_timings_json": "{}",
        }

        result = render_sprint_markdown(mock_report, mock_scorecard, "s8vj_empty")

        assert "_No findings synthesized_" in result
        assert "_None identified in this sprint_" in result
        assert "✅ Outlines constrained" in result

    def test_graceful_none_report(self):
        """Renderer degrades gracefully když report je None."""
        from hledac.universal.export.sprint_markdown_reporter import render_sprint_markdown

        scorecard = {
            "findings_per_minute": 2.5,
            "ioc_density": 0.3,
            "semantic_novelty": 0.8,
            "outlines_used": False,
            "source_yield_json": "{}",
            "phase_timings_json": "{}",
        }

        result = render_sprint_markdown(None, scorecard, "s8vj_null")

        assert "## Executive Summary" in result
        assert "_Synthesis failed or unavailable_" in result
        assert "## Research Metrics" in result

    def test_pure_function_no_side_effects(self):
        """Renderer nemá side effects — volání nesmí měnit stav."""
        from hledac.universal.export.sprint_markdown_reporter import render_sprint_markdown

        mock_report = MagicMock()
        mock_report.summary = "Test"
        mock_report.threat_actors = []
        mock_report.findings = []

        scorecard = {
            "findings_per_minute": 1.0,
            "ioc_density": 0.1,
            "semantic_novelty": 0.5,
            "outlines_used": False,
            "source_yield_json": "{}",
            "phase_timings_json": "{}",
        }

        # Call twice — output must be identical
        result1 = render_sprint_markdown(mock_report, scorecard, "test_id")
        result2 = render_sprint_markdown(mock_report, scorecard, "test_id")
        assert result1 == result2


class TestShellBridgeDelegation:
    """Testy že shell bridge správně deleguje na canonical renderer."""

    def test_bridge_delegates_to_canonical(self):
        """Shell bridge deleguje na render_sprint_markdown."""
        from hledac.universal.__main__ import _render_sprint_report_markdown

        mock_report = MagicMock()
        mock_report.summary = "Bridge test"
        mock_report.threat_actors = ["TESTActor"]
        mock_report.findings = ["BRIDGE:IOC"]

        scorecard = {
            "findings_per_minute": 3.0,
            "ioc_density": 0.4,
            "semantic_novelty": 0.9,
            "outlines_used": True,
            "source_yield_json": "{}",
            "phase_timings_json": "{}",
        }

        result = _render_sprint_report_markdown(mock_report, scorecard, "s8vj_bridge")

        assert "Bridge test" in result
        assert "`TESTActor`" in result
        assert "BRIDGE:IOC" in result


class TestPathSemanticsPreserved:
    """Testy že path semantics je zachována."""

    def test_export_uses_correct_path(self):
        """_export_markdown_report píše do ~/.hledac/reports/{sprint_id}.md."""
        from hledac.universal.__main__ import _export_markdown_report

        mock_report = MagicMock()
        mock_report.summary = "Path test"
        mock_report.threat_actors = []
        mock_report.findings = []

        scorecard = {
            "findings_per_minute": 1.0,
            "ioc_density": 0.1,
            "semantic_novelty": 0.5,
            "outlines_used": False,
            "source_yield_json": "{}",
            "phase_timings_json": "{}",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("pathlib.Path.home", return_value=Path(tmpdir)):
                path = _export_markdown_report(mock_report, scorecard, "s8vj_path_test")

        assert path.name == "s8vj_path_test.md"
        assert str(path).endswith(".hledac/reports/s8vj_path_test.md")

    def test_output_file_content_matches_bridge(self):
        """Obsah souboru odpovídá tomu co vrací bridge."""
        from hledac.universal.__main__ import _export_markdown_report, _render_sprint_report_markdown

        mock_report = MagicMock()
        mock_report.summary = "Content match"
        mock_report.threat_actors = []
        mock_report.findings = ["Finding 1"]

        scorecard = {
            "findings_per_minute": 2.0,
            "ioc_density": 0.2,
            "semantic_novelty": 0.6,
            "outlines_used": True,
            "source_yield_json": "{}",
            "phase_timings_json": "{}",
        }

        bridge_output = _render_sprint_report_markdown(mock_report, scorecard, "s8vj_content")

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("pathlib.Path.home", return_value=Path(tmpdir)):
                path = _export_markdown_report(mock_report, scorecard, "s8vj_content")
                file_content = path.read_text()

        assert file_content == bridge_output
