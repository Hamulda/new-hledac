# MEGA AUDIT v2 — Wiring + Perf + Dead-code + Guardrails
**Scope:** `/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/`
**Date:** 2026-03-06
**Status:** COMPLETE

---

## 1. Wiring Scorecard

| Category | Score | Notes |
|----------|-------|-------|
| A) Actions Registry | ✅ 10/10 | All registered in `_initialize_actions()` |
| A) Scorers O(1) | ✅ Verified | Scorers compute state, no I/O |
| A) Async Handlers | ✅ Verified | Handlers delegate to coordinators |
| A) Background Lifecycle | ✅ Verified | `add_done_callback` at line 1981 |
| B) Bounded Loops | ⚠️ 20+ while True | Need exit condition audit |
| B) Lazy Imports | ❌ EAGER | autonomous_orchestrator.py:87-236 |
| B) No Toggles | ✅ Pass | No runtime feature flags in hot paths |
| B) Async Blocking | ⚠️ 6 issues | time.sleep in async contexts |
| C) Import Cost | ❌ 4.5s+ | mlx_lm, transformers, sklearn, torch |
| C) Memory Bounded | ✅ Good | EvidenceLog uses deque(maxlen=100) |
| D) Security | ✅ Good | DNS rebinding, PII sanitization present |
| E) Test Coverage | ⚠️ Gaps | 8+ modules lack tests |

### Wiring Truth Table

| Action | Handler | Scorer | Components | Evidence Events | Gates |
|--------|---------|--------|------------|------------------|-------|
| `surface_search` | `surface_search_handler:2579` | `surface_search_scorer` | `_research_mgr` | search_result | cooldown |
| `archive_fetch` | `archive_fetch_handler:2602` | `archive_fetch_scorer` | `_archive_coordinator` | archive_hit | - |
| `render_page` | `render_page_handler:2637` | `render_page_scorer` | `_render_coordinator` | render_complete | memory |
| `investigate_contradiction` | `investigate_handler:2671` | `investigate_scorer` | `_research_mgr` | contradiction_found | - |
| `build_structure_map` | `build_structure_map_handler:2685` | `build_structure_map_scorer` | `_structure_map` | map_built | circuit |
| `scan_ct` | `_handle_ct_scan:2742` | `_ct_scorer` | CT API | ct_scan_done | - |
| `fingerprint_jarm` | `_handle_jarm:2759` | `_jarm_scorer` | JARM fingerprint | jarm_done | - |
| `scan_open_storage` | `_handle_open_storage:2772` | `_open_storage_scorer` | storage scan | storage_found | - |
| `crawl_onion` | `_handle_crawl_onion:2788` | `_onion_scorer` | Tor crawler | onion_crawled | - |
| `generate_paths` | `_handle_path_discovery:2802` | `_path_discovery_scorer` | path discovery | paths_generated | - |

---

## 2. Top 20 Issues (Ranked)

