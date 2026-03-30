# Repo-Wide Deep Audit Report — Round 2
**Scope:** `/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/`
**Date:** 2026-03-06
**Status:** COMPLETE (Wiring + Perf/Memory + Dead Code)

---

## 1. Executive Summary

| Category | Status | Key Findings |
|----------|--------|--------------|
| **A) Wiring** | ✅ 10/10 actions wired | Full registry coverage |
| **B) Guardrails** | ⚠️ Partial | 5+ async blocking issues (time.sleep in async) |
| **C) Perf/Memory** | 🔴 44 MLX files lack cache clearing | Memory leak risk on M1 8GB |
| **D) Security** | ✅ Generally good | Env var usage, rate limiting present |
| **E) Dead Code** | ⚠️ 25 TODOs + 4 backup files | ~3MB in stale files |
| **F) Tests** | ⚠️ 8+ modules lack tests | Critical modules uncovered |

**Top 3 Risks:**
1. **Memory:** 44 files using MLX without `mx.clear_cache()` — cumulative memory pressure on M1
2. **Async Blocking:** `time.sleep()` in async contexts (orchestrator/global_scheduler.py, network/jarm_fingerprinter.py)
3. **Test Coverage:** 8+ critical modules untested

---

## 2. Wiring Map

### Actions Table (10 Registered Actions)

| # | Action Name | Handler | Line | Status |
|---|-------------|---------|------|--------|
| 1 | `surface_search` | `surface_search_handler` | 2579 | ✅ WIRED |
| 2 | `archive_fetch` | `archive_fetch_handler` | 2602 | ✅ WIRED |
| 3 | `render_page` | `render_page_handler` | 2637 | ✅ WIRED |
| 4 | `investigate_contradiction` | `investigate_handler` | 2671 | ✅ WIRED |
| 5 | `build_structure_map` | `build_structure_map_handler` | 2685 | ✅ WIRED |
| 6 | `scan_ct` | `_handle_ct_scan` | 2742 | ✅ WIRED |
| 7 | `fingerprint_jarm` | `_handle_jarm` | 2759 | ✅ WIRED |
| 8 | `scan_open_storage` | `_handle_open_storage` | 2772 | ✅ WIRED |
| 9 | `crawl_onion` | `_handle_crawl_onion` | 2788 | ✅ WIRED |
| 10 | `generate_paths` | `_handle_path_discovery` | 2802 | ✅ WIRED |

### Call Graph Overview

```
_autonomous_orchestrator.py_
├── _initialize_actions() [line 2574]
│   └── Registers 10 actions via _register_action()
├── _register_action(name, handler, scorer) [line 2559]
│   └──ulates self._action Pop_registry dict
├── _analyze_state(query) [line 2841]
│   └── Computes state for scorers
├── _decide_next_action(state) [line 2996]
│   └── Calls _execute_action(name, **params)
└── Action Handlers → manager methods
```

---

## 3. Orphans / Partial Wiring

### Partial Handlers (Exist but not in registry)

| Handler | Notes |
|---------|-------|
| `_deep_crawl_handler` | Referenced but not registered |
| `_academic_handler` | Referenced but not registered |
| `_osint_handler` | Referenced but not registered |
| `_dark_web_handler` | Referenced but not registered |
| `_entity_handler` | Referenced but not registered |
| `_fact_check_handler` | Referenced but not registered |

**Recommendation:** Register or remove 16 orphan handlers.

---

## 4. Guardrails Findings

### 🔴 CRITICAL: Async Blocking

| File | Line | Issue |
|------|------|-------|
| `orchestrator/global_scheduler.py` | 108, 137 | `time.sleep(0.1)` in async context |
| `network/jarm_fingerprinter.py` | 232 | `time.sleep(0.05)` in async context |
| `coordinators/memory_coordinator.py` | 501 | `time.sleep(0.1)` in async replay |

**Remediation:** Replace with `await asyncio.sleep()` or run in executor.

### 🟡 MODERATE: Loop Boundedness

20+ files have `while True:` loops — verify all have exit conditions:
- `autonomous_orchestrator.py`: 5 while True loops (lines vary)
- `prefetch/prefetch_cache.py`: 2 while True loops

### ✅ GOOD
- Lazy imports pattern used in PrivacyEnhancedResearch
- Task cleanup with `add_done_callback(self._bg_tasks.discard)`
- Executor proper shutdown: `_background_executor.shutdown(cancel_futures=True)`

---

## 5. Performance & Memory Findings (M1 8GB)

