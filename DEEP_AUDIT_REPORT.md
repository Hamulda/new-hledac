# DEEP ARCHITECTURE AUDIT — hledac/universal/

**Date:** 2026-02-16
**Auditor:** Claude Opus 4.6 (Senior Software Architect + Performance Engineer)
**Target:** `/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/`
**System:** Fully autonomous OSINT/deep research platform, MacBook Air M1 8GB

---

## A) EXECUTIVE SUMMARY

### 5 Biggest Strengths

1. **Disk-first discipline in core paths.** EvidenceLog, WARC/WACZ archival, CDXJ indices, and SQLite-backed distillation all persist to disk. Ring buffers (evidence_ring≤20, url_ring≤10, hash_ring≤10) enforce bounded RAM in the knowledge layer. Top-K heaps cap findings (50) and sources (30) in the research manager.

2. **1-model-at-a-time lifecycle is production-grade.** `brain/model_manager.py` uses an asyncio.Lock, explicit unload → gc.collect() → mx.clear_cache() before every swap. NER subprocess isolation (`ner_engine.py`) is a best-in-class pattern: child process exits = OS reclaims all RAM. MoE router caps active experts at 2 with LRU eviction.

3. **Forensic evidence chain is end-to-end.** evidence_id flows from Claim creation → ClaimCluster.add_evidence → PersistentKnowledgeLayer.touch_node → GraphRAGOrchestrator.multi_hop_search. WARC records carry WARC-Record-ID; CDXJ maintains sorted invariant; ArchiveValidator verifies revisit dedupe + Concurrent-To linkage. EvidenceLog produces tamper-evident JSONL with run manifests.

4. **Security/text safety pipeline exists on the critical path.** `_SecurityManager` in the orchestrator chains pii_gate.sanitize → unicode_analyzer → encoding_detector → bounded payload analysis. MAX_SANITIZE_LENGTH=8192 and MAX_ANALYSIS_LENGTH=12288 are enforced. High-confidence PII categories are masked; low-confidence (USERNAME/DATE/URL) are filtered out to avoid over-masking.

5. **Tool subsystem is well-bounded.** content_extractor (50KB input / 20KB output), content_miner (50KB HTML / 50 links / 2000 chars), ftp_explorer (256KB files / depth 2 / 200 entries), delta_compressor (200KB / 20K lines), metadata_dedup (TOP_K=200, MAX_COMPARISONS=50K) — all have hard caps that prevent runaway RAM.

### 5 Biggest Risks

1. **~60% of the codebase is orphaned / not wired into the orchestrator.** 14 of 18 coordinators, all 12 layers (via LayerManager), the autonomy/ package, deep_probe.py, quantum_pathfinder.py, and most intelligence/ modules are implemented but never called from the main execution path. This is not aspirational code — many are production-quality (quantum_pathfinder: 956 lines, memory_coordinator: 2,438 lines, rag_engine: 1,225 lines with real HNSW+BM25) — they're just disconnected.

2. **autonomous_orchestrator.py is a 15,003-line God Object.** It contains FullyAutonomousOrchestrator, _ResearchManager, _SecurityManager, _MemoryManager, BudgetManager, _LazyImportCoordinator, and 20+ internal manager classes in a single file. This makes it extremely difficult to test, refactor, or reason about in isolation. The orchestrator also re-implements functionality that exists in dedicated coordinator/layer modules.

3. **Unbounded RAM collections in hypothesis_engine, inference_engine, execution_optimizer, and deduplication.** `hypothesis_engine._evidence` (Dict), `inference_engine._evidence_graph` (Dict[str, Set[str]]), `execution_optimizer.parallel_groups` (Dict), and `deduplication.worker_metrics` (Dict) all grow without caps. On multi-hour research runs, these can consume gigabytes.

4. **E2E tests import a removed module (ReAct).** `tests/e2e_autonomous_loop.py` imports `from hledac.universal.react.react_orchestrator import ReActOrchestrator` — this module no longer exists. The E2E test suite is broken. Meanwhile, test_autonomous_orchestrator.py (8,668 lines) covers many invariants but has no integration test that runs an actual research loop end-to-end.

5. **PII gate is optional (try/except) and regex-only.** If the `security.pii_gate` import fails, _SecurityManager silently degrades. There's no ML-based secondary validation, no international phone/address patterns, no IPv6, no redaction audit trail. Content from content_miner, ftp_explorer, and deep_web_hints does not explicitly pass through pii_gate before persistence.

### Top 5 Next Actions

1. **Cap all unbounded collections** — Add MAX_EVIDENCE=10,000 eviction to hypothesis_engine and inference_engine; add LRU pruning to execution_optimizer.parallel_groups and worker_metrics. Estimated: 4 hours, zero risk, high impact.

2. **Fix E2E tests** — Remove ReAct imports from e2e_autonomous_loop.py; add a minimal integration test that runs `FullyAutonomousOrchestrator.execute_research()` with mocked network. Estimated: 6 hours, low risk, high impact.

3. **Wire LayerManager.initialize_all() into orchestrator startup** — This single integration point activates all 12 layers and their GhostDirector singleton. Estimated: 8 hours, medium risk, high impact.

4. **Extract _ResearchManager, _SecurityManager, _MemoryManager from orchestrator into separate files** — First step toward decomposing the God Object. Estimated: 16 hours, medium risk, high impact.

5. **Make PII gate mandatory** — Remove try/except fallback; add explicit pii_gate.sanitize() calls in content_miner, ftp_explorer, deep_web_hints ingestion paths. Estimated: 4 hours, low risk, high impact.

---

## B) REPOSITORY MAP

### High-Level Tree

