# Sprint 8BV Report — Vector Storage Split-Brain & LanceDB vs HNSW

**Date:** 2026-03-24
**Probe Workspace:** `tests/probe_8bv/`

---

## 1. LanceDB Usage Map

### File
`knowledge/lancedb_store.py`

### Class
`LanceDBIdentityStore` (singleton via `get_identity_store()`)

### Data Stored
| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Entity identifier |
| `embedding` | list[float32, dim=768] | Vector for semantic similarity |
| `aliases` | list[string] | Alternate names |
| `first_seen` | timestamp | |
| `last_seen` | timestamp | |

### Table Schema (LanceDB "entities")
```python
pa.schema([
    pa.field("id", pa.string()),
    pa.field("embedding", pa.list_(pa.float32(), list_size=768)),
    pa.field("aliases", pa.list_(pa.string())),
    pa.field("first_seen", pa.timestamp('s')),
    pa.field("last_seen", pa.timestamp('s')),
])
```

### Embedding Pipeline
- **Primary:** `MLXEmbeddingManager` (Sprint 81 Fáze 4) via `hledac.core.mlx_embeddings`
- **Fallback 1:** CoreML ANE (`modernbert-embed.mlpackage`)
- **Fallback 2:** NumPy random (minimal footprint)
- **Cache:** LMDB with float16 quantization (50% RAM savings)
- **MRL dimension:** 768 (truncation supported)

### Search Methods
- `search_similar()` — pure vector or hybrid (vector + FTS)
- `search_similar_adaptive()` — binary prefilter → MMR → ColBERT/FlashRank/MLX reranking
- `compute_similarity()` — cosine similarity between two embeddings

### Writers
- `add_entity(entity_id, embedding, aliases)` — adds to LanceDB "entities" table
- Writeback buffer (OrderedDict, max 1000) → LMDB

### Readers
- `search_similar()`, `search_similar_adaptive()` — read from LanceDB table
- `_mlx_rerank()` — reads `_mlx_embeddings` (MLX array, loaded from LanceDB)

### Key Observations
- LanceDB stores **entity identities** (who is this person/organization?)
- No direct cross-store query — LanceDB and HNSW are never queried together for the same data
- Singleton pattern — one instance across the process

---

## 2. HNSW Usage Map

### 2A. `persistent_layer.py` — `PersistentKnowledgeLayer`

**HNSW Index:** `hnswlib.Index` (C++ hnswlib)

| Component | Detail |
|-----------|--------|
| Dim | 768 |
| Space | cosine |
| Max elements | 100,000 (bounded by `MAX_HNSW_VECTORS`) |
| M | 16 |
| ef_construction | 200 |
| ef_search | 50 |

**Stored Data:** `KnowledgeNode` objects with `{node_id: embedding}` mapping

**Methods:**
- `_build_hnsw_index(nodes, embeddings)` — sync build
- `_build_hnsw_index_async(nodes, embeddings)` — async build via thread pool
- `_search_hnsw(query_embedding, k)` — search returning `(node_id, similarity)` tuples

**Also has:**
- `IncrementalHNSW` from `tools/hnsw_builder.py` (Sprint 55, thread-safe)
- PQ Index (Sprint 57, Product Quantization for memory-efficient storage)
- Linear search fallback when nodes < 100

**Writers:**
- `_build_hnsw_index_async()` populates `_hnsw_index` and `_hnsw_id_to_node`
- `add_node()` eventually triggers index rebuild

**Readers:**
- `_search_hnsw()` queries the index
- `find_similar_vectors()` tries PQ → HNSW → linear fallback

---

### 2B. `rag_engine.py` — `RAGEngine`

**HNSW Index:** `HNSWVectorIndex` class (wraps hnswlib)

| Component | Detail |
|-----------|--------|
| Dim | 768 (configurable via `hnsw_dim`) |
| Space | cosine / l2 / ip (configurable) |
| Max elements | 100,000 |
| M | 16 |
| ef_construction | 200 |
| ef_search | 50 |

**Stored Data:** `Document` objects mapped via `_document_map {doc_id: Document}`

**Methods:**
- `build_hnsw_index(documents, embeddings)` — builds index
- `_hnsw_retrieval(query_embedding, top_k, filters)` — searches returning `RetrievedChunk` list
- `hybrid_retrieve_with_hnsw()` — BM25 + HNSW fusion
- `save_hnsw_index()` / `load_hnsw_index()` — persistence

**Writers:**
- `build_hnsw_index()` — adds vectors via `HNSWVectorIndex.add_vectors()`

**Readers:**
- `_hnsw_retrieval()` queries `_hnsw_index`

---

### 2C. `memory_coordinator.py` — `MemoryCoordinator` section

Also has HNSW (`_hnsw_index`, `hnswlib.Index`) for memory-aware retrieval.

---

## 3. Split-Brain Analysis

### Same Embedding Dimension: YES
All three stores use **768-dim** vectors. Embeddings are compatible at the vector level.

### Same Entity Type: NO (domain separation)

