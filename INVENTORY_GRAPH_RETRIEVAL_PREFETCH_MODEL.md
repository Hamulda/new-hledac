# INVENTORY: Graph / Retrieval / Prefetch / Model Planes
**Datum:** 2026-04-01
**Scope:** `hledac/universal/` — všechny subsystemy

---

## 1. Executive Summary

Systém má 4 fundamentálně odlišné plane, každá s vlastní sadou ownerů:

| Plane | Canonical Store | Algorithm Provider | Alternate Backend |
|-------|---------------|-------------------|-------------------|
| **Graph** | `knowledge/ioc_graph.py` (Kuzu) | `graph/quantum_pathfinder.py::QuantumInspiredPathFinder` | `graph/quantum_pathfinder.py::DuckPGQGraph` (SQL/PGQ) |
| **Retrieval/Semantic** | `knowledge/lancedb_store.py` (vectors) | `knowledge/rag_engine.py` (HNSW+BM25) | — |
| **Prefetch** | `prefetch/prefetch_cache.py` (LMDB) | `prefetch/prefetch_oracle.py` (Stage A+B) | — |
| **Model-Control** | `brain/model_lifecycle.py` (unload truth) | `brain/model_manager.py` (acquire/routing) | `brain/dynamic_model_manager.py` (ANE LRU) |

**Kritický nález:** `DuckPGQGraph` a `ioc_graph.py` (Kuzu) nejsou peer backends — `DuckPGQGraph` je **alternate donor** vzniklý Sprint 8VE pro SQL/PGQ path queries, zatímco Kuzu zůstává kanonickým truth storem. Oba se používají v `runtime/sprint_scheduler.py` a `runtime/windup_engine.py`, ale žádný modul je nekonzoliduje.

**Druhý kritický nález:** `capabilities.py::ModelLifecycleManager` (phase enforcement) a `brain/model_lifecycle.py` (unload order) jsou rozděleny, ale jejich call-sites v `legacy/autonomous_orchestrator.py` a `windup_engine.py` volají oba bez jasného oddělení kompetencí.

---

## 2. Graph Backend Reconciliation

### 2.1 Canonical Truth Owner

**`knowledge/ioc_graph.py` — Kuzu-backed IOC Graph**

```
Schema: IOC(id, ioc_type, value, first_seen, last_seen, confidence)
        OBSERVED(finding_id, source_type, first_seen, last_seen)
Backend: Kuzu 0.11+ (single-thread executor)
Write strategy: Sprint 8SA — buffer v ACTIVE, flush v WINDUP (500-item trigger)
```

**Evidence (ioc_graph.py:107-131):**
- `_ioc_buffer`, `_obs_buffer` — in-memory akumulátory
- `buffer_ioc()`, `buffer_observation()` — ZERO Kuzu I/O v ACTIVE
- `flush_buffers()` — bulk flush na WINDUP
- `upsert_ioc_batch()` — batch node insert
- `record_observation_batch()` — batch edge insert
- `pivot()` — Kuzu MATCH pro 1-2 depth traversal
- `export_stix_bundle()` — STIX 2.1 export

### 2.2 Alternate Backend Donor

**`graph/quantum_pathfinder.py::DuckPGQGraph` — SQL/PGQ Graph Backend**

```python
# quantum_pathfinder.py:969-1142
class DuckPGQGraph:
    # SQL:2023 MATCH clause + duckpgq extension
    # Fallback: recursive CTE
    # Schema: ioc_nodes(id, value, ioc_type, confidence, source)
    #         ioc_edges(src_id, dst_id, rel_type, weight, evidence)
```

**Evidence (quantum_pathfinder.py:969-1175):**
- `merge_from_parquet()` — Arrow/Parquet import (Sprint 8VE)
- `export_edge_list()` — edge list pro GNN inference (vrací `(src, dst, rel_type, weight)`)
- `find_connected()` — SQL/PGQ MATCH nebo recursive CTE fallback
- `get_top_nodes_by_degree()` — top-N podle out-degree
- `checkpoint()` — DuckDB WAL flush

