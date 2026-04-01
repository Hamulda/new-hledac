# INVENTORY SEMANTIC BRAIN — Sprint 8VD

**Generated:** 2026-03-31
**Scope:** `hledac/universal/` — read-only analysis
**Classification:** HOT PATH / LATENT / HELPER / DEPRECATED / FACADE / UNKNOWN

---

## 1. Executive Summary

### Canonical Authority Map (Verified)

| Domain | Canonical Owner | Secondary | Facade/Redirect |
|--------|----------------|-----------|-----------------|
| Model lifecycle | `brain/model_lifecycle.py` | `brain/dynamic_model_manager.py` | `model_lifecycle.py` (root) — DEPRECATED stub |
| Model selection/acquire | `brain/model_manager.py` | — | — |
| Model swap | `brain/model_swap_manager.py` | — | — |
| RAG retrieval | `knowledge/rag_engine.py` | — | — |
| Vector index | `knowledge/rag_engine.py` (HNSW) | `knowledge/pq_index.py` (compression) | — |
| IOC graph | `knowledge/ioc_graph.py` | `graph/quantum_pathfinder.py` | — |
| Relationship discovery | `intelligence/relationship_discovery.py` | — | — |
| Prefetch oracle | `prefetch/prefetch_oracle.py` | `prefetch/prefetch_cache.py` (cache) | — |
| Rate limiting | `utils/rate_limiters.py` | — | — |
| Memory pressure | `utils/uma_budget.py` | `resource_allocator.py` | — |
| Thread pools | `utils/thread_pools.py` | — | — |
| Intelligent cache | `utils/intelligent_cache.py` | — | — |

### Key Findings

1. **Model plane is SPLIT**: `model_manager.py` owns acquisition, `model_lifecycle.py` owns unload sequence (7K canonical order). No single authority.
2. **RAG is unified**: `rag_engine.py` owns retrieval + HNSW + hybrid + RAPTOR. `pq_index.py` is purely compression sublayer (not a separate authority).
3. **IOC Graph has write buffer**: `buffer_ioc()` → `flush_buffers()` pattern with 500-item trigger — confirmed Kuzu backend.
4. **Relationship discovery is standalone**: Uses igraph (NOT networkx), Louvain community detection, GNN predictor wrapper.
5. **Prefetch oracle is dual-stage**: Stage A (neighbors/PQ/sketches) → Stage B (SSM reranker + LinUCB UCB).
6. **Utils orchestration is fragmented**: 50+ files, no clear cohesion beyond domain grouping.

---

## 2. Model Plane Reality

### File: `brain/model_manager.py` (27 files in brain/)

**Canonical owner for model ACQUIRE. Hot path.**

| Capability | Status | Notes |
|------------|--------|-------|
| Hermes-3 3B (PLAN phase) | HOT | Primary reasoning model |
| ModernBERT (EMBED phase) | HOT | Embedding model |
| GLiNER (NER phase) | HOT | Named entity recognition |
| CoreML ANE embedder | HELPER | `_load_coreml_embedder()` for Vision |
| Phase model map | HOT | `{"PLAN": "hermes", "EMBED": "modernbert", "NER": "gliner"}` |
| `acquire_model_ctx()` | HOT | Context manager for model lifecycle |
| `ModelManager` singleton | HOT | Lazy initialization |

**Critical constraint (CLAUDE.md §M1):**
- `kv_bits=4` and `max_kv_size=8192` belong in `mlx_lm.generate()`, NOT in `load()`
- `set_cache_limit(0)` only after model swap, not permanently

### File: `brain/model_lifecycle.py`

**Canonical owner for model UNLOAD. Hot path.**

| Capability | Status | Notes |
|------------|--------|-------|
| `unload_model()` | HOT | 7K canonical unload order |
| `is_safe_to_clear_emergency()` | HOT | Called before emergency RAM release |
| `ensure_mlx_runtime_initialized()` | HOT | Lazy MLX init |
| Structured generation | LATENT | Outlines + mlx_lm fallback |
| Phase transitions | HOT | PLAN→EMBED→EXEC→DONE |

**Unload sequence (verified 7K order):**
1. Clear KV cache
2. Clear attention cache
3. Clear MLX cache
4. Remove model from memory

### File: `brain/dynamic_model_manager.py`