```
universal/
├── autonomous_orchestrator.py      ← 15,003 lines: GOD OBJECT, central spine
├── autonomous_analyzer.py          ← Analyzer entry point
├── types.py                        ← Core type definitions
├── evidence_log.py                 ← Tamper-evident JSONL log + run manifests
├── config.py                       ← M1Presets, runtime config
├── budget_manager.py               ← Time/RAM/network/snapshot budgets
├── model_lifecycle.py              ← Alternative async context manager (redundant with brain/model_manager)
├── capabilities.py                 ← Capability registry + gating
├── tool_registry.py                ← Tool registration + schema validation
├── orchestrator_integration.py     ← Integration glue
├── research_context.py             ← Research session context
├── tot_integration.py              ← Tree-of-Thought integration
├── enhanced_research.py            ← Enhanced research patterns
├── deep_probe.py                   ← 546 lines: Shadow Walker, Dorking, Wayback CDX (ORPHANED)
├── behavior_simulator.py           ← Behavior simulation (ORPHANED)
│
├── brain/                          ← LLM reasoning layer (6,500+ lines)
│   ├── model_manager.py            ← CANONICAL 1-model-at-a-time lifecycle
│   ├── hermes3_engine.py           ← Hermes-3-Llama-3.2-3B (MLX) inference
│   ├── ner_engine.py               ← GLiNER-X NER with subprocess isolation
│   ├── inference_engine.py         ← 2,243 lines: abductive/deductive/multi-hop reasoning
│   ├── hypothesis_engine.py        ← 2,269 lines: hypothesis gen + adversarial verification
│   ├── insight_engine.py           ← 1,000 lines: 5-level synthesis hierarchy
│   ├── distillation_engine.py      ← 789 lines: MLP critic + SQLite training
│   ├── moe_router.py              ← 693 lines: MoE with LRU (max 2 experts)
│   └── decision_engine.py          ← 230 lines: HELPER (not canonical)
│
├── intelligence/                   ← Domain OSINT modules (20 files)
│   ├── decision_engine.py          ← CANONICAL module routing (635 lines)
│   ├── workflow_orchestrator.py    ← Module execution + correlation (987 lines)
│   ├── input_detector.py           ← Input type classification
│   ├── archive_discovery.py        ← Advanced archive escalation
│   ├── web_intelligence.py         ← Unified web platform
│   ├── academic_search.py          ← MSQES integration
│   ├── stealth_crawler.py          ← User-agent rotation, evasion
│   ├── temporal_analysis.py        ← Temporal patterns
│   ├── temporal_archaeologist.py   ← Deep temporal research
│   ├── pattern_mining.py           ← Behavioral/communication patterns
│   ├── relationship_discovery.py   ← Social network analysis
│   ├── identity_stitching.py       ← Cross-platform identity linking
│   ├── document_intelligence.py    ← PDF/Office/image analysis
│   ├── data_leak_hunter.py         ← Data leak detection
│   ├── exposed_service_hunter.py   ← S3/DB/GraphQL/CT log discovery
│   ├── blockchain_analyzer.py      ← Crypto forensics
│   ├── cryptographic_intelligence.py ← Hash/cipher/cert analysis
│   ├── network_reconnaissance.py   ← Network mapping
│   ├── advanced_image_osint.py     ← Image analysis
│   └── dark_web_intelligence.py    ← .onion exploration
│
├── coordinators/                   ← 18 coordinator files (MOSTLY ORPHANED)
│   ├── base.py                     ← Abstract base (482 lines)
│   ├── coordinator_registry.py     ← Registry (616 lines, NEVER CALLED)
│   ├── research_optimizer.py       ← ✅ WIRED: cache, dedup, adaptive timeouts
│   ├── agent_coordination_engine.py ← ✅ CONDITIONAL: multi-agent dispatch
│   ├── memory_coordinator.py       ← 2,438 lines neuromorphic memory (ORPHANED)
│   ├── research_coordinator.py     ← 1,341 lines research routing (ORPHANED)
│   ├── execution_coordinator.py    ← 994 lines GhostDirector+Ray (ORPHANED)
│   └── [11 more orphaned files]
│
├── layers/                         ← 12 layer files (ALL DISCONNECTED from orchestrator)
│   ├── layer_manager.py            ← 912 lines: orchestrates all layers
│   ├── ghost_layer.py, memory_layer.py, security_layer.py, stealth_layer.py,
│   │   research_layer.py, privacy_layer.py, communication_layer.py,
│   │   content_layer.py, coordination_layer.py
│   └── smart_coordination.py, hive_coordination.py (ORPHANED)
│
├── knowledge/                      ← Knowledge graph + RAG (8 files)
│   ├── persistent_layer.py         ← WARC, WACZ, CDXJ, ArchiveValidator, Memento
│   ├── atomic_storage.py           ← EvidencePacket, ClaimCluster, ring buffers
│   ├── rag_engine.py               ← 1,225 lines: HNSW + BM25 hybrid (NOT WIRED)
│   ├── graph_rag.py                ← GraphRAG orchestrator
│   ├── graph_builder.py, graph_layer.py, context_graph.py, entity_linker.py
│   └── __init__.py
│
├── tools/                          ← Well-bounded extraction tools (9 files)
│   ├── content_extractor.py        ← 50KB/20KB caps
│   ├── content_miner.py            ← 966 lines: HTML/PDF/image/EXIF
│   ├── deep_web_hints.py           ← Forms, APIs, JS markers
│   ├── delta_compressor.py         ← 200KB/20K lines
│   ├── ftp_explorer.py             ← 256KB/depth 2/200 entries
│   ├── metadata_dedup.py           ← Domain-binned O(n) dedup
│   ├── reranker.py                 ← FlashRank TinyBERT (4MB ONNX)
│   ├── rolling_hash_engine.py      ← CDC: 2KB-64KB chunks, max 2048
│   └── smart_deduplicator.py       ← REDUNDANT with utils/deduplication.py
│
├── utils/                          ← Utility modules (19 files)
│   ├── bloom_filter.py             ← Scalable Bloom filter (configurable FPP)
│   ├── deduplication.py            ← 1,240 lines: semantic+content+metadata dedup
│   ├── execution_optimizer.py      ← 1,644 lines: UNBOUNDED DICTS (HIGH RISK)
│   ├── filtering.py                ← Binary fuse + quotient + persistent frontier
│   ├── intelligent_cache.py        ← LRU/LFU/adaptive, 100MB cap, 90% eviction
│   ├── entity_extractor.py         ← Regex: email, BTC, ETH, API keys, etc.
│   ├── language.py                 ← FastLangDetect + fallback
│   ├── performance_monitor.py      ← Thermal/memory pressure states
│   ├── encryption.py               ← AES-256-GCM (XOR fallback = INSECURE)
│   ├── lazy_imports.py             ← Deferred import manager
│   └── [robots_parser, rate_limiter, semantic, ranking, etc.]
│
├── security/                       ← Security pipeline (11 files)
│   ├── pii_gate.py                 ← 11 PII categories, regex-only
│   ├── ram_vault.py                ← macOS RAM disk (hdiutil), 256MB default
│   ├── audit.py, destruction.py, obfuscation.py, quantum_safe.py,
│   │   stego_detector.py, vault_manager.py, self_healing.py,
│   │   digital_ghost_detector.py, deep_research_security.py
│   └── __init__.py
│
├── text/                           ← Text analysis (3 files)
│   ├── encoding_detector.py, hash_identifier.py (532 lines), unicode_analyzer.py
│   └── __init__.py
│
├── autonomy/                       ← FULLY ORPHANED (3 files)
│   ├── agent_meta_optimizer.py, planner.py, research_engine.py
│   └── __init__.py
│
├── [small packages: deep_research/, execution/, forensics/, graph/, network/, stealth/, infrastructure/]
│
└── tests/
    ├── test_autonomous_orchestrator.py  ← 8,668 lines (comprehensive)
    ├── e2e_autonomous_loop.py           ← BROKEN (imports removed ReAct module)
    └── tool_schema_validation.py        ← Tool schema checks
```

