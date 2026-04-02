"""Sprint 8TD: RAGEngine embedder cache memory convergence test."""
from unittest.mock import patch, MagicMock


def test_rag_engine_caches_fastembed_instance():
    """RAGEngine._generate_embeddings caches TextEmbedding instance."""
    from hledac.universal.knowledge.rag_engine import RAGEngine

    engine = RAGEngine()

    # Initially no cache
    assert not hasattr(engine, '_fastembed_embedder'), \
        "Engine should not have _fastembed_embedder before first call"

    # Mock TextEmbedding at source (inside _generate_embeddings)
    with patch('fastembed.TextEmbedding') as mock_embed:
        mock_instance = MagicMock()
        mock_instance.embed.return_value = [[0.1] * 384]
        mock_embed.return_value = mock_instance

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            engine._generate_embeddings(['test text'])
        )

        # Verify cache was set
        assert hasattr(engine, '_fastembed_embedder'), \
            "_fastembed_embedder should be set after first call"
        assert engine._fastembed_embedder is not None, \
            "_fastembed_embedder should not be None after successful init"
        assert engine._fastembed_embedder is mock_instance, \
            "_fastembed_embedder should be the mocked TextEmbedding instance"


def test_rag_engine_reuses_cached_fastembed():
    """Second call to _generate_embeddings reuses cached TextEmbedding."""
    from hledac.universal.knowledge.rag_engine import RAGEngine

    engine = RAGEngine()

    with patch('fastembed.TextEmbedding') as mock_embed:
        mock_instance = MagicMock()
        mock_instance.embed.return_value = [[0.1] * 384]
        mock_embed.return_value = mock_instance

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            engine._generate_embeddings(['text1'])
        )
        first_cache = engine._fastembed_embedder

        asyncio.get_event_loop().run_until_complete(
            engine._generate_embeddings(['text2'])
        )

        # Same instance should be reused (no new TextEmbedding call)
        assert engine._fastembed_embedder is first_cache, \
            "Cached TextEmbedding instance should be reused on second call"
        assert mock_embed.call_count == 1, \
            "TextEmbedding constructor should be called only once"