**Dynamic loading with LRU + idle timeout. Hot path for frequently swapped models.**

| Capability | Status | Notes |
|------------|--------|-------|
| LRU cache | HOT | Max models in memory |
| Idle timeout | HOT | 180s default |
| Thrashing protection | HOT | `min_reload_interval=60s` |
| Thread-safe | HELPER | Lock acquisition |

### File: `brain/model_swap_manager.py`

**Double-checked locking for model swaps. HELPER role.**

| Capability | Status | Notes |
|------------|--------|-------|
| Double-checked locking | HOT | Race condition prevention |
| Drain timeout | HOT | 3s before force evict |
| Rollback on failure | HOT | `model_backup` swap |

### Other brain/ files (FACADE/LATENT/UNKNOWN)

| File | Role | Classification |
|------|------|----------------|
| `hermes3_engine.py` | Thin wrapper around model_manager | FACADE |
| `ane_embedder.py` | ANE (Apple Neural Engine) embedder | LATENT |
| `inference_engine.py` | Inference orchestration | LATENT |
| `decision_engine.py` | Decision logic | LATENT |
| `insight_engine.py` | Insight generation | LATENT |
| `moe_router.py` | Mixture of experts routing | UNKNOWN |
| `paged_attention_cache.py` | KV cache management | LATENT |
| `prompt_cache.py` | Prompt caching | HELPER |
| `dspy_optimizer.py` | DSPy optimization | UNKNOWN |
| `distillation_engine.py` | Model distillation | UNKNOWN |
| `gnn_predictor.py` | GNN wrapper (used by relationship_discovery) | HELPER |
| `hypothesis_engine.py` | Hypothesis generation | UNKNOWN |
| `research_flow_decider.py` | Flow control | UNKNOWN |
| `synthesis_runner.py` | Synthesis orchestration | LATENT |
| `ner_engine.py` | NER wrapper | FACADE |
| `apple_fm_probe.py` | Apple FM probe | UNKNOWN |
| `prompt_bandit.py` | Prompt optimization | UNKNOWN |

---

## 3. Brain / Reasoning / Synthesis Reality

### ToT Integration

**File:** `tot_integration.py` (root level)

| Capability | Status | Notes |
|------------|--------|-------|
| Czech language boost | HOT | 1.75x multiplier for Czech queries |
| `should_activate_tot()` | HOT | Complexity threshold decision |
| `analyze_complexity()` | HOT | Query complexity scoring |
| `TotIntegrationLayer` | HOT | Main orchestrator |

**Czech boost logic:**
```python
if detected_language == "cs" and complexity_score > 0.6:
    tot_depth = min(tot_depth * 1.75, max_depth)
```

### Synthesis Pipeline

**File:** `knowledge/rag_engine.py` (RAG) + `brain/synthesis_runner.py` (LATENT)

| Capability | Owner | Classification |
|------------|-------|----------------|
| RAG retrieval | `rag_engine.py` | HOT |
| Hybrid retrieval (HNSW + BM25) | `rag_engine.py` | HOT |
| RAPTOR hierarchical summarization | `rag_engine.py` | LATENT |
| Synthesis runner | `synthesis_runner.py` | LATENT |

### Reasoning Phases

Phase map (from `model_manager.py`):
- `PLAN` → Hermes-3 3B
- `EMBED` → ModernBERT
- `NER` → GLiNER

---

## 4. Knowledge / Persistence Reality

### IOC Graph

**File:** `knowledge/ioc_graph.py` (Kuzu backend)

| Capability | Status | Notes |
|------------|--------|-------|
| Kuzu backend | HOT | Primary graph DB |
| Write buffer | HOT | `buffer_ioc()` → `flush_buffers()` |
| 500-item flush trigger | HOT | WINDUP phase |
| STIX 2.1 export | LATENT | Full export capability |
| `extract_iocs_from_text()` | HOT | IOC extraction |
| Entity types | HOT | IP, domain, hash, URL, email, malware |

### DuckDB Store

**File:** `knowledge/duckdb_store.py`

| Capability | Status | Notes |
|------------|--------|-------|
| RAMDISK-first | HOT | Primary storage mode |
| OPSEC-safe degraded mode | HOT | Lazy fallback |
| Batch writes | HELPER | Batched for performance |
| Analytics | LATENT | Query analytics |

### Context Graph