### Core Spine vs Peripheral

**Core Spine (actually executes):**
- `autonomous_orchestrator.py` → `brain/model_manager.py` → `brain/hermes3_engine.py` / `brain/ner_engine.py`
- `autonomous_orchestrator.py` → `knowledge/persistent_layer.py` → `knowledge/atomic_storage.py` → `knowledge/graph_rag.py`
- `autonomous_orchestrator.py` → `coordinators/research_optimizer.py`
- `autonomous_orchestrator.py` → `security/pii_gate.py` + `text/*`
- `autonomous_orchestrator.py` → `tools/*` (content extraction, dedup, FTP, etc.)
- `evidence_log.py`, `budget_manager.py`, `config.py`, `types.py`, `capabilities.py`

**Peripheral (implemented but disconnected):**
- All 12 `layers/` modules (including LayerManager)
- 14 of 18 `coordinators/` modules
- All 3 `autonomy/` modules
- `knowledge/rag_engine.py` (HNSW+BM25 — fully implemented, not called)
- `deep_probe.py`, `graph/quantum_pathfinder.py`
- Most `intelligence/` modules (loaded lazily but not actively dispatched)

---

## C) DEPENDENCY GRAPH (CONCEPTUAL)

### Subsystem: Frontier / URL Management

| Attribute | Value |
|-----------|-------|
| **Key files** | `utils/filtering.py`, `utils/robots_parser.py`, orchestrator internal queue |
| **Inputs** | Seed URLs from research query, discovered URLs from content_miner |
| **Outputs** | Deduplicated, prioritized URL queue |
| **Storage** | Binary fuse filter (RAM), PersistentFrontier (JSON/SQLite) |
| **Caps** | MAX_URLS_PER_PHASE=20, BFF cache=1000, frontier depth-limited |
| **Orchestrator call** | Internal `_ResearchManager` URL queue management |

### Subsystem: Fetch / Content Extraction

| Attribute | Value |
|-----------|-------|
| **Key files** | `tools/content_extractor.py`, `tools/content_miner.py`, `tools/ftp_explorer.py`, `tools/deep_web_hints.py` |
| **Inputs** | URLs from frontier, HTTP responses |
| **Outputs** | ExtractedContent (text, links, metadata), DeepWebHints (forms, APIs) |
| **Storage** | Disk via WARC records in knowledge/persistent_layer |
| **Caps** | 50KB HTML input, 20KB text output, 50 links, 256KB FTP files |
| **Orchestrator call** | Via tool_registry dispatch in research loop |

### Subsystem: Robots / Sitemaps / Rate Limiting

| Attribute | Value |
|-----------|-------|
| **Key files** | `utils/robots_parser.py`, `utils/rate_limiter.py` |
| **Inputs** | Domain URLs |
| **Outputs** | Allow/deny decisions, crawl delays |
| **Storage** | In-memory cache with TTL |
| **Caps** | Per-domain rate limits, configurable delays |
| **Orchestrator call** | Pre-fetch check in research loop |

### Subsystem: Deduplication

| Attribute | Value |
|-----------|-------|
| **Key files** | `utils/deduplication.py` (1,240 lines), `tools/smart_deduplicator.py` (217 lines), `tools/metadata_dedup.py`, `tools/rolling_hash_engine.py`, `utils/bloom_filter.py` |
| **Inputs** | Extracted text, metadata, content hashes |
| **Outputs** | Duplicate flags, near-dup scores, delta patches |
| **Storage** | Bloom filter (RAM, ~120KB@100K/1%FPP), SHA256 in-memory |
| **Caps** | TOP_K=200 metadata, MAX_COMPARISONS=50K, 2048 CDC chunks |
| **Orchestrator call** | Via research_optimizer.py dedup hooks |
| **ISSUE** | smart_deduplicator.py is a simpler subset of deduplication.py — redundant |

### Subsystem: Evidence / Provenance

| Attribute | Value |
|-----------|-------|
| **Key files** | `evidence_log.py`, `knowledge/atomic_storage.py`, `knowledge/persistent_layer.py` |
| **Inputs** | Tool outputs with evidence_id, claim text, source metadata |
| **Outputs** | EvidencePacket, ClaimCluster, tamper-evident JSONL |
| **Storage** | JSONL on disk (evidence_log), SQLite (distillation), ring buffers |
| **Caps** | evidence_ring≤20, url_ring≤10, hash_ring≤10, MAX_EVIDENCE=20 per cluster, MAX_FINDINGS_IN_RAM=50 |
| **Orchestrator call** | `_ResearchManager` creates evidence, logs via evidence_log |

### Subsystem: Archival (WARC/WACZ/Memento)

| Attribute | Value |
|-----------|-------|
| **Key files** | `knowledge/persistent_layer.py` (WarcWriter, WaczPacker, ArchiveValidator) |
| **Inputs** | HTTP responses, URL metadata, Memento TimeMaps |
| **Outputs** | .warc.gz files, .wacz packages, CDXJ indices |
| **Storage** | Disk: runs/<run_id>/warcs/, runs/<run_id>/wacz/ |
| **Caps** | MAX_RECORDS_PER_RUN=500, MAX_MEMENTOS=20, MAX_SELECTED=3, MAX_AGGREGATOR_CALLS=1, MAX_CDXJ_LINES=200 |
| **Orchestrator call** | ArchiveValidator triggered on drift/404/410/js-gated+empty preview |

