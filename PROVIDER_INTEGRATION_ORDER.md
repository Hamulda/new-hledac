# PROVIDER INTEGRATION ORDER — Sprint 8VD

**Generated:** 2026-03-31
**Scope:** `hledac/universal/` — future architecture integration
**Purpose:** Recommended dependency order for new feature integration

---

## 1. Layer Dependency Graph

```
UTILS LAYER (foundation)
├── rate_limiters.py       ← TokenBucket SSOT
├── uma_budget.py          ← OS memory monitoring
├── thread_pools.py        ← PersistentActorExecutor
├── async_helpers.py       ← _check_gathered()
└── intelligent_cache.py   ← ARC + MLX scoring
         ↑
         │ (depends on)
         │
PREFETCH LAYER
├── prefetch_cache.py      ← LMDB storage
├── prefetch_oracle.py     ← LinUCB bandit (Stage A/B)
├── ssm_reranker.py        ← SSM reranking
└── budget_tracker.py      ← Budget allocation
         ↑
         │ (depends on)
         │
KNOWLEDGE LAYER
├── ioc_graph.py           ← Kuzu backend, write buffers
├── rag_engine.py          ← HNSW + BM25 + RAPTOR
├── lancedb_store.py       ← LanceDB identity store
├── duckdb_store.py        ← RAMDISK analytics
├── context_graph.py       ← Context entities
├── entity_linker.py       ← Entity resolution
├── graph_builder.py       ← Graph construction
├── graph_layer.py         ← Graph abstraction
├── graph_rag.py            ← Graph RAG
├── analytics_hook.py       ← Shadow recording
└── lmdb_boot_guard.py     ← Cold start protection
         ↑
         │ (depends on)
         │
INTELLIGENCE LAYER
├── relationship_discovery.py ← igraph, GNN, Louvain
├── temporal_analysis.py     ← Temporal patterns
├── web_intelligence.py      ← Web data
├── pattern_mining.py        ← Pattern discovery
├── stealth_crawler.py       ← Chrome136 TLS
├── ct_log_client.py         ← Certificate transparency
├── ti_feed_adapter.py      ← Threat intel feeds
├── input_detector.py        ← Input processing
├── decision_engine.py       ← Decision logic
├── document_intelligence.py ← Document analysis
├── identity_stitching.py    ← Identity resolution
└── [28 other intelligence modules]
         ↑
         │ (depends on)
         │
BRAIN LAYER
├── model_manager.py         ← Model acquire (HOT)
├── model_lifecycle.py       ← Model unload (7K order)
├── dynamic_model_manager.py ← LRU + idle timeout
├── model_swap_manager.py    ← Double-checked locking
├── hermes3_engine.py        ← Hermes wrapper
├── ane_embedder.py          ← ANE embedder
├── inference_engine.py      ← Inference orchestration
├── gnn_predictor.py         ← GNN wrapper
├── tot_integration.py        ← Czech boost (1.75x)
└── [other brain modules]
         ↑
         │ (depends on)
         │
ORCHESTRATION LAYER
├── autonomous_orchestrator.py ← Main orchestrator
├── coordinators/
│   └── fetch_coordinator.py   ← curl_cffi HTTP seam
└── tools/
    ├── http_client.py         ← HttpClient interface
    ├── url_dedup.py           ← RotatingBloomFilter
    ├── host_policies.py       ← HostPenaltyTracker
    ├── lmdb_kv.py             ← LMDB + orjson KV
    ├── prompt_compression.py   ← LLMLingua-2
    └── checkpoint.py          ← CheckpointStore
```

---

## 2. Integration Order (Phase 1-6)

### Phase 1: Foundation (Utils Layer)

**FIRST:** Always integrate utils dependencies before anything else.

| Priority | Module | Reason |
|----------|--------|--------|
| 1.1 | `rate_limiters.py` | TokenBucket SSOT — all network ops need this |
| 1.2 | `uma_budget.py` | Memory pressure monitoring — M1 8GB critical |
| 1.3 | `thread_pools.py` | Async thread→event-loop bridge |
| 1.4 | `async_helpers.py` | Exception filtering for gather |
| 1.5 | `intelligent_cache.py` | ARC cache for general KV |

