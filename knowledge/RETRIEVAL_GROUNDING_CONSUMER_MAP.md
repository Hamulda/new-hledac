# Retrieval & Grounding Consumer Map

**Datum**: 2026-04-02
**Scope**: Coupling tightening sprint — thermal/memory policy narrowing, consumer truth, semantic_store classification
**Aktualizace**: 2026-04-02 Sprint 8VY-2 — thermal coupling zúžen přes `get_reranking_context()`, semantic_store potvrzen jako separate use case

---

## 1. Ptačí perspektiva: Proč coupling tightening, ne retrieval rewrite

### Kontext

Tento sprint nedělá:
- Retrieval rewrite
- Nový retrieval framework
- Nový orchestrator nebo singleton
- Přesouvání ownership mezi `rag_engine` / `lancedb_store` / `pq_index` / `graph_rag`

Dělá:
- **Zúžení** nejživějšího coupling debt — `lancedb_store → memory_coordinator` přes `self._orch._memory_mgr`
- **Přesnou klasifikaci** `semantic_store` direct `lancedb.connect()` jako separate use case
- **Aktualizaci consumer matrix** — co je CURRENT, REFERENCE-ONLY, FUTURE
- **Testy** — ověření že role separation drží

### Proč to není rewrite

Čtyři retrieval-related moduly mají rozdílné, dobře ohraničené odpovědnosti:

| Soubor | Role | Není |
|--------|------|------|
| `rag_engine.py` | Hybrid grounding engine (BM25+HNSW+RAPTOR) | Identity store, entity resolution |
| `lancedb_store.py` | Identity/entity store (LanceDB `entities` table, MLX 768D) | Document grounding |
| `pq_index.py` | Compression layer (PQ, 12× úspora) | Primary retrieval |
| `semantic_store.py` | IOC findings ANN (LanceDB `findings_v1`, FastEmbed 384D) | Identity resolution |
| `graph_rag.py` | Multi-hop reasoning consumer/orchestrator | Backend storage owner |

Záměr tohoto sprintu: **co nejužší seam pro thermal coupling**, žádná architektonická kosmetika.

---

## 2. Co jsem ověřil v current repo

### Thermal coupling v lancedb_store

**Původní stav** (lancedb_store.py:1101-1113):
```python
# DEBT: Thermal + battery awareness — COUPLING RISK
thermal = "NORMAL"
on_battery = False
try:
    from hledac.universal.coordinators.memory_coordinator import ThermalState
    if self._orch and hasattr(self._orch, '_memory_mgr') and self._orch._memory_mgr:
        thermal = self._orch._memory_mgr.get_thermal_state().name
        on_battery = self._orch._memory_mgr._on_battery_power()  # ← private method!
except Exception:
    pass
```

**Problém**: `_on_battery_power()` je **private** (single underscore) — přímý coupling na internals.

**Dále**: `available_gb` se počítal znovu přes `psutil` v Stage 5, odděleně od thermal state.

**Ověřeno**: `MemoryCoordinator.get_power_state()` (řádek 797) vrací `on_battery`, `thermal_state`, `thermal_trend`, `memory_pressure_level`, `should_throttle`.

**Nový stav**:
```python
# Narrow seam: get_reranking_context() je jediný entry point
ctx = {"thermal": "NORMAL", "on_battery": False, "available_gb": 8.0}
try:
    if self._orch and hasattr(self._orch, '_memory_mgr') and self._orch._memory_mgr:
        ctx = self._orch._memory_mgr.get_reranking_context()
except Exception:
    pass
thermal = ctx.get("thermal", "NORMAL")
on_battery = ctx.get("on_battery", False)
available_gb = ctx.get("available_gb", 8.0)
```

**Helper přidán do memory_coordinator.py** — `get_reranking_context()`:
- Volá `get_power_state()` internally
- Přidává `available_gb` z `psutil`
- Jediný entry point pro `lancedb_store` thermal/battery awareness
- Store stále funguje bez orchestratoru (default values)

### semantic_store direct LanceDB coupling