### Subsystem: Graph Reasoning

| Attribute | Value |
|-----------|-------|
| **Key files** | `knowledge/graph_rag.py`, `knowledge/graph_builder.py`, `knowledge/context_graph.py`, `knowledge/entity_linker.py`, `brain/inference_engine.py` |
| **Inputs** | Evidence nodes, entity mentions, relationship edges |
| **Outputs** | Multi-hop paths with evidence_ids, contradiction detections |
| **Storage** | In-memory graph (Dict[str, Set[str]]) — UNBOUNDED |
| **Caps** | max_support_evidence_ids=25 per fact |
| **Orchestrator call** | GraphRAGOrchestrator.multi_hop_search() |
| **ISSUE** | Evidence graph in inference_engine is unbounded |

### Subsystem: Claims / Clustering

| Attribute | Value |
|-----------|-------|
| **Key files** | `knowledge/atomic_storage.py` |
| **Inputs** | SVO triples from text, evidence_ids, domain metadata |
| **Outputs** | ClaimCluster with veracity scores, stance scoring, contradiction indicators |
| **Storage** | Ring buffers: evidence_ids≤20, domains≤20, object_variants≤10, timeline≤10 |
| **Caps** | All ring-buffered with explicit MAX constants |
| **Orchestrator call** | Via _ResearchManager claim processing |

### Subsystem: Security / Text Safety

| Attribute | Value |
|-----------|-------|
| **Key files** | `security/pii_gate.py`, `text/unicode_analyzer.py`, `text/encoding_detector.py`, `text/hash_identifier.py` |
| **Inputs** | All tool output text before logging/persistence/LLM |
| **Outputs** | Sanitized text, PII match reports, Unicode entropy analysis |
| **Storage** | None (stateless pipeline) |
| **Caps** | MAX_SANITIZE_LENGTH=8192, MAX_ANALYSIS_LENGTH=12288, MAX_DECODED_PREVIEW=512 |
| **Orchestrator call** | `_SecurityManager._sanitize_and_analyze_tool_text()` |
| **ISSUE** | PII gate import is try/except (optional); not called on all ingestion paths |

### Subsystem: LLM Inference

| Attribute | Value |
|-----------|-------|
| **Key files** | `brain/model_manager.py`, `brain/hermes3_engine.py`, `brain/ner_engine.py`, `brain/moe_router.py` |
| **Inputs** | Research queries, text for NER, context for synthesis |
| **Outputs** | Generated text, entity lists, action decisions |
| **Storage** | Model weights on disk (~3GB Hermes, ~500MB ModernBERT, ~300MB GLiNER) |
| **Caps** | 1 model at a time, NER: 10K chars / 5 labels / 3 texts, MoE: 2 experts max |
| **Orchestrator call** | model_manager.with_phase() context manager |

---

## D) WHAT'S NOT CONNECTED / DEAD CODE

### Orphan Modules (Implemented but Never Called from Orchestrator)

| Module | Lines | Quality | Why Orphaned |
|--------|-------|---------|-------------|
| `coordinators/coordinator_registry.py` | 616 | Production | Registry pattern defined but never instantiated |
| `coordinators/memory_coordinator.py` | 2,438 | Production | Orchestrator uses internal _MemoryManager instead |
| `coordinators/research_coordinator.py` | 1,341 | Production | Orchestrator uses internal _ResearchManager instead |
| `coordinators/execution_coordinator.py` | 994 | Production | GhostDirector+Ray orchestration, never called |
| `coordinators/security_coordinator.py` | Unknown | Stub/partial | Not imported |
| `coordinators/monitoring_coordinator.py` | Unknown | Stub/partial | Not imported |
| `coordinators/validation_coordinator.py` | Unknown | Stub/partial | Not imported |
| `coordinators/advanced_research_coordinator.py` | Unknown | Stub/partial | Not imported |
| `coordinators/performance_coordinator.py` | Unknown | Stub/partial | Not imported |
| `coordinators/multimodal_coordinator.py` | Unknown | Stub/partial | Not imported |
| `coordinators/swarm_coordinator.py` | Unknown | Stub/partial | Not imported |
| `coordinators/resource_allocator.py` | Unknown | Stub/partial | Not imported |
| `coordinators/benchmark_coordinator.py` | Unknown | Stub/partial | Not imported |
| `coordinators/meta_reasoning_coordinator.py` | Unknown | Stub/partial | Not imported |
| `layers/layer_manager.py` | 912 | Production | Not called from orchestrator; layers have independent init |
| `layers/*` (all 12 layers) | ~5,000 total | Mixed | Defined but LayerManager not initialized |
| `knowledge/rag_engine.py` | 1,225 | Production | Full HNSW+BM25 but not called from research flow |
| `autonomy/agent_meta_optimizer.py` | Unknown | Stub | Not imported |
| `autonomy/planner.py` | Unknown | Stub | Not imported |
| `autonomy/research_engine.py` | Unknown | Stub | Not imported |
| `deep_probe.py` | 546 | Production | Shadow Walker + Dorking fully implemented, never dispatched |
| `graph/quantum_pathfinder.py` | 956 | Production | Quantum walks + Grover + sparse COO matrices, never called |
| `model_lifecycle.py` | 363 | Production | Alternative to brain/model_manager.py (redundant) |
| `behavior_simulator.py` | Unknown | Unknown | Never imported |

### Suspected Dead Code Paths

| Location | Symbol | Issue |
|----------|--------|-------|
| `brain/decision_engine.py` | `_llm_based_decide()`, `_hybrid_decide()` | Pass through to `_rule_based_decide()` — never produce different results |
| `brain/moe_router.py` | Entire module | Over-engineered for single-model scenario; all 5 "experts" use same Hermes-3 weights |
| `tests/e2e_autonomous_loop.py` | Entire file | Imports removed `react.react_orchestrator` — cannot execute |
| `tools/smart_deduplicator.py` | `SmartDeduplicator` class | Simpler subset of `utils/deduplication.py` |
| `model_lifecycle.py` | `ModelLifecycle`, `LazyModelLoader` | Alternative to `brain/model_manager.py` — unclear which is canonical |
| `utils/encryption.py` | XOR fallback path | Insecure; should be removed or gated behind `HLEDAC_DEV_MODE` |
| `coordinators/coordinator_registry.py` | `CoordinatorRegistry` class | 616 lines of registry machinery with no caller |