**Použití:**
- `runtime/sprint_lifecycle.py:299` — instantiace při WARMUP
- `runtime/sprint_scheduler.py:1147-1148` — fallback pokud Kuzu nedostupný
- `brain/gnn_predictor.py:581` — bridge funkce `predict_from_edge_list()`

### 2.3 Algorithm Provider

**`graph/quantum_pathfinder.py::QuantumInspiredPathFinder` — Quantum-Inspired Pathfinding**

```
Ne POŽÍVÁ DuckPGQGraph ani Kuzu — pracuje s NetworkX/dict/numpy input.
Je to ČISTÝ algorithm provider, ne graph store.
```

**Evidence (quantum_pathfinder.py:69-927):**
- `initialize()` — přijímá NetworkX graph, adjacency list, nebo numpy matrix
- `find_paths()` — Grover-style amplitude amplification + quantum random walks
- `_quantum_walk_step()` — coin + shift operátory
- `amplify_targets()` — Grover diffusion operator
- MLX/NumPy dual backend

### 2.4 Graph Hooks v duckdb_store.py

**`knowledge/duckdb_store.py` — NENÍ graph backend**

```
DUCKDB SHADOW STORE — analytics sidecar, ne graph store.
Schema: shadow_findings, shadow_runs (pro analytics, ne pro IOC graph)
```

**Důležité:** `DuckDBShadowStore` a `DuckPGQGraph` jsou DVĚ ODLIŠNÉ věci:
- `DuckDBShadowStore` = shadow analytics (Sprint 8AO)
- `DuckPGQGraph` = SQL/PGQ graph backend (Sprint 8VE)

### 2.5 Reconciliation Tabulka

| Operace | Kanonický Owner | Donor/Alt | Algorithm |
|---------|----------------|-----------|-----------|
| IOC upsert (single) | `ioc_graph.py` | — | — |
| IOC upsert (batch) | `ioc_graph.py` | — | — |
| OBSERVED edge (single) | `ioc_graph.py` | — | — |
| OBSERVED edge (batch) | `ioc_graph.py` | — | — |
| 1-2 hop pivot | `ioc_graph.py` | — | — |
| SQL/PGQ path query | — | `DuckPGQGraph` | — |
| Recursive CTE fallback | — | `DuckPGQGraph` | — |
| Parquet import | — | `DuckPGQGraph` | — |
| GNN edge list export | `DuckPGQGraph` | — | — |
| Top-N by degree | `DuckPGQGraph` | — | — |
| Quantum pathfinding | — | — | `QuantumInspiredPathFinder` |
| GraphRAG multi-hop | — | — | `GraphRAGOrchestrator` |
| STIX 2.1 export | `ioc_graph.py` | — | — |

### 2.6 Konflikty

1. **Dvě graph backendy bez konsolidace:** `ioc_graph.py` (Kuzu) a `DuckPGQGraph` (DuckDB) žijí paralelně. `SprintScheduler` drží reference na oba (`_ioc_graph` = Kuzu, DuckPGQGraph se vytváří lokálně). Žádný unify layer.

2. **Není jasné kdy použít který:** `windup_engine.py` volá `scheduler._ioc_graph.stats()` a `scheduler._ioc_graph.get_top_nodes_by_degree()` — ale `get_top_nodes_by_degree()` je metoda `DuckPGQGraph`, ne `IOCGraph`.

3. **`export_edge_list()` split:** GNN predictor volá `DuckPGQGraph.export_edge_list()`, ale `windup_engine.py` používá `scheduler._ioc_graph.export_edge_list()` — to by měl být `DuckPGQGraph`.

---

## 3. Retrieval / Grounding Matrix

### 3.1 Moduly

