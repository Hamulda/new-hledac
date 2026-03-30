# Sprint 8BK — MLX / Data / OSINT / Intelligence Readiness Audit

## 1. Executive Summary
Audit-only sprint. Goal: determine v12 readiness, duplication, and best integration paths.
Key findings:
- MLX infrastructure: ROBUST — hermes3_engine.py + moe_router.py + utils/mlx_memory.py cover v12 §2.1/2.5/2.8
- Graph/vector stack: PARTIAL — LanceDB (knowledge/lancedb_store.py) ready; Kuzu stub exists; igraph only in relationship_discovery
- OSINT modules: MOSTLY MISSING — only Wayback partially implemented; certstream/graphql/Shodan/FOFA/Netlas/Aleph dormant or absent
- RL/MCTS: rl/ directory exists (6 files) but NOT wired into autonomous_orchestrator.py; HTN planner is skeleton
- ANE embedder: skeleton (94 lines), placeholder only — no actual CoreML conversion
- CRITICAL HOTSPOT: autonomous_orchestrator.py = 30,558 LOC — must NOT receive more responsibilities

## 2. Code Inventory Summary
- **existing_doc_pipeline**: 45 files
- **existing_graph_store**: 240 files
- **existing_memory_manager**: 130 files
- **existing_osint_modules**: 1956 files
- **existing_pattern_matcher**: 101 files
- **existing_snapshot_or_priors**: 852 files

## 3. Critical Questions — Answers

### Q1: Do we already have a memory manager better than proposed?
**YES.** `utils/mlx_memory.py` already has:
- `clear_mlx_cache()`, `get_mlx_active_memory_mb()`, `get_mlx_peak_memory_mb()`, `get_mlx_cache_memory_mb()`
- `get_mlx_memory_pressure()` returning (pct, level) tuple
- `configure_mlx_limits()` with set_cache_limit
- `format_mlx_memory_snapshot()`
**Verdict**: v12 §2.1/2.2 memory manager is COVERED. Extend utils/mlx_memory.py only.

### Q2: Do we already have part of ANE/CoreML embedding infrastructure?
**PARTIAL.** `brain/ane_embedder.py` (94 lines) is a skeleton:
- Has `ANEEmbedder` class with `load()`, `convert_to_ane()`, `embed()` methods
- `convert_to_ane()` is a placeholder — no actual MLX→CoreML conversion
- `rag_engine.py` has `_load_coreml_embedder()` + `_embed_text()` priority CoreML→MLX
- actual embedding uses `MLXEmbeddingManager` from `lancedb_store.py`
**Verdict**: v12 §2.7 PARTIAL. CoreML conversion is the missing piece; ANE loading/serving is stub only.

### Q3: Do we already have a graph/vector/search stack that makes v12 duplicate?
**YES for LanceDB, NO for Kuzu.**
- `knowledge/lancedb_store.py`: full LanceDB hybrid search (vector + FTS) — already integrated in `rag_engine.py`
- `knowledge/persistent_layer.py`: has HNSW index (`_build_hnsw_index`, `_search_hnsw`), KuzuDBBackend stub, JSONBackend
- `knowledge/atomic_storage.py`: LMDB-backed entity storage with DeltaCompressor
- `intelligence/relationship_discovery.py`: igraph for cliques/stats/communities/paths/influence
- Kuzu is referenced in 9 files but `import kuzu` only in 3 project files; actual Kuzu usage is minimal/placeholder
**Verdict**: v12 §2.11 (Kuzu) is NOT required — LanceDB + igraph + LMDB already cover graph storage needs. If Kuzu is desired, it should replace the JSONBackend in persistent_layer.py, not be a new module.

### Q4: Is there already a partial MCTS/snapshot/prior system to extend?
**PARTIAL.** `rl/` directory exists (6 files: qmix.py, marl_coordinator.py, replay_buffer.py, state_extractor.py, actions.py):
- QMIX joint trainer with Double DQN, mixing network, Shamir secret sharing
- MARLCoordinator with epsilon decay and checkpointing
- RL replay buffer with .npz persistence
- BUT: NOT connected to autonomous_orchestrator.py at all — no action selection integration
- HTN planner in `planning/htn_planner.py` (169 lines) is a skeleton
- Cost model in `planning/cost_model.py` (242 lines) has ridge regression + Mamba residual
**Verdict**: v12 §2.6 MCTS director would need new integration wiring. Existing RL code should be moved closer to the action selection loop in autonomous_orchestrator.py, not duplicated.