**File:** `knowledge/context_graph.py`

| Capability | Status | Notes |
|------------|--------|-------|
| Context storage | HOT | Graph-based context |
| Entity linking | LATENT | `entity_linker.py` |

### Entity Linker

**File:** `knowledge/entity_linker.py`

| Capability | Status | Notes |
|------------|--------|-------|
| Entity resolution | LATENT | Cross-reference entities |
| Identity stitching | LATENT | `intelligence/identity_stitching.py` |

### Graph Builder

**File:** `knowledge/graph_builder.py`

| Capability | Status | Notes |
|------------|--------|-------|
| Graph construction | HELPER | Builder pattern |
| Layer integration | HELPER | `graph_layer.py` |

### Graph Layer

**File:** `knowledge/graph_layer.py`

| Capability | Status | Notes |
|------------|--------|-------|
| Graph abstraction | HELPER | Interface layer |
| Graph RAG | LATENT | `graph_rag.py` |

### Analytics Hook

**File:** `knowledge/analytics_hook.py`

| Capability | Status | Notes |
|------------|--------|-------|
| Analytics recording | LATENT | Shadow recording |
| Evidence logging | HELPER | `evidence_log.py` |

### LMDB Boot Guard

**File:** `knowledge/lmdb_boot_guard.py`

| Capability | Status | Notes |
|------------|--------|-------|
| Cold start protection | HELPER | Boot-time validation |

---

## 5. IOC Graph vs Graph Plane Reality

### IOC Graph (Primary Authority)

**Owner:** `knowledge/ioc_graph.py`

| Capability | Classification |
|------------|----------------|
| Kuzu backend | HOT |
| Write buffer pattern | HOT |
| STIX 2.1 export | LATENT |
| IOC extraction from text | HOT |
| Relationship types | HOT |

### Graph Plane (Secondary)

**Owner:** `graph/quantum_pathfinder.py`

| Capability | Classification |
|------------|----------------|
| Quantum pathfinding | UNKNOWN |
| Graph algorithms | HELPER |

**Relationship:** `graph/` directory has ONLY 5 files including `__init__.py`. No overlapping authority — IOC graph owns STIX-style IOCs, graph plane owns algorithmic pathfinding.

### Split Analysis

| Aspect | IOC Graph | Graph Plane |
|--------|----------|-------------|
| Backend | Kuzu | Unknown |
| Focus | IOC entities | Pathfinding |
| Export | STIX 2.1 | None |
| Relationship to each other | `intelligence/relationship_discovery.py` queries both | Uses graph algorithms |

**Verdict:** No real conflict. IOC graph = entity storage, graph plane = algorithmic layer.

---

## 6. Retrieval / RAG / Vector / PQ Reality

### RAG Engine (Primary Authority)

**File:** `knowledge/rag_engine.py`

| Capability | Status | Classification |
|------------|--------|----------------|
| HNSWVectorIndex | HOT | Primary vector index |
| BM25Index | HOT | Keyword retrieval |
| Hybrid retrieval | HOT | HNSW + BM25 fusion |
| RAPTOR tree | LATENT | Hierarchical summarization |
| CoreML/MLX embedder | HOT | Embedding generation |
| `search_similar_adaptive()` | HOT | Adaptive retrieval |

### PQ Index (Compression Sublayer)

**File:** `knowledge/pq_index.py`

| Capability | Status | Classification |
|------------|--------|----------------|
| Product Quantization | HOT | 12x compression (768→8 bytes) |
| OPQ preprocessing | HOT | Optimal rotation |
| Compression only | HELPER | No retrieval logic |

**Verdict:** `pq_index.py` is NOT a separate authority. It's a compression sublayer for embeddings BEFORE they're stored in the HNSW index. Retrieval still goes through `rag_engine.py`.

### LanceDB Identity Store

**File:** `knowledge/lancedb_store.py`

| Capability | Status | Classification |
|------------|--------|----------------|
| LanceDB vector DB | HOT | Primary identity store |
| LMDB embedding cache | HOT | Float16 quantization |
| Binary signatures | HELPER | `add_binary_signature()` |
| MMR reranking | HOT | Maximal Marginal Relevance |
| ColBERT/FlashRank | LATENT | Rerankers |
| `upsert_ioc_batch()` | HOT | Batch operations |
| `pivot()` | LATENT | Pivot queries |