| Modul | Role | Backend | Algorithm |
|-------|------|---------|-----------|
| `knowledge/rag_engine.py` | Hybrid retrieval engine | HNSWVectorIndex (hnswlib) + BM25Index | cosine similarity + BM25 |
| `knowledge/lancedb_store.py` | Entity identity store | LanceDB + LMDB cache | MLX cosine similarity |
| `knowledge/pq_index.py` | Compression layer | In-memory centroids | Product Quantization |
| `knowledge/graph_rag.py` | Multi-hop reasoning | KuzuDB (via knowledge_layer) | centrality, community detection |

### 3.2 RAG Engine Detail

**`knowledge/rag_engine.py` — Hybrid Retrieval (HNSW + BM25)**

```python
# rag_engine.py:50-76 — RAGConfig
RAGConfig:
  enable_hybrid_retrieval: bool = True
  dense_weight: float = 0.5    # HNSW
  sparse_weight: float = 0.5    # BM25
  use_hnsw: bool = True
  hnsw_dim: int = 768
  hnsw_M: int = 16
  hnsw_ef_construction: int = 200
  hnsw_ef_search: int = 50
```

**Evidence (rag_engine.py:101-184):**
- `BM25Index` — pure Python BM25 implementation + optional `rank_bm25` library
- `HNSWVectorIndex` — hnswlib wrapper, cosine/ip/l2 metric
- `search()` — fúze `dense_score * dense_weight + sparse_score * sparse_weight`
- `Document`, `RetrievedChunk` dataclassy

### 3.3 LanceDB Identity Store Detail

**`knowledge/lancedb_store.py` — Entity Identity Stitching**

```python
# lancedb_store.py:58-163
class LanceDBIdentityStore:
  # Sprint 76: LMDB embedding cache (float16, 50% RAM savings)
  # Sprint 76: Binary embeddings (32x compression)
  # Sprint 76: MMR diversity filtering
  # Sprint 76: Adaptive reranking (ColBERT/FlashRank/MLX)
  # Sprint 77: Writeback buffer (1000-item)
  # Sprint 81: MLXEmbeddingManager reference
```

### 3.4 PQ Index Detail

**`knowledge/pq_index.py` — Product Quantization Compression**

```python
# pq_index.py:22-56
class PQIndex:
  # OPQ preprocessing
  # Výstup: cosine similarity 1/(1+L2)
  # 12× paměťová úspora (768 → 8 byte per vector)
  # m=96 sub-vectors, k=256 centroids per sub-vector
```

### 3.5 GraphRAG Detail

**`knowledge/graph_rag.py` — Multi-Hop Reasoning**

```python
# graph_rag.py:77-103
class GraphRAGOrchestrator:
  MAX_QUEUE_LENGTH = 100
  MAX_VISITED_NODES = 500
  MAX_EXPANSION_PER_NODE = 10

  # Multi-hop traversal přes KuzuDB (disk-based)
  # score_path() — path scoring s embeddingy
  # centrality analysis, community detection
```

### 3.6 Grounding Matrix

| Zdroj | RAG Engine | LanceDB | PQ Index | GraphRAG |
|-------|-------------|---------|----------|----------|
| Web documents | ✅ HNSW + BM25 | — | — | — |
| IOC entities | — | ✅ Hybrid + FTS | ✅ Compression | ✅ Multi-hop |
| Findings (canonical) | ✅ Hybrid | — | — | — |
| Entity resolution | — | ✅ Vector + FTS | ✅ PQ codes | — |
| Graph traversal | — | — | — | ✅ Kuzu backend |

### 3.7 Konflikty

1. **RAG Engine a LanceDB jsou oddělené systemy** bez jasného unify. RAG Engine indexuje documents, LanceDB indexuje entity identities. Není žádný layer který by mezi nimi konsolidoval.

2. **PQ Index je standalone** — používá se v `prefetch_oracle.py` pro Stage A candidate selection, ale není propojen s HNSW v rag_engine.

---

## 4. Prefetch Dependency Matrix

### 4.1 Moduly

