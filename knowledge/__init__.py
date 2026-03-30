"""
Knowledge komponenty pro UniversalResearchOrchestrator.

Obsahuje:
- KnowledgeGraphLayer: KuzuDB-based persistent knowledge graph (KuzuDB)
- AtomicJSONKnowledgeGraph: RAM-efficient JSON storage (bez DB závislostí)
- ContextGraph: Simple in-memory context graph
- RAGEngine: Ultra Context + SPR Compression
- PersistentKnowledgeLayer: KuzuDB + Model2Vec for semantic search
- GraphRAGOrchestrator: Multi-hop reasoning over knowledge graph
- KnowledgeGraphBuilder: Regex-based fact extraction
"""

from .graph_layer import KnowledgeGraphLayer
from .atomic_storage import AtomicJSONKnowledgeGraph, KnowledgeEntry, get_atomic_storage
from .context_graph import ContextGraph
from .rag_engine import RAGEngine, RAGConfig, Document, RetrievedChunk, BM25Index, HNSWVectorIndex

# Nové komponenty ze supreme
from .persistent_layer import (
    PersistentKnowledgeLayer,
    KnowledgeNode,
    KnowledgeEdge,
    NodeType,
    EdgeType,
    KuzuDBBackend,
    JSONBackend
)
from .graph_rag import (
    GraphRAGOrchestrator,
    CentralityScores,
    Community,
    GraphContradiction,
)
from .graph_builder import KnowledgeGraphBuilder
from .entity_linker import (
    EntityLinker,
    EntityCandidate,
    LinkedEntity,
    SimpleCache,
    link_entities,
    resolve_entity,
    get_linker,
)

__all__ = [
    # Existující
    "KnowledgeGraphLayer",
    "AtomicJSONKnowledgeGraph",
    "KnowledgeEntry",
    "get_atomic_storage",
    "ContextGraph",
    "RAGEngine",
    "RAGConfig",
    "Document",
    "RetrievedChunk",
    "BM25Index",
    "HNSWVectorIndex",
    # Nové ze supreme
    "PersistentKnowledgeLayer",
    "KnowledgeNode",
    "KnowledgeEdge",
    "NodeType",
    "EdgeType",
    "KuzuDBBackend",
    "JSONBackend",
    "GraphRAGOrchestrator",
    "KnowledgeGraphBuilder",
    # Entity Linking
    "EntityLinker",
    "EntityCandidate",
    "LinkedEntity",
    "SimpleCache",
    "link_entities",
    "resolve_entity",
    "get_linker",
    # Network Analysis (from evidence_network_analyzer.py)
    "CentralityScores",
    "Community",
    "GraphContradiction",
]