### Q5: Which proposed OSINT modules already exist in partial or superior form?
| Module | Status | Location |
|--------|--------|----------|
| Wayback | PARTIAL | autonomous_orchestrator.py (_wayback_quick_check, _wayback_cdx_stream, wayback_rescue_handler) |
| JARM TLS fingerprinting | READY | network/jarm_fingerprinter.py |
| CT Log scanning | READY | network/ct_log_scanner.py |
| Favicon hashing | READY | network/favicon_hasher.py |
| JS bundle/source map extraction | READY | network/js_bundle_extractor.py, js_source_map_extractor.py |
| Open storage scanner (S3/Firebase/ES/Mongo) | READY | network/open_storage_scanner.py |
| Tor / I2P | READY | network/tor_manager.py |
| Document forensics (EXIF/GPS/ELA) | PARTIAL | document_intelligence.py (ELA, stegdetect) |
| Certstream | MISSING | — |
| GraphQL introspection | MISSING | — |
| Fediverse / Mastodon | MISSING | — |
| Shodan / Censys / FOFA / Netlas | MISSING | — |
| Aleph / OpenSanctions | MISSING | — |
| Maigret / Holehe | MISSING | — |

### Q6: Which proposals should be integrated into existing files vs new modules?
**Integrate INTO existing files** (do NOT create new modules):
- Memory pressure reactor → extend `utils/mlx_memory.py`
- Thermal monitor → extend `utils/mlx_memory.py` or macos/thermal detection
- Pattern matcher → extend `intelligence/pattern_mining.py` or `utils/`
- KV cache manager → extend `brain/hermes3_engine.py`
- ANE embedder offline conversion → extend `brain/ane_embedder.py` + `rag_engine.py`
- Kuzu store → replace JSONBackend in `knowledge/persistent_layer.py`
- OSINT new sources → extend `intelligence/` existing modules

**NEW modules only when unavoidable**:
- QMIX/MARL integration layer → only if connecting rl/ to autonomous_orchestrator.py (not duplicating rl/)
- Certstream / GraphQL / Fediverse clients → genuinely new intelligence/ sources

## 4. Hotspots / Risk Files
Files that MUST NOT receive more responsibilities:
- **autonomous_orchestrator.py** (30558 LOC)
- **tests/test_autonomous_orchestrator.py** (22154 LOC)
- **knowledge/persistent_layer.py** (3575 LOC)
- **coordinators/memory_coordinator.py** (2776 LOC)
- **knowledge/atomic_storage.py** (2742 LOC)
- **layers/stealth_layer.py** (2662 LOC)
- **intelligence/stealth_crawler.py** (2637 LOC)
- **knowledge/graph_rag.py** (2549 LOC)
- **brain/hypothesis_engine.py** (2516 LOC)
- **brain/inference_engine.py** (2370 LOC)

## 5. Minimal-Edit Integration Map
### 2_11_kuzu_store
- ❌ database/ (missing)
- ✅ knowledge/ (dir)
- ✅ brain/ (dir)
### 2_12_lance_to_kuzu
- ❌ database/ (missing)
- ✅ knowledge/ (dir)
### 2_13_lightrag_bridge
- ✅ brain/ (dir)
- ❌ database/ (missing)
### 2_1_mlx_memory_manager
- ✅ utils/mlx_memory.py (file)
- ✅ brain/hermes3_engine.py (file)
- ✅ brain/moe_router.py (file)
### 2_2_memory_pressure_reactor
- ❌ macos/ (missing)
- ✅ utils/ (dir)
- ✅ autonomous_orchestrator.py (file)
### 2_3_thermal_monitor
- ❌ macos/ (missing)
- ✅ utils/ (dir)
- ✅ autonomous_orchestrator.py (file)
### 2_4_pattern_matcher
- ✅ utils/ (dir)
- ✅ intelligence/document_intelligence.py (file)
- ✅ intelligence/dark_web_intelligence.py (file)
### 2_5_kv_cache_manager
- ✅ brain/hermes3_engine.py (file)
- ✅ brain/ (dir)
- ✅ utils/mlx_memory.py (file)
### 2_6_mcts_director
- ✅ planning/ (dir)
- ✅ brain/ (dir)
- ✅ autonomous_orchestrator.py (file)
### 2_7_ane_embedder
- ✅ utils/ (dir)
- ✅ brain/ (dir)
- ❌ database/ (missing)
- ✅ planning/ (dir)
### 2_8_hermes_lazy_loading
- ✅ brain/hermes3_engine.py (file)
- ✅ autonomous_orchestrator.py (file)
### 3_osint_core_modules
- ✅ intelligence/ (dir)
- ✅ coordinators/ (dir)
### 4_advanced_analytics
- ✅ intelligence/ (dir)
- ✅ brain/ (dir)
- ❌ database/ (missing)