| Modul | Role | Klíčová data |
|-------|------|-------------|
| `prefetch/prefetch_oracle.py` | Two-stage URL selection | candidates, SSM reranker, LinUCB bandit |
| `prefetch/prefetch_cache.py` | LMDB-backed storage | TTL, LRU, background writer |
| `prefetch/budget_tracker.py` | Network/CPU budget | Sliding window budgeting |

### 4.2 PrefetchOracle Detail

**`prefetch_oracle.py:38-95` — Two-Stage Architecture**

```
Stage A (≤1.5ms):
  - Common neighbors (max 10)
  - PQ index lookup (k=5)
  - CountMinSketch + SimHashSketch dedup
  - Adaptive limits (klouzavý průměr)

Stage B (ML reranker):
  - SSMReranker (state-space model)
  - LinUCB contextual bandit (64+3+64 dim feature vector)
  - UCB score combination
```

**Dependencies (prefatch_oracle.py:19-23):**
```python
from hledac.universal.research.parallel_scheduler import ParallelResearchScheduler
from hledac.universal.intelligence.relationship_discovery import RelationshipDiscoveryEngine
from hledac.universal.federated.sketches import CountMinSketch, SimHashSketch
from hledac.universal.knowledge.pq_index import PQIndex
from hledac.universal.prefetch.prefetch_cache import PrefetchCache
```

### 4.3 PrefetchCache Detail

**`prefetch_cache.py` — LMDB-backed prefetch cache**

```python
# prefetch_cache.py:15-29
class PrefetchCache:
  # max_size_mb: int = 100
  # max_entries: int = 10000
  # async writer queue + background task
  # TTL support
  # LRU eviction via access_count
```

### 4.4 BudgetTracker Detail

**`prefetch/budget_tracker.py` — Network/CPU budgeting**

```python
# budget_tracker.py:9-35
class BudgetTracker:
  # network_mb_per_hour: float = 10.0
  # cpu_ms_per_min: float = 100.0
  # Sliding window: 1h network, 1min CPU
  # can_afford() — budget check
  # record() — usage tracking
```

### 4.5 Dependency Flow

```
BudgetTracker
    ↓ (can_afford check)
PrefetchOracle.on_new_candidates()
    ↓ (Stage A candidates)
PQIndex.search() + CountMinSketch + SimHashSketch
    ↓ (filtered candidates)
SSMReranker + LinUCB bandit
    ↓ (top-K URLs)
PrefetchCache.put()
    ↓ (LMDB storage)
Scheduler/ResearchWorker fetch
```

### 4.6 Konflikty

1. **BudgetTracker není integrován do PrefetchOracle:** `can_afford()` existuje, ale `on_new_candidates()` ji nevolá. Budget tracking je přítomen ale nepoužíván se v premarket path.

2. **PrefetchOracle má vlastní adaptivní limity** (`_neighbors_limit`, `_pq_k`, `_max_candidates_dynamic`) které jsou nezávislé na `BudgetTracker`. Dva nezávislé budgetovací systémy.

---

## 5. Model-Control Split Owners

### 5.1 Canonical Lifecycle Owners

| Komponenta | Soubor | Role |
|-----------|--------|------|
| `ModelManager` | `brain/model_manager.py:89` | **Acquire owner** — load model, 1-model-at-a-time, phase-to-model mapping |
| `ModelLifecycle` | `brain/model_lifecycle.py` | **Unload-cleanup owner** — 7K unload order, emergency unload |
| `DynamicModelManager` | `brain/dynamic_model_manager.py` | **ANE LRU + CoreML** — ANE compilation tracking, coremltools caching |
| `ModelSwapManager` | `brain/model_swap_manager.py` | **Swap arbiter** — Qwen↔Hermes race-free swap |
| `ModelLifecycleManager` | `capabilities.py:279` | **Phase enforcer** — enforce_phase_models(), BRAIN/TOOLS/SYNTHESIS/CLEANUP |

### 5.2 ModelManager — Acquire Owner

**Evidence (model_manager.py:47-149):**

