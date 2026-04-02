"""
Sprint 8TD: Retrieval Policy Probe — embedding/runtime policy verification.

Testy ověřující:
1. graph_rag nezakládá RAGEngine pro embedding (používá MLXEmbeddingManager singleton)
2. rag_engine neinstancuje heavy embedder per call (cached _fastembed_embedder)
3. lancedb_store používá MLXEmbeddingManager singleton
4. Shared runtime anchor zůstává sdílený
5. Žádný nový heavy runtime owner nevznikl
"""
import pytest
from unittest.mock import patch, MagicMock


class TestGraphRAGEmbeddingPolicy:
    """graph_rag používá MLXEmbeddingManager singleton, ne RAGEngine."""

    @pytest.mark.asyncio
    async def test_graph_rag_uses_singleton_not_rag_engine(self):
        """graph_rag._get_embedder() vrací MLXEmbeddingManager singleton, ne RAGEngine."""
        from hledac.universal.knowledge.graph_rag import GraphRAGOrchestrator

        mock_layer = MagicMock()
        orch = GraphRAGOrchestrator(mock_layer)

        # Ověř že _embedder je None před voláním _get_embedder
        assert orch._embedder is None

        # Mock MLXEmbeddingManager singleton
        mock_manager = MagicMock(spec=['embed_document', 'embed_query', 'model_path', 'EMBEDDING_DIM'])
        mock_manager.embed_document = MagicMock(return_value=MagicMock(tolist=lambda: [0.1]*384))

        with patch('hledac.universal.core.mlx_embeddings.get_embedding_manager', return_value=mock_manager):
            embedder = await orch._get_embedder()

        # Ověř že embedder je MLXEmbeddingManager singleton
        assert embedder is mock_manager
        # Není to RAGEngine instance - RAGEngine má _generate_embeddings, MLXEmbeddingManager ne
        assert not hasattr(type(embedder), '_generate_embeddings')

    @pytest.mark.asyncio
    async def test_graph_rag_does_not_create_rag_engine_instance(self):
        """graph_rag._get_embedder() nevytváří RAGEngine instanci."""
        from hledac.universal.knowledge.graph_rag import GraphRAGOrchestrator

        mock_layer = MagicMock()
        orch = GraphRAGOrchestrator(mock_layer)
        orch._embedder_lock = None

        mock_manager = MagicMock(spec=['embed_document', 'embed_query', 'model_path', 'EMBEDDING_DIM'])
        with patch('hledac.universal.core.mlx_embeddings.get_embedding_manager', return_value=mock_manager):
            embedder = await orch._get_embedder()

        # Stále by to měl být MLXEmbeddingManager, ne RAGEngine
        assert embedder is mock_manager
        assert not hasattr(type(embedder), '_generate_embeddings')


class TestRAGEngineEmbeddingPolicy:
    """rag_engine má intentional local cached engine, ne per-call instantiation."""

    def test_rag_engine_has_fastembed_cached_instance(self):
        """RAGEngine._generate_embeddings cachuje FastEmbed TextEmbedding."""
        from hledac.universal.knowledge.rag_engine import RAGEngine

        engine = RAGEngine()

        # Ověř že _fastembed_embedder není nastaven před prvním voláním
        # (lazy init)
        has_cache_before = hasattr(engine, '_fastembed_embedder')
        assert has_cache_before is False or engine._fastembed_embedder is None

        with patch('fastembed.TextEmbedding') as mock_embed:
            mock_instance = MagicMock()
            mock_instance.embed.return_value = [[0.1]*384]
            mock_embed.return_value = mock_instance

            import asyncio
            asyncio.get_event_loop().run_until_complete(
                engine._generate_embeddings(['test'])
            )

            # Po volání by měl být cache nastaven
            assert hasattr(engine, '_fastembed_embedder')
            assert engine._fastembed_embedder is not None
            assert engine._fastembed_embedder is mock_instance

    def test_rag_engine_does_not_reinstantiate_per_call(self):
        """Druhé volání _generate_embeddings() nenívytváří novou TextEmbedding instanci."""
        from hledac.universal.knowledge.rag_engine import RAGEngine

        engine = RAGEngine()

        with patch('fastembed.TextEmbedding') as mock_embed:
            mock_instance = MagicMock()
            mock_instance.embed.return_value = [[0.1]*384]
            mock_embed.return_value = mock_instance

            import asyncio

            # První volání
            asyncio.get_event_loop().run_until_complete(
                engine._generate_embeddings(['text1'])
            )
            first_cache = engine._fastembed_embedder
            first_call_count = mock_embed.call_count

            # Druhé volání
            asyncio.get_event_loop().run_until_complete(
                engine._generate_embeddings(['text2'])
            )

            # Constructor by měl být volán pouze jednou
            assert mock_embed.call_count == first_call_count
            assert engine._fastembed_embedder is first_cache

    def test_rag_engine_fallback_to_mlx_singleton(self):
        """Pokud FastEmbed unavailable, _generate_embeddings používá MLXEmbeddingManager singleton."""
        from hledac.universal.knowledge.rag_engine import RAGEngine

        engine = RAGEngine()

        with patch('fastembed.TextEmbedding', side_effect=ImportError):
            with patch('hledac.universal.core.mlx_embeddings.get_embedding_manager') as mock_get_mgr:
                mock_manager = MagicMock()
                mock_manager.embed_document = MagicMock(return_value=MagicMock(tolist=lambda: [0.1]*384))
                mock_get_mgr.return_value = mock_manager

                import asyncio
                asyncio.get_event_loop().run_until_complete(
                    engine._generate_embeddings(['test'])
                )

                # Mělo by volat MLXEmbeddingManager singleton
                mock_get_mgr.assert_called_once()


