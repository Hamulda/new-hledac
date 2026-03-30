# HLEDAC UNIVERSAL CONNECTIVITY AUDIT — FINAL

**Date**: 2026-03-18
**Audit Scope**: `hledac/universal` (301 non-test Python files, 175,371 lines)
**Audit Type**: Static analysis + import graph + call chain tracing

---

## 1. Executive Summary

| Metric | Value |
|--------|-------|
| Total Python Files | 428 (301 non-test) |
| Total Lines | 175,371 |
| Active Entry Points | 3 |
| Registered Actions | 18 |
| Primary Production Entry | `autonomous_orchestrator.py:10450` (research) |
| Primary Benchmark Entry | `autonomous_orchestrator.py:24246` (run_benchmark) |

**MAIN FINDING**: Universal codebase is WELL-INTEGRATED. The primary research loop has 18 registered actions, all with handlers and scorers. However, several HIGH-VALUE OSINT capabilities exist but are DISABLED by config flags or never triggered.

---

## 2. File Inventory

| Subdirectory | Files | Lines (est) |
|--------------|-------|-------------|
| tools/ | 34 | ~45,000 |
| utils/ | 33 | ~25,000 |
| intelligence/ | 21 | ~28,000 |
| security/ | 14 | ~15,000 |
| knowledge/ | 14 | ~18,000 |
| coordinators/ | 24 | ~22,000 |
| brain/ | 18 | ~12,000 |
| **autonomous_orchestrator.py** | 1 | **27,054** |
| layers/ | 13 | ~10,000 |
| network/ | 9 | ~8,000 |
| federated/ | 13 | ~10,000 |
| transport/ | 6 | ~4,000 |

**Top 5 Largest Files**:
1. autonomous_orchestrator.py — 27,054 lines
2. knowledge/persistent_layer.py — 3,575 lines
3. coordinators/memory_coordinator.py — 2,759 lines
4. knowledge/atomic_storage.py — 2,742 lines
5. layers/stealth_layer.py — 2,652 lines

---

## 3. Active Entry Points

| Entry Point | File | Line | Type | Active? | Called By |
|-------------|------|------|------|---------|-----------|
| research() | autonomous_orchestrator.py | 10450 | async | **YES** | External callers |
| run_benchmark() | autonomous_orchestrator.py | 24246 | async | **YES** | Tests, benchmarks |
| research_autonomous() | autonomous_orchestrator.py | 12496 | async | SHADOWED | Legacy entry |
| research() | enhanced_research.py | 1583 | async | DISCONNECTED | Not called from main |
| research_with_meta_reasoning() | orchestrator_integration.py | 457 | async | DISCONNECTED | Not called |
| research_with_swarm() | orchestrator_integration.py | 512 | async | DISCONNECTED | Not called |
| research_with_validation() | orchestrator_integration.py | 606 | async | DISCONNECTED | Not called |

**VERDICT**: PRIMARY_PRODUCTION_ENTRY = `autonomous_orchestrator.py:10450` (research method with Sprint 82A+ loop)

---

## 4. Action Registry Truth

All 18 actions are **CONNECTED_ACTIVE**:

| Action | Registry Line | Handler | Reachable | Scorer | State |
|--------|--------------|---------|-----------|--------|-------|
| surface_search | 4435 | ✓ async | ✓ | ✓ | CONNECTED_ACTIVE |
| archive_fetch | 4470 | ✓ async | ✓ | ✓ | CONNECTED_ACTIVE |
| render_page | 4504 | ✓ async | ✓ | ✓ | CONNECTED_ACTIVE |
| investigate_contradiction | 4518 | ✓ async | ✓ | ✓ | CONNECTED_ACTIVE |
| build_structure_map | 4576 | ✓ async | ✓ | ✓ | CONNECTED_ACTIVE |
| scan_ct | 4600 | ✓ async | ✓ | ✓ | CONNECTED_ACTIVE |
| fingerprint_jarm | 4619 | ✓ async | ✓ | ✓ | CONNECTED_ACTIVE |
| scan_open_storage | 4640 | ✓ async | ✓ | ✓ | CONNECTED_ACTIVE |
| crawl_onion | 4661 | ✓ async | ✓ | ✓ | CONNECTED_ACTIVE |
| generate_paths | 4682 | ✓ async | ✓ | ✓ | CONNECTED_ACTIVE |
| ct_discovery | 4732 | ✓ async | ✓ | ✓ | CONNECTED_ACTIVE |
| wayback_rescue | 4778 | ✓ async | ✓ | ✓ | CONNECTED_ACTIVE |
| commoncrawl_rescue | 4807 | ✓ async | ✓ | ✓ | CONNECTED_ACTIVE |
| necromancer_rescue | 4848 | ✓ async | ✓ | ✓ | CONNECTED_ACTIVE |
| prf_expand | 4948 | ✓ async | ✓ | ✓ | CONNECTED_ACTIVE |
| onion_fetch | 4980 | ✓ async | ✓ | ✓ | CONNECTED_ACTIVE |
| network_recon | 5201 | ✓ async | ✓ | ✓ | CONNECTED_ACTIVE |
| identity_stitching | 6409 | ✓ async | ✓ | ✓ | CONNECTED_ACTIVE |