```python
class ModelManager:
  # MODEL_REGISTRY: hermes → HERMES, modernbert → MODERNBERT, gliner → GLINER
  # PHASE_MODEL_MAP:
  #   PLAN/DECIDE/SYNTHESIZE → hermes
  #   EMBED/DEDUP/ROUTING → modernbert
  #   NER/ENTITY → gliner
  # _current_model: Optional[ModelType] — single active model
  # model_lifecycle() — async context manager
```

**Phase enforcement:**
- `model_lifecycle()` context manager — yield model, v finally release + gc.collect() + mx.clear_cache()
- `_load_model_async()` — load dle ModelType
- `_release_current_async()` — unload current

### 5.3 ModelLifecycle — Unload-Cleanup Owner

**Evidence (model_lifecycle.py:1-107):**

```python
# Canonical 7K unload order (SSOT):
# 1. _shutdown_batch_worker(timeout=3.0)
# 2. _batch_queue = None + _batch_worker_task = None
# 3. _warmup_cache eviction
# 4. _save_cache()
# 5. _prompt_cache / _system_prompt_cache eviction
# 6. invalidate_prefix_cache()
# 7. _model = None + _tokenizer = None + _outlines_model = None
# 8. gc.collect()
# 9. mx.eval([]) + mx.metal.clear_cache()

unload_model()  # helper s fail-open
is_safe_to_clear_emergency()  # 7K safe-clear preconditions
request_emergency_unload()  # watchdog flag
```

### 5.4 DynamicModelManager — ANE LRU Owner

**Evidence (dynamic_model_manager.py:1-150+):**

```python
# ANE compilation tracking (limit 119)
# _ane_lock, _ane_compile_counter, ANE_COMPILE_LIMIT = 119
# _load_or_compile_mps() — MPSGraphPackage caching
# _load_coreml_model() — CoreML conversion s hash-based cache
# LRU eviction pro modely
```

### 5.5 ModelSwapManager — Swap Arbiter

**Evidence (model_swap_manager.py:1-148+):**

```python
class ModelSwapManager:
  # ModelLifecycleProtocol — injected lifecycle contract
  # SwapResult, SwapStatus, DrainResult — typed results
  # async_swap_to(target_model) — race-free swap
  # Protokol: drain → unload → load → rollback on failure
```

### 5.6 ModelLifecycleManager — Phase Enforcer

**Evidence (capabilities.py:287-369):**

```python
class ModelLifecycleManager:
  # enforce_phase_models(phase_name):
  #   BRAIN → Hermes loaded, ModernBERT+GLiNER released
  #   TOOLS → Hermes released, ModernBERT/GLiNER on-demand
  #   SYNTHESIS → Hermes loaded, others released
  #   CLEANUP → all released
  # load_model_for_task() — single-model constraint
```

### 5.7 Call-Sites v Hot-Path

| Soubor | Volá | Účel |
|--------|------|------|
| `runtime/windup_engine.py:134-136` | `ModelLifecycle()` | SynthesisRunner construction |
| `legacy/autonomous_orchestrator.py:1753` | `ModelLifecycleManager` | Phase enforcement |
| `coordinators/graph_coordinator.py` | žádného z nich přímo | Graph reasoning delegation |
| `runtime/sprint_lifecycle.py` | žádného z nich přímo | Sprint phase management |

### 5.8 Split Owners Detail

| Owner | Phase Enforcer | Acquire | Unload-Cleanup | Routing Advisor | Compat Shim |
|-------|---------------|---------|----------------|----------------|-------------|
| `ModelManager` | — | ✅ primary | — | ✅ PHASE_MODEL_MAP | — |
| `ModelLifecycle` | — | — | ✅ 7K order | — | ✅ fail-open |
| `DynamicModelManager` | — | — | ✅ ANE LRU | — | ✅ CoreML |
| `ModelSwapManager` | — | ✅ swap | ✅ swap | — | — |
| `ModelLifecycleManager` | ✅ enforce_phase | — | — | — | — |

---

## 6. Authority Conflicts

### 6.1 Graph — DuckPGQGraph vs Kuzu IOCGraph