## 6. Hidden Debt

### HD-1: autonomous_orchestrator.py (30,558 LOC)
This file is already the entire system. Adding more managers here creates an unmaintainable monolith.
所有 new features must be placed in subordinate modules and only minimally wired here.

### HD-2: Kuzu stub vs actual usage
Kuzu is referenced in 9 files but imported in only 3. The DuckDB store (knowledge/duckdb_store.py) coexists
without clear boundary. Decision needed: Kuzu or DuckDB or both?

### HD-3: RL/QMIX not wired
rl/ has 6 files with working QMIX implementation but zero integration into autonomous_orchestrator.py.
No clear entry point for RL-based action selection. This is latent capability, not active code.

### HD-4: ANE embedder is a placeholder
brain/ane_embedder.py has load/embed stubs but convert_to_ane() is a placeholder.
rag_engine.py tries CoreML→MLX fallback but without actual .mlpackage conversion the ANE path never fires.

### HD-5: database/ directory does not exist
Several v12 items reference database/ which doesn't exist. All DB code lives in knowledge/.
No migration needed — just don't create database/ as a separate silo.

### HD-6: OSINT sources are mostly absent
Only wayback (partial), jarm, ct_log, favicon, js_bundle, tor are implemented.
High-value missing: Shodan, FOFA, Netlas, Certstream, GraphQL, Fediverse.

### HD-7: HTN planner skeleton
planning/htn_planner.py (169 lines) and cost_model.py (242 lines) exist but are not called from
autonomous_orchestrator.py. The MCTS director proposal (v12 §2.6) would need to wire into
the existing RL replay buffer + MARLCoordinator, not create a new MCTS from scratch.

## 7. Required Output Table

| PLAN_ITEM | READINESS | BEST_FILE_TO_EXTEND | EXISTING_SIMILAR | REQUIRED_FIXES | DUPLICATION_RISK | ARCH_NOTES |
|---|---|---|---|---|---|---|
| §2.1 MLX Memory Manager | **READY** | utils/mlx_memory.py | clear_cache, pressure, metrics | None | HIGH if new class | Extend existing, don't replace |
| §2.2 Memory Pressure Reactor | **READY** | utils/mlx_memory.py | get_mlx_memory_pressure | Wire to autonomous_orchestrator | MEDIUM | Add threshold callbacks |
| §2.3 Thermal Monitor | **PARTIAL** | utils/mlx_memory.py | get_mlx_memory_metrics | psutil thermal zone reading | LOW | MacOS thermal zones via IOKit |
| §2.4 Pattern Matcher | **PARTIAL** | intelligence/pattern_mining.py | pyahocorasick hits (but not wired) | Wire pyahocorasick into mining pipeline | MEDIUM | Extend pattern_mining.py |
| §2.5 KV Cache Manager | **READY** | brain/hermes3_engine.py | max_kv_size, attention_sink, draft_model, speculative decoding | None | LOW | Already fully implemented |
| §2.6 MCTS Director | **CONFLICT** | planning/htn_planner.py + rl/ | RL/QMIX exists but not wired | Wire rl/ into action selection loop | HIGH | Extend RL not rewrite MCTS |
| §2.7 ANE Embedder | **PARTIAL** | brain/ane_embedder.py | CoreML loading stub, MLX fallback | Real MLX→CoreML conversion in convert_to_ane() | LOW | Offline conversion is the gap |
| §2.8 Hermes Lazy Loading | **READY** | brain/hermes3_engine.py | load() lazy, semaphore, gc | None | LOW | Already done in Sprint 37+ |
| §2.11 Kuzu Store | **MISSING** | knowledge/persistent_layer.py | LanceDB + LMDB exist | Decide: replace JSONBackend or coexist | HIGH | Kuzu would compete with DuckDB |
| §2.12 Lance→Kuzu | **MISSING** | knowledge/lancedb_store.py | LanceDB hybrid search ready | Only if Kuzu is chosen above | HIGH | See HD-2 |
| §2.13 LightRAG Bridge | **MISSING** | — | No lightrag code exists | Would need new module | HIGH | LightRAG = new dep, likely unnecessary |
| §3 OSINT Core (Certstream) | **MISSING** | intelligence/ | wayback partial only | New intelligence/ module | LOW | New file in intelligence/ |
| §3 OSINT Core (GraphQL) | **MISSING** | intelligence/ | — | New intelligence/ module | LOW | New file in intelligence/ |
| §3 OSINT Core (Shodan/FOFA/Netlas) | **MISSING** | intelligence/ | network_reconnaissance.py partial | New intelligence/ module or extend | LOW | New file in intelligence/ |
| §3 OSINT Core (Aleph/OpenSanctions) | **MISSING** | intelligence/ | — | New intelligence/ module | LOW | New file in intelligence/ |
| §3 OSINT Core (Maigret/Holehe) | **MISSING** | enhanced_research.py | — | Extend enhanced_research.py | LOW | Already has osint_frameworks.py |
| §4 Advanced Analytics | **PARTIAL** | intelligence/ + brain/ | RL latent, GNN partial | Wire RL, complete ANE conversion | MEDIUM | See RL/ANE gaps above |

