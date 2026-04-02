# Retrieval & Grounding Consumer Map

**Datum**: 2026-04-02
**Scope**: Consumer-map sprint (Sprint 8VY) — current vs future consumer audit, coupling debt documentation, seam guards
**Aktualizace**: 2026-04-02 Sprint 8VY — current vs future consumer rozlišení, semantic_store direct coupling analysis, hypothesis_engine jako reference-only, layer_manager jako lazy singleton

---

## 1. Ptačí perspektiva: Proč consumer-map sprint, ne retrieval rewrite

### Aktuální stav (2026-04-02)

Čtyři retrieval-related moduly v `knowledge/` mají překrývající se názvy, ale rozdílné odpovědnosti:

| Soubor | Název evokuje | Skutečná role |
|--------|---------------|---------------|
| `rag_engine.py` | "RAG engine" → retrieval | Hybrid grounding engine (BM25+HNSW+RAPTOR) |
| `lancedb_store.py` | "LanceDB store" → vector DB | Identity/entity store pro entity resolution |
| `pq_index.py` | "PQ index" → vector index | Kompresní vrstva (embedding quantization) |
| `graph_rag.py` | "GraphRAG" → graph retrieval | Consumer/orchestrator nad knowledge layer |

**Základní problém**: Názvy jsou misleadující. RAGEngine není "engine pro RAG retrieval" v tom smyslu, že by byl jediná nebo primární retrieval authority. Je to **grounding** engine — pomáhá LLM contextu při generování.

### Proč NE normalizační refactor teď

1. **RAGEngine je living code** — má aktivní vývoj (Sprint 42: CoreML, RAPTOR, HNSW)
2. **lancedb_store má HLUBOKÉ embedding optimalizace** — MLXCompiled similarity, binary signatures, writeback buffer, MMR, adaptive reranking. Přesunutí by bylo rizikové
3. **graph_rag závisí na legacy persistent_layer** — viz deprecation warning v persistent_layer.py řádek 19-21
4. **Žádný nový retrieval orchestrator** — sprint zakazuje vytvářet novou orchestration vrstvu
5. **M1 8GB constraint** — jakékoli přesuny kódu mohou mít RAM implikace

### Co tento sprint *je*

- **Authority clarification** — kdo je owner čeho (authority notes v source souborech)
- **Consumer map** — kdo volá koho a proč
- **Seam guards** — malé assertions, které zabrání zaměnitelnosti
- **Coupling documentation** — co je riskantní a proč
- **Testy** — role separation probes

---

## 2. Retrieval Consumer Map

### CURRENT Consumers (přímo volatelní v runtime)

| Consumer | Volá | Backend | Path |
|----------|------|---------|------|
| `synthesis_runner.py:384` | `RAGEngine().query()` | RAGEngine přímo | RAG grounding pro synthesis |
| `synthesis_runner.py:414` | `GraphRAGOrchestrator(PersistentKnowledgeLayer())` | PersistentKnowledgeLayer | GraphRAG multi-hop |
| `layer_manager.py:847` | `RAGEngine()` lazy singleton přes `.rag` property | RAGEngine | Coordinator lazy init |
| `enhanced_research.py:1328` | `self.rag = RAGEngine(RAGConfig)` | RAGEngine | Research context augmentation |
| `semantic_store.py:85` | `lancedb.connect()` | **DIRECT LANCEDB** | IOC findings ANN search |
| `persistent_layer.py:1050` | `PQIndex().train()/add()` | PQIndex přímo | Embedding compression |
| `prefetch_oracle.py:22` | `PQIndex()` constructor injection | PQIndex přímo | Ultra-light candidate selection |

### CURRENT Reference-Only (imports, comments, metadata)

| Consumer | Evidence | Status |
|----------|----------|--------|
| `hypothesis_engine.py:546` | Comment `# Step 8: Generate path explanations (if graph_rag available)` | REFERENCE ONLY — comment guard |
| `hypothesis_engine.py:1245` | `metadata['scoring_fn'] = 'graph_rag.score_path'` | METADATA ONLY — string value, no runtime call |
| `duckdb_store.py:942` | `Sprint 8SB: Inject SemanticStore instance` | INFRA ONLY — store creation, not runtime call |
| `knowledge/assertions.py:22` | `from hledac.universal.knowledge.rag_engine import RAGEngine` | TEST IMPORT ONLY |

### FUTURE Candidates (planned but not wired)

