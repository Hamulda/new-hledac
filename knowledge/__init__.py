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
from .context_graph import ContextGraph
from .rag_engine import RAGEngine, RAGConfig, Document, RetrievedChunk, BM25Index, HNSWVectorIndex

# Sprint 8VC: atomic_storage and persistent_layer moved to legacy/
# These imports now proxy to legacy/ with deprecation warnings
import warnings as _warnings
_warnings.warn(
    "knowledge.atomic_storage is DEPRECATED. Use knowledge.duckdb_store instead.",
    DeprecationWarning,
    stacklevel=2,
)
from ..legacy.atomic_storage import AtomicJSONKnowledgeGraph, KnowledgeEntry, get_atomic_storage

_warnings.warn(
    "knowledge.persistent_layer is DEPRECATED. Use knowledge.duckdb_store instead.",
    DeprecationWarning,
    stacklevel=2,
)
from ..legacy.persistent_layer import (
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