**Ověřeno** (semantic_store.py:83-100):
- Přímé `lancedb.connect(str(self._db_path))`
- Tabulka `findings_v1` (LIASED proti `entities` v `lancedb_store`)
- Embedding model: `BAAI/bge-small-en-v1.5` (384D FastEmbed) vs `lancedb_store` MLX 768D
- Žádný coupling na `self._orch._memory_mgr`
- Žádný shared schema

**Klasifikace**: **Separate use case** — IOC findings ANN, ne entity resolution. Není coupling debt.

---

## 3. Retrieval Consumer Matrix

### CURRENT Consumers (přímo volané v runtime)

| Consumer | Volá | Supplier | Path |
|----------|------|----------|------|
| `brain/synthesis_runner.py:387` | `RAGEngine().query()` | rag_engine | RAG grounding pro synthesis (Sprint 8VA B.2) |
| `brain/synthesis_runner.py:418` | `GraphRAGOrchestrator(PersistentKnowledgeLayer())` | graph_rag | IOC relationship context (Sprint 8VA C.2) |
| `layers/layer_manager.py:847` | `RAGEngine()` lazy singleton | rag_engine | Coordinator lazy init (dormant — instantiated, no `hybrid_retrieve()` called) |
| `enhanced_research.py:1328` | `self.rag = RAGEngine(RAGConfig)` | rag_engine | Research context augmentation (config-gated) |
| `core/__main__.py:313` | `run_semantic_pivot()` CLI | semantic_store | ANN search for IOC findings |
| `knowledge/duckdb_store.py:949` | `inject_semantic_store()` DI | semantic_store | Sprint 8SB semantic store injection |
| `knowledge/duckdb_store.py:940` | `self._semantic_store` buffer slot | semantic_store | `_semantic_buffer_findings()` calling `buffer_finding()` |
| `persistent_layer.py:1050` | `PQIndex().train()/add()` | pq_index | Embedding compression |
| `prefetch_oracle.py:22` | `PQIndex()` constructor injection | pq_index | Ultra-light candidate selection |
| `legacy/autonomous_orchestrator.py:5678` | `GraphRAGOrchestrator.add_node()` | graph_rag | Legacy subdomain discovery (NOT in current sprint) |
| `legacy/autonomous_orchestrator.py:15956` | `GraphRAGOrchestrator.ask_with_reasoning()` | graph_rag | Legacy reasoning queries (NOT in current sprint) |

### CURRENT Reference-Only (imports, comments, metadata — žádné runtime volání)

| Consumer | Evidence | Status |
|----------|----------|--------|
| `hypothesis_engine.py:546` | Comment `# Step 8: Generate path explanations (if graph_rag available)` | REFERENCE ONLY |
| `hypothesis_engine.py:1245` | `metadata['scoring_fn'] = 'graph_rag.score_path'` | METADATA ONLY |
| `duckdb_store.py:942` | `Sprint 8SB: Inject SemanticStore instance` | INFRA ONLY |
| `knowledge/assertions.py:22-23` | `from rag_engine import ...; from lancedb_store import ...` | TEST IMPORT ONLY |

### FUTURE Candidates (planned, not wired in current sprint)

| Candidate | Planned For | Evidence | Blocker |
|-----------|-------------|----------|---------|
| Planner/ToT integration | Context grounding | `RETRIEVAL_GROUNDING_CONSUMER_MAP.md` | Not yet wired in orchestrator |
| DeepResearch | Extended grounding | `RETRIEVAL_GROUNDING_CONSUMER_MAP.md` | Not yet wired |
| LanceDBIdentityStore integration | Entity resolution | Standalone capability, zero active consumers | Needs wiring into sprint lifecycle |
| duckdb_store graph traversal | GraphRAG backend | `persistent_layer` deprecated | duckdb_store lacks graph traversal API |

### Internal Module Dependencies

| Module | Volá | Purpose |
|--------|------|---------|
| `rag_engine.py:724,733,744` | `infinite_context_engine`, `spr_compressor`, `secure_enclave_manager` | Ultra-context, SPR, SecureEnclave |
| `rag_engine.py:_embed_text()` | CoreML/MLX per-instance | RAPTOR tree building |
| `graph_rag.py:_get_embedder()` | `MLXEmbeddingManager` singleton | Path scoring embedder |
| `lancedb_store.py:_initialize_embedder()` | `MLXEmbeddingManager` singleton | Entity embedding computation |
| `lancedb_store.py:search_similar_adaptive()` | `self._orch._memory_mgr.get_reranking_context()` | **Thermal awareness (NARROW SEAM)** |