**FINDING**: Action registry is FULLY OPERATIONAL. No dead handlers, all have scorers.

---

## 5. Import vs Call Reality

### Imports in autonomous_orchestrator.py (line 1300+):

| Module | Import Type | Actually Called? |
|--------|------------|-----------------|
| layers | from .layers import | ✓ initialize_all() |
| coordinators.fetch_coordinator | FetchCoordinator | ✓ used in handlers |
| coordinators.research_coordinator | ResearchCoordinator | ✓ via _research_mgr |
| knowledge.rag_engine | RAGEngine | ✓ via _research_mgr |
| knowledge.atomic_storage | AtomicJSONKnowledgeGraph | ✓ via _research_mgr |
| knowledge.persistent_layer | PersistentKnowledgeLayer | ✓ via _memory_mgr |
| brain.hermes3_engine | Hermes3Engine | ✓ via _brain_mgr |
| brain.inference_engine | InferenceEngine | ✓ via _brain_mgr |
| tools.content_miner | MetadataExtractor | ✓ used |
| tools.osint_frameworks | OSINTFrameworkRunner | ✓ action handler exists |
| tools.darknet | DarknetConnector | ✓ action handler exists |
| federated/ | FederatedEngine | ⚠️ LAZY, config-gated |
| transport/ | TorTransport, NymTransport | ⚠️ LAZY, rarely used |

### Uncalled / Rarely Called Modules:

