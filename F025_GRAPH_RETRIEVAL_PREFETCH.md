# F025: Graph / Retrieval / Prefetch Inventory Scan

**Datum:** 2026-04-01
**Scope:** `hledac/universal/`
**Zdroje:** inventory scan 14 souborů napříč knowledge/, graph/, prefetch/, intelligence/

---

## 1. Executive Summary

| Plane | Primary Store | Alt. Backend | Algorithm Provider | Dormant |
|-------|--------------|--------------|-------------------|---------|
| **Graph** | `IOCGraph` (Kuzu) | `DuckPGQGraph` (DuckDB) | `QuantumInspiredPathFinder`, `GraphRAGOrchestrator` | `KnowledgeGraphBuilder` |
| **Retrieval** | `RAGEngine` (HNSW+BM25) | `LanceDBIdentityStore` (vector+FTS) | `SSMReranker` (v prefetch) | — |
| **Prefetch** | `PrefetchOracle` | — | `SSMReranker` | — |

**Klíčová rizika:**
1. Graph truth je fragmentovaný mezi Kuzu (`IOCGraph`) a DuckDB (`DuckPGQGraph`) — žádný unified owner
2. `RelationshipDiscoveryEngine` je současně algorithm provider pro graph I prefetch plane — cross-plane coupling
3. `PQIndex` má dual roli: compression sublayer PRO graph I přímý search v PrefetchOracle
4. `GraphRAGOrchestrator` importuje `RAGEngine` — retrieval-graph coupling
5. `DuckDBShadowStore` vs `DuckPGQGraph` — confusion risk (shadow ≠ graph backend)

---

## 2. Graph Backend Reconciliation

### 2.1 Truth Owner: `IOCGraph` (Kuzu)

**File:** `knowledge/ioc_graph.py`

```
Schema:
  IOC(id PK, ioc_type, value, first_seen, last_seen, confidence)
  OBSERVED(finding_id, source_type, first_seen, last_seen)
```

**Důkaz truth owner:**
- `buffer_ioc()` / `buffer_observation()` — zero I/O v ACTIVE fázi
- `flush_buffers()` — volá se v WINDUP (500-item trigger)
- `_upsert_ioc_batch_sync()` — přímý Kuzu executor
- `pivot()` — MATCH query přes Kuzu
- `export_stix_bundle()` — STIX 2.1 export přes Kuzu

**Lifecycle integrace:**
```python
# Sprint 8SA write buffer pattern
async def buffer_ioc(self, ioc_type, value, confidence):
    self._ioc_buffer.append((ioc_type, value, confidence))
    if len(self._ioc_buffer) >= self._BUFFER_FLUSH_SIZE:
        await self.flush_buffers()  # WINDUP only
```

### 2.2 Alternate Backend: `DuckPGQGraph` (DuckDB)

**File:** `graph/quantum_pathfinder.py` (line 969+)

```python
class DuckPGQGraph:
    """SQL/PGQ graph backend pres DuckDB."""
    def __init__(self, db_path: str | None = None):
        from paths import get_ioc_db_path  # local import
        _ensure_duckpgq(self.con)  # lazy extension load

    def find_connected(self, value, max_hops=2):
        # SQL:2023 MATCH clause s duckpgq
        # Fallback: recursive CTE
```

**Klíčové metody:**
- `find_connected()` — SQL/PGQ MATCH s recursive CTE fallback
- `merge_from_parquet()` — Arrow/Parquet import
- `export_edge_list()` — pro GNN inference
- `get_top_nodes_by_degree()` — degree centrality

**Důležité:** `_stable_node_id()` používá SHA1 (ne Python `hash()`) pro deterministické 63-bit ID napříč procesy.

### 2.3 Algorithm Providers

| Provider | File | Role |
|----------|------|------|
| `QuantumInspiredPathFinder` | `graph/quantum_pathfinder.py` | Quantum random walks, Grover amplification |
| `GraphRAGOrchestrator` | `knowledge/graph_rag.py` | Multi-hop reasoning, centrality, community detection |