| Candidate | Planned For | Evidence | Blocker |
|-----------|-------------|----------|---------|
| Planner / ToT integration | Context grounding | `RETRIEVAL_GROUNDING_CONSUMER_MAP.md:361` future owner table | Not yet wired in orchestrator |
| DeepResearch | Extended grounding | `RETRIEVAL_GROUNDING_CONSUMER_MAP.md:361` future owner table | Not yet wired |
| Prefetch expansion | Candidate selection | `prefetch_oracle.py` — PQIndex stage A only | Full pipeline not connected |
| duckdb_store graph traversal | GraphRAG backend migration | `persistent_layer` deprecated | duckdb_store lacks graph traversal API |

### Internal Module Dependencies

| Module | Volá | Purpose |
|--------|------|---------|
| `rag_engine.py:724,733,744` | `infinite_context_engine`, `spr_compressor`, `secure_enclave_manager` | Ultra-context, SPR, SecureEnclave |
| `rag_engine.py:_embed_text()` | CoreML/MLX per-instance | RAPTOR tree building (Sprint 42) |
| `graph_rag.py:_get_embedder()` | `MLXEmbeddingManager` singleton | Path scoring embedder |
| `lancedb_store.py:_initialize_embedder()` | `MLXEmbeddingManager` singleton | Entity embedding computation |
| `lancedb_store.py:search_similar_adaptive()` | `self._orch._memory_mgr` | Thermal awareness (OPTIONAL coupling) |

---

## 3. Role potvrzené a zpřesněné

### `rag_engine.py` = **Grounding Authority** (NOT identity/entity store)

**Přesná definice**:
- Hybrid retrieval engine pro **context grounding** — kombinuje dense (HNSW) + sparse (BM25) pro augmentaci LLM contextu
- HNSW Vector Index pro rychlé ANN vyhledávání nad dokumentovými chunky
- RAPTOR hierarchické summarizace pro multi-level retrieval
- SPR komprese pro redukci contextu
- UltraContext Engine pro velké kontexty
- SecureEnclave pro citlivá data

**Není owner**:
- ❌ Identity/entity resolution
- ❌ Embedding cache (to je `lancedb_store`)
- ❌ Graph storage (to je `persistent_layer` / budoucí `duckdb_store`)
- ❌ Entity relationship storage

**Přímo voláno z**: `orchestrator.py`

**Embedding Policy (Sprint 8TD)**:
- **Shared Runtime Anchor**: `MLXEmbeddingManager` singleton (pro fallback)
- **Intentional Local Cached Engine**: `_fastembed_embedder` (cached `TextEmbedding` instance in `self`)
  - Proč: `hybrid_retrieve()` a `hybrid_retrieve_with_hnsw()` volají `_generate_embeddings()` per-call
  - Bez cache by se `TextEmbedding` model načítal při každém volání → memory fragmentation
  - M1 8GB: cached instance zamezuje repeated model loading
- **Fallback Path**: `_generate_embeddings()` → FastEmbed cached → MLXEmbeddingManager singleton → hash-based
- **RAPTOR Internal Helper**: `_embed_text()` používá `_coreml_embedder` / `_mlx_embedder` (per-instance, lazy)
  - Není to shared anchor — je to interní helper pro RAPTOR tree building
  - Spadá pod "broad engine" pro RAPTOR, ne pro general retrieval

**M1 Memory Guardrails**:
- `_fastembed_embedder` je atribut instance, ne global
- `_generate_embeddings()` volá `asyncio.to_thread(manager.embed_document, text)` pro MLX fallback
- Žádný eager model load v `__init__`

---

### `lancedb_store.py` = **Identity/Entity Store** (NOT grounding authority)

**Přesná definice**:
- LanceDB-backed **entity identity store** — ukládá entity (osoby, organizace, URL) s vektorovými embeddingy a aliasy
- Hybrid search (vector similarity + FTS přes aliasy) pro entity resolution
- LMDB embedding cache s float16 kvantizací (50% RAM úspora)
- Binary embeddings (64-bit) pro Hamming-distance rychlý pre-filter
- MMR (Maximal Marginal Relevance) pro diverzitu výsledků
- Adaptive reranking — ColBERT (GPU), FlashRank (CPU), MLX fallback
- MLX-compiled cosine similarity pro batch operace
- Writeback buffer pro batching embedding writes
- Thermal-aware index building (spolupracuje s `memory_coordinator` přes `self._orch`)

**Není owner**:
- ❌ Document/content retrieval (to je `rag_engine`)
- ❌ Grounding context generation
- ❌ Graph storage
- ❌ Primary vector search pro dokumenty (to je `rag_engine` přes HNSW)