### Vector Index Reality

| Index Type | Owner | Hot Path |
|------------|-------|----------|
| HNSW | `rag_engine.py` | YES |
| BM25 | `rag_engine.py` | YES |
| PQ compression | `pq_index.py` | HELPER only |
| LanceDB | `lancedb_store.py` | YES (identity) |

**Clear authority:** RAG retrieval = `rag_engine.py`. LanceDB = separate identity store (not RAG).

---

## 7. Relationship Discovery / Graph Intelligence Reality

### Primary Authority

**File:** `intelligence/relationship_discovery.py`

| Capability | Status | Classification |
|------------|--------|----------------|
| `RelationshipDiscoveryEngine` | HOT | Main orchestrator |
| igraph (NOT networkx) | HOT | Graph operations |
| `GNNPredictorWrapper` | LATENT | Graph neural network |
| LSH link prediction | HOT | `LSHLinkPredictor` |
| `detect_communities()` | HOT | Louvain community detection |
| `find_hidden_paths()` | HOT | Path discovery |
| `predict_relationships()` | HOT | GNN-based prediction |
| Temporal analysis | LATENT | `temporal_analysis.py` |

### Supporting Intelligence Files

| File | Role | Classification |
|------|------|----------------|
| `temporal_analysis.py` | Temporal patterns | LATENT |
| `web_intelligence.py` | Web data | LATENT |
| `pattern_mining.py` | Pattern discovery | LATENT |
| `blockchain_analyzer.py` | Blockchain IoC | UNKNOWN |
| `cryptographic_intelligence.py` | Crypto intelligence | UNKNOWN |
| `exposed_service_hunter.py` | Service detection | UNKNOWN |
| `stealth_crawler.py` | Crawling | HOT (chrome136 TLS) |
| `input_detector.py` | Input processing | HELPER |
| `decision_engine.py` | Decision logic | LATENT |
| `document_intelligence.py` | Document analysis | LATENT |
| `temporal_archaeologist.py` | Historical analysis | UNKNOWN |
| `identity_stitching.py` | Identity resolution | LATENT |
| `ct_log_client.py` | Certificate transparency | HOT |
| `dark_web_intelligence.py` | Dark web sources | UNKNOWN |
| `data_leak_hunter.py` | Leak detection | UNKNOWN |
| `archive_discovery.py` | Archive sources | UNKNOWN |
| `advanced_image_osint.py` | Image OSINT | UNKNOWN |
| `network_reconnaissance.py` | Network recon | UNKNOWN |
| `onion_seed_manager.py` | Tor seeds | UNKNOWN |
| `ti_feed_adapter.py` | Threat intel feeds | HOT |
| `workflow_orchestrator.py` | Workflow management | UNKNOWN |

### GNN Predictor

**File:** `brain/gnn_predictor.py` (used by relationship_discovery)

| Capability | Status | Classification |
|------------|--------|----------------|
| GNN wrapper | LATENT | Used by relationship_discovery |
| Graph neural network | LATENT | Prediction engine |

### Verdict

**Clear authority:** `intelligence/relationship_discovery.py` owns graph intelligence. No conflicts detected. igraph is correctly used (NOT networkx as suggested in initial concern).

---

## 8. Prefetch Reality

### Prefetch Oracle (Primary Authority)

**File:** `prefetch/prefetch_oracle.py`

| Capability | Status | Classification |
|------------|--------|----------------|
| Stage A (neighbors) | HOT | PQ + sketch neighbors |
| Stage B (SSM reranker) | HOT | SSM model reranking |
| LinUCB contextual bandit | HOT | UCB-based exploration |
| `on_cache_hit()` reward | HOT | Learning signal |
| Adaptive limits | HOT | Dynamic budget |

### Prefetch Cache

**File:** `prefetch/prefetch_cache.py`

| Capability | Status | Classification |
|------------|--------|----------------|
| LMDB storage | HOT | Persistent cache |
| TTL eviction | HOT | Time-based expiry |
| Async writer queue | HELPER | Write batching |

### SSM Reranker

**File:** `prefetch/ssm_reranker.py`

| Capability | Status | Classification |
|------------|--------|----------------|
| SSM-based reranking | LATENT | Sequence-to-sequence model |
| Budget tracking | HELPER | `budget_tracker.py` |