**Konflikt:** Dva graph backendy bez konsolidace.

```
runtime/sprint_scheduler.py drží:
  - self._ioc_graph → IOCGraph (Kuzu)
  - DuckPGQGraph se vytváří lokálně v různých funkcích

windup_engine.py očekává:
  - scheduler._ioc_graph.stats() → IOCGraph.stats() ✅
  - scheduler._ioc_graph.get_top_nodes_by_degree() → DuckPGQGraph method ❌
```

**Toto je BUG: `get_top_nodes_by_degree` je metoda `DuckPGQGraph`, ne `IOCGraph`.**

### 6.2 Model — ModelLifecycleManager vs ModelLifecycle

**Konflikt:** Phase enforcement (`capabilities.py`) a unload order (`model_lifecycle.py`) nejsou konzistentně odděleny.

```
autonomous_orchestrator.py:1753:
  ModelLifecycleManager — phase enforcement

windup_engine.py:134-136:
  ModelLifecycle() — přímo vytváří SynthesisRunner
```

ModelLifecycleManager Enforces phase → ale windup_engine.py obchází jeho abstrakci a volá ModelLifecycle přímo pro SYNTHESIS runner construction.

### 6.3 Prefetch — BudgetTracker vs Oracle Adaptive Limits

**Konflikt:** Dva nezávislé budgetovací systémy.

```
BudgetTracker:
  - can_afford(network_mb, cpu_ms) → bool
  - record(network_mb, cpu_ms)

PrefetchOracle:
  - _neighbors_limit, _pq_k, _max_candidates_dynamic
  - Adaptivní limiting na základě _stage_a_time_accum
```

`can_afford()` není volána z `on_new_candidates()`.

---

## 7. Recommended Canonical Owners

### 7.1 Graph Plane

| Operace | Canonical Owner | Zdrojový soubor |
|---------|----------------|----------------|
| IOC node/edge CRUD | `IOCGraph` | `knowledge/ioc_graph.py` |
| SQL/PGQ path queries | `DuckPGQGraph` | `graph/quantum_pathfinder.py` |
| Quantum pathfinding algorithm | `QuantumInspiredPathFinder` | `graph/quantum_pathfinder.py` |
| GraphRAG multi-hop | `GraphRAGOrchestrator` | `knowledge/graph_rag.py` |
| GNN inference | `GNNPredictor` | `brain/gnn_predictor.py` |
| **Unify layer (není implementován)** | — | — |

### 7.2 Retrieval Plane

| Operace | Canonical Owner | Zdrojový soubor |
|---------|----------------|----------------|
| Document retrieval (hybrid) | `RAGEngine` | `knowledge/rag_engine.py` |
| Entity identity (vector+FTS) | `LanceDBIdentityStore` | `knowledge/lancedb_store.py` |
| Embedding compression | `PQIndex` | `knowledge/pq_index.py` |
| Graph reasoning | `GraphRAGOrchestrator` | `knowledge/graph_rag.py` |

### 7.3 Prefetch Plane

| Operace | Canonical Owner | Zdrojový soubor |
|---------|----------------|----------------|
| URL selection (Stage A+B) | `PrefetchOracle` | `prefetch/prefetch_oracle.py` |
| Prefetch storage | `PrefetchCache` | `prefetch/prefetch_cache.py` |
| Budget coordination | `BudgetTracker` | `prefetch/budget_tracker.py` |

**Doporučení:** Integrovat `BudgetTracker.can_afford()` do `PrefetchOracle.on_new_candidates()`.

### 7.4 Model-Control Plane

| Operace | Canonical Owner | Zdrojový soubor |
|---------|----------------|----------------|
| Phase enforcement | `ModelLifecycleManager` | `capabilities.py` |
| Model acquire | `ModelManager` | `brain/model_manager.py` |
| Unload order (7K) | `ModelLifecycle` | `brain/model_lifecycle.py` |
| ANE/CoreML management | `DynamicModelManager` | `brain/dynamic_model_manager.py` |
| Swap arbitration | `ModelSwapManager` | `brain/model_swap_manager.py` |

