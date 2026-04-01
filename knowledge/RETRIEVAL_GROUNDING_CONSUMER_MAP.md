# Retrieval & Grounding Consumer Map

**Datum**: 2026-04-02
**Scope**: Audit-first, guard-first, consumer-map sprint — **NE** retrieval refactor

---

## 1. Ptačí perspektiva: Proč audit-first a ne "normalizační"

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

- **Authority clarification** — kdo je owner čeho
- **Consumer map** — kdo volá koho a proč
- **Seam guards** — malé assertions, které zabrání zaměnitelnosti
- **Coupling documentation** — co je riskantní a proč

---

## 2. Retrieval Consumer Map

### Consumer → Provider → Owner

| Consumer | Co potřebuje | Current Provider | Correct Future Owner | Mismatch / Risk | Blocker |
|----------|--------------|------------------|---------------------|-----------------|---------|
| `orchestrator.py` (SprintScheduler) | Context grounding pro LLM | `RAGEngine.hybrid_retrieve()` | `RAGEngine` (už správně) | Žádný — přímá cesta | Žádný |
| `graph_rag.py` → `_get_embedder()` | Embedding pro path scoring | Vytváří **vlastní** `RAGEngine()` instance na řádku 114 | `MLXEmbeddingManager` (sprint 81) | **DUPLICITNÍ RAGEngine** — grave risk | Sprint 81 embedder singleton |
| `lancedb_store.py` → `add_entity()` | Identity resolution | `LanceDBIdentityStore` | `LanceDBIdentityStore` (správně) | Žádný | Žádný |
| `lancedb_store.py` → thermal awareness | Thermal state | `memory_coordinator.py` přes `self._orch` | Závislost na orchestrator | **Coupling risk** — store závisí na orchestrator | Refactor thermal awareness mimo orch |
| `graph_rag.py` → `multi_hop_search()` | Knowledge graph traversal | `PersistentKnowledgeLayer` (deprecated) | `duckdb_store` (future) | **Legacy coupling** — graph_rag používá deprecated API | duckdb_store graph traversal API |
| `rag_engine.py` → `UltraContext` | Infinite context | `infinite_context_engine` import na řádku 724 | Stejně | Žádný | Žádný |
| `rag_engine.py` → `SPRCompressor` | Semantic compression | `spr_compressor` import na řádku 733 | Stejně | Žádný | Žádný |
| `rag_engine.py` → `SecureEnclave` | Secure processing | `secure_enclave_manager` import na řádku 744 | Stejně | Žádný | Žádný |
| `rag_engine.py` → `_embed_text()` | CoreML/MLX embedder | `ModernBERTEmbedder` + coremltools | `MLXEmbeddingManager` singleton | **Duplicate model** — RAGEngine vytváří vlastní embedder | Sprint 81 MLXEmbeddingManager |

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

**Přímo voláno z**: `orchestrator.py`, interní `graph_rag._get_embedder()` (duplikovaně)

**Hidden assumptions**:
- FastEmbed je primary embedder (s CoreML/MLX fallbacks)
- Document map (`_document_map`) je v paměti — není persistentní napříč restartama
- HNSW index je postaven in-memory z dokumentů předaných přes `build_hnsw_index()`
- `_embed_text()` vytváří vlastní CoreML/MLX embedder — ne sdílí s `lancedb_store`

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
- Path scoring s embeddingy (volá vlastní RAGEngine pro embedding!)

**Není owner**:
- ❌ Backend storage (`persistent_layer` je deprecated, ne graph_rag)
- ❌ Embedding computation (vytváří vlastní RAGEngine!)
- ❌ Primary retrieval
- ❌ Identity resolution

**Přímo voláno z**: `orchestrator.py` (volá `multi_hop_search()`)

**Hidden assumptions**:
- `knowledge_layer` je instance `PersistentKnowledgeLayer` (deprecated!)
- Pro embedding volá vlastní `RAGEngine()` na řádku 114 — **DUPLICITNÍ embedder instance**
- Volá `knowledge_layer.search()` pro hop-0 semantic search
- Volá `knowledge_layer.get_related_sync()` pro graph traversal
- Volá `knowledge_layer._backend.get_node()` přímo na interní backend
- `_run_async_safe()` — shared thread pool pro sync/async bridging

---

## 4. Nejnebezpečnější couplingy

### 🔴 CRITICAL: `graph_rag.py` vytváří vlastní `RAGEngine()` embedder

**Lokace**: `graph_rag.py:114`
```python
from hledac.universal.knowledge.rag_engine import RAGEngine
self._embedder = RAGEngine()
```