**QuantumInspiredPathFinder:**
```python
# Lazy-loaded, MLX-accelerated
QUANTUM_PATHFINDER_AVAILABLE = True
try:
    from .quantum_pathfinder import QuantumInspiredPathFinder
except ImportError:
    QuantumInspiredPathFinder = None
```

**GraphRAGOrchestrator** (2550 lines):
- `multi_hop_search()` — hop 0 semantic search, hop 1..N graph traversal
- `calculate_centrality()` — degree, betweenness, closeness, eigenvector, PageRank
- `detect_communities()` — label propagation (Louvain-style)
- `find_contradictions()` — heuristic negation detection
- `calculate_network_metrics()` — density, clustering, path length

### 2.4 Graph Layer Facade

**File:** `knowledge/graph_layer.py`

```python
class KnowledgeGraphLayer:
    def __init__(self):
        self._kg = None           # PersistentKnowledgeLayer (Kuzu)
        self._graph_rag = None    # GraphRAGOrchestrator
        self._builder = None      # KnowledgeGraphBuilder
```

**Dependency chain:** `KnowledgeGraphLayer` → `PersistentKnowledgeLayer` + `GraphRAGOrchestrator`

### 2.5 Dormant Canonical: `KnowledgeGraphBuilder`

**File:** `knowledge/graph_builder.py`

Regex-based fact extraction (ne NLP). Napojení na `PersistentKnowledgeLayer`, ne na `IOCGraph přímo`.

---

## 3. Retrieval / Grounding Matrix

### 3.1 Primary Grounding: `RAGEngine`

**File:** `knowledge/rag_engine.py`

| Komponenta | Role |
|-----------|------|
| `HNSWVectorIndex` | HNSW approximate nearest neighbor (hnswlib) |
| `BM25Index` | Sparse retrieval (rank_bm25 library) |
| `Hybrid retrieval` | Dense (HNSW) + Sparse (BM25) fusion |

**Konfigurace:**
```python
RAGConfig:
    hnsw_dim: 768
    hnsw_max_elements: 100000
    hnsw_ef_search: 50
    dense_weight: 0.5, sparse_weight: 0.5
    chunk_size: 512, chunk_overlap: 128
```

**Retrieval flow:**
```
query → hybrid_retrieve() → HNSW (dense) + BM25 (sparse)
                          → weighted fusion
                          → RRF merge (pro multi-source)
```

### 3.2 Alt. Grounding: `LanceDBIdentityStore`

**File:** `knowledge/lancedb_store.py`

Hybrid (vector + FTS) pro entity resolution.

| Feature | Implementace |
|---------|-------------|
| Vector store | LanceDB |
| FTS | aliases_fts index |
| Cache | LMDB (float16 quantization, 50% RAM savings) |
| MLX acceleration | `_cosine_sim_batch` compiled |
| Binary embeddings | 64-bit Hamming pre-filter |
| Reranking | ColBERT (GPU), FlashRank (CPU), MLX fallback |
| MMR diversity | Max Marginal Relevance |

**Key methods:**
- `search_similar()` — pure vector search
- `search_similar_adaptive()` — thermal-aware adaptive reranking
- `_embed_single()` / `_embed_batch()` — MLX/GPU/CPU fallback chain

### 3.3 PQ jako Compression Sublayer

**File:** `knowledge/pq_index.py`

```
12x paměťová úspora (768 → 8 byte per vector)
OPQ preprocessing
Vrací: 1/(1+L2_distance) — konzistentní s HNSW cosine similarity
```

**Důležité:** PQ NENÍ primární semantic story. Je to compression sublayer pro embedding storage. Primární semantic search jde přes HNSW (`RAGEngine`) nebo LanceDB vector search.

### 3.4 DuckDB Shadow Store — NENÍ Graph Store

**File:** `knowledge/duckdb_store.py`

```
DuckDBShadowStore ≠ DuckPGQGraph
Shadow = analytical sidecar (sprint_delta, source_hit_log, sprint_scorecard)
Graph = DuckPGQGraph (ioc_nodes, ioc_edges)
```

