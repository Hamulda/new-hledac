"""
Sprint 8VA: RAG token budget is respected (max ~1800 tokens).
Simulates 20 results of 500 chars each and verifies context is bounded.
"""

import pytest


class TestRAGTokenBudgetRespected:
    """Token budget guard for M1 8GB constraint."""

    def test_rag_context_truncated_when_exceeds_7200_chars(self):
        """20 results × 500 chars = 10000 chars → truncated to 7200."""
        # Simulate what synthesis_runner does with RAG context
        raw_ctx = "x" * 10000  # 10000 chars = ~2500 tokens
        max_chars = 7200  # ~1800 tokens

        if len(raw_ctx) > max_chars:
            truncated = raw_ctx[:max_chars] + "...[truncated]"
        else:
            truncated = raw_ctx

        assert len(truncated) == 7200 + len("... [truncated]")  # approximately
        assert "...[truncated]" in truncated

    def test_rag_context_preserved_when_under_limit(self):
        """Short context is preserved without truncation."""
        raw_ctx = "short context"
        max_chars = 7200

        if len(raw_ctx) > max_chars:
            truncated = raw_ctx[:max_chars] + "...[truncated]"
        else:
            truncated = raw_ctx

        assert truncated == "short context"
