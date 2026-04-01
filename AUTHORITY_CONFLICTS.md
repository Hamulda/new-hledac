# AUTHORITY CONFLICTS — Sprint 8VD

**Generated:** 2026-03-31
**Scope:** `hledac/universal/` — read-only analysis

---

## Conflict / Duplication Table

| Oblast | Konflikt / duplicita | Moduly | Kanonický owner | Riziko | Doporučení |
|--------|---------------------|--------|-----------------|--------|------------|
| **Model lifecycle** | Split ownership: acquire vs unload | `brain/model_manager.py` vs `brain/model_lifecycle.py` | `model_lifecycle.py` (unload), `model_manager.py` (acquire) | MEDIUM — 7K unload order must stay in sync with acquire phases | Rozdělit jasně: `ModelAcquirer` vs `ModelLifecycleManager` |
| **Model loading** | LRU vs dynamic vs swap manager | `brain/dynamic_model_manager.py` vs `brain/model_swap_manager.py` vs `brain/model_manager.py` | Žádný — tři různé strategy | HIGH — race conditions při souběžném load | `model_manager.py` jako jediný entry point, ostatní jsou interní detaily |
| **Model lifecycle root** | DEPRECATED stub | `model_lifecycle.py` (root) → `brain.model_lifecycle` | `brain/model_lifecycle.py` | LOW — stub pouze přesměrovává | Odstranit stub po audit所有call sites |
| **IOC graph** | Kuzu vs igraph split | `knowledge/ioc_graph.py` (Kuzu) vs `intelligence/relationship_discovery.py` (igraph) | `ioc_graph.py` (entity), `relationship_discovery.py` (relationships) | LOW — různé účely | Jasně oddělit: IOC graph = storage, relationship discovery = analytics |
| **Graph plane** | Mini graph plane vs full graph | `graph/` (5 souborů) vs `knowledge/` graph files | Žádný konflikt reálně | LOW — `graph/quantum_pathfinder.py` je jediný skutečný soubor | Zachovat oddělení: graph plane = algoritmy, knowledge = persistence |
| **RAG retrieval** | Unified authority | `knowledge/rag_engine.py` | `rag_engine.py` | LOW | Žádný konflikt — `pq_index.py` je čistě kompresní sublayer |
| **Vector index** | HNSW vs PQ vs LanceDB | `knowledge/rag_engine.py` (HNSW) vs `knowledge/pq_index.py` (PQ) vs `knowledge/lancedb_store.py` (LanceDB) | `rag_engine.py` (RAG), `lancedb_store.py` (identity) | LOW | Jasně formulováno: RAG = retrieval, LanceDB = identity store |
| **DuckDB store** | Analytics vs evidence vs tool exec | `knowledge/duckdb_store.py` vs `evidence_log.py` vs `tool_exec_log.py` | `duckdb_store.py` (data), `evidence_log.py` (audit), `tool_exec_log.py` (tool evidence) | LOW | Různé účely — žádný překryv |
| **Prefetch** | Oracle vs cache vs SSM | `prefetch/prefetch_oracle.py` vs `prefetch/prefetch_cache.py` vs `prefetch/ssm_reranker.py` | `prefetch_oracle.py` (prediction), `prefetch_cache.py` (storage) | LOW | Správně odděleno — oracle predikuje, cache ukládá |
| **Intelligent cache** | ARC vs prefetch vs LMDB | `utils/intelligent_cache.py` vs `prefetch/` vs `knowledge/lmdb_kv.py` | `intelligent_cache.py` (general ARC), `prefetch/` (specialized prefetch) | LOW | Různé use cases — žádný konflikt |
| **UMA budget** | System vs request level | `utils/uma_budget.py` vs `resource_allocator.py` | `uma_budget.py` (OS level), `resource_allocator.py` (request level) | LOW | Správně odděleno — různé abstrakční úrovně |
| **Rate limiting** | TokenBucket SSOT | `utils/rate_limiters.py` | `rate_limiters.py` | LOW | Žádný konflikt — jediná authority |
| **Async helpers** | Helper vs utility | `utils/async_helpers.py` vs `utils/async_utils.py` | `async_helpers.py` (jediný existující) | LOW | `async_utils.py` NEEXISTUJE — žádný konflikt |
| **Thread pools** | PersistentActor vs generic executor | `utils/thread_pools.py` vs `utils/executors.py` | `thread_pools.py` (specific), `executors.py` (generic) | LOW | `PersistentActorExecutor` je specifičtější — preferovat |
| **Budget tracking** | Prefetch budget vs UMA budget | `prefetch/budget_tracker.py` vs `utils/uma_budget.py` | `prefetch/budget_tracker.py` (prefetch), `uma_budget.py` (system) | LOW | Správně odděleno — různé domény |
| **Evidence logging** | Evidence vs analytics hook | `evidence_log.py` vs `knowledge/analytics_hook.py` | `evidence_log.py` (primary), `analytics_hook.py` (shadow) | LOW | `analytics_hook` je shadow recording — ne konflikt |
| **Tool exec log** | Tool evidence vs general evidence | `tool_exec_log.py` vs `evidence_log.py` | Oba oddělené účely | LOW | Různé účely — evidence vs tool execution |
| **Metrics registry** | Prometheus-style metrics | `metrics_registry.py` | Samostatný | LOW | Žádný konflikt |
| **Memory pressure** | psutil vs mlx metal | `resource_allocator.py` vs `utils/uma_budget.py` | Oba měří různé | LOW | Správně — psutil = system, mlx = GPU cache |
| **Model swap** | Double-checked locking | `brain/model_swap_manager.py` | Samostatný | MEDIUM | Pouze pokud se používá souběžně s dynamic_model_manager |
| **ToT integration** | Czech boost vs general | `tot_integration.py` | Samostatný | LOW | Správně odděleno — jazyková specializace |