**Schema (shadow):**
- `shadow_findings` — id, query, source_type, confidence, ts
- `shadow_runs` — run_id, started_at, ended_at, total_fds, rss_mb
- `sprint_delta` — sprint metrics
- `source_hit_log` — source-level hit rates

---

## 4. Prefetch Plane Matrix

### 4.1 Architektura

```
PrefetchOracle
├── Stage A: Candidate Generation
│   ├── Common neighbors (RelationshipDiscoveryEngine)
│   ├── PQIndex ANN search
│   └── Sketch deduplication (CountMinSketch, SimHashSketch)
├── Stage B: SSM Reranker (top-K)
└── LinUCB: Contextual Bandit (per-arm UCB)
```

**Dependency graph:**
```
PrefetchOracle
├── scheduler: ParallelResearchScheduler
├── rel_engine: RelationshipDiscoveryEngine
├── pq_index: PQIndex
└── cache: PrefetchCache
```

### 4.2 Stage A — Candidate Generation

**Time budget:** 1.5ms (adaptivní)

```python
# Dynamické limity (adaptivní podle klouzavého průměru)
_neighbors_limit = 10        # common neighbors
_pq_k = 5                   # PQ ANN results
_max_candidates_dynamic    # bounded by Stage A time
```

**Candidate sources:**
1. `rel_engine.get_common_neighbors(entity)` — graph neighbors
2. `pq_index.search(emb, k=_pq_k)` — approximate nearest neighbors
3. Sketch deduplication — CountMinSketch + SimHashSketch

### 4.3 Stage B — SSM Reranker

**File:** `prefetch/ssm_reranker.py`

```python
class SSMReranker(nn.Module):
    def __init__(self, feature_dim=137):
        self.embed = nn.Linear(feature_dim, 64)
        self.blocks = [SSMBlock(64) for _ in range(2)]
        self.out_proj = nn.Linear(64, 1)
```

**Feature dim = 137:**
- rank_norm: 1
- type_emb: 4 (graph, pq, pattern, other)
- stage_score: 1
- bandit_context: 64 + 3 + 64 = 131 (entity_emb + quality + task_emb)

**Depthwise benchmark:** Měří jestli depthwise conv je rychlejší než normální konvoluce, volí fast path.

### 4.4 LinUCB Bandit

```python
# Per-arm ridge regression
bandit_arms[arm_id] = {
    'A': np.eye(d) * lambda_prior,    # regularization
    'b': np.zeros(d),                   # observations
    'A_inv': np.linalg.inv(A)           # Sherman-Morrison updates
}
```

**Reward:**
- Cache hit: +1.0
- Prefetch miss: -(lambda_waste * cost)
- Expired: -(lambda_waste * 0.1)

### 4.5 Cache Backing: `PrefetchCache`

**File:** `prefetch/prefetch_cache.py`

```python
class PrefetchCache:
    # LMDB-backed LRU s TTL
    # Background writer (asyncio.Queue)
    # 100MB default, 10k entries max
```

### 4.6 Budget Tracker

**File:** `prefetch/budget_tracker.py`

Jednoduchý sliding window pro network a CPU:
- Network: 1-hour window
- CPU: 1-minute window

---

## 5. Hidden Couplings

### 5.1 Cross-Plane Coupling

| From | To | Coupling Type |
|------|-----|---------------|
| PrefetchOracle | RelationshipDiscoveryEngine | Přímé volání `get_common_neighbors()`, `get_entity_embedding()` |
| PrefetchOracle | PQIndex | `pq_index.search()` — ANN pro prefetch kandidáty |
| GraphRAGOrchestrator | RAGEngine | `await embedder._embed_text()` v `score_path()` |
| KnowledgeGraphLayer | PersistentKnowledgeLayer | Legacy wrapper |

### 5.2 Graph Internals Coupling