| Store | Data Type | Purpose |
|-------|-----------|---------|
| LanceDB "entities" | Person/org identities | "Is this the same John Smith?" |
| PersistentKnowledgeLayer HNSW | KnowledgeNodes | Graph knowledge retrieval |
| RAGEngine HNSW | Document chunks | RAG retrieval |

### Split-Brain Scenario: LOW RISK

The same query **cannot hit both stores** because they serve different domains:
- Entity resolution queries go to `LanceDBIdentityStore`
- Knowledge/graph queries go to `PersistentKnowledgeLayer._hnsw_index`
- RAG queries go to `RAGEngine._hnsw_index`

**However**, if the same `KnowledgeNode` entity gets both:
1. An identity record in LanceDB (`add_entity()`)
2. A vector in the PersistentKnowledgeLayer HNSW

...then a cross-store query COULD produce divergent results because:
- LanceDB uses MLXEmbeddingManager for embeddings
- PersistentKnowledgeLayer uses SemanticFilter (Model2Vec) or custom embedder
- RAGEngine uses FastEmbed or custom embedder

**No evidence found** of cross-store queries in the codebase. Each store is queried independently.

### Additional Risk: Multiple HNSW Instances

Three separate HNSW indexes exist:
1. `persistent_layer.PersistentKnowledgeLayer._hnsw_index`
2. `rag_engine.RAGEngine._hnsw_index`
3. `memory_coordinator.MemoryCoordinator._hnsw_index`

If the same data is indexed in multiple places, **different results** can occur due to:
- Different `ef_search` / `M` parameters
- Different build orders
- Different embedding models used

---

## 4. Embedder Consistency Audit

| Store | Embedder | Fallback |
|-------|----------|----------|
| LanceDB | MLXEmbeddingManager → CoreML → NumPy | NumPy random |
| PersistentKnowledgeLayer | SemanticFilter (Model2Vec) or MLX | Linear search |
| RAGEngine | FastEmbed → NumPy | NumPy random |
| MemoryCoordinator | ? (lazy loaded) | ? |

**Risk:** If the same text is embedded by different stores using different embedders, cosine similarity scores will not be comparable across stores.

---

## 5. Consolidation Recommendation

### Option A: Unified LanceDB Store (RECOMMENDED)
Consolidate ALL vector storage into LanceDB:
- LanceDB already has: FTS, vector search, hybrid retrieval, MLX acceleration, LMDB cache
- Add: `PersistentKnowledgeLayer` entities as new table "knowledge_nodes"
- Add: Document chunks as new table "documents" (RAGEngine use case)
- Keep: Separate tables for domain separation but same embedding pipeline

**Pros:** Single embedder, single store, consistent embeddings
**Cons:** Requires refactoring PersistentKnowledgeLayer and RAGEngine to use LanceDB

### Option B: Keep Separate, Unify Embedder
- Create single `EmbeddingManager` that all stores use
- Keep LanceDB for identity, HNSW for graph, HNSW for RAG
- Add cross-store metadata linking (entity_id → node_id)

**Pros:** Less refactoring
**Cons:** Multiple vector stores, potential divergence, more RAM

### Option C: LanceDB + DuckDB (from Sprint 8BJ)
Per CLAUDE.md memory:
> DuckDB store: `knowledge/duckdb_store.py` — RAMDISK-first / OPSEC-safe degraded mode, lazy import

If DuckDB is the authoritative graph store, and LanceDB is the identity store, they serve different purposes and split-brain risk is acceptable as long as embeddings are consistent.

---

## 6. Verdict

| Finding | Risk Level |
|---------|------------|
| Three separate HNSW indexes (persistent_layer, rag_engine, memory_coordinator) | MEDIUM — wasted RAM, potential divergence |
| Three different embedder paths (MLXEmbeddingManager, SemanticFilter, FastEmbed) | HIGH — embeddings for same text will differ |
| LanceDB vs HNSW for same entity type | LOW — currently domain-separated |
| No cross-store queries found | LOW — but architecture is fragile |

**Recommended Action:** Sprint 8BW should implement Option A or B to unify the embedding pipeline. At minimum, create a shared `EmbeddingManager` singleton that all three stores import to ensure embedding consistency.

---

## Appendix: Key File Locations

| Component | File | Lines |
|-----------|------|-------|
| LanceDBIdentityStore | `knowledge/lancedb_store.py` | 58-1163 |
| LanceDB table schema | `knowledge/lancedb_store.py` | 870-880 |
| MLXEmbeddingManager wiring | `knowledge/lancedb_store.py` | 197-229 |
| PersistentKnowledgeLayer HNSW | `knowledge/persistent_layer.py` | 771-881 |
| RAGEngine HNSWVectorIndex | `knowledge/rag_engine.py` | 187-622 |
| RAGEngine build_hnsw | `knowledge/rag_engine.py` | 974-1047 |
| MemoryCoordinator HNSW | `coordinators/memory_coordinator.py` | 2366-2383 |