---

## 8. Top 15 Konkrétních Ticketů

| # | Ticket | Priority | Plane | Popis |
|---|--------|----------|-------|-------|
| 1 | **BUGFIX: get_top_nodes_by_degree na IOCGraph** | CRITICAL | Graph | `IOCGraph` nemá `get_top_nodes_by_degree()` — volání z `windup_engine.py:83` failuje. Nutné přesunout na správný backend. |
| 2 | **Graph Unify Layer** | HIGH | Graph | Implementovat konsolidační vrstvu nad Kuzu IOCGraph a DuckPGQGraph. Určit kdy použít který. |
| 3 | **DuckPGQGraph lifecycle management** | HIGH | Graph | DuckPGQGraph je vytvářen ad-hoc v různých funkcích bez jasného lifecycle. Sjednotit přes SprintScheduler. |
| 4 | **BudgetTracker integrace** | HIGH | Prefetch | `PrefetchOracle.on_new_candidates()` nevolá `BudgetTracker.can_afford()`. Připojit budget check. |
| 5 | **PrefetchOracle ↔ RAGEngine PQIndex link** | MEDIUM | Retrieval | `PrefetchOracle` používá `PQIndex` Stage A, ale `RAGEngine` má vlastní HNSW. Propojit je. |
| 6 | **ModelSwapManager ↔ ModelManager reconciliation** | HIGH | Model | `windup_engine.py` obchází `ModelSwapManager` a volá `ModelManager` přímo pro synthesis runner. |
| 7 | **Phase enforcement boundary** | HIGH | Model | `ModelLifecycleManager.enforce_phase_models()` a `ModelLifecycle.unload_model()` — jasně oddělit kompetence. |
| 8 | **DynamicModelManager ANE limit tracking** | MEDIUM | Model | ANE compilation counter (`_ane_compile_counter`) je modulová proměnná. Přesunout do instance. |
| 9 | **GNNPredictor duckpgq bridge cleanup** | MEDIUM | Graph | `brain/gnn_predictor.py:581` — bridge funkce `predict_from_edge_list()` závisí na DuckPGQGraph. Zajistit stabilní kontrakt. |
| 10 | **LanceDB ↔ RAGEngine overlap** | MEDIUM | Retrieval | LanceDB a RAGEngine jsou dva nezávislé retrieval systémy. Určit jasný scope každého. |
| 11 | **PrefetchCache TTL implementace** | LOW | Prefetch | `PrefetchCache` má TTL parameter v `put()`, ale expiration check je v `get()`. Pokud cache nerestartuje, expirace se nekontroluje. |
| 12 | **DuckDBShadowStore ≠ Graph backend** | MEDIUM | Graph | Zaměnitelnost jmen — `duckdb_store.py` obsahuje `DuckDBShadowStore` (analytics), ne graph store. Přejmenovat pro jasnost. |
| 13 | **QuantumInspiredPathFinder isolation** | MEDIUM | Graph | `QuantumInspiredPathFinder` přijímá NetworkX/dict/numpy, ne pracuje s Kuzu/DuckPGQGraph. Zajistit konzistentní data flow. |
| 14 | **Emergency unload seam audit** | HIGH | Model | `is_safe_to_clear_emergency()` — volat z `windup_engine.py` před synthesis runner construction. |
| 15 | **SprintScheduler dual graph reference** | HIGH | Graph | `SprintScheduler` drží `self._ioc_graph` (Kuzu) ale `DuckPGQGraph` se vytváří odděleně. Konsolidovat do jedné reference. |

---

## 9. Exit Criteria pro Fáze

### F6.5

**Scope:** Graph backend split dokončen

