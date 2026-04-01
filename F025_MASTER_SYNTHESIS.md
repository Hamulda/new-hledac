# F025 — Master Synthesis Report
**Datum:** 2026-04-01
**Scope:** `hledac/universal/` — all F025 inventory scans
**Status:** SSOT BASELINE CONFIRMED

---

## 1. Executive Summary

### Co je potvrzeno (CONFIRMED)
1. **Passive path = skutečný hot path** — `_run_public_passive_once()` běží defaultně, SprintScheduler je UNPLUGGED
2. **UMA authority je SPLIT** — `uma_budget.py` a `resource_governor.py` počítají stejný stav nezávisle
3. **Sprint mode je ROZBITÝ** — `_run_sprint_mode()` reference undefined `scheduler` variable
4. **TransportResolver existuje ale není napojen** — FetchCoordinator používá přímé if/else na URL suffix
5. **Wayback CDX je 3× duplikovaný** — 3 nezávislé implementace
6. **GhostExecutor a ToolRegistry jsou paralelní systémy** — žádný bridge, žádné mapování ActionType → Tool

### Co je HYPOTÉZA (needs verification)
1. `SprintScheduler` je 62KB ale 0 instantiation — HYPOTHESIS: nikdy neměl být v production
2. `_LifecycleAdapter` v `runtime/sprint_scheduler.py` — HYPOTHEZA: měl být bridge mezi dvěma verzemi lifecycle
3. `research_flow_decider.py` je helper, ne canonical — HYPOTÉZA potvrzena v its own header comment
4. DuckDBShadowStore vs DuckPGQGraph confusion — HYPOTHESIS: jde o různé věci (shadow=analytics, graph=store)

### Co se rozchází mezi reporty (CONFLICT)
| Konflikt | Report A | Report B |
|----------|----------|---------|
| WINDUP plane wiring | RUNTIME: `windup_engine.run_windup()` defined ale NOT CALLED | MODEL: `windup_engine` volá `SynthesisRunner(ModelLifecycle())` — own isolated world |
| UmaWatchdog vs UMAAlarmDispatcher | CONTEXT: dva nezávislé alarm systémy | SECURITY: používá se pouze v sprint mode |
| Legacy autonomous_orchestrator | LEGACY: dormant ale active consumers existují | RUNTIME: `__main__.py` používá `runtime/sprint_scheduler.py`, ne legacy |
| DuckDBShadowStore | GRAPH: shadow = DuckDB analytics sidecar | GRAPH: DuckPGQGraph = alternate graph backend (confusingly podobné jméno) |

---

## 2. Evidence Hierarchy

### RUNTIME TRUTH (confirmed by direct file read + grep)
```
__main__.py:2771: asyncio.run(_run_public_passive_once(_get_and_clear_signal_flag))
__main__.py:2767: asyncio.run(_run_sprint_mode(sprint_target, ...))
__main__.py:2546: if hasattr(scheduler, "_ioc_graph"):  # ← scheduler NOT DEFINED
SprintScheduler grep __main__.py → 0 matches for instantiation
```

### CAPABILITY TRUTH (confirmed by grep call-sites)
```
capabilities.py:372: create_default_registry() → register()
ghost_executor.py:146: execute() → _actions dict lookup
tool_registry.py:519: validate_call() → rate limit check
autonomous_analyzer.py:433: _detect_tools() → shadow detection
```

### TOPOLOGY TRUTH (confirmed by grep call-sites)
```
fetch_coordinator.py:969: if url.endswith('.onion'):  # ← NOT TransportResolver
archive_discovery.py: grep "wayback_cdx" → WaybackMachineClient.get_cdx()
duckduckgo_adapter.py: grep "wayback_cdx" → _search_wayback_cdx()
deep_research_sources.py: grep "wayback_cdx" → wayback_cdx_lookup()
```

### NARRATIVE / HYPOTHESIS (NEEDS VERIFICATION)
- SprintScheduler was "planned but never wired" — HYPOTHESIS based on 0 instantiation
- `research_flow_decider.py` helper status — CONFIRMED via file header comment
- DuckDBShadowStore confusion — HYPOTHESIS, needs domain expert confirmation
- Nym dormant code — CONFIRMED via circuit_breaker.py comment "Nym skip pro normální tasky"

---