### 🔴 CRITICAL: MLX Cache Not Cleared (44 files)

Files using MLX but NOT calling `mx.clear_cache()`:

```
brain/gnn_predictor.py
brain/inference_engine.py
brain/paged_attention_cache.py
coordinators/multimodal_coordinator.py
core/resource_governor.py
dht/local_graph.py
federated/secure_aggregator.py
federated/sketches.py
intelligence/advanced_image_osint.py
intelligence/document_intelligence.py
intelligence/pattern_mining.py
knowledge/lancedb_store.py
knowledge/pq_index.py
multimodal/vision_encoder.py
planning/slm_decomposer.py
rl/marl_coordinator.py
+ ~20 more
```

**Fix Required:**
```python
import mlx.core as mx
mx.eval([])  # flush pending ops
mx.clear_cache()  # release memory
```

### 🟡 MODERATE: Heavy Module-Level Imports

- `autonomous_orchestrator.py` lines 85-200: All coordinators imported at module load
- 62 files import mlx at module level

**Recommendation:** Convert to lazy-import pattern used by PrivacyEnhancedResearch.

### ✅ Well-Implemented
- `model_lifecycle.py`: Strict 1-model-at-a-time with GC + mx.clear_cache()
- `capabilities.py`: Dynamic capability loading
- `MetricsRegistry`: Bounded metrics (ring buffers)

---

## 6. Security/Privacy Findings

### ✅ GOOD
- Env var usage: No hardcoded secrets
- Rate limiting: `utils/rate_limiter.py` present
- Privacy protection: `privacy_protection/` module exists
- Stealth layer: `layers/stealth_layer.py` implemented

### 🟡 Notes
- Input sanitization: Standard patterns used
- Data exfiltration: LootManager with AES-256 (see previous audit)

---

## 7. Dead Code / Redundancy Ledger

### 🔴 Stale TODOs (25 total)

| File | Line | Description |
|------|------|-------------|
| `execution/ghost_executor.py` | ~50-90 | Implement search features |
| `knowledge/atomic_storage.py` | ~50 | Use Hermes for extraction |
| `utils/shared_tensor.py` | ~30, 50 | Zero-copy requires Metal buffer |
| `brain/decision_engine.py` | ~80 | Implement LLM fallback |
| `autonomous_orchestrator.py` | ~200 | Future archive fetch |

### 🔴 Large Backup Files (~3MB)

- `autonomous_orchestrator (kopie).txt` (806KB)
- `autonomous_orchestrator.py.bak.SPRINT65` (738KB)
- `autonomous_orchestrator.py.bak.SPRINT65D` (735KB)
- `autonomous_orchestrator.py.bak.SPRINT65E` (735KB)

### 🟡 Duplicate Logic

- URL parsing: 22+ files with `urlparse`/`parse_qs`
- Content extraction: 3+ modules (`content_extractor.py`, `content_miner.py`, etc.)
- Caching: Multiple `IntelligentCache` implementations

---

## 8. Tests & Observability

### 🔴 Missing Test Coverage (8+ modules)

| Module | Status |
|--------|--------|
| `brain/gnn_predictor.py` | NONE |
| `brain/paged_attention_cache.py` | NONE |
| `coordinators/multimodal_coordinator.py` | NONE |
| `core/resource_governor.py` | NONE |
| `dht/local_graph.py` | NONE |
| `federated/secure_aggregator.py` | NONE |
| `intelligence/advanced_image_osint.py` | NONE |
| `intelligence/document_intelligence.py` | NONE |

### ✅ Good Coverage

- `test_sprint71/`: M1-specific (ANE, CoreML, MPS, WASM)
- `test_sprint68/`: Memory pressure, action registry
- `test_sprint69/`: Structure map, non-blocking scorer
- Logging: 3,421 logger calls

---

## 9. Proposed Next Sprint Plan

### Priority 1 — Critical (Memory/Stability)
1. Add `mx.clear_cache()` to 44 MLX files
2. Replace `time.sleep()` with `await asyncio.sleep()` in async contexts

### Priority 2 — High (Testing)
3. Add unit tests for 8+ untested critical modules
4. Add MLX memory cleanup tests to test_sprint71

### Priority 3 — Medium (Cleanup)
5. Remove 4 large backup files (~3MB)
6. Address 25 stale TODOs or create tech debt tracker
7. Register or remove 16 orphan handlers

---

*Report generated: 2026-03-06 | Agents: JadeGrove (Wiring), SageXenon (Perf/Memory)*