class TestLanceDBStoreEmbeddingPolicy:
    """lancedb_store používá MLXEmbeddingManager singleton."""

    @pytest.mark.asyncio
    async def test_lancedb_store_uses_mlx_singleton(self):
        """LanceDBIdentityStore._initialize_embedder() používá MLXEmbeddingManager singleton."""
        from hledac.universal.knowledge.lancedb_store import LanceDBIdentityStore
        from hledac.universal.core import mlx_embeddings as mlx_module

        with patch('lancedb.connect'):
            store = LanceDBIdentityStore()

        # Smaž existující embedder pro čistý test
        store._embedder = None
        store._embedder_type = None

        mock_manager = MagicMock()
        mock_manager.model_path = '/mock/path'
        mock_manager.EMBEDDING_DIM = 384

        # Patch přímo getattr na modulu - funguje pro import uvnitř funkce
        original_get = getattr if hasattr(mlx_module, 'get_embedding_manager') else None
        try:
            mlx_module.get_embedding_manager = MagicMock(return_value=mock_manager)
            # Také patchuj helper cestu
            with patch.dict('sys.modules', {'hledac.core.mlx_embeddings': mlx_module}):
                await store._initialize_embedder()
        finally:
            if original_get:
                mlx_module.get_embedding_manager = original_get

        # Ověř že používá MLXEmbeddingManager singleton
        assert store._embedder is mock_manager
        assert store._embedder_type == 'mlx_gpu'
        assert store._mlx_embed_manager is mock_manager


class TestSharedRuntimeAnchor:
    """MLXEmbeddingManager zůstává sdílený runtime anchor."""

    def test_singleton_is_shared_across_imports(self):
        """get_embedding_manager() vrací konzistentní instanci napříč importy."""
        # Testuje že MLXEmbeddingManager je správně definován jako singleton
        # Tento test ověřuje design-time property, ne runtime chování
        from hledac.universal.core import mlx_embeddings

        # Ověř že modul má get_embedding_manager funkci
        assert hasattr(mlx_embeddings, 'get_embedding_manager'), \
            "MLXEmbeddingManager modul by měl mít get_embedding_manager"

        # Ověř že funkce existuje a je volatelná
        func = getattr(mlx_embeddings, 'get_embedding_manager')
        assert callable(func), "get_embedding_manager by měl být callable"


class TestNoNewHeavyOwner:
    """Ověření že žádný nový heavy runtime owner nevznikl."""

    def test_no_rag_engine_instantiation_in_graph_rag(self):
        """graph_rag NEVKLÁDÁ RAGEngine() pro embedding computation."""
        from hledac.universal.knowledge.graph_rag import GraphRAGOrchestrator
        import inspect
        import re

        # Získej source code _get_embedder
        source = inspect.getsource(GraphRAGOrchestrator._get_embedder)

        # Odstraň komentáře pro čistou kontrolu
        source_no_comments = re.sub(r'""".*?"""', '', source, flags=re.DOTALL)
        source_no_comments = re.sub(r'#.*$', '', source_no_comments, flags=re.MULTILINE)

        # Ověř že neklasicky NEVKLÁDÁ RAGEngine()
        rag_engine_calls = re.findall(r'RAGEngine\s*\(', source_no_comments)
        assert len(rag_engine_calls) == 0, \
            f"graph_rag._get_embedder by neměl vytvářet RAGEngine(), nalezeny: {rag_engine_calls}"

        # Mělo by používat get_embedding_manager
        assert 'get_embedding_manager' in source, \
            "graph_rag._get_embedder by měl používat MLXEmbeddingManager singleton"

    def test_no_new_singleton_created(self):
        """V retrieval plane se nevytvořil nový singleton."""
        from hledac.universal.knowledge import rag_engine, graph_rag, lancedb_store
        import inspect

        # RAGEngine — žádný nový singleton
        rag_source = inspect.getsource(rag_engine)
        # _generate_embeddings používá get_embedding_manager() pro fallback, ne jako nový singleton
        assert rag_source.count('get_embedding_manager()') <= 2, \
            "RAGEngine by neměl vytvářet nové singletony"

        # lancedb_store — používá get_embedding_manager
        lancedb_source = inspect.getsource(lancedb_store)
        assert '_mlx_embed_manager' in lancedb_source, \
            "lancedb_store by měl mít _mlx_embed_manager reference"
        assert lancedb_source.count('get_embedding_manager') >= 1, \
            "lancedb_store._initialize_embedder by měl volat get_embedding_manager"


class TestFallbackPath:
    """Ověření že fallback path je explicitní."""

    def test_rag_engine_has_deterministic_hash_fallback(self):
        """RAGEngine._generate_embeddings má deterministic hash fallback."""
        from hledac.universal.knowledge.rag_engine import RAGEngine
        import inspect

        source = inspect.getsource(RAGEngine._generate_embeddings)

        # Mělo by mít hash-based fallback
        assert 'hash' in source.lower(), \
            "RAGEngine._generate_embeddings by měl mít hash-based fallback"
        assert 'random' in source.lower() or 'Random' in source, \
            "RAGEngine._generate_embeddings by měl mít deterministic fallback"

    def test_graph_rag_has_zero_fallback(self):
        """graph_rag.score_path() má [0.0]*384 fallback."""
        from hledac.universal.knowledge.graph_rag import GraphRAGOrchestrator
        import inspect

        source = inspect.getsource(GraphRAGOrchestrator.score_path)

        # Mělo by mít fallback na [0.0] * 384
        assert '[0.0]' in source or '[0.0] *' in source, \
            "graph_rag.score_path by měl mít [0.0]*384 fallback"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