**Přímo voláno z**: `orchestrator.py` (volá `get_identity_store()` singleton), `graph_rag.py` (thermal awareness)

**Embedding Policy (Sprint 81 Fáze 4)**:
- **Shared Runtime Anchor**: `MLXEmbeddingManager` singleton (přes `_mlx_embed_manager`)
- **Intentional Local Cached Engine**: `_embedder` + `_embedder_type` (tracked per store instance)
  - Proč: `_embed_batch()` a `_embed_single()` jsou volány z `add_entity()`, `search_similar_adaptive()`
  - Bez sledování by embedder type byl lost mezi voláními
  - M1 8GB: embedder je lazy-inited, žádný eager load
- **Fallback Path**: `MLXEmbeddingManager` → CoreML ANE → numpy_fallback
- **Consumer Status**: lancedb_store je **consumer** MLXEmbeddingManager, ne owner

**Thermal Awareness Coupling** (debt):
- `search_similar_adaptive()` volá `self._orch._memory_mgr` pro thermal/battery state
- Toto je **volitelný** coupling — store funguje i bez orchestratoru reference
- Debt: externalizovat thermal policy do samostatné třídy

**Hidden assumptions**:
- LanceDB table "entities" — schema obsahuje `id`, `embedding`, `aliases`, `first_seen`, `last_seen`
- Identity resolution je založeno na **alias matching** + **vector similarity** — ne na graph traversalu
- Embedder inicializace jde přes MLXEmbeddingManager → CoreML → numpy_fallback chain
- Thermal-aware — při low memory/thermal throttles odloží index build

---

### `pq_index.py` = **Compression/Acceleration Layer** (NOT retrieval authority)

**Přesná definice**:
- Product Quantization (PQ) komprese embeddingů — 768D → 8 bytes per vector (12× úspora)
- OPQ (Optimized PQ) preprocessing
- Vrací similarity jako `1/(1+L2)` — konzistentní s HNSW cosine similarity
- MLX-native implementace
- Standalone — trénuje se na datech, ne je nevyužívá jako primární index

**Není owner**:
- ❌ Primární vector retrieval (to je `rag_engine` HNSW)
- ❌ Identity store
- ❌ Graph storage

**Hidden assumptions**:
- Musí být trained před použitím (`train()` → `encode()` → `search()`)
- `search()` vrací similarity, ne distance — pro konzistenci s HNSW cosine
- Memory usage estimation je approximate

---

### `graph_rag.py` = **Consumer/Orchestrator/Helper** (NOT backend owner)

**Přesná definice**:
- **Consumer** — pracuje nad `PersistentKnowledgeLayer` (deprecated backend)
- **Orchestrator** — multi-hop graph traversal, novelty detection, contradiction detection, timeline analysis, narrative building
- **Helper** — centrality analysis, community detection, key path analysis
- Path scoring s embeddingy (volá MLXEmbeddingManager singleton)

**Není owner**:
- ❌ Backend storage (`persistent_layer` je deprecated, ne graph_rag)
- ❌ Embedding computation (používá MLXEmbeddingManager singleton!)
- ❌ Primary retrieval
- ❌ Identity resolution

**Přímo voláno z**: `orchestrator.py` (volá `multi_hop_search()`)

**Embedding Policy (Sprint 81 Fáze 4 — RESOLVED)**:
- **Shared Runtime Anchor**: `MLXEmbeddingManager` singleton (z `core/mlx_embeddings`)
- **Intentional Local Cached Engine**: Žádný (graph_rag není embedder owner)
  - Proč: graph_rag používá embedder pouze pro `score_path()` — jediná operace
  - Žádné repeated embedding calls — jen path scoring, ne per-doc indexing
  - M1 8GB: žádný local embedder = žádná memory fragmentation
- **Fallback Path**: `embed_document()` → exception → `[0.0]*384` (deterministic fallback)
- **Consumer Status**: graph_rag je **consumer** MLXEmbeddingManager, ne owner
  - Důkaz: `_get_embedder()` volá `get_embedding_manager()` a nic neukládá permanentně
- **No Broad Engine**: graph_rag NEVKLÁDÁ RAGEngine pro embedding — používá singleton

