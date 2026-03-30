# Sprint 8BM — Dependency / Test / Ownership Truth Audit

## 1. Executive Summary

| Dimension | Finding |
|-----------|---------|
| Dependency management | requirements.txt ONLY (no pyproject.toml) — torch + torchvision pinned |
| Real torch usage | 5 project files only — torch is NOT a heavy dependency of the core system |
| Core ML stack | MLX + mlx_lm dominate inference; torch only in ner_engine, moe_router, document_intelligence, stealth_layer, stego_detector |
| Graph storage | LanceDB (1 file), Kuzu (1 file), DuckDB (1 file) — co-exist without clear winner |
| Test biggest risk | autonomous_orchestrator.py = 875 test hits — largest blast radius in the codebase |
| Ownership | osint_intel = 116 files, shutdown_opsec = 93 files — highest fragmentation |
| Missing deps | No certstream, nostr_sdk, pyahocorasick, vectorscan, i2plib, stix2, pyyaml, tokenizers |

## 2. Dependency Truth Matrix (project-only imports)

✅ **duckdb** (2 proj)
    - knowledge/duckdb_store.py
    - tests/live_8be/test_live_searxng_8be.py
✅ **uvloop** (0 proj)
✅ **selectolax** (2 proj)
    - loops/fetch_loop.py
    - tools/content_miner.py
❌ **pyroaring**
✅ **xxhash** (6 proj)
    - autonomous_orchestrator.py
    - brain/prompt_cache.py
    - tests/test_sprint79b/test_optimizations.py
    - tools/content_miner.py
    - tools/url_dedup.py
    - ... +1 more
❌ **warcio**
✅ **setproctitle** (1 proj)
    - layers/stealth_layer.py
✅ **httpx** (2 proj)
    - autonomous_orchestrator.py
    - intelligence/blockchain_analyzer.py
✅ **dns** (1 proj)
    - intelligence/network_reconnaissance.py
✅ **msgspec** (3 proj)
    - autonomous_orchestrator.py
    - brain/ner_engine.py
    - utils/shadow_dtos.py
✅ **curl_cffi** (4 proj)
    - autonomous_orchestrator.py
    - coordinators/security_coordinator.py
    - intelligence/stealth_crawler.py
    - stealth/stealth_manager.py
✅ **polars** (0 proj)
✅ **kuzu** (1 proj)
    - knowledge/persistent_layer.py
✅ **usearch** (1 proj)
    - knowledge/lancedb_store.py
✅ **outlines** (2 proj)
    - brain/hermes3_engine.py
    - brain/ner_engine.py
✅ **coremltools** (10 proj)
    - autonomous_orchestrator.py
    - brain/ane_embedder.py
    - brain/dynamic_model_manager.py
    - brain/model_manager.py
    - brain/ner_engine.py
    - ... +5 more
✅ **aiohttp_socks** (5 proj)
    - coordinators/fetch_coordinator.py
    - intelligence/dark_web_intelligence.py
    - tests/test_sprint46.py
    - tools/darknet.py
    - transport/tor_transport.py
❌ **nostr_sdk**
✅ **websockets** (1 proj)
    - transport/nym_transport.py
❌ **pyrogram**
❌ **stix2**
❌ **vectorscan**
❌ **pyahocorasick**
✅ **torch** (7 proj)
    - brain/moe_router.py
    - brain/ner_engine.py
    - intelligence/document_intelligence.py
    - layers/stealth_layer.py
    - security/stego_detector.py
    - ... +2 more
✅ **requests** (3 proj)
    - coordinators/fetch_coordinator.py
    - intelligence/stealth_crawler.py
    - security/self_healing.py
✅ **bs4** (7 proj)
    - coordinators/validation_coordinator.py
    - deep_research/utils.py
    - intelligence/archive_discovery.py
    - intelligence/dark_web_intelligence.py
    - layers/content_layer.py
    - ... +2 more
✅ **pandas** (1 proj)
    - knowledge/lancedb_store.py
❌ **i2plib**
✅ **aiodns** (0 proj)
❌ **whoosh**
❌ **tantivy**
✅ **lancedb** (1 proj)
    - knowledge/lancedb_store.py
❌ **maturin**
✅ **igraph** (3 proj)
    - intelligence/relationship_discovery.py
    - tests/test_sprint44.py
    - tests/test_sprint45.py
❌ **pyyaml**
✅ **aioquic** (1 proj)
    - stealth/stealth_manager.py
❌ **pyppeteer**
✅ **nodriver** (1 proj)
    - coordinators/fetch_coordinator.py
✅ **playwright** (1 proj)
    - coordinators/render_coordinator.py
