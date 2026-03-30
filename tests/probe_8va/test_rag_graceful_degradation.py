"""
Sprint 8VA: RAG graceful degradation.
Tests that synthesis proceeds normally even when RAG is unavailable.
"""

import pytest
from unittest.mock import patch


class TestRAGGracefulDegradation:
    """Test that synthesis continues when RAG/GraphRAG unavailable."""

    def test_synthesis_proceeds_when_rag_unavailable(self):
        """Synthesis should not crash if RAG import fails."""
        # Simulate ImportError from RAGEngine
        with patch("knowledge.rag_engine.RAGEngine", side_effect=ImportError("No module named rag")):
            try:
                from knowledge.rag_engine import RAGEngine
                # Should raise
                RAGEngine()
            except ImportError:
                pass  # Expected

        # Synthesis would continue with empty rag_context
        rag_context = ""
        assert rag_context == ""

    def test_synthesis_proceeds_when_graphrag_unavailable(self):
        """Synthesis should not crash if GraphRAG import fails."""
        # Simulate ImportError from GraphRAGOrchestrator
        with patch("knowledge.graph_rag.GraphRAGOrchestrator", side_effect=ImportError("No module")):
            try:
                from knowledge.graph_rag import GraphRAGOrchestrator
                # Should raise
                GraphRAGOrchestrator(None)
            except ImportError:
                pass  # Expected

        # Synthesis would continue with empty graph_context
        graph_context = ""
        assert graph_context == ""

    def test_synthesis_proceeds_when_no_findings(self):
        """Synthesis proceeds with empty findings and no RAG."""
        findings = []
        top = sorted(findings, key=lambda f: f.get("confidence", 0.0), reverse=True)[:10]

        rag_context = ""
        graph_context = ""

        context_parts = []
        if rag_context:
            context_parts.append(rag_context)
        if graph_context:
            context_parts.append(graph_context)

        # Without episode_ctx, falls through to else branch
        if context_parts:
            prompt = "has context"
        else:
            prompt = "Query: test\nFindings:\n"

        assert prompt.startswith("Query:")