| Component | Accesses | Method |
|-----------|----------|--------|
| GraphRAGOrchestrator | `knowledge_layer._backend.get_node()` | `_traverse_hop_with_paths()`, `get_all_node_ids()` |
| GraphRAGOrchestrator | `knowledge_layer._backend.get_all_node_ids()` | `_get_all_node_ids()` |
| DuckPGQGraph | DuckDB connection | `duckdb.connect()` |

### 5.3 Export/Report → Graph Internals

**IOCGraph.export_stix_bundle():**
```python
def _export_stix_bundle_sync(self):
    res = conn.execute(
        "MATCH (n:IOC) RETURN n.id, n.ioc_type, n.value ..."
    )
    # STIX 2.1 object construction
```

**DuckPGQGraph.export_edge_list():**
```python
def export_edge_list(self) -> list[tuple[str, str, str, float]]:
    rows = con.execute("""
        SELECT s.value, d.value, e.rel_type, e.weight
        FROM ioc_edges e JOIN ioc_nodes ...
    """)
```

---

## 6. Canonical Candidates

### 6.1 Truth Owners

| Store | File | Canonical pro |
|-------|------|--------------|
| `IOCGraph` | `knowledge/ioc_graph.py` | IOC entity graph (Kuzu) |
| `RAGEngine` | `knowledge/rag_engine.py` | Semantic search (HNSW+BM25) |
| `LanceDBIdentityStore` | `knowledge/lancedb_store.py` | Identity resolution |
| `DuckDBShadowStore` | `knowledge/duckdb_store.py` | Sprint analytics (NENÍ graph) |

### 6.2 Algorithm Providers

| Provider | File | Algorithm |
|----------|------|-----------|
| `QuantumInspiredPathFinder` | `graph/quantum_pathfinder.py` | Quantum random walks |
| `GraphRAGOrchestrator` | `knowledge/graph_rag.py` | Multi-hop, centrality, community detection |
| `RelationshipDiscoveryEngine` | `intelligence/relationship_discovery.py` | Social network analysis |
| `SSMReranker` | `prefetch/ssm_reranker.py` | SSM-based reranking |
| `KnowledgeGraphBuilder` | `knowledge/graph_builder.py` | Regex-based fact extraction (dormant) |

### 6.3 Dormant Canonical

| Module | File | Status |
|--------|------|--------|
| `KnowledgeGraphBuilder` | `knowledge/graph_builder.py` | Regex extraction, nenahrazuje IOCGraph |
| `PersistentKnowledgeLayer` | `legacy/persistent_layer.py` | Legacy, IOCGraph je novější |

---

## 7. What Must NOT Be Merged Too Early

### 7.1 Graph Backends

**Kuzu (`IOCGraph`) ≠ DuckDB (`DuckPGQGraph`)**

Důvody:
- Různá schémata (IOC nodes vs ioc_nodes)
- Různé přístupy (MATCH clause vs recursive CTE)
- Různé lifecycle (write buffer vs checkpoint)
- DuckPGQGraph má `merge_from_parquet()` pro bulk import

**Ne mergeovat dokud:**
- [ ] DuckPGQGraph není plně otestovaný jako drop-in replacement
- [ ] IOCGraph write buffer pattern není portovaný do DuckPGQGraph
- [ ] STIX export není ověřený přes DuckDB backend

### 7.2 Retrieval vs Prefetch

**RAGEngine ≠ PrefetchOracle**

Důvody:
- RAGEngine: dense HNSW + sparse BM25 fusion, heavy compute
- PrefetchOracle: lightweight candidates + SSM reranker, strict time budget
- RAGEngine._embed_text() používá CoreML/MLX embedder
- PrefetchOracle používá entity embeddings přes RelationshipDiscoveryEngine

**Ne mergeovat dokud:**
- [ ] Prefetch oracle není stabilizovaný (LinUCB convergence)
- [ ] Společný embedding provider není definovaný
- [ ] Cache strategy není sjednocená

### 7.3 PQIndex Dual Role

**PQIndex jako compression sublayer ≠ PQIndex jako search index**