**Problém**:
- Vytváří **druhou nezávislou instanci** RAGEngine
- Každá instance má vlastní embedder (CoreML/MLX)
- Na M1 8GB RAM to znamená **dvě souběžné embedder allocations**
- RAGEngine embedder je určen pro **grounding** (krátké chunky), ne pro **path scoring** (celé dokumenty)

**Current reality**: Oba embeddery jsou initialized lazily, takže crash nenastane hned. Ale:
- Memory footprint je 2× v高水平
- Model weights mohou být loaded 2× (pokud oba používají stejný model)

**Správné řešení** (až Sprint 81):
- `MLXEmbeddingManager` singleton sdílený mezi `rag_engine` a `graph_rag`
- `graph_rag` by měl použít `embed_document()` z jednoho sdíleného embedderu
- NE vytvářet novou RAGEngine instanci

**Prozatím**: graph_rag embedder zůstává jak je — velký refactor není v scope

---

### 🟠 HIGH: `lancedb_store.py` couple na `memory_coordinator` přes `self._orch`

**Lokace**: `lancedb_store.py:1090-1093`
```python
from hledac.universal.coordinators.memory_coordinator import ThermalState
if self._orch and hasattr(self._orch, '_memory_mgr') and self._orch._memory_mgr:
    thermal = self._orch._memory_mgr.get_thermal_state().name
    on_battery = self._orch._memory_mgr._on_battery_power()
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
- V současnosti je耦合 jen v `search_similar_adaptive()` — ostatní path jsou čisté

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

## 5. Future owners (až přijde čas)

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

## 6. Spolehlivé seams (malé, stabilní)

| Seam | Loc | Assertion |
|------|-----|-----------|
| RAGEngine není identity store | `rag_engine.py` — nemá `add_entity()`, `search_similar()` | ✅ Clean |
| LanceDB není grounding authority | `lancedb_store.py` — nemá `hybrid_retrieve()`, `HNSWVectorIndex` | ✅ Clean |
| PQIndex není retrieval authority | `pq_index.py` — nemá `search()` na collection, jen trained index | ✅ Clean |
| GraphRAG není backend owner | `graph_rag.py` — vše přes `knowledge_layer` consumer API | ✅ Clean |

---

## 7. Souhrn změn

Žádné funkční změny — pouze dokumentace a malé seam guards:

1. **`RETRIEVAL_GROUNDING_CONSUMER_MAP.md`** — tento dokument
2. **`knowledge/assertions.py`** — malé runtime assertions (volitelné, pro debugging)
3. **`knowledge/__init__.py`** — případné re-exporty pro clarity

---

## 8. Odpovědi na klíčové otázky

### Kdo je grounding authority?
**`rag_engine.py` — `RAGEngine`**
- Hybrid retrieval (dense + sparse) pro context grounding
- HNSW Vector Index pro ANN
- RAPTOR hierarchical summarization
- SPR compression pro context reduction

### Kdo je identity/entity store?
**`lancedb_store.py` — `LanceDBIdentityStore`**
- LanceDB-backed entity storage s hybrid search (vector + FTS)
- LMDB embedding cache s float16 quantization
- Binary signatures, MMR, adaptive reranking
- NOT pro document grounding

### Kdo je compression layer?
**`pq_index.py` — `PQIndex`**
- Product Quantization pro embedding compression
- OPQ preprocessing
- 12× memory savings (768D → 8 bytes)
- Standalone — není primary retrieval

### Co je graph_rag?
**Consumer/Orchestrator/Helper**
- Multi-hop graph traversal nad `PersistentKnowledgeLayer` (deprecated)
- Novelty detection, contradiction detection, timeline analysis
- NENÍ backend owner — jen consumer
- Vytváří vlastní RAGEngine pro embedding (DUPLICITNÍ — future fix: Sprint 81 MLXEmbeddingManager singleton)

### Které couplingy jsou nejnebezpečnější?
1. **🔴 graph_rag → own RAGEngine instance** — duplicate embedder allocation (M1 RAM impact)
2. **🟠 lancedb_store → memory_coordinator přes self._orch** — optional coupling, store still functional without it
3. **🟡 rag_engine → ultra_context imports** — implicit dependency transfer

### Co zůstává blocker před planner / DeepResearch integrací?
1. **Sprint 81: MLXEmbeddingManager singleton** — odstraní duplicate embedder mezi rag_engine a graph_rag
2. **duckdb_store graph traversal API** — nahradí deprecated persistent_layer v graph_rag
3. **Thermal-aware policy externalization** — oddělí lancedb_store od přímého volání memory_coordinator