| # | Location | Severity | M1 Impact | Fix Plan | Test Plan |
|---|----------|----------|-----------|----------|-----------|
| 1 | `autonomous_orchestrator.py:87-236` | CRITICAL | 4.5s+ import time, RAM spike | Convert to lazy import pattern like PrivacyEnhancedResearch | Import-time test with threshold |
| 2 | `autonomous_orchestrator.py:87` | CRITICAL | mlx_lm 1.4s eager load | Move to `_load_model()` lazy loader | Mock import time |
| 3 | `autonomous_orchestrator.py:87` | CRITICAL | transformers 928ms | Lazy load in action handlers | Import-time regression |
| 4 | `coordinators/memory_coordinator.py:501` | HIGH | Blocks event loop | Replace `time.sleep(0.1)` with `await asyncio.sleep(0.1)` | Async test with mock time |
| 5 | `orchestrator/global_scheduler.py:108,137` | HIGH | Event loop blocking | Replace with `await asyncio.sleep()` | Async scheduler tests |
| 6 | `network/jarm_fingerprinter.py:232` | MEDIUM | 50ms blocking per call | Use `await asyncio.to_thread()` | Thread pool test |
| 7 | `tools/content_miner.py:1184` | MEDIUM | Unbounded file_cache | Add explicit LRU maxsize parameter | Cache eviction test |
| 8 | `autonomous_orchestrator.py:2255` | MEDIUM | Only 6 to_thread for 192 async | Add `to_thread` for CPU-heavy: `_mlx_post_action_cleanup`, `_analyze_input` | CPU load test |
| 9 | 44 MLX files | MEDIUM | Memory leak risk | Add `mx.clear_cache()` to cleanup paths | MLX memory test |
| 10 | `evidence_log.py:215` | LOW | Queue flush lag risk | Already bounded: maxsize=500 | Flush latency test |
| 11 | `autonomous_orchestrator.py:1913` | LOW | No test for macOS 15+ wired | Add test for `mx.metal.get_wired_memory()` | Platform-specific test |
| 12 | `autonomous_orchestrator.py:1525` | LOW | Non-Darwin untested | Add CI test for fallback path | Cross-platform CI |
| 13 | 25 stale TODOs | MEDIUM | Technical debt | Create tracking issue | - |
| 14 | 4 backup files (~3MB) | LOW | Confusion, repo bloat | Delete `.bak`, `.txt` backup files | - |
| 15 | 16 orphan handlers | LOW | Dead code risk | Decide integrate/merge/retire | Reference check test |
| 16 | `autonomous_orchestrator.py:2210` | LOW | Circuit breaker untested | Add test for cooldown + circuit | Circuit test |
| 17 | `evidence_log.py:283` | LOW | Encryption path untested | Add encrypt_at_rest test | Encryption fixture |
| 18 | `test_sprint71/` gaps | MEDIUM | M1-specific branches | Add ANE, CoreML, MPS tests | Platform-specific CI |
| 19 | URL parsing duplication | LOW | Maintenance burden | Single source: `utils/url_parser.py` | Consolidation test |
| 20 | Content extraction duplication | LOW | Logic divergence | Single source: `utils/content_extractor.py` | Consolidation test |

---

## 3. Orphans / Partial Wiring

### Orphan Handlers (Not in Registry)

| Handler | Decision | Integration Seam | O(1) Trigger |
|---------|----------|------------------|--------------|
| `_deep_crawl_handler` | RETIRE | - | - |
| `_academic_handler` | MERGE | Into `surface_search` with `source=academic` | query contains "academic" |
| `_osint_handler` | MERGE | Into `surface_search` with `source=osint` | query contains "osint" |
| `_dark_web_handler` | RETIRE | - | - |
| `_entity_handler` | INTEGRATE | New action `extract_entities` | NER pattern in query |
| `_fact_check_handler` | MERGE | Into `investigate_contradiction` | query contains "verify" |
| `_stego_handler` | RETIRE | - | - |
| `_hermes_handler` | INTEGRATE | Into `_analyze_input` | text input detected |

### Partial Components

| Component | Status | Notes |
|-----------|--------|-------|
| `coordinators/*` | ✅ Wired | Called via managers |
| `intelligence/*` | ⚠️ Partial | Some unused, need audit |
| `brain/*` | ⚠️ Partial | Decision engine not in loop |
| `knowledge/*` | ⚠️ Partial | RAGEngine not wired to actions |

---

## 4. Guardrails Findings

### Async Blocking Issues

| File | Line | Issue | Severity | Remediation | Regression Risk |
|------|------|-------|----------|-------------|------------------|
| `coordinators/memory_coordinator.py` | 501 | `time.sleep(0.1)` in async | HIGH | Replace with `await asyncio.sleep()` | Low |
| `orchestrator/global_scheduler.py` | 108, 137 | `time.sleep(0.1)` in async | HIGH | Replace with `await asyncio.sleep()` | Low |
| `network/jarm_fingerprinter.py` | 232 | `time.sleep(0.05)` in async | MEDIUM | Wrap in `to_thread` | Low |