Důvody:
- V graph contextu: PQ komprese pro embedding storage
- V prefetch contextu: `pq_index.search()` pro ANN kandidáty
- Různé lifecycle (training vs inference)

**Ne mergeovat dokud:**
- [ ] PQ training pipeline není oddělený od search
- [ ] Embedding dim management není unified

### 7.4 DuckDB Shadow vs Graph

**DuckDBShadowStore ≠ DuckPGQGraph**

Důvody:
- Shadow: analytický sidecar pro sprint metrics
- Graph: graph store s MATCH clause
- Různá schémata, různý účel

---

## 8. Top 20 Konkrétních Ticketů

### Graph Backend (F10)

1. **[F10-G1]** Definovat graph truth owner explicitně — `IOCGraph` je canonical, `DuckPGQGraph` je alternate backend
2. **[F10-G2]** Oddělit `export_stix_bundle()` od Kuzu direct dependency — přes abstraktní rozhraní
3. **[F10-G3]** Portovat IOCGraph write buffer pattern do DuckPGQGraph pro konzistentní WINDUP
4. **[F10-G4]** Ověřit DuckPGQGraph `find_connected()` parity s IOCGraph `pivot()`
5. **[F10-G5]** Refaktorovat `GraphRAGOrchestrator._backend.get_node()` volání přes abstraktní rozhraní

### Retrieval Plane (F12)

6. **[F12-R1]** Definovat grounding authority — `RAGEngine` pro semantic search, `LanceDBIdentityStore` pro identity
7. **[F12-R2]** Extrahovat `HNSWVectorIndex` jako samostatný modul (耦开 RAGEngine coupling)
8. **[F12-R3]** Sjednotit embedding provider napříč `RAGEngine._embed_text()` a `PrefetchOracle._get_entity_embedding()`
9. **[F12-R4]** Dokumentovat PQIndex dual role (compression sublayer + ANN search) — NE mergeovat do jedno
10. **[F12-R5]** Ověřit `LanceDBIdentityStore` MMREvaluation parity s HNSW

### Prefetch Plane (F15)

11. **[F15-P1]** Definovat prefetch dependency gates — `RelationshipDiscoveryEngine` NESMÍ být coupling na graph truth
12. **[F15-P2]** Extrahovat `SSMReranker` jako sdílený modul (používá se pouze v prefetch)
13. **[F15-P3]** Refaktorovat `PrefetchOracle._get_common_neighbors()` přes abstraktní graph interface
14. **[F15-P4]** Sjednotit cache interface mezi `PrefetchCache` a `LanceDBIdentityStore._cache_env`
15. **[F15-P5]** Dokumentovat LinUCB cold-start strategii pro nové domény

### Hidden Couplings (F16)

16. **[F16-C1]** Odstranit přímé `RelationshipDiscoveryEngine` volání z PrefetchOracle — přes interface
17. **[F16-C2]** Refaktorovat `GraphRAGOrchestrator` → `RAGEngine` coupling přes sdílený embedder
18. **[F16-C3]** Definovat `PersistentKnowledgeLayer` vs `IOCGraph` vztah (legacy vs current)
19. **[F16-C4]** Oddělit `DuckDBShadowStore` namespace od `DuckPGQGraph` (confusion risk)
20. **[F16-C5]** Definovat cross-plane dependency rules — prefetch NESMÍ záviset na graph internals přímo

---

## 9. Exit Criteria

### F10 (Graph Backend Split)

```
[ ] IOCGraph zůstává canonical truth owner
[ ] DuckPGQGraph je alternate backend s explicitním feature flag
[ ] GraphRAGOrchestrator nepoužívá _backend.get_node() přímo
[ ] STIX export jde přes abstraktní rozhraní
[ ] Write buffer pattern je portovaný nebo dokumentovaný jako divergence
```

### F12 (Retrieval / Grounding)