❌ **structlog**
✅ **orjson** (14 proj)
    - autonomous_orchestrator.py
    - dht/kademlia_node.py
    - dht/local_graph.py
    - federated/model_store.py
    - memory/shared_memory_manager.py
    - ... +9 more
✅ **lmdb** (15 proj)
    - coordinators/fetch_coordinator.py
    - dht/local_graph.py
    - federated/model_store.py
    - knowledge/atomic_storage.py
    - knowledge/lancedb_store.py
    - ... +10 more
✅ **msgspec** (3 proj)
    - autonomous_orchestrator.py
    - brain/ner_engine.py
    - utils/shadow_dtos.py
❌ **yara**
❌ **psycopg2**
❌ **asyncpg**
❌ **motor**
✅ **redis** (0 proj)
✅ **faiss** (3 proj)
    - context_optimization/context_cache.py
    - context_optimization/dynamic_context_manager.py
    - coordinators/memory_coordinator.py
✅ **onnxruntime** (0 proj)
❌ **vllm**
✅ **transformers** (2 proj)
    - layers/stealth_layer.py
    - tests/test_sprint8l_live.py
❌ **tokenizers**
❌ **sentencepiece**
❌ **tiktoken**
✅ **rapidfuzz** (2 proj)
    - intelligence/identity_stitching.py
    - knowledge/entity_linker.py
❌ **jellyfish**

## 3. Capability Overlap (project-only)

### ane_embedder: 23 project files
- autonomous_orchestrator.py
- brain/ane_embedder.py
- brain/dynamic_model_manager.py
- brain/model_manager.py
- brain/ner_engine.py
- captcha_solver.py
- coordinators/resource_allocator.py
- core/resource_governor.py
- ... +15 more
### pattern_matcher: 7 project files
- intelligence/document_intelligence.py
- tests/probe_8bd/phase1_ft_probe_314.py
- tests/probe_8bd/test_phase1_ft_probe_314.py
- tests/probe_8bg/probe_compat_313t.py
- tests/test_sprint8au_aho_shadow.py
- tests/test_sprint8aw_aho_integration.py
- utils/aho_extractor.py
### kuzu_store: 121 project files
- __init__.py
- autonomous_analyzer.py
- autonomous_orchestrator.py
- brain/dynamic_model_manager.py
- brain/gnn_predictor.py
- brain/hypothesis_engine.py
- brain/inference_engine.py
- brain/insight_engine.py
- ... +113 more
### lightrag_bridge: 27 project files
- __init__.py
- autonomous_orchestrator.py
- brain/hypothesis_engine.py
- capabilities.py
- coordinators/graph_coordinator.py
- core/mlx_embeddings.py
- enhanced_research.py
- knowledge/__init__.py
- ... +19 more
### certstream: 3 project files
- intelligence/stealth_crawler.py
- tests/test_sprint61.py
- transport/nym_transport.py
### graphql_scanner: 5 project files
- autonomous_orchestrator.py
- intelligence/__init__.py
- intelligence/exposed_service_hunter.py
- network/js_bundle_extractor.py
- tools/deep_web_hints.py
### fediverse: 0 project files
### websocket_monitor: 5 project files
- coordinators/swarm_coordinator.py
- intelligence/data_leak_hunter.py
- intelligence/stealth_crawler.py
- tests/test_sprint61.py
- transport/nym_transport.py
### ipfs_probe: 2 project files
- intelligence/archive_discovery.py
- intelligence/temporal_archaeologist.py
### shodan_fofa_netlas: 0 project files
### aleph_open_sanctions: 0 project files
### whisper_audio: 7 project files
- autonomous_orchestrator.py
- config.py
- coordinators/multimodal_coordinator.py
- forensics/__init__.py
- forensics/metadata_extractor.py
- intelligence/decision_engine.py
- layers/stealth_layer.py
### visual_osint: 51 project files
- autonomous_analyzer.py
- autonomous_orchestrator.py
- captcha_solver.py
- config.py
- coordinators/multimodal_coordinator.py
- coordinators/render_coordinator.py
- forensics/__init__.py
- forensics/metadata_extractor.py
- ... +43 more

## 4. Test Impact Hotspots (project-only)

| Target | Project Test Hits | Risk Level |
|--------|-------------------|------------|
| autonomous_orchestrator | 875 | CRITICAL |
| pattern | 204 | HIGH |
| snapshot | 177 | HIGH |
| shutdown | 100 | MEDIUM |
| hermes3_engine | 85 | MEDIUM |
| fetch_coordinator | 57 | MEDIUM |
| lance | 53 | MEDIUM |
| Queue | 49 | LOW |
| mlx_memory | 27 | LOW |
| moe_router | 25 | LOW |
| duckdb_store | 22 | LOW |
| ClientSession | 17 | LOW |
| ddgs | 3 | LOW |
| kuzu | 1 | LOW |
| uvloop | 0 | LOW |