### Budget Tracker

**File:** `prefetch/budget_tracker.py`

| Capability | Status | Classification |
|------------|--------|----------------|
| Budget allocation | HELPER | Tracks prefetch budget |
| `UmaBudget` | HELPER | Part of larger budget system |

### Relationship to Intelligent Cache

**File:** `utils/intelligent_cache.py`

| Capability | Prefetch Oracle | Intelligent Cache |
|------------|-----------------|-------------------|
| Purpose | Prefetch prediction | General KV cache |
| Algorithm | LinUCB bandit | ARC eviction |
| MLX scoring | No | Yes (`mx.exp(-recency_m)`) |
| Owner | `prefetch_oracle.py` | `intelligent_cache.py` |

**Verdict:** No conflict. Prefetch oracle = predictive prefetching. Intelligent cache = general ARC cache. Different use cases.

---

## 9. Utils Orchestration Audit

### 50+ files in utils/

**Critical Files (HOT PATH):**

| File | Capability | Status |
|------|------------|--------|
| `rate_limiters.py` | TokenBucket SSOT | HOT |
| `thread_pools.py` | PersistentActorExecutor | HOT |
| `uma_budget.py` | UmaWatchdog | HOT |
| `intelligent_cache.py` | ARC cache + MLX | HOT |
| `async_helpers.py` | `_check_gathered()` | HOT |

### Rate Limiting (Single Authority)

**File:** `utils/rate_limiters.py`

| Capability | Status | Notes |
|------------|--------|-------|
| `TokenBucket` | HOT | SSOT for all rate limiting |
| Shodan | HOT | 1 req/sec |
| HIBP | HOT | Per-key limits |
| RIPE Stat | HOT | 10 req/sec |
| Gaussian jitter | HOT | ±15% |

**Other rate limit files:** NONE. `rate_limiters.py` is SOLE authority.

### Thread Pools

**File:** `utils/thread_pools.py`

| Capability | Status | Notes |
|------------|--------|-------|
| `PersistentActorExecutor` | HOT | Thread→event-loop bridge |
| `get_ane_executor()` | HOT | ANE offload |
| `get_db_executor()` | HOT | Database operations |
| QoS classes | HELPER | Priority levels |

### Memory Pressure

**File:** `utils/uma_budget.py`

| Capability | Status | Notes |
|------------|--------|-------|
| `UmaWatchdog` | HOT | 0.5s polling, 2s debounce |
| `get_uma_snapshot()` | HOT | Memory state |
| `get_uma_pressure_level()` | HOT | normal/warn/critical |
| `is_uma_critical()` | HOT | Emergency check |
| `is_uma_warn()` | HOT | Warning check |

**vs `resource_allocator.py`:** Different scope. `uma_budget.py` = OS-level UMA monitoring. `resource_allocator.py` = request-level RAM prediction + allocation.

### Async Helpers

**File:** `utils/async_helpers.py`

| Capability | Status | Notes |
|------------|--------|-------|
| `_check_gathered()` | HOT | Exception filtering |
| `async_getaddrinfo()` | HELPER | DNS resolution |

**vs `utils/async_utils.py`:** Does NOT exist. No conflict.

### MLX Utilities

| File | Capability | Status |
|------|------------|--------|
| `mlx_cache.py` | MLX cache management | HELPER |
| `mlx_memory.py` | MLX memory ops | HELPER |
| `mlx_utils.py` | General MLX utils | HELPER |
| `mlx_prompt_cache.py` | Prompt caching | HELPER |
| `mps_graph.py` | MPS computation graph | HELPER |

### Other Utils

| File | Capability | Classification |
|------|------------|----------------|
| `bloom_filter.py` | Bloom filter | HELPER |
| `filtering.py` | Data filtering | HELPER |
| `ranking.py` | Ranking algorithms | HELPER |
| `semantic.py` | Semantic operations | HELPER |
| `query_expansion.py` | Query expansion | LATENT |
| `entity_extractor.py` | Entity extraction | LATENT |
| `language.py` | Language detection | HELPER |
| `encryption.py` | Encryption utilities | HELPER |
| `performance_monitor.py` | Performance tracking | LATENT |
| `platform_info.py` | Platform detection | HELPER |
| `thermal.py` | Thermal monitoring | LATENT |
| `predictive_planner.py` | Planning algorithms | UNKNOWN |
| `workflow_engine.py` | Workflow execution | UNKNOWN |
| `lazy_imports.py` | Lazy import helpers | HELPER |
| `flow_trace.py` | Flow tracing | HELPER |
| `validation.py` | Validation utilities | HELPER |
| `sketches.py` | Bloom/Count sketches | HELPER |
| `shadow_dto.py` | DTO patterns | HELPER |