```
[ ] RAGEngine je explicitní grounding authority pro semantic search
[ ] LanceDBIdentityStore je explicitní authority pro identity resolution
[ ] HNSWVectorIndex je extrahovaný jako standalone modul
[ ] Embedding provider má unified interface (CoreML/MLX/numpy fallback chain)
[ ] PQIndex role je dokumentovaná (compression ≠ primary search)
```

### F15 (Prefetch Plane)

```
[ ] PrefetchOracle má abstraktní interface pro graph dependencies
[ ] SSMReranker je sdílený modul mezi prefetch a budoucím retrieval
[ ] LinUCB convergence je monitorovaný (reward tracking)
[ ] BudgetTracker je integrovaný s orchestrátorovým memory management
[ ] Prefetch cache má explicitní TTL a eviction strategy
```

### F16 (Hidden Couplings)

```
[ ] Žádné cross-plane direct imports (PrefetchOracle ↔ RelationshipDiscoveryEngine)
[ ] GraphRAGOrchestrator má abstraktní interface místo _backend.get_node()
[ ] DuckDBShadowStore a DuckPGQGraph jsou v oddělených namespace
[ ] Cross-plane dependency rules jsou dokumentované v CLAUDE.md
[ ] žádné "god object" v knowledge/ graph/ prefetch/
```

---

## 10. What This Changes in Graph/Retrieval Ordering

### Current State

```
Graph: IOCGraph (Kuzu) ←→ DuckPGQGraph (DuckDB)
                          ↑
                          │ (confusion)
Retrieval: RAGEngine ←→ LanceDBIdentityStore
                  ↑
                  │ (GraphRAG coupling)
                  ↓
Prefetch: PrefetchOracle → RelationshipDiscoveryEngine → Graph internals
```

### Target State

```
                    ┌─────────────────────────────────────┐
                    │        Abstraction Layer            │
                    │  (GraphInterface, EmbedderInterface) │
                    └─────────────────────────────────────┘
                                    ↑
        ┌───────────────────────────┼───────────────────────────┐
        ↓                           ↓                           ↓
   Graph Plane               Retrieval Plane               Prefetch Plane
   ┌─────────────┐           ┌─────────────┐           ┌─────────────┐
   │ IOCGraph    │           │ RAGEngine   │           │PrefetchOracle│
   │ (canonical) │           │ (grounding) │           │             │
   ├─────────────┤           ├─────────────┤           ├─────────────┤
   │DuckPGQGraph │           │LanceDBIdSt. │           │ SSMReranker │
   │ (alternate) │           │ (identity)  │           │             │
   └─────────────┘           └─────────────┘           └─────────────┘
```

### Dependency Rules (New)

1. **Prefetch plane** NESMÍ importovat z `knowledge/ioc_graph.py`, `knowledge/graph_rag.py`, `intelligence/relationship_discovery.py` přímo
2. **Retrieval plane** NESMÍ importovat z graph plane modules přímo
3. **Graph plane** NESMÍ importovat z prefetch plane modules
4. Všechny cross-plane závislosti jdou přes abstraktní interface definované v `knowledge/interfaces.py`

### Ordering Implications

| Pokud děláme F10 | Pak F12 závisí na | Blocker? |
|-----------------|-------------------|----------|
| Graph truth owner | Embedding provider unified | Ne, ale doporučeno |
| Graph interface | RAGEngine refactoring | Ano, pokud RAGEngine používá graph internals |

| Pokud děláme F15 | Pak F16 závisí na | Blocker? |
|-----------------|-------------------|----------|
| Prefetch abstraction | RelationshipDiscoveryEngine isolation | Ano, cross-plane coupling |

**Doporučené pořadí:** F16 (couplings) → F10 (graph split) → F12 (retrieval) → F15 (prefetch)

---

*Report generován na základě inventory scanu 14 souborů: ioc_graph.py, quantum_pathfinder.py, graph_rag.py, graph_layer.py, graph_builder.py, rag_engine.py, lancedb_store.py, duckdb_store.py, pq_index.py, prefetch_oracle.py, prefetch_cache.py, budget_tracker.py, ssm_reranker.py, relationship_discovery.py*