## 5. Ownership Fragmentation (project-only)

- **transport**: 42 files
- **mlx_inference**: 51 files
- **graph_vector_rag**: 46 files
- **osint_intel**: 116 files
- **shutdown_opsec**: 93 files

## 6. Hidden Debt

### HD-1: torch is pinned but barely used
requirements.txt pins torch==2.5.1 and torchvision==0.20.1.
Only 5 project files import torch: moe_router, ner_engine, document_intelligence, stealth_layer, stego_detector.
This is a HEAVY dependency (≈2GB) for minimal usage. Consider replacing torch-based NER with MLX alternative.

### HD-2: No pyproject.toml
The entire project has no structured dependency declaration. requirements.txt has 2 lines.
This makes it impossible to understand what is prod vs dev vs optional.

### HD-3: Three graph stores coexist
LanceDB (knowledge/lancedb_store.py), Kuzu (knowledge/persistent_layer.py), DuckDB (knowledge/duckdb_store.py).
All three are referenced but none dominate. Kuzu import is in persistent_layer.py but only 1 site.
Decision required: consolidate on one or define clear boundaries.

### HD-4: OSINT ownership is fragmented across 116 files
No single owner for OSINT pipeline. intelligence/, network/, autonomous_orchestrator.py all contain OSINT code.
This makes it hard to add new OSINT sources without overlap.

### HD-5: pyahocorasick and vectorscan not imported anywhere
Both are listed in model_data_hits as keywords but have 0 actual Python imports.
Pattern matching is done via regex or other means. Adding these deps would be net-new.

### HD-6: autonomous_orchestrator test blast radius
875 test hits referencing 'autonomous_orchestrator'. Any refactor here breaks the most tests.
This file should NEVER be expanded — all new code goes to subordinate modules.

## 7. Required Output Table

| PLAN_ITEM | READINESS | ALREADY_HAVE | BEST_FILE_TO_EXTEND | DEP_STATUS | TEST_RISK | DUP_RISK | NOTES |
|-----------|-----------|--------------|---------------------|------------|-----------|----------|-------|
| torch ML | PARTIAL | ner_engine, doc_intel, stealth, stego | replace torch with mlx | KEEP/REDUCE | MEDIUM | LOW | 5 files only; consider mlx replacement |
| coremltools | PARTIAL | ane_embedder, model_manager | brain/ane_embedder.py | KEEP | LOW | LOW | ANE offline conversion is the gap |
| mlx-lm | READY | hermes3_engine, moe_router | brain/hermes3_engine.py | KEEP | MEDIUM | LOW | Full speculative + KV cache |
| duckdb | READY | knowledge/duckdb_store.py | knowledge/duckdb_store.py | KEEP | MEDIUM | MEDIUM | Coexists with LanceDB/Kuzu |
| kuzu | PARTIAL | knowledge/persistent_layer.py only | decision needed | DEV_ONLY | LOW | HIGH | Only 1 import; decide keep or remove |
| lancedb | READY | knowledge/lancedb_store.py | knowledge/lancedb_store.py | KEEP | MEDIUM | MEDIUM | Coexists with DuckDB/Kuzu |
| igraph | READY | intelligence/relationship_discovery.py | intelligence/relationship_discovery.py | KEEP | LOW | LOW | Used for graph analytics only |
| orjson | READY | 14 project files | (already everywhere) | KEEP | LOW | LOW | Standard in project |
| lmdb | READY | 19 project files | (already everywhere) | KEEP | LOW | LOW | Standard in project |
| curl_cffi | READY | 4 project files | coordinators/fetch_coordinator.py | KEEP | MEDIUM | LOW | Stealth HTTP transport |
| msgspec | READY | 4 project files | (already in use) | KEEP | LOW | LOW | Used in shadow DTOs |
| pyahocorasick | MISSING | 0 imports | intelligence/pattern_mining.py | ADD | LOW | LOW | O(n) pattern matching |
| vectorscan | MISSING | 0 imports | — | ADD if needed | LOW | LOW | Only if pyahocorasick insufficient |
| certstream | MISSING | 0 imports | intelligence/certstream_client.py (NEW) | ADD | LOW | LOW | Real-time cert OSINT |
| nostr_sdk | MISSING | 0 imports | — | DO NOT ADD | LOW | LOW | No nostr plan in v12 |
| i2plib | MISSING | 0 imports | — | DO NOT ADD | LOW | LOW | Tor already covers darknet |
| pyyaml | MISSING | 0 imports | — | DEV_ONLY | LOW | LOW | Only if config YAML needed |
| tokenizers | MISSING | 0 imports | huggingface/tokenizers via mlx_lm | DEV_ONLY | LOW | LOW | Already covered by mlx_lm |
| whisper | PARTIAL | 17 files mention | intelligence/audio_intel.py (NEW) | ADD | LOW | LOW | mlx-whisper for audio OSINT |
| stix2 | MISSING | 0 imports | — | DO NOT ADD | LOW | LOW | CTI formats not in v12 plan |