**Why first:** These have ZERO dependencies on other project modules. They are pure utilities.

---

### Phase 2: Data Layer (Knowledge Persistence)

**SECOND:** Integrate storage and persistence after utils.

| Priority | Module | Reason |
|----------|--------|--------|
| 2.1 | `ioc_graph.py` | Kuzu backend — entity storage |
| 2.2 | `lmdb_boot_guard.py` | Cold start protection |
| 2.3 | `duckdb_store.py` | Analytics storage (RAMDISK) |
| 2.4 | `lancedb_store.py` | Identity vector store |
| 2.5 | `lmdb_kv.py` (tools/) | Zero-copy KV store |

**Why second:** Storage has minimal external deps (just utils). Everything else reads/writes here.

---

### Phase 3: Retrieval Layer (RAG + Vector)

**THIRD:** Integrate RAG after data layer is stable.

| Priority | Module | Reason |
|----------|--------|--------|
| 3.1 | `rag_engine.py` | HNSW + BM25 + hybrid retrieval |
| 3.2 | `pq_index.py` | PQ compression (optional, for M1 RAM) |
| 3.3 | `context_graph.py` | Context storage |
| 3.4 | `entity_linker.py` | Entity resolution |
| 3.5 | `graph_builder.py` | Graph construction |

**Why third:** RAG depends on storage (ioc_graph, lancedb_store). No brain deps yet.

---

### Phase 4: Intelligence Layer (Analytics + Discovery)

**FOURTH:** Integrate intelligence after RAG is stable.

| Priority | Module | Reason |
|----------|--------|--------|
| 4.1 | `relationship_discovery.py` | Graph intelligence (uses igraph) |
| 4.2 | `temporal_analysis.py` | Temporal patterns |
| 4.3 | `ct_log_client.py` | Certificate transparency |
| 4.4 | `ti_feed_adapter.py` | Threat intel feeds |
| 4.5 | `stealth_crawler.py` | Chrome136 TLS |
| 4.6 | `pattern_mining.py` | Pattern discovery |

**Why fourth:** Intelligence modules query RAG (ioc_graph, rag_engine). Heavy analytics.

---

### Phase 5: Prefetch Layer (Prediction)

**FIFTH:** Integrate prefetch after intelligence is stable.

| Priority | Module | Reason |
|----------|--------|--------|
| 5.1 | `prefetch_cache.py` | LMDB prefetch storage |
| 5.2 | `budget_tracker.py` | Budget allocation |
| 5.3 | `ssm_reranker.py` | SSM reranking |
| 5.4 | `prefetch_oracle.py` | LinUCB bandit (Stage A/B) |

**Why fifth:** Prefetch oracle queries intelligence layer (relationship patterns) and knowledge layer (ioc_graph).

---

### Phase 6: Brain Layer (Model + Reasoning)

**LAST:** Integrate brain/modal layer after everything else is stable.

| Priority | Module | Reason |
|----------|--------|--------|
| 6.1 | `model_lifecycle.py` | Model unload (7K canonical order) |
| 6.2 | `model_swap_manager.py` | Double-checked locking |
| 6.3 | `dynamic_model_manager.py` | LRU + idle timeout |
| 6.4 | `model_manager.py` | Model acquire (phase map) |
| 6.5 | `tot_integration.py` | Czech boost (1.75x) |
| 6.6 | `gnn_predictor.py` | GNN wrapper (used by intelligence) |
| 6.7 | `hermes3_engine.py` | Hermes wrapper |
| 6.8 | `ane_embedder.py` | ANE embedder |
| 6.9 | `inference_engine.py` | Inference orchestration |

**Why last:** Brain layer is the most complex and has the most dependencies. It coordinates everything.

---

## 3. Cross-Cutting Concerns

### Memory Pressure Chain