### Duplicate/Redundant Abstractions

| Pair | Lines | Recommendation |
|------|-------|---------------|
| `brain/decision_engine.py` vs `intelligence/decision_engine.py` | 230 vs 635 | NOT duplicates (different layers) but confusing names. Rename brain's to `research_flow_decider.py` |
| `brain/model_manager.py` vs `model_lifecycle.py` | 550 vs 363 | Both enforce 1-model-at-a-time. model_manager is canonical; delete or merge model_lifecycle |
| `tools/smart_deduplicator.py` vs `utils/deduplication.py` | 217 vs 1,240 | Consolidate into deduplication.py |
| Orchestrator `_MemoryManager` vs `coordinators/memory_coordinator.py` | Internal vs 2,438 | Dual implementations — delegate orchestrator to coordinator |
| Orchestrator `_ResearchManager` vs `coordinators/research_coordinator.py` | Internal vs 1,341 | Dual implementations — delegate orchestrator to coordinator |
| Orchestrator `_SecurityManager` vs `coordinators/security_coordinator.py` | Internal vs unknown | Dual implementations — delegate orchestrator to coordinator |

---

## E) PERFORMANCE & RESOURCE ANALYSIS (M1 8GB)

### RAM Hot Spots

| Component | Risk | Current State | Recommended Fix |
|-----------|------|--------------|----------------|
| `brain/hypothesis_engine._evidence` | 🔴 HIGH | Dict, unbounded | Add MAX_EVIDENCE=10,000, LRU eviction |
| `brain/hypothesis_engine._source_credibility` | 🔴 HIGH | Dict, unbounded | Add MAX_SOURCES=5,000 |
| `brain/inference_engine._evidence_graph` | 🔴 HIGH | Dict[str, Set[str]], unbounded | Add MAX_NODES=10,000, prune on overflow |
| `brain/inference_engine._evidence` | 🔴 HIGH | Dict, unbounded | Match with graph node cap |
| `utils/execution_optimizer.parallel_groups` | 🔴 HIGH | Dict, unbounded | Add OrderedDict + age-based pruning |
| `utils/execution_optimizer.worker_metrics` | 🟡 MEDIUM | Dict, unbounded | Cap at max_workers count |
| `utils/deduplication.embedding_cache` | 🟡 MEDIUM | Dict, bounded by `_can_cache_embedding()` | Verify enforcement; add hard 256MB check |
| `tools/rolling_hash_engine` | 🟡 MEDIUM | Max 2048 chunks × 64KB = 128MB worst case | Add pre-check: reject files >128MB for CDC |
| Model loading (Hermes 3B) | ✅ MANAGED | 1-model-at-a-time with gc+mx.clear_cache | Working correctly |
| NER (GLiNER-X) | ✅ MANAGED | Subprocess isolation, 10K char limit | Working correctly |

### IO Hot Spots

| Pattern | Risk | Location | Issue |
|---------|------|----------|-------|
| WARC write per-record | 🟡 MEDIUM | `knowledge/persistent_layer.py` WarcWriter | Each record triggers file I/O; consider buffered writer |
| CDXJ sort on every append | 🟡 MEDIUM | `knowledge/persistent_layer.py` | Sorted insert is O(n); use bisect.insort or defer sort |
| Evidence JSONL append | ✅ LOW | `evidence_log.py` | Append-only, efficient |
| SQLite distillation | ✅ LOW | `brain/distillation_engine.py` | WAL mode would help for concurrent access |
| Bloom filter save/load | ✅ LOW | `utils/bloom_filter.py` | Binary format, efficient |

### CPU Hot Spots

| Operation | Risk | Location | Issue |
|-----------|------|----------|-------|
| Contradiction detection O(n²) | 🟡 MEDIUM | `brain/hypothesis_engine` | Window=100 items caps it, but still 10K comparisons |
| Evidence graph BFS | 🟡 MEDIUM | `brain/inference_engine` | Unbounded queue on large graphs |
| Semantic dedup cosine similarity | 🟡 MEDIUM | `utils/deduplication.py` | Sentence transformer inference per pair |
| Metadata dedup pairwise | ✅ LOW | `tools/metadata_dedup.py` | Domain-binned, capped at 50K comparisons |
| Rolling hash (Gear hash) | ✅ LOW | `tools/rolling_hash_engine.py` | O(n) streaming, efficient |
| PII regex scanning | ✅ LOW | `security/pii_gate.py` | 11 patterns on bounded text (8192 chars) |

### Where to Add/Adjust Caps

| Location | Current | Recommended |
|----------|---------|-------------|
| `hypothesis_engine._evidence` | None | MAX_EVIDENCE=10,000 |
| `hypothesis_engine._source_credibility` | None | MAX_SOURCES=5,000 |
| `inference_engine._evidence_graph` | None | MAX_NODES=10,000 |
| `execution_optimizer.parallel_groups` | None | MAX_GROUPS=100 + age pruning (>1hr) |
| `execution_optimizer.worker_metrics` | None | MAX_WORKERS=16 |
| `deduplication.embedding_cache` | 256MB soft | 256MB hard check with len() guard |
| Rolling hash input | 128MB implicit | Explicit reject at 64MB |
| BFS in inference_engine | None | MAX_BFS_DEPTH=10, MAX_QUEUE=1000 |

### Where to Switch from Eager to Streaming

| Operation | Current | Improvement |
|-----------|---------|------------|
| WARC record writing | Eager per-record | Buffer up to 10 records, flush batch |
| CDXJ index building | Sorted list in RAM | Write unsorted, sort at finalize time |
| Evidence log writing | Append per event | Already streaming (good) |
| Content extraction | Full HTML in RAM (50KB cap) | Already bounded (good) |
| Multi-hop graph search | BFS accumulates all paths | Streaming yield of paths with depth limit |

---

## F) CORRECTNESS & AUDITABILITY

### Are All Claims Traceable?

**YES, on the critical path.** The evidence chain flows:

```
Claim.create_from_text(text, evidence_id)
  → ClaimCluster.add_evidence(evidence_id, domain, ...)
    → evidence_ids ring buffer (≤20)
    → source_fp_map: Dict[evidence_id → source_fp]
  → PersistentKnowledgeLayer.touch_node(node_id, metadata={'evidence_id': ...})
    → evidence_ring[-20:]
  → GraphRAGOrchestrator.multi_hop_search()
    → Returns: {'evidence_ids': [id1, id2, ...], 'support_evidence_ids': [...]}
```