## 3. Definitive Plane Map

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              PLANE HIERARCHY                                  │
├──────────────┬───────────────────────────────────────────────────────────────┤
│ RUNTIME      │ PASSIVE (default) ──→ _run_public_passive_once()            │
│              │ SPRINT (--sprint) ──→ _run_sprint_mode() [BROKEN]           │
│              │                                                                 │
│              │ UNPLUGGED: SprintScheduler (62KB, 0 instantiation)           │
├──────────────┼───────────────────────────────────────────────────────────────┤
│ FOUNDATION   │ Canonical: uma_budget.py (UnifiedMemoryBudgetAccountant)    │
│              │ ⚠️ SPLIT: resource_governor.py independently computes same    │
│              │                                                                 │
│              │ Canonical: async_utils.py (bounded_map/gather)               │
│              │ Canonical: bloom_filter.py (RotatingBloomFilter)             │
│              │ Canonical: rate_limiter.py                                   │
├──────────────┼───────────────────────────────────────────────────────────────┤
│ CONTROL      │ Fragmented:                                                   │
│              │  • UmaWatchdog (uma_budget.py) — polling 0.5s, debounce 2s   │
│              │  • UMAAlarmDispatcher (resource_governor.py) — polling 5s    │
│              │  • evaluate_uma_state() ≠ get_uma_pressure_level()          │
│              │                                                                 │
│              │ Canonical: evidence_log.py, tool_exec_log.py, metrics_registry│
├──────────────┼───────────────────────────────────────────────────────────────┤
│ CONTEXT      │ Canonical: research_context.py::ResearchContext (Pydantic)   │
│              │ ⚠️ LEGACY: to_hermes_prompt() v ResearchContext — PATTERN    │
├──────────────┼───────────────────────────────────────────────────────────────┤
│ CAPABILITY   │ Canonical: capabilities.py::CapabilityRegistry              │
│              │ Canonical: capabilities.py::CapabilityRouter                │
│              │ Canonical: capabilities.py::ModelLifecycleManager           │
│              │ ⚠️ PARALLEL SYSTEM: tool_registry.py::ToolRegistry          │
│              │ ⚠️ PARALLEL SYSTEM: ghost_executor.py::GhostExecutor        │
│              │  • GhostExecutor.ActionType (17 akcí) → žádný mapping na   │
│              │    ToolRegistry.Tool                                       │
│              │  • AutonomousAnalyzer._detect_tools() → shadow detection     │
├──────────────┼───────────────────────────────────────────────────────────────┤
│ SOURCE/      │ Canonical: fetch_coordinator.py::FetchCoordinator           │
│ TRANSPORT    │  • TransportResolver.exists() ← NOT WIRED                    │
│              │  • Přímé url.endswith('.onion') dispatch                    │
│              │                                                                 │
│              │ ⚠️ 3× WAYBACK CDX:                                           │
│              │   archive_discovery.py::WaybackMachineClient                  │
│              │   deep_research_sources.py::wayback_cdx_lookup                │
│              │   duckduckgo_adapter.py::_search_wayback_cdx                  │
│              │                                                                 │
│              │ ⚠️ 3× TOR:                                                   │
│              │   tor_transport.py::TorTransport (subprocess)                │
│              │   circuit_breaker.py::resilient_fetch (SOCKS5 proxy)         │
│              │   fetch_coordinator.py::_get_tor_session (pool)             │
│              │                                                                 │
│              │ Nym: DORMANT (circuit_breaker comment "skip pro normální    │
│              │ tasky")                                                       │
├──────────────┼───────────────────────────────────────────────────────────────┤
│ GRAPH        │ SPLIT OWNERSHIP:                                             │
│              │  • IOCGraph (Kuzu) — canonical truth owner                   │
│              │  • DuckPGQGraph (DuckDB) — alternate backend                │
│              │  • DuckDBShadowStore — analytics (≠ graph)                   │
│              │                                                                 │
│              │ ⚠️ CROSS-PLANE COUPLING:                                     │
│              │   RelationshipDiscoveryEngine → Graph I Prefetch plane       │
│              │   GraphRAGOrchestrator → RAGEngine (retrieval coupling)       │
│              │   PrefetchOracle → RelationshipDiscoveryEngine (direct)      │
├──────────────┼───────────────────────────────────────────────────────────────┤
│ RETRIEVAL    │ Canonical: rag_engine.py::RAGEngine (HNSW+BM25)              │
│              │ Canonical: lancedb_store.py::LanceDBIdentityStore             │
│              │ ⚠️ PQIndex dual role: compression sublayer ≠ ANN search      │
│              │ ⚠️ GraphRAGOrchestrator imports RAGEngine (cross-plane)       │
├──────────────┼───────────────────────────────────────────────────────────────┤
│ PREFETCH     │ Canonical: prefetch_oracle.py::PrefetchOracle               │
│              │  • Stage A: Candidate Generation (rel_engine, PQIndex)       │
│              │  • Stage B: SSM Reranker                                     │
│              │  • LinUCB: Contextual Bandit                                 │
│              │                                                                 │
│              │ ⚠️ COUPLING: PrefetchOracle přímo volá RelationshipDiscovery│
│              │   Engine bez abstraktního interface                            │
├──────────────┼───────────────────────────────────────────────────────────────┤
│ SECURITY     │ Canonical: pii_gate.py::SecurityGate (always-on)             │
│              │ Canonical: stego_detector.py::StatisticalStegoDetector        │
│              │ Canonical: vault_manager.py::LootManager (late provider)      │
│              │                                                                 │
│              │ OVERLAP: stego_detector ↔ vision_encoder (CoreML/Vision)    │
│              │ DEEP PROVIDERS: RamDiskVault, DigitalGhostDetector, KeyManager│
│              │  (post-F16, require vault lifecycle)                         │
├──────────────┼───────────────────────────────────────────────────────────────┤
│ FORENSICS    │ Canonical: metadata_extractor.py::UniversalMetadataExtractor  │
│              │  (single module, SQLite bounded cache)                        │
├──────────────┼───────────────────────────────────────────────────────────────┤
│ MULTIMODAL   │ Canonical: vision_encoder.py::VisionEncoder (CoreML dummy) │
│              │ Canonical: fusion.py::MambaFusion, MobileCLIPFusion          │
│              │ Canonical: captcha_solver.py::VisionCaptchaSolver (stub)     │
│              │                                                                 │
│              │ CI=DUMMY MODE: všechny CoreML/Vision moduly                 │
│              │ Dummy mode MUSÍ logovat WARNING, vracet stable dummy output  │
├──────────────┼───────────────────────────────────────────────────────────────┤
│ MODEL/       │ 3-MODEL SPLIT:                                               │
│ REASONING    │  • Hermes-3-3B → PLAN/DECIDE/SYNTHESIZE (Hermes3Engine)     │
│              │  • ModernBERT → EMBED/DEDUP/ROUTING (ModernBERTEngine)       │
│              │  • GLiNER → NER/ENTITY extraction (GLiNEREngine)             │
│              │                                                                 │
│              │ REASONING PIPELINE:                                           │
│              │  inference_engine → hypothesis_engine → insight_engine        │
│              │                              ↓                                │
│              │                        synthesis_runner (WINDUP only)        │
│              │                                                                 │
│              │ ⚠️ WINDUP ISOLATION (architekturní záměr):                   │
│              │   windup_engine.py:136 → SynthesisRunner(ModelLifecycle())   │
│              │   ← VLASTNÍ isolated model world, NE main scheduler lifecycle│
│              │                                                                 │
│              │ Dormant: enhanced_research.py::UnifiedResearchEngine         │
│              │ Helper: research_flow_decider.py (header: "HELPER only")     │
└──────────────┴───────────────────────────────────────────────────────────────┘
```

---

## 4. Canonical Candidate Map

### Canonical = ACTIVE / ON HOT PATH / PRODUCTION

| Domain | Canonical | File | Notes |
|--------|-----------|------|-------|
| Runtime entry | `_run_public_passive_once()` | `__main__.py` | ACTUAL hot path |
| Sprint mode | `_run_sprint_mode()` | `__main__.py` | BROKEN — undefined scheduler |
| Lifecycle | `runtime/sprint_lifecycle.py::SprintLifecycleManager` | `runtime/` | Async-native, checkpoint seam |
| Lifecycle (legacy) | `utils/sprint_lifecycle.py::SprintLifecycleManager` | `utils/` | Older dataclass version |
| UMA foundation | `uma_budget.py` | `utils/` | Named "UnifiedMemoryBudgetAccountant" |
| Memory governor | `resource_governor.py` | `core/` | ⚠️ SPLIT authority |
| Context carrier | `ResearchContext` | `research_context.py` | Pydantic model |
| Capability registry | `CapabilityRegistry` | `capabilities.py` | |
| Capability router | `CapabilityRouter` | `capabilities.py` | |
| Model lifecycle | `ModelLifecycleManager` | `capabilities.py` | |
| Tool registry | `ToolRegistry` | `tool_registry.py` | ⚠️ PARALLEL s GhostExecutor |
| Graph (canonical) | `IOCGraph` | `knowledge/ioc_graph.py` | Kuzu backend |
| Retrieval | `RAGEngine` | `knowledge/rag_engine.py` | HNSW+BM25 |
| Identity | `LanceDBIdentityStore` | `knowledge/lancedb_store.py` | Vector+FTS |
| Prefetch | `PrefetchOracle` | `prefetch/prefetch_oracle.py` | |
| Evidence log | `EvidenceLog` | `evidence_log.py` | Append-only, hash chain |
| Tool audit | `ToolExecLog` | `tool_exec_log.py` | Hash-chain forensic |
| Metrics | `MetricsRegistry` | `metrics_registry.py` | |
| Security gate | `SecurityGate` | `security/pii_gate.py` | Always-on |
| Stego detector | `StatisticalStegoDetector` | `security/stego_detector.py` | |
| Forensics | `UniversalMetadataExtractor` | `forensics/metadata_extractor.py` | |
| Multimodal | `VisionEncoder` | `multimodal/vision_encoder.py` | CI=dummy |
| Fetch | `FetchCoordinator` | `coordinators/fetch_coordinator.py` | Jediný runtime entry |
| Source dedup | `RotatingBloomFilter` | `utils/bloom_filter.py` | URL dedup ONLY |
| Path truth | `paths.py` | `paths.py` | SSOT for all paths |

### Canonical = DORMANT / LAZY / NOT ON HOT PATH

| Domain | Module | File | Notes |
|--------|--------|------|-------|
| Sprint scheduler | `SprintScheduler` | `runtime/sprint_scheduler.py` | 62KB, 0 instantiation |
| Windup engine | `windup_engine.run_windup()` | `runtime/windup_engine.py` | Defined, NOT called |
| Export | `export_sprint()` | `export/sprint_exporter.py` | Test-only |
| STIX export | `stix_exporter.py` | `export/stix_exporter.py` | UNPLUGGED |
| JSON-LD export | `jsonld_exporter.py` | `export/jsonld_exporter.py` | UNPLUGGED |
| Legacy orchestrator | `FullyAutonomousOrchestrator` | `legacy/autonomous_orchestrator.py` | DEPRECATED facade |
| Legacy atomic storage | `AtomicJSONKnowledgeGraph` | `legacy/atomic_storage.py` | DEPRECATED |
| Legacy persistent layer | `PersistentKnowledgeLayer` | `legacy/persistent_layer.py` | DEPRECATED |
| Graph alternate | `DuckPGQGraph` | `graph/quantum_pathfinder.py` | DuckDB backend |
| Graph analytics | `DuckDBShadowStore` | `knowledge/duckdb_store.py` | ≠ graph |
| Deep research | `UnifiedResearchEngine` | `enhanced_research.py` | 85% ready |
| Coordinators | `IntegratedOrchestrator` | `orchestrator_integration.py` | Orphaned, tests only |

### Capability Donors = PRESERVE (NEVER REMOVE without migration)

| Donor | Capability | Status |
|-------|-----------|--------|
| `dht/kademlia_node.py` | BEP-9/BEP-10 torrent metadata | FULL implementation |
| `federated/post_quantum.py` | Post-quantum crypto (Kyber, Dilithium) | PREMIUM capability |
| `federated/secure_aggregator.py` | Secure aggregation | PREMIUM capability |
| `federated/differential_privacy.py` | DP noise + RDP accountant | PREMIUM capability |
| `federated/sketches.py` | CountMinSketch, MinHashSketch, SimHashSketch | UTILITY |
| `rl/marl_coordinator.py` | QMIX multi-agent RL | SOLID implementation |

---

## 5. Authority Conflict List

### CRITICAL (blockují integraci)

| # | Conflict | A | B | Resolution Required |
|---|----------|---|---|-------------------|
| 1 | Dual UMA state authority | `uma_budget.get_uma_pressure_level()` | `resource_governor.evaluate_uma_state()` | Arbitráž: `uma_budget.py` = FOUNDATION authority (Sprint 1B), `resource_governor` musí delegovat |
| 2 | Dual alarm system | `UmaWatchdog` (uma_budget.py, 0.5s polling) | `UMAAlarmDispatcher` (resource_governor.py, 5s polling) | Konsolidace nebo jasné hranice |
| 3 | GhostExecutor ↔ ToolRegistry gap | GhostExecutor.ActionType (17 akcí) | ToolRegistry.Tool (registered tools) | Vytvořit `_ACTION_TO_TOOL` mapping |
| 4 | Sprint mode broken | `_run_sprint_mode()` references undefined `scheduler` | | Instantiate SprintScheduler v `_run_sprint_mode()` |
| 5 | Wayback CDX 3× duplication | archive_discovery / deep_research_sources / duckduckgo_adapter | | ONE canonical source v archive_discovery.py |

### HIGH (blokují F1-F6)

| # | Conflict | A | B | Resolution Required |
|---|----------|---|---|-------------------|
| 6 | AutonomousAnalyzer ↔ CapabilityRouter | `_detect_tools()` (shadow) | `CapabilityRouter.route()` (canonical) | AutonomousAnalyzer musí volat CapabilityRouter |
| 7 | TransportResolver není napojen | `TransportResolver.resolve()` existuje | `fetch_coordinator.py:969` if/else suffix dispatch | Napojit TransportResolver do FetchCoordinator |
| 8 | ModelLifecycleManager neovlivňuje Tool execution | `enforce_phase_models()` exists | `ToolRegistry.execute_with_limits()` fáze-agnostic | Přidat phase gates do Tool execution |
| 9 | Graph backend split | IOCGraph (Kuzu, canonical) | DuckPGQGraph (DuckDB, alternate) | Jasná separace, DuckPGQGraph = explicit alternate |
| 10 | Windup double-wired | `windup_engine.run_windup()` NOT called | `_windup_synthesis()` inline v __main__.py | Rozhodnout: jedna implementace |

### MEDIUM (blokují DeepResearch activation)

| # | Conflict | A | B | Resolution Required |
|---|----------|---|---|-------------------|
| 11 | Dual MLX memory tracking | `uma_budget.get_mlx_memory_mb()` | `resource_allocator.get_mlx_memory_mb()` | Sjednotit na jednu canonical funkci |
| 12 | Nym dormant code | NymTransport plně implementován | circuit_breaker: "skip pro normální tasky" | Remark jako DORMANT nebo plně integrovat |
| 13 | Capability → Tool gap | ToolRegistry nemá `required_capabilities` | CapabilityRegistry není volána při tool execution | Přidat `required_capabilities` do Tool |
| 14 | Audit trail fragmented | AuditLogger (security/) | GhostLayer._action_count | GhostLayer má používat AuditLogger |
| 15 | DuckDB Shadow vs Graph | DuckDBShadowStore (analytics) | DuckPGQGraph (graph) | Jasně oddělit — stejný "DuckDB" prefix, různý účel |

### LOW (dokumentační / cleanup)

| # | Conflict | Notes |
|---|----------|-------|
| 16 | Rate limiter duplication | `rate_limiter.py` vs `rate_limiters.py` — určit který je canonical |
| 17 | MLX memory duplication | `mlx_cache.py` vs `mlx_memory.py` — investigace potřeba |
| 18 | research_flow_decider helper | Header comment říká "HELPER only" — respektovat |
| 19 | SUPREME_INTEGRATION_AVAILABLE=True | Hardcoded LIE v `__init__.py` — opravit |
| 20 | two sprint_lifecycle versions | runtime/ (async-native) vs utils/ (dataclass) — rozhodnout canonical |

---

## 6. Macro Convergence Order

Toto je pořadí, ve kterém je MOŽNÉ stabilizovat systém (ne nutně master plan priority).

```
FAZE 0: FOUNDATION STABILIZATION (prerekvizita pro všechno)
═══════════════════════════════════════════════════════════════
1. ⚠️  [CRITICAL] Dual UMA authority resolution
   A: uma_budget.py (FOUNDATION authority)
   B: resource_governor.py (deleguje na uma_budget)
   → Výstup: jediný canonical `get_uma_pressure_level()`
   → Blokuje: všechny ostatní práce na control plane

2. ⚠️  [CRITICAL] Dual alarm consolidation
   UmaWatchdog + UMAAlarmDispatcher → single alarm system
   → Výstup: jasná hranice mezi watchdog a dispatcher
   → Blokuje: F1-F6 runtime governance

3. ⚠️  [CRITICAL] SUPREME_INTEGRATION_AVAILABLE fix
   → Výstup: flag reflects actual load state
   → Blokuje: public API contract

───────────────────────────────────────────────────────────────
FAZE 1: RUNTIME WIRING (hot path fix)
═══════════════════════════════════════════════════════════════
4. Sprint mode wire-up
   → Instantiate SprintScheduler v _run_sprint_mode()
   → F0.25a: scheduler variable defined
   → F0.25b: run_warmup() wired
   → F0.25c: run_windup() wired
   → F0.25d: export_sprint() wired
   → F0.25e: lifecycle duality resolved

5. Export plane cleanup
   → stix_exporter.py, jsonld_exporter.py: documented call-sites OR removed
   → sprint_exporter.py: production call-site (not just test)

───────────────────────────────────────────────────────────────
FAZE 2: SOURCE/TRANSPORT CONSOLIDATION
═══════════════════════════════════════════════════════════════
6. ⚠️  [CRITICAL] Wayback CDX deduplication
   → ONE canonical: archive_discovery.py
   → deep_research_sources, duckduckgo_adapter: import from canonical

7. ⚠️  [CRITICAL] TransportResolver napojení
   → FetchCoordinator._fetch_url() → TransportResolver.resolve_url()
   → Remove direct url.endswith('.onion') dispatch

8. Tor management consolidation
   → ONE canonical Tor transport (TorTransport subprocess OR aiohttp_socks)
   → Odstranit dual-management

9. Nym dormant remark
   → "DORMANT" v circuit_breaker.py Nym branch
   → NEBO plná integrace přes NymTransport

───────────────────────────────────────────────────────────────
FAZE 3: CAPABILITY/EXECUTION BRIDGE
═══════════════════════════════════════════════════════════════
10. GhostExecutor → ToolRegistry bridge
    → _ACTION_TO_TOOL mapping dict
    → GhostExecutor.execute() deleguje na ToolRegistry

11. AutonomousAnalyzer → CapabilityRouter
    → _detect_tools() volá CapabilityRouter.route()
    → Shadow detection removed

12. Tool capability requirements
    → Tool.required_capabilities: Set[Capability]
    → execute_with_limits() kontroluje CapabilityRegistry.is_available()

13. Phase-gated tool execution
    → ModelLifecycleManager.get_enabled_tools(phase)
    → ToolRegistry fázová filtrace

───────────────────────────────────────────────────────────────
FAZE 4: GRAPH/RETRIEVAL/PREFETCH SEPARATION
═══════════════════════════════════════════════════════════════
14. Graph truth owner explicitní
    → IOCGraph = canonical
    → DuckPGQGraph = alternate (s explicitním feature flagem)

15. DuckDB Shadow vs Graph separation
    → DuckDBShadowStore = analytics (≠ graph)
    → DuckPGQGraph = graph (DuckDB PGQ backend)
    → Oddělit jmenný prostor

16. Prefetch → Graph abstraction layer
    → PrefetchOracle NESMÍ přímo volat RelationshipDiscoveryEngine
    → Abstraktní interface přes knowledge/interfaces.py

17. RAGEngine ↔ GraphRAGOrchestrator decoupling
    → GraphRAGOrchestrator._backend.get_node() přes interface

───────────────────────────────────────────────────────────────
FAZE 5: SECURITY/FORENSICS/MULTIMODAL INTEGRATION
═══════════════════════════════════════════════════════════════
18. PII gate integration do fetch pipeline
    → SecurityGate invoked na všech fetch output管道ch
    → fallback_sanitize() registered jako fail-safe

19. Stego detection integration
    → StatisticalStegoDetector invoked na image fetch outputs

20. Metadata extractor → knowledge store pipeline
    → UniversalMetadataExtractor → evidence_log → duckdb_store

21. Vision/CoreML resource governance
    → ANE contention řešena přes ResourceGovernor
    → Stego + Vision share CoreML pool

───────────────────────────────────────────────────────────────
FAZE 6: MODEL/REASONING INTEGRATION
═══════════════════════════════════════════════════════════════
22. Windup isolation preservation
    → SynthesisRunner(ModelLifecycle()) zůstává ISOLATED
    → NEMERGE s main scheduler lifecycle

23. HypothesisEngine independence
    → AdversarialVerifier zůstává self-contained
    → NEMERGE s inference engine

24. MoE router activation functions separation
    → route_synthesis() a route_embedding() oddělené
    → NEMERGE do jedné funkce

25. enhanced_research activation
    → UnifiedResearchEngine lazy-loaded tools
    → Memory pressure adaptive depth degradation

───────────────────────────────────────────────────────────────
FAZE 7: LEGACY CONTAINMENT
═══════════════════════════════════════════════════════════════
26. orchestrator_integration.py removal
    → P0 safe-to-remove (orphaned, tests only)

27. knowledge/ proxy-import migration
    → graph_layer, graph_rag, graph_builder → duckdb_store
    → Odstranit legacy/persistent_layer importy

28. Federated/federated_engine v1 removal
    → Ponechat pouze v2

29. Legacy donor conservation
    → dht/, federated/, rl/ → zakonzervovat jako dormant donors
    → Dokumentovat API pro každý donor

30. Facade removal
    → autonomous_orchestrator.py facade removal
    → Po migraci všech consumerů na canonical path
```

---

## 7. Intra-Plane Dependency Order

### RUNTIME PLANE
```
_run_public_passive_once() [HOT]
  └── async_run_live_public_pipeline()
  └── async_run_default_feed_batch()

_run_sprint_mode() [BROKEN]
  ├── SprintLifecycleManager (utils verze)
  ├── SprintScheduler [MISSING - undefined]
  ├── run_warmup() [MISSING - not wired]
  ├── ANE warmup [WRONG PLACE - before WARMUP phase done]
  ├── _windup_synthesis() [INLINE vs run_windup()]
  ├── run_windup() [MISSING - not wired]
  ├── export_sprint() [MISSING - not wired]
  └── _print_scorecard_report() [definition unknown]
```

### CAPABILITY PLANE
```
CapabilityRegistry (load/unload)
  └── ModelLifecycleManager.enforce_phase_models()
        └── TOOLS phase → ToolRegistry.get_tools_by_phase()
              └── ToolRegistry.execute_with_limits()
                    └── AuditLogger.log()

AutonomousAnalyzer._detect_tools() [SHADOW - should use CapabilityRouter]
  └── CapabilityRouter.route() [CANONICAL]
        └── CapabilityRegistry.is_available()
```

### SOURCE/TRANSPORT PLANE
```
FetchCoordinator._fetch_url()
  ├── TransportResolver.resolve_url() [NOT WIRED - currently if/else]
  ├── _fetch_with_tor() → Tor connection pool
  ├── _fetch_with_curl() → StealthCrawler
  └── _maybe_deep_research()
        ├── search_text_sync() → ddgs_client
        ├── wayback_cdx_lookup() → [DUPLICATE - should use archive_discovery]
        └── urlscan_search()

TransportResolver.resolve()
  ├── SourceTransportMap.get(suffix)
  └── TransportContext(anonymity, risk)
```

### GRAPH/RETRIEVAL/PREFETCH PLANE
```
PrefetchOracle
  ├── RelationshipDiscoveryEngine [CROSS-PLANE COUPLING]
  │     └── get_common_neighbors() → IOCGraph
  │     └── get_entity_embedding()
  ├── PQIndex.search() [DUAL ROLE: compression ≠ ANN]
  └── LinUCB bandit

RAGEngine
  ├── HNSWVectorIndex (embedding)
  ├── BM25Index (sparse)
  └── GraphRAGOrchestrator [CROSS-PLANE COUPLING]
        └── RAGEngine._embed_text()

IOCGraph (Kuzu) [CANONICAL TRUTH]
  └── buffer_ioc() → flush_buffers() (WINDUP)

DuckPGQGraph (DuckDB) [ALTERNATE]
  └── DuckDBShadowStore [≠ graph - analytics sidecar]
```

---

## 8. Hard Blockers Before F1–F6

### F1: Sprint Mode Activation
**Blokující issues:**
1. `scheduler` is undefined in `_run_sprint_mode()` — NameError on line 2546
2. `run_warmup()` not wired — line 2433 `lifecycle.mark_warmup_done()` bez následovníka
3. `run_windup()` not wired — line 2526 `lifecycle.request_windup()` bez následovníka
4. `export_sprint()` not wired — line 2595 `lifecycle.request_export()` bez následovníka
5. SprintScheduler not instantiated — 62KB module, 0 call-sites

**Dohromady:** Sprint mode cannot run as-is. Even with `--sprint` flag, it crashes.

### F2: Capability/Tool Integration
**Blokující issues:**
1. GhostExecutor nemá mapping na ToolRegistry — parallel systems
2. AutonomousAnalyzer._detect_tools() shadow vs CapabilityRouter.route() canonical
3. Tool.required_capabilities doesn't exist
4. ModelLifecycleManager doesn't gate Tool execution

**Dohromady:** Tool execution is capability-agnostic. Phase-gating doesn't work.

### F3: Transport/Source Consolidation
**Blokující issues:**
1. Wayback CDX 3× duplikovaný — změna API musí být na 3 místech
2. TransportResolver exists but not wired — if/else dispatch
3. Tor management 3-way split

**Dohromady:** Transport policy is fragmented, not centralized.

### F4: Graph/Retrieval/Prefetch Separation
**Blokující issues:**
1. RelationshipDiscoveryEngine cross-plane coupling
2. Graph backend split (IOCGraph vs DuckPGQGraph)
3. DuckDBShadowStore confusion (analytics vs graph)
4. PQIndex dual role (compression sublayer ≠ ANN search)

**Dohromady:** Clear plane boundaries don't exist. Cross-plane coupling everywhere.

### F5: Foundation/Control Consolidation
**Blokující issues:**
1. Dual UMA authority (uma_budget vs resource_governor)
2. Dual alarm system (UmaWatchdog vs UMAAlarmDispatcher)
3. SUPREME_INTEGRATION_AVAILABLE hardcoded lie
4. Dual MLX memory tracking

**Dohromady:** Foundation and control planes have hidden splits. Runtime governance is unreliable.

### F6: Security/Forensics Integration
**Blokující issues:**
1. PII gate not integrated into fetch pipeline
2. Stego detection not integrated into image fetch
3. Metadata extractor not wired to knowledge store
4. Vision/CoreML ANE contention unresolved

**Dohromady:** Security/forensics planes exist but are not integrated into production pipeline.

---

## 9. Hard Blockers Before DeepResearch Activation

### DeepResearch = enhanced_research.py::UnifiedResearchEngine

| Blocker | Severity | Status | Workaround |
|---------|----------|--------|------------|
| intelligence modul není v `universal/` | MEDIUM | Import guards handle | Degraded mode |
| Memory pressure (M1 8GB) | HIGH | Research depth=BASIC | Memory-aware degradation |
| Hermes3Engine not singleton | HIGH | Helper only | Use canonical Hermes3Engine |
| Model swap not race-free | MEDIUM | ModelSwapManager drain 3.0s | Reduce to 1.5s |
| EnhancedResearchEngine 85% ready | MEDIUM | Import guards | Lazy load |

**Additional blockers specific to DeepResearch:**
1. `research_flow_decider.py` is HELPER only — cannot be canonical decision surface
2. `enhanced_research.py` intelligence tools are lazy — some may not be available
3. HybridRAG requires RAGEngine which requires graph stability (F4 prerequisite)
4. BehaviorSimulator requires stealth_layer (LATENT — not confirmed on hot path)

**Before activating DeepResearch:**
- F1 (Sprint Mode) must be stable — DeepResearch uses sprint lifecycle
- F4 (Graph/Retrieval) must be stable — HybridRAG depends on RAGEngine
- Memory governor must be reliable — DeepResearch is memory-intensive
- Model swap must be race-free — concurrent DeepResearch + inference would crash

---

## 10. Legacy Containment Conclusions

### MUST BE PRESERVED (Critical Donors)
```
dht/crawl_dht_for_keyword()     — BEP-9/BEP-10 plná implementace, jediná DHT OSINT capability
federated/post_quantum.py       — PQC (Kyber, Dilithium), premium security
federated/secure_aggregator.py  — Secure aggregation, federated learning
federated/differential_privacy.py — DP noise + RDP privacy accountant
federated/sketches.py           — CountMinSketch, MinHashSketch, SimHashSketch
rl/marl_coordinator.py          — QMIX multi-agent RL, solid implementation
```

### SAFE TO REMOVE (Orchestrated)
```
orchestrator_integration.py     — Orphaned, tests only (P0)
federated/federated_engine v1   — Duplikát v2 (P1)
ScalableBloomFilter             — DEPRECATED, RotatingBloomFilter je náhrada (P1)
```

### MUST MIGRATE BEFORE REMOVAL
```
legacy/autonomous_orchestrator.py facade
  └── Čeká na: všechny consumerů migrace na runtime/sprint_scheduler.py
  └── DeprecationWarning už existuje při importu

legacy/atomic_storage.py
  └── Čeká na: knowledge/__init__.py proxy-import removal
  └── Migrace: graph_layer, graph_rag, graph_builder → duckdb_store

legacy/persistent_layer.py
  └── Čeká na: graph modulů migrace na duckdb_store
  └── Migrace: graph_layer, graph_rag, graph_builder importuí z PersistentKnowledgeLayer
```

### LATENT CAPABILITY DONORS (zakonzervovat, dokumentovat)
```
dht/        — DHT crawl, KademliaNode, SketchExchange
federated/  — PQC, secure aggregation, differential privacy, sketches
rl/         — QMIX, MARL coordinator
```

### Key Principles
1. **"Not on hot path" ≠ "is waste"** — DHT, federated, RL are valuable dormant donors
2. **Import graph ≠ actual usage** — verify runtime call sites, not just imports
3. **Remove after migration, not before** — removing before migration = capability loss

---

## 11. Final Recommended Plan Delta

### Co MĚLO BÝT v master planu ale CHYBÍ

| # | Delta | Zdroj report | Priority |
|---|-------|--------------|----------|
| 1 | Dual UMA authority resolution (F0.25-ticket-1) | CONTEXT | P0 |
| 2 | SUPREME_INTEGRATION_AVAILABLE hardcoded lie | CONTEXT | P0 |
| 3 | Sprint mode wire-up (scheduler undefined) | RUNTIME | P0 |
| 4 | Wayback CDX 3× deduplication | SOURCE | P0 |
| 5 | TransportResolver napojení | SOURCE | P0 |
| 6 | GhostExecutor → ToolRegistry bridge | TOOL | P1 |
| 7 | AutonomousAnalyzer shadow removal | TOOL | P1 |
| 8 | Graph truth owner explicitní | GRAPH | P1 |
| 9 | DuckDB Shadow vs Graph separation | GRAPH | P1 |
| 10 | Windup double-wired resolution | RUNTIME | P1 |

### Co JE v master planu ale je HYPOTÉZA (potřebuje ověření)

| # | Hypotéza | Potřebuje | Priority |
|---|----------|-----------|----------|
| H1 | SprintScheduler "planned but never wired" | Ověřit intent vs bug | P1 |
| H2 | DuckDBShadowStore confusion (analytics vs graph) | Domain expert confirmation | P2 |
| H3 | Nym dormant code intentional | Ověřit jestli někdy bylo použito | P3 |
| H4 | legacy AO consumers exist | Grep all imports of autonomous_orchestrator | P1 |

### Co JE v master planu ale rozchází se s realitou

| # | Plán říká | Realita | Delta |
|---|-----------|---------|-------|
| P1 | uma_budget.py = SSOT for memory pressure | resource_governor.py ALSO computes same state | Přidat arbitraci |
| P2 | SprintScheduler is on sprint path | SprintScheduler is UNPLUGGED | SprintScheduler wire-up nebo remark jako dormant |
| P3 | WINDUP plane = windup_engine.run_windup() | windup_engine.run_windup() NOT called, _windup_synthesis() inline | Rozhodnout jednu implementaci |
| P4 | TransportResolver is wired | TransportResolver exists but NOT wired to FetchCoordinator | Napojit TransportResolver |
| P5 | ToolRegistry is primary execution surface | GhostExecutor is parallel system without bridge | Přidat _ACTION_TO_TOOL mapping |

---

## 12. Top 30 Konkrétních Ticketů

### P0 — Must Fix Before Any F1-F6 (CRITICAL)

| # | Ticket | Source | Action | Exit Criterion |
|---|--------|--------|--------|----------------|
| 1 | F025-T001: Dual UMA authority | CONTEXT | `resource_governor.evaluate_uma_state()` musí delegovat na `uma_budget.get_uma_pressure_level()` | `grep "psutil.virtual_memory" resource_governor.py` → 0 matches (delegates) |
| 2 | F025-T002: Sprint mode `scheduler` undefined | RUNTIME | Instantiate `SprintScheduler` v `_run_sprint_mode()` around line 2415 | Sprint mode runs without NameError |
| 3 | F025-T003: Wayback CDX 3× | SOURCE |ONE canonical source v `archive_discovery.py::WaybackMachineClient` | `grep "wayback_cdx" --include="*.py"` → MAX 2 (canonical + callers) |
| 4 | F025-T004: TransportResolver not wired | SOURCE | FetchCoordinator._fetch_url() → TransportResolver.resolve_url() | `grep "TransportResolver" fetch_coordinator.py` → call site exists |
| 5 | F025-T005: SUPREME_INTEGRATION_AVAILABLE lie | CONTEXT | Změnit na `try/except` skutečný stav | `grep "SUPREME_INTEGRATION_AVAILABLE" __init__.py` → not hardcoded True |

### P1 — Must Fix Before F1-F3 (HIGH)

| # | Ticket | Source | Action | Exit Criterion |
|---|--------|--------|--------|----------------|
| 6 | F025-T006: run_warmup() not wired | RUNTIME | Call after `lifecycle.mark_warmup_done()` (line 2433) | `grep "run_warmup" __main__.py` → call site exists |
| 7 | F025-T007: run_windup() not wired | RUNTIME | Wire `windup_engine.run_windup()` in WINDUP phase | `grep "run_windup" __main__.py` → call site exists |
| 8 | F025-T008: export_sprint() not wired | RUNTIME | Call after `lifecycle.request_export()` (line 2595) | `grep "export_sprint" __main__.py` → call site exists |
| 9 | F025-T009: GhostExecutor ActionType → ToolRegistry | TOOL | Create `_ACTION_TO_TOOL` mapping dict | `grep "_ACTION_TO_TOOL" ghost_executor.py` → exists |
| 10 | F025-T010: AutonomousAnalyzer → CapabilityRouter | TOOL | `_detect_tools()` calls `CapabilityRouter.route()` | `grep "CapabilityRouter" autonomous_analyzer.py` → import + call |
| 11 | F025-T011: Tool.required_capabilities | TOOL | Add `required_capabilities: Set[Capability]` to `Tool` class | `grep "required_capabilities" tool_registry.py` → exists |
| 12 | F025-T012: Phase-gated tool execution | TOOL | `ModelLifecycleManager.get_enabled_tools(phase)` → `ToolRegistry` | `grep "get_enabled_tools" capabilities.py` → exists |
| 13 | F025-T013: Graph truth owner explicit | GRAPH | IOCGraph = canonical, DuckPGQGraph = alternate with flag | DuckPGQGraph has explicit "alternate backend" documentation |
| 14 | F025-T014: DuckDB Shadow vs Graph separation | GRAPH | DuckDBShadowStore → analytics namespace, DuckPGQGraph → graph namespace | No confusion in code comments |
| 15 | F025-T015: Dual alarm consolidation | CONTEXT | `UmaWatchdog` + `UMAAlarmDispatcher` → single alarm OR clear boundaries | Documented boundary between watchdog and dispatcher |

### P2 — Must Fix Before DeepResearch (MEDIUM)

| # | Ticket | Source | Action | Exit Criterion |
|---|--------|--------|--------|----------------|
| 16 | F025-T016: Sjednotit get_mlx_memory_mb() | CONTEXT | Pick ONE canonical `get_mlx_memory_mb()` across uma_budget/resource_allocator/mlx_cache | `grep "def get_mlx_memory_mb" --include="*.py"` → single definition |
| 17 | F025-T017: Nym dormant remark | SOURCE | Add "DORMANT" logger.debug in circuit_breaker Nym branch | `grep "DORMANT" circuit_breaker.py` → exists |
| 18 | F025-T018: capability → tool bridge | TOOL | `ToolRegistry.execute_with_limits()` calls `CapabilityRegistry.is_available()` | `grep "CapabilityRegistry" tool_registry.py` → exists |
| 19 | F025-T019: AuditLogger v GhostLayer | TOOL | GhostLayer uses AuditLogger instead of `_action_count` | `grep "AuditLogger" ghost_layer.py` → exists |
| 20 | F025-T020: Prefetch → Graph abstraction | GRAPH | PrefetchOracle přes abstraktní interface, ne RelationshipDiscoveryEngine direct | `grep "RelationshipDiscoveryEngine" prefetch_oracle.py` → 0 matches |

### P3 — Cleanup / Documentation (LOW)

| # | Ticket | Source | Action | Exit Criterion |
|---|--------|--------|--------|----------------|
| 21 | F025-T021: Rate limiter canonical | CONTEXT | Určit který `rate_limiter.py` vs `rate_limiters.py` je canonical | Dead code removed or documented |
| 22 | F025-T022: MLX memory duplication investigation | CONTEXT | `mlx_memory.py` vs `mlx_cache.py` audit | Report findings, merge or document |
| 23 | F025-T023: research_flow_decider helper | MODEL | Respektovat header comment "HELPER only" | No integration dependency on research_flow_decider |
| 24 | F025-T024: Legacy AO consumers | LEGACY | Grep all imports of `autonomous_orchestrator.py` facade | List of consumers for migration plan |
| 25 | F025-T025: knowledge/ proxy-import migration | LEGACY | graph_layer, graph_rag, graph_builder → duckdb_store | `grep "legacy.persistent_layer" knowledge/` → 0 matches |
| 26 | F025-T026: orchestrator_integration.py removal | LEGACY | DELETE orphaned file | File removed |
| 27 | F025-T027: federated_engine v1 removal | LEGACY | DELETE v1, keep v2 | File removed |
| 28 | F025-T028: ScalableBloomFilter removal | LEGACY | Replace with RotatingBloomFilter everywhere | `grep "ScalableBloomFilter" --include="*.py"` → 0 matches |
| 29 | F025-T029: Legacy donor conservation | LEGACY | Zakonzervovat dht/, federated/, rl/ jako dormant donors | No removal without migration path |
| 30 | F025-T030: Lifecycle duality resolution | RUNTIME | Rozhodnout canonical verze (runtime/ vs utils/) | Jedna verze dokumentovaná jako canonical |

---

## Definitive Changes Required in the Master Plan

### ADD IMMEDIATELY (P0 blockers)

1. **F0.25: Dual UMA Authority Resolution**
   - Current: `uma_budget.py` and `resource_governor.py` both compute same state independently
   - Required: `resource_governor` DELEGATES to `uma_budget` — no duplicate psutil calls
   - Impact: All runtime governance depends on this

2. **F0.25: Sprint Mode Wire-Up**
   - Current: `_run_sprint_mode()` references undefined `scheduler` variable
   - Required: Instantiate SprintScheduler + wire run_warmup/run_windup/export_sprint
   - Impact: Sprint mode cannot run until this is fixed

3. **F0.25: Wayback CDX Single Source**
   - Current: 3 independent implementations
   - Required: ONE canonical in archive_discovery.py
   - Impact: Source maintenance and API consistency

4. **F0.25: TransportResolver Wiring**
   - Current: TransportResolver exists but FetchCoordinator uses if/else
   - Required: FetchCoordinator uses TransportResolver.resolve_url()
   - Impact: Centralized transport policy

5. **F0.25: SUPREME_INTEGRATION_AVAILABLE Truth**
   - Current: hardcoded `True` regardless of actual state
   - Required: `try/except` actual load state
   - Impact: Public API contract correctness

### REVISIT (assumptions don't match reality)

6. **SprintScheduler Status**
   - Current assumption: SprintScheduler is on sprint path
   - Reality: UNPLUGGED, 62KB, 0 instantiation
   - Required: Either wire it OR mark as deprecated dormant

7. **WINDUP Plane**
   - Current assumption: windup_engine.run_windup() is the windup implementation
   - Reality: NOT CALLED, _windup_synthesis() is inline in __main__.py
   - Required: Single implementation, clear ownership

8. **ToolRegistry vs GhostExecutor**
   - Current assumption: ToolRegistry is primary execution surface
   - Reality: GhostExecutor is parallel system without bridge
   - Required: _ACTION_TO_TOOL mapping OR GhostExecutor deprecation

9. **Graph Truth**
   - Current assumption: Single graph truth owner
   - Reality: IOCGraph (Kuzu) vs DuckPGQGraph (DuckDB) split
   - Required: IOCGraph = canonical, DuckPGQGraph = explicit alternate

10. **Legacy Consumers**
    - Current assumption: Legacy autonomous_orchestrator has active consumers
    - Reality: UNKNOWN — needs grep survey
    - Required: Survey all imports before facade removal

### PRESERVE (don't break)

11. **Capability Donors** (dht/, federated/, rl/) — NEVER remove without migration path
12. **Windup Isolation** — SynthesisRunner(ModelLifecycle()) is ISOLATED by design, don't merge
13. **ResearchContext** — Clean canonical context carrier, no changes needed
14. **research_flow_decider** — Helper only, don't depend on for canonical decisions
15. **Passive Path** — This is the ACTUAL hot path, don't neglect in favor of sprint mode

---

*Master synthesis completed: 2026-04-01*
*Sources: F025_RUNTIME_REALITY, F025_CONTEXT_FOUNDATION_CONTROL, F025_TOOL_CAPABILITY_EXECUTION, F025_SOURCE_TRANSPORT, F025_SECURITY_FORENSICS_MULTIMODAL, F025_GRAPH_RETRIEVAL_PREFETCH, F025_MODEL_REASONING_DEEP_PROVIDER, F025_LEGACY_CONTAINMENT*