```
uma_budget.py (OS monitoring)
       ↓
resource_allocator.py (request scheduling)
       ↓
prefetch_oracle.py (adaptive limits)
       ↓
model_lifecycle.py (emergency unload)
       ↓
mlx.clear_cache() (if needed)
```

**Integration note:** This chain is CRITICAL for M1 8GB. Must integrate in order.

### Evidence Chain

```
evidence_log.py (primary)
       ↓
tool_exec_log.py (tool execution)
       ↓
analytics_hook.py (shadow recording)
       ↓
duckdb_store.py (analytics)
```

---

## 4. What NOT to Integrate Together

| Pair | Reason | Recommendation |
|------|--------|----------------|
| `async_helpers.py` + `thread_pools.py` | Different async patterns | Integrate separately, test independently |
| `rag_engine.py` + `lancedb_store.py` | Different use cases (RAG vs identity) | Keep separate interfaces |
| `pq_index.py` + `rag_engine.py` | PQ is optional compression | Integrate PQ as plugin, not default |
| `gnn_predictor.py` + `relationship_discovery.py` | Circular if not careful | gnn_predictor is helper, not owner |

---

## 5. M1 8GB Specific Constraints

### Memory Budget Order

```
1. macOS system             ~2.5 GB (fixed)
2. Orchestrator overhead    ~1.0 GB
3. LLM (Hermes 3B)          ~2.0 GB
4. KV cache                 ~0.75 GB
5. Buffer zone              ~0.25 GB
─────────────────────────────
TOTAL                       ~6.5 GB (WARN threshold)
```

### Integration Sequence for Memory-Critical Path

```
uma_budget.py           → monitors
    ↓
resource_allocator.py  → predicts + allocates
    ↓
prefetch_oracle.py     → adapts limits based on pressure
    ↓
model_lifecycle.py      → unload when critical
    ↓
mlx_cache.py / clear_mlx_cache_if_needed() → free GPU cache
```

---

## 6. Hot Path vs Latent Path

### Hot Path (Always on critical path)

| Module | Reason |
|--------|--------|
| `rate_limiters.py` | Every network operation |
| `uma_budget.py` | Every request on M1 |
| `ioc_graph.py` | Every IOC extracted |
| `rag_engine.py` | Every RAG query |
| `model_manager.py` | Every model acquire |
| `prefetch_oracle.py` | Every prefetch decision |

### Latent Path (On-demand, not every request)

| Module | Trigger |
|--------|---------|
| `pq_index.py` | Large vector batches |
| `relationship_discovery.py` | Graph analysis requests |
| `tot_integration.py` | Complex queries (Czech, high complexity) |
| `ssm_reranker.py` | When Stage B prefetch activates |
| `dynamic_model_manager.py` | When model thrashing detected |

---

## 7. Recommended Test Order

When integrating a new module, test in this order:

1. **Unit tests** — Does it work in isolation?
2. **Integration with immediate deps** — Does it work with Phase N-1 modules?
3. **Memory pressure test** — Does it respect M1 8GB limits?
4. **Concurrent load test** — Does it handle 3 concurrent requests?
5. **Graceful degradation test** — Does it fail safely?

---

## 8. Summary

| Phase | Layer | Key Modules | Deps |
|-------|-------|------------|------|
| 1 | Utils | rate_limiters, uma_budget, thread_pools | NONE |
| 2 | Knowledge (persistence) | ioc_graph, duckdb_store, lancedb_store | Utils |
| 3 | Knowledge (retrieval) | rag_engine, pq_index, context_graph | Phase 2 |
| 4 | Intelligence | relationship_discovery, ct_log_client, ti_feed_adapter | Phase 3 |
| 5 | Prefetch | prefetch_oracle, prefetch_cache, ssm_reranker | Phase 4 |
| 6 | Brain | model_lifecycle, model_manager, tot_integration | All above |

**Critical path:** Utils → Knowledge → Intelligence → Brain

**Memory path:** uma_budget → resource_allocator → prefetch_oracle → model_lifecycle → mlx_cache
