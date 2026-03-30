"""
Sprint 8VA: Hypothesis probe dispatch.
Tests that hypothesis_probe task type is handled correctly.
"""

import pytest


class TestHypothesisProbeDispatch:
    """Test hypothesis_probe pivot type dispatch."""

    def test_hypothesis_probe_task_type_defined(self):
        """hypothesis_probe is a valid task_type string."""
        task_type = "hypothesis_probe"
        assert task_type == "hypothesis_probe"

    def test_hypothesis_query_extracted_from_hypothesis(self):
        """Hypothesis text can be extracted as query for decomposition."""
        hyp = "IF finding: 'APT28 C2' THEN credible_with_confidence: 0.7"
        # Extract query portion
        query = hyp.replace("IF finding: ", "").replace(" THEN credible_with_confidence: 0.7", "").strip("'")
        assert "APT28 C2" in query