**GAP:** Evidence ID generation is hash-based but there's no explicit validation at ingestion time. A malformed evidence_id would propagate silently.

**GAP:** Source fingerprint (`source_fp`) computation algorithm is not documented — unclear if it's deterministic across runs.

### Missing evidence_id / Provenance Links

| Location | Issue |
|----------|-------|
| `tools/content_miner.py` output | No evidence_id attached to MiningResult |
| `tools/deep_web_hints.py` output | No evidence_id attached to DeepWebHints |
| `tools/ftp_explorer.py` output | No evidence_id attached to FTPListingItem |
| `intelligence/*` module outputs | Evidence_id attachment depends on orchestrator wrapping |

### Are Logs Tamper-Evident End-to-End?

**YES, for the EvidenceLog.** JSONL with hash chaining, run manifests, and finalize freeze.

**NO, for tool execution logs.** Tool outputs are logged to standard Python logging (not hash-chained). If an attacker modifies tool output logs, there's no integrity check.

### Are Security/Text Safety Hooks Guaranteed on All Ingestion Points?

**PARTIALLY.** The `_SecurityManager._sanitize_and_analyze_tool_text()` is called from the orchestrator's tool execution path. However:

| Ingestion Point | PII Gate Called? | Unicode Analysis? |
|----------------|-----------------|-------------------|
| Tool execution via orchestrator | ✅ Yes | ✅ Yes |
| Direct content_miner.mine_html() | ❌ No | ❌ No |
| Direct ftp_explorer.list() | ❌ No | ❌ No |
| Direct deep_web_hints.extract() | ❌ No | ❌ No |
| intelligence/ module outputs | ⚠️ Depends on orchestrator wrapping | ⚠️ Depends |
| Graph node metadata | ❌ No explicit sanitization | ❌ No |
| WARC record content | ❌ No (raw archival) | ❌ No |

**Recommendation:** Add a `@sanitized` decorator or pre-persist hook that enforces PII gating on any text before it reaches logs, LLM context, or disk persistence.

---

## G) REFACTOR OPPORTUNITIES

### 1. Decompose the God Object (autonomous_orchestrator.py)

**Current:** 15,003 lines in one file containing 20+ classes.

**Proposed split:**

| New Module | Contents | Est. Lines |
|-----------|----------|-----------|
| `orchestrator/core.py` | FullyAutonomousOrchestrator skeleton, main loop | ~3,000 |
| `orchestrator/research_manager.py` | _ResearchManager + research loop | ~4,000 |
| `orchestrator/security_manager.py` | _SecurityManager | ~1,000 |
| `orchestrator/memory_manager.py` | _MemoryManager + GC coordination | ~1,500 |
| `orchestrator/lazy_imports.py` | _LazyImportCoordinator | ~500 |
| `orchestrator/budget.py` | BudgetManager (or merge with budget_manager.py) | ~500 |
| `orchestrator/phase_engine.py` | Phase transitions, model lifecycle orchestration | ~2,000 |
| `orchestrator/tool_dispatch.py` | Tool execution, schema validation | ~1,500 |

### 2. Eliminate Dual Implementations

| Internal Manager | External Coordinator | Action |
|-----------------|---------------------|--------|
| `_ResearchManager` | `coordinators/research_coordinator.py` | Delegate to coordinator; remove internal |
| `_MemoryManager` | `coordinators/memory_coordinator.py` | Delegate to coordinator; remove internal |
| `_SecurityManager` | `coordinators/security_coordinator.py` | Delegate to coordinator; remove internal |

### 3. Wire LayerManager

Add to orchestrator initialization:
```python
async def _init_layers(self):
    from .layers.layer_manager import LayerManager
    self._layer_manager = LayerManager(config=self.config)
    await self._layer_manager.initialize_all()
```

### 4. Wire RAG Engine

Add to research flow:
```python
# In _ResearchManager.execute_research():
context = await self.rag_engine.hybrid_retrieve(query, top_k=10)
# Feed context to Hermes3 synthesis
```

### 5. Naming / Typing / Contracts

| Current Name | Issue | Proposed Name |
|-------------|-------|--------------|
| `brain/decision_engine.py` | Confusing vs intelligence/decision_engine.py | `brain/research_flow_decider.py` |
| `model_lifecycle.py` (top-level) | Redundant with brain/model_manager.py | Delete or merge into model_manager |
| `tools/smart_deduplicator.py` | Subset of utils/deduplication.py | Delete; update imports |
| `_LazyImportCoordinator` | Not a coordinator; it's a registry | `_LazyImportRegistry` |

### 6. Candidate Interfaces (Ports)

Define these protocols to reduce coupling:

```python
# protocols.py
from typing import Protocol, AsyncIterator

class EvidenceStore(Protocol):
    async def add_evidence(self, evidence_id: str, content: str, metadata: dict) -> None: ...
    async def get_evidence(self, evidence_id: str) -> dict: ...

class TextSanitizer(Protocol):
    def sanitize(self, text: str, max_length: int = 8192) -> str: ...
    def detect_pii(self, text: str) -> list: ...

class ModelGate(Protocol):
    async def load(self, model_type: str) -> None: ...
    async def release(self) -> None: ...
    def current_model(self) -> str | None: ...

class ContentExtractor(Protocol):
    async def extract(self, url: str, html: bytes) -> dict: ...
```

---

## H) TEST SUITE GAPS

### What IS Tested (test_autonomous_orchestrator.py — 8,668 lines)

- Orchestrator initialization smoke tests
- Capability gating (registry, routing, unavailable handling)
- Model lifecycle (M1 8GB constraint, single model loaded, phase transitions)
- Evidence trace (JSONL format, runs directory)
- Concurrency control (semaphore, early-stop)
- ReAct removal verification (pattern scanning)
- Graph wiring (ingest, multi-hop search, capability gating)
- Graph dedup (content hash, URL normalization, edge dedup)
- Persistent dedup across runs
- Evidence IDs end-to-end (multi-hop paths, contradiction detection)
- Temporal metadata (ring buffer limits: evidence≤20, url≤10, hash≤10)
- WARC/WACZ archival (WarcWriter, WaczPacker, ArchiveValidator, CDXJ)
- Security (sanitization, PII gating, Unicode analysis)
- Memory cleanup (gc.collect, mx.clear_cache)

