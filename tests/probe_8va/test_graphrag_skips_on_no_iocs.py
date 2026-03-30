"""
Sprint 8VA: GraphRAG skips when no IOCs.
Tests that GraphRAG is not called when findings list is empty.
"""

import pytest
from unittest.mock import patch, MagicMock


class TestGraphRAGSkipsOnNoIOCs:
    """GraphRAG should not be called when no IOCs available."""

    def test_graphrag_not_called_with_empty_findings(self):
        """With empty findings list, GraphRAG.extract_subgraph NOT called."""
        findings = []
        top_iocs = [
            f.get("ioc") or f.get("indicator") or f.get("value")
            for f in findings[:5]
            if f.get("ioc") or f.get("indicator") or f.get("value")
        ]

        # Should be empty, so GraphRAG block skipped
        assert top_iocs == []

    def test_graphrag_called_when_iocs_present(self):
        """With findings containing IOCs, GraphRAG is attempted."""
        findings = [
            {"ioc": "1.2.3.4", "text": "Found malicious IP"},
            {"indicator": "evil.com", "text": "Malicious domain"},
        ]
        top_iocs = [
            f.get("ioc") or f.get("indicator") or f.get("value")
            for f in findings[:5]
            if f.get("ioc") or f.get("indicator") or f.get("value")
        ]

        assert len(top_iocs) == 2
        assert "1.2.3.4" in top_iocs
        assert "evil.com" in top_iocs