**Hidden assumptions**:
- `knowledge_layer` je instance `PersistentKnowledgeLayer` (deprecated!)
- Pro embedding volá `MLXEmbeddingManager` singleton (2026-04-02: **DUPLICITNÍ embedder REMOVED**)
- Volá `knowledge_layer.search()` pro hop-0 semantic search
- Volá `knowledge_layer.get_related_sync()` pro graph traversal
- Volá `knowledge_layer._backend.get_node()` přímo na interní backend
- `_run_async_safe()` — shared thread pool pro sync/async bridging

---

## 4. Authority Notes (zdrojové soubory)

### rag_engine.py
```python
"""
ROLE: Grounding Authority (NOT identity/entity store)
====================================================
Tento modul je grounding authority pro context augmentation.
NENÍ owner identity/entity resolution - to je lancedb_store.
NENÍ owner embedding computation - to je MLXEmbeddingManager singleton.
"""
```

### lancedb_store.py
```python
"""
ROLE: Identity/Entity Store (NOT grounding authority)
=====================================================
Tento modul je identity/entity store pro entity resolution.
NENÍ owner context grounding - to je rag_engine.
NENÍ owner document retrieval - to je rag_engine HNSWVectorIndex.
"""
```

### pq_index.py
```python
"""
ROLE: Compression/Acceleration Layer (NOT retrieval authority)
===========================================================
- komprimuje embeddingy pomocí Product Quantization (12× úspora)
- NENÍ owner primary vector retrieval → rag_engine HNSWVectorIndex
- NENÍ owner identity store → lancedb_store
"""
```

### graph_rag.py
```python
"""
ROLE: Consumer/Orchestrator (NOT backend owner)
============================================
Tento modul je consumer/orchestrator pro multi-hop reasoning.
NENÍ owner backend storage → persistent_layer (deprecated!)
NENÍ owner embedding computation → MLXEmbeddingManager singleton
NENÍ owner primary retrieval → rag_engine
"""
```

---

## 5. Seam Guards (malé, stabilní)

| Seam | Loc | Assertion |
|------|-----|-----------|
| RAGEngine není identity store | `rag_engine.py` — nemá `add_entity()`, `search_similar()` | ✅ Clean |
| LanceDB není grounding authority | `lancedb_store.py` — nemá `hybrid_retrieve()`, `HNSWVectorIndex` | ✅ Clean |
| PQIndex není retrieval authority | `pq_index.py` — nemá `search()` na collection, jen trained index | ✅ Clean |
| GraphRAG není backend owner | `graph_rag.py` — vše přes `knowledge_layer` consumer API | ✅ Clean |
| semantic_store není LanceDBIdentityStore | `semantic_store.py:85` — přímý `lancedb.connect()`, oddělené use case | ⚠️ DIFF USE CASE — semantic pro IOC findings, identity pro entity resolution |

---

## 6. Coupling Risks

### ✅ RESOLVED: `graph_rag.py` používá sdílený `MLXEmbeddingManager`

**Lokace**: `graph_rag.py:105-126` (`_get_embedder()`)

**Před**:
```python
from hledac.universal.knowledge.rag_engine import RAGEngine
self._embedder = RAGEngine()  # DUPLICITNÍ embedder!
```

**Po** (2026-04-02):
```python
from hledac.universal.core.mlx_embeddings import get_embedding_manager
self._embedder = get_embedding_manager()  # Sdílený singleton
```

**Co bylo opraveno**:
- `graph_rag` již nevytváří vlastní `RAGEngine()` instanci
- Používá `MLXEmbeddingManager` singleton z `core/mlx_embeddings.py`
- M1 8GB memory convergence: žádné duplikátní embedder alokace

**Stav**: ✅ Fixed

---

### ✅ RESOLVED: `rag_engine.py` cachuje `TextEmbedding` instanci

**Lokace**: `rag_engine.py:926-969` (`_generate_embeddings()`)

**Co bylo opraveno**:
- `TextEmbedding` instance se již nevytváří při každém volání `_generate_embeddings()`
- M1 8GB memory convergence: žádná repeated model loading fragmentation
- Fallback na `MLXEmbeddingManager` singleton pokud FastEmbed unavailable

**Stav**: ✅ Fixed

---

### ✅ RESOLVED: `lancedb_store.py` používá `MLXEmbeddingManager` singleton

**Lokace**: `lancedb_store.py:197-229` (`_initialize_embedder()`)

**Co bylo opraveno**:
- `_embedder` je inicializován přes `get_embedding_manager()` singleton
- Žádný nový embedder owner — pouze consumer relationship

**Stav**: ✅ Fixed

---

### 🟠 MEDIUM: `lancedb_store.py` couple na `memory_coordinator` přes `self._orch`