### Lazy Import Issues

| File | Lines | Issue | Severity | Remediation |
|------|-------|-------|----------|-------------|
| `autonomous_orchestrator.py` | 87-236 | 50+ modules at import | CRITICAL | Convert to lazy pattern |

### Loop Boundedness

| File | Line | Status | Notes |
|------|------|--------|-------|
| `autonomous_orchestrator.py` | multiple | ✅ Exit via `return` | OODA loop bounded |
| `prefetch/prefetch_cache.py` | 2 loops | ⚠️ Verify | Need exit condition audit |

### Security Findings

| Finding | Status | Notes |
|---------|--------|-------|
| DNS Rebinding | ✅ Protected | `_is_ip_public()`, `_validate_fetch_target()` |
| Darkweb Separation | ✅ Good | `_is_valid_onion_target()`, `_is_safe_clearnet_target()` |
| PII Handling | ✅ Good | `fallback_sanitize` integrated |
| EvidenceLog | ✅ Bounded | deque(maxlen=100) |

---

## 5. Perf & Memory Deep Dive

### Import-Time Hot List

| Module | Time | Location | Lazy Load Plan |
|--------|------|----------|----------------|
| `mlx_lm` | 1.4s | autonomous_orchestrator.py:87 | Move to `_load_model()` |
| `transformers` | 928ms | autonomous_orchestrator.py:87 | Action-level import |
| `sklearn.ensemble` | 901ms | resource_allocator.py | Lazy in allocator |
| `torch` | 836ms | autonomous_orchestrator.py:87 | Only for MPS checks |
| `pandas` | 520ms | Various | Lazy in data science |

### Memory Hot List

| Component | Status | Evidence |
|------------|--------|----------|
| EvidenceLog | ✅ Bounded | deque(maxlen=100) |
| _execution_history | ✅ Bounded | deque(maxlen=100) |
| _attribution_ring | ✅ Bounded | deque(maxlen=200) |
| _simhash_fingerprints | ✅ Bounded | _LRUDict(maxsize=10_000) |
| structure_map file_cache | ⚠️ NEEDS BOUND | tools/content_miner.py:1184 |
| SQLite batch queue | ✅ Bounded | maxsize=500 |

### Event Loop Risks

| Risk | Location | Severity | Fix |
|------|----------|----------|-----|
| Sync I/O in async | 192 async defs, only 6 to_thread | HIGH | Add `to_thread` for CPU-heavy |
| _mlx_post_action_cleanup | mx.eval + mx.metal.clear_cache | MEDIUM | Move to executor |
| _analyze_input | CoreML classification | MEDIUM | Async classification |

### M1-Specific Notes

1. **Memory Pressure Gates**: `_memory_pressure_ok()` used at lines 2206, 2380, 2912 ✅
2. **MLX Cache**: 44 files lack `mx.clear_cache()` — memory leak risk
3. **Wired Memory**: macOS 15+ path untested (line 1913)
4. **Non-Darwin**: Fallback not tested (line 1525)

---

## 6. Security / Privacy Findings

| Finding | Status | Evidence |
|---------|--------|----------|
| Hardcoded secrets | ✅ None found | No hardcoded API keys |
| EvidenceLog PII | ✅ Sanitized | fallback_sanitize present |
| DNS rebinding | ✅ Protected | _validate_fetch_target() |
| Darkweb clear-net fallback | ✅ Prevented | _is_valid_onion_target() |
| Rate limiting | ✅ Present | utils/rate_limiter.py |
| LootManager encryption | ✅ AES-256 | Previous audit verified |

---

## 7. Dead Code / Redundancy Ledger

### Unused Imports

| File | Unused |
|------|--------|
| `captcha_solver.py` | collections, Vision, typing, pathlib, coremltools |
| `enhanced_research.py` | layers, __future__, enum, knowledge, types, utils, dataclasses |
| `autonomous_orchestrator.py` | collections, autonomy, intelligence, privacy_protection, cryptography, layers |