| Criterion | Měřítko | Status |
|-----------|---------|--------|
| IOCGraph má jasný kontrakt | `pivot()`, `upsert_ioc_batch()`, `record_observation_batch()` jsou jediné veřejné write API | ⬜ |
| DuckPGQGraph kontrakt stabilní | `find_connected()`, `export_edge_list()`, `get_top_nodes_by_degree()` — pouze DuckPGQGraph | ⬜ |
| Žádné volání `get_top_nodes_by_degree()` na IOCGraph | grep v celém codebase | ⬜ |
| SprintScheduler drží jedinou graph referenci | buď DuckPGQGraph nebo wrapraper, ne oba odděleně | ⬜ |

### F10

**Scope:** Retrieval/Semantic plane konsolidace

| Criterion | Měřítko | Status |
|-----------|---------|--------|
| RAGEngine a LanceDB mají oddělené scope | RAGEngine = documents, LanceDB = entity identities | ⬜ |
| PQIndex používá sdílený embedder | `MLXEmbeddingManager` z `lancedb_store.py` | ⬜ |
| GraphRAG má明确ní backend kontrakt | GraphRAGOrchestrator přijímá pouze KuzuDB-backed knowledge_layer | ⬜ |
| Žádné duplicitní indexing | stejný text se neindexuje v obou systémech | ⬜ |

### F12

**Scope:** Prefetch plane integrace

| Criterion | Měřítko | Status |
|-----------|---------|--------|
| BudgetTracker.can_afford() je volána z PrefetchOracle | integration test s mock BudgetTracker | ⬜ |
| Adaptivní limity PrefetchOracle respektují BudgetTracker | when budget exhausted, Stage A limits constricted | ⬜ |
| PrefetchCache TTL expiration funguje i bez restartu | background expiration task, ne jen get-time check | ⬜ |
| PQIndex Stage A a HNSW Stage B jsou propojeny | stejný embedder, konzistentní feature prostor | ⬜ |

### F15

**Scope:** Model-control reconciliation

| Criterion | Měřítko | Status |
|-----------|---------|--------|
| ModelLifecycleManager je jediný phase enforcer | `windup_engine.py` volá pouze `ModelLifecycleManager`, ne přímo ModelLifecycle | ⬜ |
| 7K unload order zůstává v ModelLifecycle | `hermes3_engine.py` je jediný implementor 7K order | ⬜ |
| ModelSwapManager je použit pro všechny swap operace | žádné přímé `ModelManager._release_current_async()` mimo SwapManager | ⬜ |
| DynamicModelManager ANE counter je per-instance | žádné modulové proměnné pro ANE state | ⬜ |
| Emergency unload seam je spotřebováván | `windup_engine.py` volá `is_safe_to_clear_emergency()` před synthesis | ⬜ |

---

## What must NOT be merged too early

1. **DuckPGQGraph → Kuzu IOCGraph merger**
   - Příliš brzké sloučení zničí Sprint 8VE alternate backend experiment
   - DuckPGQGraph má SQL/PGQ path queries které Kuzu nemá
   - Nutné nejprve určit provozní charakteristiky obou v produkci

2. **RAGEngine ↔ LanceDB unify**
   - RAGEngine je document-centric, LanceDB je entity-centric
   - Pokus o sloučení by zničil distinct trust boundaries
   - Nejprve definovat jasný handoff protokol mezi nimi

3. **ModelSwapManager jako jediný swap arbiter**
   - Současný `ModelManager._release_current_async()` v `windup_engine.py` obchází SwapManager
   - Příliš brzké forced adoption by způsobilo breaking changes v synthesis runner
   - Nejprve refactorovat windup_engine na použití SwapManager, pak mandatorní

4. **BudgetTracker jako mandatory prefetch gate**
   - V současnosti `BudgetTracker.can_afford()` existuje ale není volána
   - Přinucení přes rewrite by mohlo zničit working prefetch strategii
   - Nejprve integrovat jako opt-in, pak mandatory

5. **QuantumInspiredPathFinder s Kuzu backend**
   - QPF je čistý in-memory algorithm provider (NetworkX/dict/numpy input)
   - Napojení na Kuzu by vyžadovalo změnu architektury na obou stranách
   - Toto je redesign, ne evoluce — vyžaduje vlastní sprint