### Executors

**File:** `utils/executors.py`

| Capability | Status | Notes |
|------------|--------|-------|
| Executor pool | LATENT | Generic executor |

**vs `thread_pools.py`:** `thread_pools.py` has `PersistentActorExecutor` which is more specific. No conflict — different abstraction levels.

---

## 10. Apple Silicon / M1 8GB Implications

### Memory Pressure Thresholds (Verified)

**From `utils/uma_budget.py`:**

| Level | Threshold | Action |
|-------|-----------|--------|
| WARN | 6.0 GiB | Log warning |
| CRITICAL | 6.5 GiB | Begin emergency handling |
| EMERGENCY | 7.0 GiB | Force task cancellation |

**From `resource_allocator.py`:**

| Level | Threshold | Action |
|-------|-----------|--------|
| MAX_RAM_GB | 5.5 | Reject new requests |
| EMERGENCY_RAM_GB | 6.2 | Cancel lowest priority task |

### Adaptive Concurrency

**From `resource_allocator.py`:**

```python
_CONCURRENCY_CEILING = 3  # M1 8GB hard limit
_CONCURRENCY_FLOOR = 1

def get_adaptive_concurrency() -> int:
    pressure = {"normal": 0.0, "warn": 0.6, "critical": 0.9}.get(pressure_str, 0.0)
    if pressure < 0.4:   return 3
    elif pressure < 0.6: return 2
    elif pressure < 0.75: return 1
    else: return 1  # memory critical
```

### MLX Memory Management

| Function | File | Purpose |
|----------|------|---------|
| `get_mlx_memory_mb()` | `resource_allocator.py` | Cache usage monitoring |
| `clear_mlx_cache_if_needed()` | `resource_allocator.py` | Cache cleanup (threshold 500MB) |
| `ensure_mlx_runtime_initialized()` | `brain/model_lifecycle.py` | Lazy MLX init |

**Critical:** `mx.eval([])` before `mx.metal.clear_cache()` — without eval, clear_cache is no-op (lazy evaluation).

### Product Quantization Impact

**From `knowledge/pq_index.py`:**
- 12x compression: 768 floats → 8 bytes per vector
- 100K vectors: 76800 bytes uncompressed → ~6400 bytes with PQ
- Significant RAM savings on M1 8GB

### Resource Allocator vs Resource Governor

| Aspect | `resource_allocator.py` | `utils/uma_budget.py` |
|--------|------------------------|----------------------|
| Scope | Request-level | System-level |
| MLX prediction | YES | NO |
| Concurrent limit | 3 | N/A |
| Emergency brake | 6.2 GB | 7.0 GB |
| Owner | Root level | utils/ |

**Verdict:** Different abstraction levels, no conflict. `uma_budget.py` = OS monitoring, `resource_allocator.py` = request scheduling.

---

## Appendix: Classification Legend

| Classification | Meaning |
|----------------|---------|
| **HOT** | Active, in-use, on critical path |
| **LATENT** | Available but not currently on hot path |
| **HELPER** | Utility/support, not primary authority |
| **DEPRECATED** | Stub/redirect, scheduled for removal |
| **FACADE** | Thin wrapper, delegates to another authority |
| **UNKNOWN** | Unable to verify from code analysis |

---

## Appendix: File Count by Domain

| Domain | Files | Primary Authority |
|--------|-------|------------------|
| brain/ | 27 | `model_manager.py`, `model_lifecycle.py` |
| knowledge/ | 12 | `rag_engine.py`, `ioc_graph.py`, `lancedb_store.py` |
| intelligence/ | 29 | `relationship_discovery.py` |
| graph/ | 5 | `quantum_pathfinder.py` |
| prefetch/ | 4 | `prefetch_oracle.py`, `prefetch_cache.py` |
| utils/ | 50+ | `rate_limiters.py`, `thread_pools.py`, `uma_budget.py` |