---

## Duplicate Pattern Summary

### TRUE Duplicates (HIGH priority)

| Pattern | Files | Action |
|---------|-------|--------|
| Žádné true duplicates nenalezeny | — | — |

### SPLIT OWNERS (MEDIUM priority)

| Pattern | Files | Action |
|---------|-------|--------|
| Model lifecycle acquire/unload split | `model_manager.py` vs `model_lifecycle.py` | Dokumentovat hranice, nepřekrývat |
| Model loading strategies | `dynamic_model_manager.py` vs `model_swap_manager.py` | Zvážit sjednocení přes model_manager |

### FALSE Positives (LOW/INFO)

| Pattern | Reason |
|---------|--------|
| `pq_index.py` vs `rag_engine.py` | `pq_index` je kompresní sublayer, ne samostatná authority |
| `async_utils.py` vs `async_helpers.py` | `async_utils.py` neexistuje |
| `prefetch/` vs `intelligent_cache.py` | Různé domény (prefetch prediction vs general cache) |
| `uma_budget.py` vs `resource_allocator.py` | Různé úrovně abstrakce (OS vs request) |

---

## Recommendations

1. **Model lifecycle boundary**: Explicitně oddělit `acquire_model()` v `model_manager.py` od `unload_model()` v `model_lifecycle.py`. Žádný cross-calling bez jasného kontraktu.

2. **Remove DEPRECATED stub**: `model_lifecycle.py` root redirect je deprecated — odstranit po verifikaci všech call sites.

3. **Dynamic model manager usage**: Pokud se `dynamic_model_manager.py` používá v produkčním kódu, měl by být plně integrován přes `model_manager.py` entry point.

4. **Graph plane clarification**: `graph/quantum_pathfinder.py` by měl mít jasný README definující vztah k `knowledge/ioc_graph.py`.

5. **RAG vs LanceDB boundary**: Jasně dokumentovat že `rag_engine.py` = RAG retrieval a `lancedb_store.py` = identity store. Ne překrývání.

---

## Non-Conflicts (Verified)

| Pair | Verdict |
|------|---------|
| `rag_engine.py` vs `lancedb_store.py` | RŮZNÉ ÚČELY: RAG retrieval vs identity storage |
| `prefetch_oracle.py` vs `prefetch_cache.py` | RŮZNÉ ÚČELY: prediction vs storage |
| `uma_budget.py` vs `resource_allocator.py` | RŮZNÉ ÚROVNĚ: OS monitoring vs request scheduling |
| `rate_limiters.py` vs rate limit helper | JEDINÁ AUTHORITY: `rate_limiters.py` |
| `thread_pools.py` vs `executors.py` | SPECIFIČTĚJŠÍ VÍTĚZÍ: `PersistentActorExecutor` preferred |
| `evidence_log.py` vs `tool_exec_log.py` | RŮZNÉ ÚČELY: general evidence vs tool execution |
| `analytics_hook.py` vs `evidence_log.py` | SHADOW PATTERN: `analytics_hook` zaznamenává do `evidence_log` |

---

## Summary

- **TRUE conflicts:** 0
- **SPLIT OWNERSHIP (medium risk):** 2 (model lifecycle, model loading)
- **FALSE POSITIVES:** 8+
- **DEPRECATED stubs:** 1 (`model_lifecycle.py` root)

**Overall health:** GOOD — kód je dobře oddělený, hlavní riziko je split ownership v model lifecycle doméně.