## 8. Top 10 Highest-ROI Implementation Targets (in order)

1. **[HIGH ROI] Complete ANE embedder offline conversion**
   → File: brain/ane_embedder.py + rag_engine.py
   → Impact: ANE inference for embeddings (zero RAM, max speed on M1)
   → Existing: skeleton + MLX fallback; missing: real CoreML conversion

2. **[HIGH ROI] Wire RL/QMIX into autonomous_orchestrator.py action selection**
   → File: rl/marl_coordinator.py + autonomous_orchestrator.py (minimal wiring)
   → Impact: learned action policy instead of static bandits
   → Existing: full QMIX impl in rl/ not connected; needs entry point

3. **[HIGH ROI] Implement missing OSINT sources (Shodan + FOFA + Netlas)**
   → File: new intelligence/shodan_client.py, intelligence/fofa_client.py
   → Impact: 80% of OSINT value from these 3 sources
   → Existing: network_reconnaissance.py partial; no dedicated client libs

4. **[MEDIUM ROI] Extend pattern_mining.py with pyahocorasick wired pipeline**
   → File: intelligence/pattern_mining.py
   → Impact: O(n) pattern matching instead of regex loops
   → Existing: pyahocorasick imported in 101 files but not used in mining

5. **[MEDIUM ROI] Implement Certstream WebSocket client**
   → File: new intelligence/certstream_client.py
   → Impact: real-time certificate threat intelligence
   → Existing: nothing equivalent; certstream is the standard tool

6. **[MEDIUM ROI] Extend HTN planner → autonomous_orchestrator integration**
   → File: planning/htn_planner.py + autonomous_orchestrator.py
   → Impact: hierarchical task decomposition for complex research goals
   → Existing: skeleton htn_planner.py (169 LOC) not called anywhere

7. **[MEDIUM ROI] Thermal monitoring (MacOS IOKit thermal zones)**
   → File: utils/mlx_memory.py (extend) or new macos/thermal.py
   → Impact: thermal throttling awareness for sustained inference
   → Existing: memory pressure only; thermal zone reading absent

8. **[LOW-MEDIUM ROI] Decide Kuzu vs DuckDB for persistent graph**
   → File: knowledge/persistent_layer.py, knowledge/duckdb_store.py
   → Impact: cleaner architecture, remove stub Kuzu references
   → Existing: Kuzu mentioned 9x, imported 3x, used 0x; DuckDB also present

9. **[LOW ROI] Implement GraphQL introspection client**
   → File: new intelligence/graphql_introspector.py
   → Impact: API discovery for GraphQL endpoints
   → Existing: nothing equivalent

10. **[LOW ROI] LightRAG bridge (only if RAG gap exists)**
   → File: N/A — do NOT create new module
   → Impact: would duplicate LanceDB + graph_rag.py + rag_engine.py stack
   → Existing: LanceDB hybrid search + graph_rag.py already cover RAG needs

## 9. Files that should NOT receive more responsibilities

- **autonomous_orchestrator.py** (30,558 LOC) — already the entire system; new code goes to subordinate modules
- **knowledge/persistent_layer.py** (3,575 LOC) — Kuzu decision needed first; otherwise freeze
- **intelligence/relationship_discovery.py** (2,279 LOC) — igraph already complex; don't add more algorithms here
- **brain/hypothesis_engine.py** (2,516 LOC) — keep hypothesis logic here; don't expand scope

## 10. Truly Unavoidable New Files (NEW_REQUIRED)

| File | Reason |
|---|---|
| intelligence/shodan_client.py | Shodan API — genuinely new OSINT source, not extending existing |
| intelligence/fofa_client.py | FOFA — same reasoning |
| intelligence/netlas_client.py | Netlas — same reasoning |
| intelligence/certstream_client.py | Certstream WebSocket — no equivalent in codebase |
| macos/thermal.py | MacOS IOKit thermal zone monitoring — no existing equivalent |

All other v12 items can be integrated into existing files without new top-level modules.