### What is NOT Tested

| Missing Test | Invariant at Risk | Priority |
|-------------|-------------------|----------|
| Budget enforcement integration | BudgetManager.check_*_allowed() actually stops execution | 🔴 CRITICAL |
| RAM caps under load | Collections stay bounded during long runs | 🔴 CRITICAL |
| Disk-first invariant | No full text in RAM; only bounded previews | 🔴 CRITICAL |
| Full research loop (E2E) | Orchestrator produces valid output end-to-end | 🔴 CRITICAL |
| PII detection accuracy | False positive / false negative rates | 🟡 HIGH |
| Archive discovery escalation | Triggered on drift/404/410/js-gated correctly | 🟡 HIGH |
| Dedupe determinism | Same input → same dedup result across runs | 🟡 HIGH |
| Model lifecycle under concurrent requests | No double-load under asyncio.gather | 🟡 HIGH |
| CDXJ sorted invariant | Index stays sorted after concurrent writes | 🟡 MEDIUM |
| Memento routing cache stats | Cache hit ratio tracked correctly | 🟡 MEDIUM |
| Evidence chain end-to-end | evidence_id survives from ingestion to synthesis | 🟡 MEDIUM |

### Suggested New Tests (in test_autonomous_orchestrator.py)

```python
# 1. Budget enforcement actually stops execution
async def test_budget_hard_stop():
    """When budget is exhausted, orchestrator MUST stop within 1 iteration."""
    orch = FullyAutonomousOrchestrator(config=test_config)
    orch.budget_manager.force_exhaust()  # Set all budgets to 0
    result = await orch.execute_research("test query")
    assert result.iterations <= 1
    assert result.stop_reason == "budget_exhausted"

# 2. RAM caps under simulated load
async def test_ram_caps_under_load():
    """Collections must not exceed configured maximums."""
    orch = FullyAutonomousOrchestrator(config=test_config)
    # Simulate 1000 evidence additions
    for i in range(1000):
        orch._research_manager._add_finding(fake_finding(i))
    assert len(orch._research_manager._findings_heap) <= 50  # MAX_FINDINGS_IN_RAM

# 3. Disk-first: no full text in RAM
async def test_disk_first_no_full_text():
    """After processing, only bounded previews remain in RAM."""
    orch = FullyAutonomousOrchestrator(config=test_config)
    await orch._process_document(large_doc(size=50_000))
    # Check all in-memory representations are bounded
    for item in orch._research_manager._get_ram_items():
        assert len(str(item)) < 1024, f"Full text in RAM: {len(str(item))} bytes"

# 4. Audit chain continuity
async def test_audit_chain_hash_continuity():
    """Evidence log hash chain must be unbroken."""
    log = EvidenceLog(run_id="test")
    for i in range(100):
        log.append({"event": f"test_{i}", "evidence_id": f"eid_{i}"})
    log.finalize()
    # Verify hash chain
    entries = log.read_all()
    for i in range(1, len(entries)):
        assert entries[i]["prev_hash"] == hash(entries[i-1])

# 5. Archive escalation triggers correctly
async def test_archive_escalation_on_404():
    """AdvancedArchiveDiscovery triggers on 404 response."""
    orch = FullyAutonomousOrchestrator(config=test_config)
    mock_response = MockResponse(status=404, url="https://example.com/gone")
    escalated = await orch._check_archive_escalation(mock_response)
    assert escalated is True

# 6. Dedup determinism
async def test_dedup_determinism():
    """Same input produces same dedup decisions across runs."""
    docs = [fake_doc(f"content_{i}") for i in range(50)]
    result1 = await dedup_engine.deduplicate(docs)
    result2 = await dedup_engine.deduplicate(docs)
    assert result1.duplicate_ids == result2.duplicate_ids

# 7. Barrier/archival logic
async def test_warc_cdxj_sorted_invariant():
    """CDXJ index must remain sorted after multi-record writes."""
    writer = WarcWriter(run_id="test")
    urls = ["https://z.com", "https://a.com", "https://m.com"]
    for url in urls:
        await writer.write_record(url, b"content")
    cdxj = writer.get_cdxj_index()
    keys = [line.split(" ")[0] for line in cdxj]
    assert keys == sorted(keys)

# 8. PII gate coverage
async def test_pii_gate_on_all_tool_outputs():
    """Every tool output passes through PII gate before persistence."""
    orch = FullyAutonomousOrchestrator(config=test_config)
    pii_gate_calls = []
    orch._security_manager.sanitize_for_logs = lambda t: pii_gate_calls.append(t) or t
    await orch._execute_tool("fetch", {"url": "https://example.com"})
    assert len(pii_gate_calls) > 0, "PII gate not called on tool output"
```

---

## I) PRIORITIZED ROADMAP

### Priority 1: Cap Unbounded Collections
- **Impact:** HIGH — prevents OOM on long runs
- **Risk:** LOW — additive change, no behavior change
- **Complexity:** S (4 hours)
- **Files:** `brain/hypothesis_engine.py`, `brain/inference_engine.py`, `utils/execution_optimizer.py`
- **Test:** `test_ram_caps_under_load()`

### Priority 2: Fix Broken E2E Tests
- **Impact:** HIGH — restores test coverage
- **Risk:** LOW — removing dead imports
- **Complexity:** S (6 hours)
- **Files:** `tests/e2e_autonomous_loop.py`
- **Test:** Run the E2E suite; verify it passes

### Priority 3: Make PII Gate Mandatory
- **Impact:** HIGH — closes security gap
- **Risk:** LOW — fails loudly if pii_gate unavailable
- **Complexity:** S (4 hours)
- **Files:** `security/pii_gate.py`, `autonomous_orchestrator.py` (_SecurityManager init)
- **Test:** `test_pii_gate_on_all_tool_outputs()`

### Priority 4: Add Budget Enforcement Integration Test
- **Impact:** HIGH — validates core invariant
- **Risk:** LOW — test-only change
- **Complexity:** S (4 hours)
- **Files:** `tests/test_autonomous_orchestrator.py`
- **Test:** `test_budget_hard_stop()`

### Priority 5: Delete Redundant model_lifecycle.py
- **Impact:** MEDIUM — reduces confusion
- **Risk:** LOW — brain/model_manager.py is canonical
- **Complexity:** S (2 hours)
- **Files:** Delete `model_lifecycle.py`, update any imports
- **Test:** Existing model lifecycle tests still pass