---

## 4. Změněné soubory

| Soubor | Změna |
|--------|-------|
| `coordinators/memory_coordinator.py` | Přidán `get_reranking_context()` helper (řádek ~809) |
| `knowledge/lancedb_store.py` | Thermal coupling zúžen přes `get_reranking_context()` místo přímých `get_thermal_state()` a `_on_battery_power()` volání; odstraněn duplicitní `psutil` výpočet v Stage 5 |
| `knowledge/RETRIEVAL_GROUNDING_CONSUMER_MAP.md` | Aktualizovaná consumer matrix, semantic_store klasifikace, thermal coupling status |

**Žádné nové soubory nevznikly.**

---

## 5. Role potvrzené

### rag_engine.py = **Grounding Authority**

- Hybrid retrieval (BM25 + HNSW) pro context augmentation
- RAPTOR hierarchické summarizace
- SPR komprese, UltraContext, SecureEnclave
- **Není**: identity/entity store, primary graph storage

### lancedb_store.py = **Identity/Entity Store**

- LanceDB `entities` table, MLX 768D embeddings
- Hybrid search (vector + FTS přes aliasy)
- LMDB embedding cache, binary signatures, MMR, adaptive reranking
- Thermal-aware index building (teď přes úzký seam)
- **Není**: document grounding, IOC findings

### semantic_store.py = **Separate Use Case — IOC Findings ANN**

- LanceDB `findings_v1` table, FastEmbed 384D
- Buffered během sprint lifecycle (`buffer_finding()`)
- Sprint 8SB CLI (`run_semantic_pivot()`)
- **Není**: entity resolution, identity store
- **Coupling**: žádný na `self._orch._memory_mgr`

### pq_index.py = **Compression/Acceleration Layer**

- Product Quantization, 768D → 8 bytes (12× úspora)
- Standalone, train-before-use
- **Není**: primary retrieval, identity store

### graph_rag.py = **Consumer/Orchestrator**

- Multi-hop reasoning nad `PersistentKnowledgeLayer`
- Path scoring přes `MLXEmbeddingManager` singleton
- **Není**: backend storage owner, embedding computation owner

---

## 6. Thermal/Memory Coupling — Resolution

### ✅ RESOLVED: lancedb_store → memory_coordinator narrow seam

**Lokace**: `lancedb_store.py:1101-1111`

**Před**:
```python
thermal = self._orch._memory_mgr.get_thermal_state().name  # volá private method
on_battery = self._orch._memory_mgr._on_battery_power()
# available_gb počítán odděleně přes psutil v Stage 5
```

**Po**:
```python
ctx = self._orch._memory_mgr.get_reranking_context()
thermal = ctx["thermal"]
on_battery = ctx["on_battery"]
available_gb = ctx["available_gb"]
```

**Helper** (`memory_coordinator.py:809`):
```python
def get_reranking_context(self) -> dict:
    state = self.get_power_state()
    state["available_gb"] = psutil.virtual_memory().available / (1024**3)
    return state
```

**Co bylo zúženo**:
- Přímé volání `get_thermal_state().name` a `_on_battery_power()` nahrazeno jedním voláním `get_reranking_context()`
- `available_gb` už není počítán dvakrát (poprvé v context, podruhé v Stage 5)
- Seam je úzký — jedna metoda, jeden entry point
- Store stále funguje bez orchestratoru (default values)

---

## 7. Semantic Store Classification

### ✅ CONFIRMED: Separate Use Case

**semantic_store** a **lancedb_store** jsou oddělené use cases:

| Aspekt | semantic_store | lancedb_store |
|--------|----------------|---------------|
| LanceDB table | `findings_v1` | `entities` |
| Embedding model | FastEmbed 384D (`BAAI/bge-small-en-v1.5`) | MLX 768D |
| Účel | IOC findings ANN | Entity resolution |
| Lifecycle | Buffered během sprintu | Persistentní |
| Thermal coupling | Žádný | Přes `get_reranking_context()` |
| Consumer | `duckdb_store` (DI), `__main__.py` CLI | Standalone (zero active consumers) |

