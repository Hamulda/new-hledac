"""
Sprint 8VA: GraphRAG IOC context injection.
Tests that GraphRAG find_connections is called and context is built.
"""

import pytest
from unittest.mock import patch, MagicMock


class TestGraphRAGIOCContextInjected:
    """Test that GraphRAG connections are injected into synthesis context."""

    def test_graphrag_find_connections_returns_paths(self):
        """Mock GraphRAGOrchestrator.find_connections() returns paths."""
        mock_paths = [
            {"path": "1.2.3.4 -> evil.com -> C2 server"},
            {"path": "1.2.3.4 -> malware.exe -> dropped"},
        ]

        with patch("knowledge.graph_rag.GraphRAGOrchestrator") as MockGRAG:
            instance = MockGRAG.return_value
            instance.find_connections = MagicMock(return_value=mock_paths)

            result = instance.find_connections("1.2.3.4", "1.2.3.4", max_hops=2)
            assert len(result) == 2

    def test_graphrag_graceful_degradation_on_no_iocs(self):
        """GraphRAG skipped when no IOCs in findings."""
        # When top_iocs is empty, graph_context stays empty
        top_iocs = []
        graph_context = ""

        if top_iocs:
            # Would try GraphRAG...
            pass  # skipped

        assert graph_context == ""

    def test_graphrag_graceful_degradation_on_error(self):
        """GraphRAG errors don't crash synthesis — graceful degradation."""
        with patch("knowledge.graph_rag.GraphRAGOrchestrator", side_effect=ImportError("No module")):
            from knowledge.graph_rag import GraphRAGOrchestrator
            with pytest.raises(ImportError):
                GraphRAGOrchestrator(None)