### Stale TODOs (25)

| File | Line | Description |
|------|------|-------------|
| `execution/ghost_executor.py` | ~50-90 | Search implementation TODOs |
| `knowledge/atomic_storage.py` | ~50 | Hermes extraction |
| `utils/shared_tensor.py` | ~30,50 | Zero-copy Metal buffer |
| `brain/decision_engine.py` | ~80 | LLM fallback |
| `autonomous_orchestrator.py` | ~200 | Archive fetch |

### Backup Files (~3MB)

- `autonomous_orchestrator (kopie).txt` (806KB)
- `autonomous_orchestrator.py.bak.SPRINT65` (738KB)
- `autonomous_orchestrator.py.bak.SPRINT65D` (735KB)
- `autonomous_orchestrator.py.bak.SPRINT65E` (735KB)

### Single Source of Truth Recommendations

| Duplicate Pattern | Canonical Location |
|-------------------|-------------------|
| URL parsing | utils/url_parser.py (create if not exists) |
| Content extraction | utils/content_extractor.py (consolidate) |
| Validation | validation_coordinator.py (use exclusively) |
| Caching | utils/intelligent_cache.py (consolidate) |

---

## 8. Test Gaps

### Critical M1-Specific Branches Without Coverage

| Branch | Location | Test to Add |
|--------|----------|-------------|
| `mx.metal.get_wired_memory()` | autonomous_orchestrator.py:1913 | TestM1WiredMemory |
| `platform.system() != 'Darwin'` | autonomous_orchestrator.py:1525 | TestNonDarwinFallback |
| `sys.platform == "darwin"` | autonomous_orchestrator.py:1951 | TestMemoryCalcNonM1 |
| `mlx_lm` load failures | Lazy loaders | TestModelLoadFailure |
| `_structure_map_should_run` | autonomous_orchestrator.py:2210 | TestCircuitBreaker |
| EvidenceLog encryption | evidence_log.py:283 | TestEncryptAtRest |

### Missing Modules (8+)

| Module | Status |
|--------|--------|
| brain/gnn_predictor.py | NO TESTS |
| brain/paged_attention_cache.py | NO TESTS |
| coordinators/multimodal_coordinator.py | NO TESTS |
| core/resource_governor.py | NO TESTS |
| dht/local_graph.py | NO TESTS |
| federated/secure_aggregator.py | NO TESTS |
| intelligence/advanced_image_osint.py | NO TESTS |
| intelligence/document_intelligence.py | NO TESTS |

### Determinism Strategy

1. Use `time.monotonic()` not `time.time()` — already done
2. Mock `_memory_pressure_ok()` for predictable tests
3. Seed random for entropy/jitter tests: `random.seed(42)`
4. Isolate network with `responses` library or fixtures
5. Mock time.monotonic() for circuit breaker tests

---

## 9. Proposed Next Sprint Plan

### Priority 1 — Critical (Fix Before Production)
1. **Lazy import conversion**: autonomous_orchestrator.py lines 87-236 → lazy pattern
2. **Async blocking fix**: Replace `time.sleep()` with `await asyncio.sleep()` in 3 files

### Priority 2 — High (Memory/Stability)
3. **MLX cache clearing**: Add `mx.clear_cache()` to 44 MLX files
4. **structure_map file_cache bound**: Add LRU maxsize to tools/content_miner.py:1184

### Priority 3 — Medium (Testing)
5. **Add tests**: 8+ untested critical modules
6. **M1-specific tests**: wired_memory, circuit breaker, non-Darwin paths

### Priority 4 — Low (Cleanup)
7. **Delete backup files**: 4 files (~3MB)
8. **Address TODOs**: Create tech debt tracking issue
9. **Consolidate duplicates**: URL parsing, content extraction, caching

---

*Report generated: 2026-03-06 | Sources: WIRING_AUDIT_REPORT.md, PERF_M1_AUDIT.md, Guardrails feed*
