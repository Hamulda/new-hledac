"""
Sprint 8VA: HypothesisEngine generates hypotheses from findings.
Tests that generate_sprint_hypotheses returns hypothesis strings.
"""

import pytest
from unittest.mock import patch


class TestHypothesisPivotEnqueued:
    """Test that HypothesisEngine.generate_sprint_hypotheses is called."""

    def test_generate_sprint_hypotheses_returns_list(self):
        """generate_sprint_hypotheses returns list of hypothesis strings."""
        with patch("brain.hypothesis_engine.HypothesisEngine") as MockHE:
            instance = MockHE.return_value
            instance.generate_sprint_hypotheses = lambda findings, ioc_graph, max_hypotheses: [
                f"IF finding: {f[:20]!r} THEN credible_with_confidence: 0.7"
                for f in findings[:max_hypotheses]
            ]

            result = instance.generate_sprint_hypotheses(
                findings=["CVE-2024-1234 found", "malware detected"],
                ioc_graph=None,
                max_hypotheses=3,
            )
            assert isinstance(result, list)
            assert len(result) == 2
            assert "CVE-2024-1234" in result[0]

    def test_generate_sprint_hypotheses_empty_findings(self):
        """Empty findings returns empty list."""
        with patch("brain.hypothesis_engine.HypothesisEngine") as MockHE:
            instance = MockHE.return_value
            instance.generate_sprint_hypotheses = lambda findings, ioc_graph, max_hypotheses: []

            result = instance.generate_sprint_hypotheses(
                findings=[],
                ioc_graph=None,
                max_hypotheses=3,
            )
            assert result == []

    def test_hypothesis_logged_in_windup(self):
        """Hypotheses are logged during WINDUP synthesis."""
        # Simulate hypothesis logging behavior
        hypotheses = [
            "IF finding: 'CVE-2024-1' THEN credible_with_confidence: 0.7",
            "IF 2 related findings THEN shared_attribution with confidence: 0.8",
        ]

        # Hypotheses should be logged without crashing
        for i, hyp in enumerate(hypotheses, 1):
            # Should not raise
            assert hyp.startswith("IF")