**Lokace**: `lancedb_store.py:1101-1106`
```python
# DEBT: Thermal + battery awareness — COUPLING RISK
# lancedb_store volá self._orch._memory_mgr přímo.
# Toto je OPTIONAL coupling - store funguje i bez orchestratoru.
# Debt: externalizovat thermal policy do samostatné třídy.
```

**Problém**:
- `LanceDBIdentityStore` má **volitelný** `orchestrator` reference (konstruktor parametr)
- Pokud je předán, store aktivně čte thermal state
- To znamená, že store **není plně izolovaný** — závisí na existenci a struktuře orchestratoru
- Memory pressure decision v `ensure_index()` závisí na `psutil` přímo, ne přes orchestrator

**Co je OK**:
- Thermal awareness je **optional enhancement** — store funguje i bez orchestratoru
- `health_check()` a `shutdown()` nemají coupling
- Writeback buffer funguje nezávisle

**Co zůstává jako debt**:
- Thermal-aware decisions by měly být externalizovány do policy třídy
- V současnosti je coupling jen v `search_similar_adaptive()` — ostatní path jsou čisté

---

### 🟡 MEDIUM: `rag_engine.py` legacy imports

**Lokace**: `rag_engine.py:724, 733, 744`
```python
from hledac.ultra_context.infinite_context_engine import InfiniteContextEngine
from hledac.ultra_context.spr_compressor import SPRCompressor
from hledac.ultra_context.secure_enclave_manager import SecureEnclaveManager
```

**Problém**:
- RAGEngine importuje z `hledac.ultra_context` — to je oddělený module
- Pokud `ultra_context` modul má jiné dependencies nebo memory profily, RAGEngine to implicitně přenáší
- Žádný jasný seam — ultra_context by měl mít vlastní memory budget

**Co je OK**:
- Všechny imports jsou lazy (`await _init_*()`) — nepřidávají OKAMŽITOU memory zátěž
- Fallback to warning pokud import selže

---

### 🟡 MEDIUM: `semantic_store.py` direct LanceDB backend coupling

**Lokace**: `knowledge/semantic_store.py:85`
```python
self._db = lancedb.connect(str(self._db_path))
```

**Problém**:
- `SemanticStore` volá `lancedb.connect()` přímo, ne přes `LanceDBIdentityStore`
- Oddělené use case: semantic_store = IOC findings ANN (384D FastEmbed), identity_store = entity resolution
- Ale coupling risk: oba drží LanceDB connection, potential table/schema conflicts

**Co je OK**:
- `semantic_store` a `LanceDBIdentityStore` používají různé table names (`findings_v1` vs `entities`)
- Různé embedding modely (FastEmbed 384D vs MLX 768D)
- Žádný shared schema — čistě oddělené use cases

**Coupling debt** (nízká priorita):
- Doc: explicitně uvést, že semantic_store a identity_store jsou oddělené use cases
- Seam: pokud by se někdy měly sjednotit, jít přes LanceDBIdentityStore interface
- M1 8GB: dvě LanceDB instance = ~50MB RAM, acceptable

---

## 7. Future owners (až přijde čas)

### Pro Planner / DeepResearch integraci

| Komponenta | Future Owner | Připravenost |
|------------|--------------|--------------|
| Context grounding | `RAGEngine` (už owner) | ✅ Ready |
| Entity identity | `LanceDBIdentityStore` (už owner) | ✅ Ready |
| Embedding computation | `MLXEmbeddingManager` singleton | ⚠️ Sprint 81 — potřebuje merge |
| Graph traversal | `duckdb_store` graph API | ⚠️ Deprecated `persistent_layer` — potřebuje migraci |
| Compression layer | `PQIndex` (už standalone) | ✅ Ready |

### Co by bylo příliš brzký refactor

1. **Sloučení RAGEngine + LanceDBIdentityStore** — oba mají oddělené use cases (grounding vs identity)
2. **Přesun PQIndex do rag_engine** — PQIndex je compression tool, ne retrieval authority
3. **GraphRAG → duckdb_store migrace** — `persistent_layer` je deprecated, ale duckdb_store nemá ekvivalentní graph traversal API
4. **RAGEngine → MLXEmbeddingManager** — vlastní embedder v RAGEngine má CoreML/MLX specific logic (Sprint 42)

---

## 8. Sprint Souhrn změn

### Změny (2026-04-02)