## 8. Final Recommendations

### 15 items to implement by extending existing files:

- ANE offline conversion → *brain/ane_embedder.py*: convert_to_ane() placeholder → real MLX→CoreML
- MLX KV cache compression → *brain/hermes3_engine.py*: _compress_kv_cache already exists, refine
- torch → MLX NER replacement → *brain/ner_engine.py*: Replace torch NER with mlx-lm based NER
- pyahocorasick pipeline → *intelligence/pattern_mining.py*: Wire automaton into mining loop
- Certstream WebSocket client → *new: intelligence/certstream_client.py*: Standard Python websocket client
- Shodan API client → *new: intelligence/shodan_client.py*: shodan Python SDK
- FOFA API client → *new: intelligence/fofa_client.py*: FOFA SDK or requests
- GraphQL introspection → *new: intelligence/graphql_scanner.py*: graphql-request library
- DuckDB/LanceDB boundary → *knowledge/duckdb_store.py + knowledge/lancedb_store.py*: Define clear data model split
- Thermal monitoring → *utils/mlx_memory.py*: Extend with IOKit thermal zone reading
- RL/QMIX wiring → *rl/marl_coordinator.py + autonomous_orchestrator.py*: Connect existing QMIX to action selection
- HTN planner activation → *planning/htn_planner.py*: Wire skeleton into execution loop
- Kuzu decision → *knowledge/persistent_layer.py*: Resolve: Kuzu or not — then implement or remove
- WebSocket monitoring → *intelligence/websocket_monitor.py (NEW)*: socket.io / WebSocket scraping
- Whisper audio OSINT → *intelligence/audio_intel.py (NEW)*: mlx-whisper integration

### 10 items NOT to add yet (duplicate current stack):

- LightRAG — duplicates LanceDB + graph_rag + rag_engine stack
- vllm — M1 incompatible, MLX is the inference target
- tantivy / whoosh — LanceDB FTS already covers search
- psycopg2 / asyncpg / motor — no PostgreSQL in v12 architecture
- redis — LMDB already covers persistence use cases
- faiss — LanceDB HNSW is the vector index
- maturin — Python-only project, no Rust native extensions needed
- stix2 — CTI formats not in current v12 scope
- pyrogram — Telegram scraping deferred
- nostr_sdk — nostr not in v12 OSINT plan

### 10 highest-risk dependency changes:

- torch → MLX replacement in ner_engine (breaking change for NER quality)
- Adding pyahocorasick (new native dep, build on M1 may fail)
- Adding certstream (new WebSocket dependency)
- Changing duckdb/lancedb/kuzu boundary (data migration risk)
- Adding whisper (heavy MLX model, RAM pressure)
- Removing kuzu (if it has hidden deps elsewhere)
- Upgrading mlx-lm version (KV cache API changes)
- Changing coremltools version (ANE compatibility)
- Adding shapely / geospatial libs (not yet needed)
- Adding networkx (igraph already covers graph algorithms)

### 10 test hotspots that must be protected:

- **autonomous_orchestrator.py**: 875 hits — any change here has massive test blast radius
- **fetch_coordinator pattern refs**: 204 pattern hits — pattern matching is core loop
- **snapshot/refactor targets**: 177 snapshot hits — state management critical
- **shutdown hooks**: 100 shutdown hits — graceful shutdown invariant
- **Queue operations**: 49 queue hits — async message passing integrity
- **hermes3_engine**: 85 hits — LLM inference correctness
- **duckdb_store**: 22 hits — persistent storage correctness
- **lance references**: 53 lance hits — vector search correctness
- **ClientSession**: 17 hits — HTTP transport
- **ddgs (DuckDuckGo)**: 3 hits — search integration

## 9. Truly Unavoidable New Files

| File | Justification |
|------|---------------|
| intelligence/certstream_client.py | Certstream WebSocket — no equivalent in codebase |
| intelligence/shodan_client.py | Shodan API — core OSINT source, not covered |
| intelligence/fofa_client.py | FOFA — same |
| intelligence/graphql_scanner.py | GraphQL introspection — no equivalent |
| intelligence/audio_intel.py | mlx-whisper audio OSINT — no audio pipeline exists |
| macos/thermal.py | MacOS IOKit thermal monitoring — utils/mlx_memory.py gap |
All other items extend existing files.