### Priority 6: Consolidate Deduplication
- **Impact:** MEDIUM — removes redundancy
- **Risk:** LOW — smart_deduplicator is subset
- **Complexity:** S (4 hours)
- **Files:** Delete `tools/smart_deduplicator.py`, update `tools/__init__.py`
- **Test:** Existing dedup tests still pass

### Priority 7: Wire LayerManager into Orchestrator
- **Impact:** HIGH — activates 12 dormant layers
- **Risk:** MEDIUM — new integration surface
- **Complexity:** M (8 hours)
- **Files:** `autonomous_orchestrator.py`, `layers/layer_manager.py`
- **Test:** New integration test verifying all layers initialize

### Priority 8: Wire RAG Engine into Research Flow
- **Impact:** HIGH — enables HNSW+BM25 retrieval
- **Risk:** MEDIUM — needs careful memory management
- **Complexity:** M (12 hours)
- **Files:** `knowledge/rag_engine.py`, `autonomous_orchestrator.py`
- **Test:** New test: RAG retrieval returns relevant results for query

### Priority 9: Extract _ResearchManager from Orchestrator
- **Impact:** HIGH — first step to decompose God Object
- **Risk:** MEDIUM — many internal references
- **Complexity:** L (16 hours)
- **Files:** Create `orchestrator/research_manager.py`, update imports
- **Test:** All existing orchestrator tests still pass

### Priority 10: Extract _SecurityManager from Orchestrator
- **Impact:** MEDIUM — continues God Object decomposition
- **Risk:** LOW — security manager is relatively self-contained
- **Complexity:** M (8 hours)
- **Files:** Create `orchestrator/security_manager.py`, update imports
- **Test:** All security-related tests still pass

### Priority 11: Wire deep_probe.py into Orchestrator
- **Impact:** MEDIUM — activates Shadow Walker + Dorking
- **Risk:** LOW — additive, optional dispatch
- **Complexity:** M (8 hours)
- **Files:** `deep_probe.py`, `autonomous_orchestrator.py`
- **Test:** New test: deep_probe triggered on appropriate research queries

### Priority 12: Rename brain/decision_engine.py
- **Impact:** LOW — reduces confusion
- **Risk:** LOW — rename + import update
- **Complexity:** S (2 hours)
- **Files:** Rename to `brain/research_flow_decider.py`, update imports
- **Test:** Existing tests still pass

### Priority 13: Add Streaming to Multi-Hop Graph Search
- **Impact:** MEDIUM — reduces peak RAM for large graphs
- **Risk:** MEDIUM — changes iteration pattern
- **Complexity:** M (8 hours)
- **Files:** `brain/inference_engine.py`, `knowledge/graph_rag.py`
- **Test:** `test_multihop_streaming_bounded_memory()`

### Priority 14: Add Evidence ID Validation at Ingestion
- **Impact:** MEDIUM — prevents malformed IDs propagating
- **Risk:** LOW — additive validation
- **Complexity:** S (4 hours)
- **Files:** `knowledge/atomic_storage.py`, `knowledge/persistent_layer.py`
- **Test:** `test_malformed_evidence_id_rejected()`

### Priority 15: Remove XOR Encryption Fallback
- **Impact:** LOW (security hygiene)
- **Risk:** LOW — only affects dev mode
- **Complexity:** S (2 hours)
- **Files:** `utils/encryption.py`
- **Test:** Verify AES path works; XOR path raises error

### Priority 16: Delete Orphaned Coordinator Stubs
- **Impact:** LOW — reduces codebase size by ~3,000 lines
- **Risk:** LOW — confirmed unused
- **Complexity:** S (4 hours)
- **Files:** Delete 10+ coordinator stubs, update `coordinators/__init__.py`
- **Test:** No existing tests reference these

### Priority 17: Wire Quantum Pathfinder for Knowledge Graph Analysis
- **Impact:** MEDIUM — activates advanced graph reasoning
- **Risk:** MEDIUM — new integration
- **Complexity:** M (12 hours)
- **Files:** `graph/quantum_pathfinder.py`, `knowledge/graph_rag.py`
- **Test:** New test: quantum walks discover paths not found by BFS

### Priority 18: Add PII Detection for International Formats
- **Impact:** LOW — expands coverage
- **Risk:** LOW — additive patterns
- **Complexity:** M (8 hours)
- **Files:** `security/pii_gate.py`
- **Test:** New test: international phone numbers, bank codes detected

### Priority 19: Delegate Orchestrator Internals to Coordinators
- **Impact:** HIGH — major architectural cleanup
- **Risk:** HIGH — largest refactor
- **Complexity:** L (40 hours)
- **Files:** `autonomous_orchestrator.py`, all coordinator files
- **Test:** Full regression suite

### Priority 20: Add Prometheus-Style Memory Metrics
- **Impact:** MEDIUM — enables runtime monitoring
- **Risk:** LOW — observability only
- **Complexity:** M (8 hours)
- **Files:** `utils/performance_monitor.py`, `autonomous_orchestrator.py`
- **Test:** Verify metrics emit correctly during research run

---

## APPENDIX: STATIC ANALYSIS TOOL RECOMMENDATIONS

### Ruff (Linting + Formatting)
```toml
# pyproject.toml
[tool.ruff]
target-version = "py311"
line-length = 120
select = ["E", "F", "W", "I", "UP", "B", "SIM", "PIE"]
ignore = ["E501"]  # Line length handled separately

[tool.ruff.per-file-ignores]
"tests/*" = ["B", "SIM"]
"*/__init__.py" = ["F401"]  # Allow unused imports in __init__

[tool.ruff.isort]
known-first-party = ["hledac"]
```

### Pyright (Type Checking)
```json
{
  "include": ["hledac/universal"],
  "exclude": ["**/legacy/**", "**/__pycache__/**"],
  "typeCheckingMode": "basic",
  "reportMissingImports": true,
  "reportUnusedImport": true,
  "reportUnusedVariable": true,
  "pythonVersion": "3.11"
}
```

### Vulture (Dead Code Detection)
```bash
vulture hledac/universal/ --min-confidence 80 --exclude legacy/,__pycache__/
```

---

*End of audit. Total codebase analyzed: ~150+ Python files, ~50,000+ lines across 15 packages.*