**Závěr**: `semantic_store` direct `lancedb.connect()` není coupling debt — je to legitimní oddělený LanceDB use case se samostatným tabelem/schema/modelem.

---

## 8. Seam Guards

| Seam | Loc | Assertion |
|------|-----|-----------|
| RAGEngine není identity store | `rag_engine.py` | Nemá `add_entity()`, `search_similar()` ✅ |
| LanceDB není grounding authority | `lancedb_store.py` | Nemá `hybrid_retrieve()`, `HNSWVectorIndex` ✅ |
| PQIndex není retrieval authority | `pq_index.py` | Nemá collection `search()` ✅ |
| GraphRAG není backend owner | `graph_rag.py` | Vše přes `knowledge_layer` consumer API ✅ |
| semantic_store není identity store | `semantic_store.py:85` | Oddělené table/model — **separate use case** ✅ |

---

## 9. Retrieval Debt (po tomto sprintu)

| Debt | Status | Blocker |
|------|--------|---------|
| LanceDBIdentityStore — zero active consumers | **OPEN** | Dormant capability, needs integration wiring when entity resolution is planned |
| duckdb_store graph traversal API | **OPEN** | `persistent_layer` deprecated, duckdb_store nemá ekvivalentní API |
| RAGEngine — instantiated but `hybrid_retrieve()` uncalled in current sprint pipeline | **OPEN** | Dormant unless `enable_rag=True` in config |
| graph_rag — legacy autonomous_orchestrator only | **OPEN** | Not in current sprint orchestration |

**NOTOPEN — CLOSED this sprint**:
- `lancedb_store → memory_coordinator` thermal coupling: ✅ Zúžen na `get_reranking_context()` narrow seam
- `semantic_store` direct LanceDB: ✅ Potvrzen jako separate use case

---

## 10. Odpovědi na klíčové otázky sprintu

### Kdo je grounding authority?
**`knowledge/rag_engine.py`** — Hybrid grounding engine (BM25+HNSW) pro context augmentation LLM.

### Kdo je identity/entity store?
**`knowledge/lancedb_store.py`** — LanceDB-backed identity store s `entities` table, MLX 768D embeddings, hybrid vector+FTS search.

### Jak je řešen thermal/memory coupling?
**Narrow seam přes `MemoryManager.get_reranking_context()`** — jediný entry point. `lancedb_store` volá `self._orch._memory_mgr.get_reranking_context()`, ne přímé `get_thermal_state()` a `_on_battery_power()`. Store funguje i bez orchestratoru (default values: NORMAL, False, 8.0GB).

### Jak je klasifikovaný semantic_store?
**Separate use case** — IOC findings ANN s vlastní `findings_v1` table a FastEmbed 384D modelem. Není coupling debt — je to legitimní oddělený LanceDB use case.

### Co zůstává retrieval debt?
1. **LanceDBIdentityStore dormant** — zero active consumers, capability ready but unwired
2. **duckdb_store graph traversal** — blocked by deprecated `persistent_layer`, duckdb_store lacks API
3. **RAGEngine uncalled** — instantiated but `hybrid_retrieve()` not in current pipeline (config-gated)
4. **graph_rag legacy** — all consumers in `legacy/autonomous_orchestrator.py`, not current sprint

---

## 11. Testy

```
tests/test_retrieval_role_separation.py
tests/probe_8vy/test_retrieval_consumer_separation.py
```

### Nové testy pro tento sprint (přidat do `tests/probe_8vy/`):

1. **`test_reranking_context_narrow_seam`** — ověří že `lancedb_store` volá `get_reranking_context()`, ne přímé `get_thermal_state()` / `_on_battery_power()`
2. **`test_semantic_store_separate_use_case`** — ověří že semantic_store a lancedb_store používají různé table names a modely
3. **`test_memory_coordinator_get_reranking_context`** — ověří že helper vrací správné klíče včetně `available_gb`
4. **`test_lancedb_store_default_without_orchestrator`** — ověří že store funguje s default hodnotami bez orchestratoru