| Module | Status | Root Cause |
|--------|--------|------------|
| orchestrator_integration.py | DISCONNECTED | Alternate entry points never called |
| enhanced_research.py | DISCONNECTED | Standalone alternative, not wired |
| autonomy/research_engine.py | IMPORTED_ONLY | Separate orchestrator, not used in main |
| layers/layer_manager.py | CONNECTED_IDLE | Methods exist but primary uses _*_mgr directly |
| graph/quantum_pathfinder.py | IMPORTED_ONLY | Lazy import, not actively used |
| dht/* | IMPORTED_ONLY | DHT setup exists but not critical path |

---

## 6. Connectivity Matrix by Subdirectory

### TOP 30 DETAILED ANALYSIS:

| File | Defines | Imported | Referenced | Callable | State | Reconnect Value |
|------|---------|----------|------------|----------|-------|-----------------|
| autonomous_orchestrator.py | Main orchestrator | N/A | ✓ | ✓ | **CONNECTED_ACTIVE** | N/A |
| intelligence/identity_stitching.py | IdentityStitchingEngine | ✓ lazy | ✓ | ✓ | **CONNECTED_ACTIVE** | HIGH |
| intelligence/network_reconnaissance.py | NetworkReconnaissance | ✓ lazy | ✓ | ✓ | **CONNECTED_ACTIVE** | HIGH |
| intelligence/stealth_crawler.py | StealthCrawler | ✓ | ✓ | ✓ | **CONNECTED_ACTIVE** | HIGH |
| intelligence/document_intelligence.py | DocumentIntelligence | ✓ | ✓ | ✓ | **CONNECTED_ACTIVE** | HIGH |
| intelligence/archive_discovery.py | ArchiveDiscovery | ✓ | ✓ | ✓ | **CONNECTED_ACTIVE** | HIGH |
| intelligence/relationship_discovery.py | RelationshipDiscovery | ✓ | ✓ | ✓ | **CONNECTED_ACTIVE** | MEDIUM |
| intelligence/exposed_service_hunter.py | ExposedServiceHunter | ✓ | ✓ | ✓ | **CONNECTED_ACTIVE** | HIGH |
| knowledge/graph_rag.py | GraphRAG | ✓ | ✓ | ✓ | **CONNECTED_ACTIVE** | MEDIUM |
| knowledge/rag_engine.py | RAGEngine | ✓ | ✓ | ✓ | **CONNECTED_ACTIVE** | MEDIUM |
| knowledge/lancedb_store.py | LanceDBStore | ✓ | ✓ | ✓ | **CONNECTED_ACTIVE** | MEDIUM |
| brain/hermes3_engine.py | Hermes3Engine | ✓ | ✓ | ✓ | **CONNECTED_ACTIVE** | HIGH |
| brain/hypothesis_engine.py | HypothesisEngine | ✓ | ✓ | ✓ | **CONNECTED_ACTIVE** | MEDIUM |
| brain/inference_engine.py | InferenceEngine | ✓ | ✓ | ✓ | **CONNECTED_ACTIVE** | HIGH |
| tools/content_miner.py | ContentMiner | ✓ | ✓ | ✓ | **CONNECTED_ACTIVE** | HIGH |
| tools/osint_frameworks.py | OSINTFrameworkRunner | ✓ | ✓ | ✓ | **CONNECTED_ACTIVE** | HIGH |
| transport/tor_transport.py | TorTransport | ⚠️ lazy | ⚠️ | ⚠️ | **DISCONNECTED** | HIGH |
| transport/nym_transport.py | NymTransport | ⚠️ lazy | ⚠️ | ⚠️ | **DISCONNECTED** | HIGH |
| federated/ | FederatedOSINT | ⚠️ lazy | ⚠️ | ⚠️ | **DISCONNECTED** | MEDIUM |
| orchestrator_integration.py | Alt research methods | ✗ | ✗ | ✗ | **DISCONNECTED** | LOW |
| enhanced_research.py | Alt orchestrator | ✗ | ✗ | ✗ | **DISCONNECTED** | LOW |
| autonomy/research_engine.py | Alt research | ✓ | ✗ | ✗ | **IMPORTED_ONLY** | LOW |
| graph/quantum_pathfinder.py | QuantumPathFinder | ✓ | ✗ | ✗ | **IMPORTED_ONLY** | MEDIUM |
| dht/* | Kademlia DHT | ✓ | ✗ | ✗ | **IMPORTED_ONLY** | LOW |

### AGGREGATED BY SUBDIRECTORY:

| Subdirectory | CONNECTED_ACTIVE | CONNECTED_IDLE | IMPORTED_ONLY | DISCONNECTED |
|--------------|------------------|----------------|---------------|--------------|
| intelligence/ | 15 | 0 | 3 | 3 |
| knowledge/ | 8 | 2 | 2 | 2 |
| brain/ | 6 | 1 | 2 | 1 |
| tools/ | 12 | 3 | 5 | 4 |
| transport/ | 0 | 0 | 2 | 4 |
| federated/ | 0 | 0 | 2 | 11 |
| network/ | 4 | 1 | 2 | 2 |
| security/ | 8 | 2 | 2 | 2 |
| layers/ | 6 | 3 | 2 | 2 |
| coordinators/ | 12 | 4 | 4 | 4 |

---

## 7. Shadowing / Duplicate / Legacy Findings

### SHADOWING FINDINGS:

| Shadowed | Active | Location | Harmless? |
|----------|--------|----------|-----------|
| research() in enhanced_research.py | research() in autonomous_orchestrator.py | Line 1583 vs 10450 | YES - alternate entry |
| run_benchmark() in benchmarks/ | run_benchmark() in autonomous_orchestrator.py | Multiple vs 24246 | YES - test helpers |
| research_with_* in orchestrator_integration.py | research() in autonomous_orchestrator.py | Lines 457, 512, 606 | YES - unused alternates |

### LEGACY LEFTOVERS:

| Module | Status | Notes |
|--------|--------|-------|
| autonomy/planner.py | IMPORTED_ONLY | Alternative planning, not integrated |
| tot_integration.py | IMPORTED_ONLY | Tree-of-thoughts integration, not active |
| behavior_simulator.py | IMPORTED_ONLY | Simulation capability, not used in main loop |

### DANGLING TASK RISKS:

| Location | Risk | Assessment |
|----------|------|------------|
| background tasks in research() | LOW | Properly tracked with _*_task variables |
| asyncio.create_task for meta_optimizer | LOW | Properly awaited/checked for done() |
| asyncio.create_task for dns_monitor | LOW | Properly awaited/checked for done() |

---

## 8. Lazy / Cache / Singleton Audit

| Component | File | Init Style | Activated | Hidden State Risk | Verdict |
|-----------|------|------------|-----------|-------------------|---------|
| NetworkReconnaissance | intelligence/network_reconnaissance.py | Lazy (line 2157) | ✓ On action call | LOW | CONNECTED_ACTIVE |
| IdentityStitchingEngine | intelligence/identity_stitching.py | Lazy (line 2073) | ✓ On action call | LOW | CONNECTED_ACTIVE |
| FederatedEngine | federated/ | Lazy + config | ✗ Only if enable_federated_osint=True | MEDIUM | DISCONNECTED |
| TorTransport | transport/tor_transport.py | Lazy | ✗ Not used in main | MEDIUM | DISCONNECTED |
| NymTransport | transport/nym_transport.py | Lazy | ✗ Not used in main | MEDIUM | DISCONNECTED |
| DSPyOptimizer | brain/dspy_optimizer.py | Lazy | ⚠️ Rarely used | LOW | CONNECTED_IDLE |
| PromptBandit | brain/prompt_bandit.py | Lazy | ⚠️ Rarely used | LOW | CONNECTED_IDLE |

---

## 9. High-Value Domain Deep Dives

### _SynthesisManager (line 25016)

| Question | Answer |
|----------|--------|
| When does synthesis run? | At end of research() loop (line 11373) |
| Is synthesis called from research()? | **YES** - `await self._synthesis_mgr.synthesize_report()` |
| How many findings enter synthesis? | All confirmed findings from `_findings_heap` |
| Is output usable? | **YES** - ComprehensiveResearchResult with claims, confidence |

**VERDICT**: FULLY CONNECTED

### transport/ (Tor, Nym)

| Question | Answer |
|----------|--------|
| Implementation complete? | TorTransport is ~400 lines, NymTransport ~350 lines |
| Is Nym client imported? | ⚠️ Lazy, may fail if nymclient not installed |
| Which action could use it? | crawl_onion, onion_fetch |
| Is it start-able on M1? | Requires external process, possible but complex |
| Verdict | **DORMANT GOLDMINE** - Ready but not wired to actions |

### Deep OSINT Radar

| Keyword | Found Modules | Active? |
|---------|--------------|---------|
| tor/onion | stealth_crawler.py, crawl_onion action | ✓ YES |
| proxy | stealth_manager.py, proxy rotation | ✓ YES |
| headless | nodriver in fetch_coordinator | ✓ YES |
| shodan | exposed_service_hunter.py | ✓ YES |
| leak | data_leak_hunter.py | ✓ YES |
| ocr | document_intelligence.py | ✓ YES |
| pdf | document_intelligence.py | ✓ YES |
| archive | archive_discovery.py, wayback_rescue | ✓ YES |
| metadata | metadata_extractor.py, forensics | ✓ YES |

**FINDING**: Deep OSINT capabilities ARE PRESENT and MOSTLY CONNECTED.

---

## 10. Root Cause Classification

| Module | State | Root Cause | Reconnect Difficulty |
|--------|-------|------------|---------------------|
| FederatedEngine | DISCONNECTED | FEATURE_FLAG_NEVER_ENABLED (enable_federated_osint config) | LOW |
| TorTransport | DISCONNECTED | NO_IMPORT_IN_HANDLERS | MEDIUM |
| NymTransport | DISCONNECTED | NO_IMPORT_IN_HANDLERS | MEDIUM |
| orchestrator_integration.py | DISCONNECTED | SHADOWED_BY_OTHER_ENTRY | NONE |
| enhanced_research.py | DISCONNECTED | SHADOWED_BY_OTHER_ENTRY | NONE |
| autonomy/research_engine.py | IMPORTED_ONLY | NO_CALL_FROM_ACTIVE_PATH | HIGH |
| graph/quantum_pathfinder.py | IMPORTED_ONLY | LAZY_BUT_NEVER_CALLED | MEDIUM |
| dht/* | IMPORTED_ONLY | INFRA_ONLY (not OSINT critical) | LOW |
| DSPyOptimizer | CONNECTED_IDLE | ALWAYS_ON_BUT_UNDERUTILIZED | LOW |

---

## 11. Top Reconnect Candidates (MAX 15)

### HIGH-VALUE OSINT RECONNECT:

| # | Module | Current State | Root Cause | OSINT Value | M1 Risk | ROI | Recommendation |
|---|--------|---------------|-------------|-------------|---------|-----|----------------|
| 1 | FederatedEngine | DISCONNECTED | FEATURE_FLAG_NEVER_ENABLED | MEDIUM | LOW | **HIGH** | RECONNECT_NEXT |
| 2 | TorTransport | DISCONNECTED | NO_IMPORT_IN_HANDLERS | HIGH | MEDIUM | **HIGH** | RECONNECT_NEXT |
| 3 | NymTransport | DISCONNECTED | NO_IMPORT_IN_HANDLERS | HIGH | MEDIUM | **MEDIUM** | RECONNECT_LATER |
| 4 | QuantumPathFinder | IMPORTED_ONLY | LAZY_BUT_NEVER_CALLED | MEDIUM | LOW | MEDIUM | KEEP_DORMANT |
| 5 | DSPyOptimizer | CONNECTED_IDLE | UNDERUTILIZED | LOW | LOW | LOW | KEEP_DORMANT |

### OTHER DISCONNECTED (Low OSINT Value):

| # | Module | Current State | Root Cause | OSINT Value | Recommendation |
|---|--------|---------------|-------------|-------------|----------------|
| 6 | orchestrator_integration.py | DISCONNECTED | SHADOWED | LOW | REMOVE_CANDIDATE |
| 7 | enhanced_research.py | DISCONNECTED | SHADOWED | LOW | REMOVE_CANDIDATE |
| 8 | autonomy/research_engine.py | IMPORTED_ONLY | NO_CALL | LOW | KEEP_DORMANT |
| 9 | dht/* | IMPORTED_ONLY | INFRA_ONLY | LOW | KEEP_DORMANT |

---

## 12. Low-Hanging Fruit

### Easy Wins (<20 lines):

| Module | Fix | Lines | Risk |
|--------|-----|-------|------|
| FederatedEngine | Add `enable_federated_osint=True` to config OR wire into research() loop | 5-10 | LOW |
| TorTransport in handlers | Add `from .transport.tor_transport import TorTransport` to crawl_onion handler | 5 | LOW |
| NymTransport in handlers | Similar to TorTransport | 5 | LOW |

### Medium Effort (20-100 lines):

| Module | Fix | Lines | Risk |
|--------|-----|-----|------|
| QuantumPathFinder activation | Wire into research() as optional enhancement | 50-80 | MEDIUM |

---

## 13. What Must NOT Be Touched

| Module | Reason |
|--------|--------|
| autonomous_orchestrator.py main loop | Core production path |
| Action registry (18 actions) | All working correctly |
| _research_mgr, _synthesis_mgr | Properly wired |
| intelligence/identity_stitching.py | Active, high-value |
| intelligence/network_reconnaissance.py | Active, high-value |
| benchmarks/* | Test infrastructure |

---

## 14. Recommended Reconnect Pattern

For future sprints, follow this pattern:

```
1. FEATURE FLAG: Use config.gate (not hardcoded)
   - enable_<feature>: bool = False  # default OFF

2. LAZY IMPORT: Always lazy load heavy deps
   - from .module import Module  # inside function

3. BOUNDED QUEUE: Feed results properly
   - if hasattr(self, '_results_queue'):
       await self._results_queue.put(result)

4. RESULT CONSUMPTION: Always wire to _findings_heap
   - findings = result.get('findings', [])
   - for f in findings:
       await self._research_mgr._add_finding_with_limit(f)

5. BENCHMARKABILITY: Add metric in run_benchmark
   - <feature>_runs: int
   - <feature>_findings: int
```

---

## 15. Concrete Next Sprint Recommendation

**Priority 1 (Do First)**:
1. Enable FederatedOSINT in config — adds multi-session retention
2. Wire TorTransport into crawl_onion/onion_fetch actions — enables real dark web access

**Priority 2 (Next Sprint)**:
3. NymTransport wiring — adds mixnet capability
4. QuantumPathFinder integration — adds quantum-inspired path finding

**Do NOT**:
- Remove orchestrator_integration.py (keep for reference)
- Remove enhanced_research.py (keep for reference)
- Add new modules without wiring to action registry

---

## CLASSIFICATION SUMMARY

| State | Count |
|-------|-------|
| CONNECTED_ACTIVE | ~120 |
| CONNECTED_IDLE | ~15 |
| IMPORTED_ONLY | ~25 |
| PARTIALLY_WIRED | 0 |
| SHADOWED | 8 |
| DISCONNECTED | ~20 |
| DEAD_WEIGHT | 0 |

**MAIN FINDING**: Universal codebase is WELL-INTEGRATED. The primary research loop has 18 registered actions, all with handlers and scorers. The main disconnect is FederatedOSINT (config-gated) and Tor/Nym transports (not imported in handlers). Deep OSINT capabilities (archive, OCR, PDF, metadata, leak, shodan) are PRESENT and CONNECTED.