1. **`knowledge/rag_engine.py`** — přidána ROLE authority note v docstringu
2. **`knowledge/lancedb_store.py`** — přidána ROLE authority note v docstringu + seam guard comment pro thermal coupling
3. **`knowledge/pq_index.py`** — přidána ROLE authority note v docstringu
4. **`knowledge/graph_rag.py`** — přidána ROLE authority note v docstringu (class-level)
5. **`knowledge/RETRIEVAL_GROUNDING_CONSUMER_MAP.md`** — aktualizovaná consumer map, authority notes, coupling risks

### Žádné nové soubory
- Nevznikl žádný nový singleton
- Nevznikl žádný nový orchestrator
- Nevznikl žádný nový broad engine
- Nevznikl žádný eager model load
- Retrieval plane zůstává M1-friendly a memory-predictable

---

## 9. Odpovědi na klíčové otázky

### Kdo je SHARED RUNTIME ANCHOR?
**`core/mlx_embeddings.py` — `MLXEmbeddingManager` singleton**
- Jediný true singleton pro embedding computation napříč retrieval plane
- Používaný jako fallback z rag_engine i jako primární z lancedb_store
- Není vytvářen žádnou další komponentou — pouze sdílen

### Kde je INTENTIONAL LOCAL CACHED ENGINE?
1. **RAGEngine: `_fastembed_embedder`**
   - Proč: `hybrid_retrieve()` / `hybrid_retrieve_with_hnsw()` volají `_generate_embeddings()` per-call
   - Bez cache by se FastEmbed model načítal při každém volání → memory fragmentation
   - Lokace: `rag_engine.py:934-940` (cached v `self`)

2. **lancedb_store: `_embedder` + `_embedder_type`**
   - Proč: sledování typu embedderu mezi volání `_embed_batch()` / `_embed_single()`
   - Lokace: `lancedb_store.py:127-131` (instance proměnné)

### Kde je FALLBACK PATH?

**RAGEngine._generate_embeddings():**
```
FastEmbed cached (_fastembed_embedder)
    → MLXEmbeddingManager singleton (get_embedding_manager())
    → hash-based deterministic [random.Random(hash(t)).random()...]
```

**lancedb_store._initialize_embedder():**
```
MLXEmbeddingManager (get_embedding_manager())
    → CoreML ANE (ct.models.MLModel)
    → numpy_fallback (random normalized)
```

**graph_rag.score_path():**
```
MLXEmbeddingManager.embed_document()
    → exception → [0.0]*384 (deterministic fallback)
```

### Které couplingy jsou nejnebezpečnější?
1. **✅ RESOLVED: graph_rag → MLXEmbeddingManager singleton** — duplicate embedder allocation removed
2. **🟠 lancedb_store → memory_coordinator přes self._orch** — optional coupling, store still functional without it
3. **🟡 rag_engine → ultra_context imports** — implicit dependency transfer

### Co zůstává RETRIEVAL DEBT?
1. **Thermal-aware policy externalization** — lancedb_store volá `self._orch._memory_mgr` přímo
2. **duckdb_store graph traversal API** — nahradí deprecated persistent_layer v graph_rag
3. **RAGEngine RAPTOR embed_text()** — používá per-instance CoreML/MLX embedder (není shared anchor, ale není to ani problém — jen pro RAPTOR tree building)

---

## 10. Další krok pro F8 / F11

### F8: duckdb_store graph traversal API
**Blocker**: `persistent_layer` je deprecated, ale `duckdb_store` nemá ekvivalentní graph traversal API
**Akce**: Přidat graph traversal methods do `duckdb_store` BEFORE graph_rag migrace
**Scope**: Malé, inkrementální — žádný big-bang refactor

### F11: Thermal-aware policy externalization
**Blocker**: lancedb_store volá `self._orch._memory_mgr` přímo
**Akce**: Vytvořit samostatnou `ThermalPolicy` třídu v `coordinators/`
**Scope**: Malé, izolované — žádný coupling s store internals

---

## 11. Testy (role separation probes)

```
tests/test_retrieval_role_separation.py
```

Testy ověřující:
- `rag_engine` NENÍ identity store (nemá `add_entity`, `search_similar`)
- `lancedb_store` NENÍ grounding authority (nemá `hybrid_retrieve`, `HNSWVectorIndex`)
- `pq_index` NENÍ retrieval authority (nemá collection `search()`)
- `graph_rag` NENÍ backend owner (vše přes `knowledge_layer` consumer API)
- Embedding ownership: graph_rag používá singleton, ne vlastní engine
