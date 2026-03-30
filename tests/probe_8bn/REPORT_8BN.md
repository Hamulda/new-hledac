# Sprint 8BN — Bootstrap / Lifecycle / Shutdown Truth Audit

## 0. Key Findings (ONE-TIME TRUTHS)

| Finding | Truth | Implication |
|---|---|---|
| `__main__.py` | **DOES NOT EXIST** | No explicit entrypoint; uvloop cannot be installed via conventional means |
| `config/paths.py` | **DOES NOT EXIST** | Real path module is `paths.py` (root), not `config/paths.py` |
| `shutdown_all` at 12204 | In `FullyAutonomousOrchestrator` (class@3103) | ✅ PRIMARY shutdown — closes research_mgr, model_mgr, metadata_cache, MLX cache, monitor, source_bandit |
| `shutdown_all` at 22198 | In `_LRUDict` helper class@21933 | ⚠️ Different class, only closes SearXNG client — NOT a conflict, just a helper |
| `cleanup_stale_lmdb_locks` call | `initialize@11419` → `cleanup_stale_lmdb_locks@11495` | ✅ Correct: LMDB cleanup happens at BOOT in initialize() |
| `cleanup_stale_sockets` call | `initialize@11419` → `cleanup_stale_sockets@11501` | ✅ Correct: socket cleanup happens at BOOT in initialize() |
| `uvloop` | **0 calls found** | MISSING: no uvloop.install() anywhere in project |

## 1. uvloop Activation

| ITEM | READYNESS | SINGLE_SOURCE_OF_TRUTH_FILE | SINGLE_SOURCE_OF_TRUTH_FUNCTION | DUPLICATE_LOCATIONS | PRE-REQ_FIX | TOUCH_AO | NOTES |
|---|---|---|---|---|---|---|---|
| uvloop activation | **MISSING** | N/A — no entrypoint exists | N/A | None | **CREATE** `__main__.py` OR add to existing CLI entry point | YES | `__main__.py` does not exist; must be created first |

**Integration**: Since `__main__.py` does not exist, the project uses some other entry point. Need to find which file is the actual CLI entry (look for `if __name__ == '__main__'` or console_scripts in pyproject.toml). uvloop.install() must be the FIRST line before any async code.

## 2. RAMdisk / Paths Bootstrap

| ITEM | READYNESS | SSOT_FILE | SSOT_FUNCTION | DUP_LOCS | PRE-REQ_FIX | TOUCH_AO | NOTES |
|---|---|---|---|---|---|---|---|
| RAMDISK path authority | **READY** | `paths.py` | Module-level constants (RAMDISK_ROOT, DB_ROOT, LMDB_ROOT, etc.) | None | None | NO | paths.py already has `_ensure_dir()` for all subdirs |
| RAMDISK validation | **READY** | `paths.py` | `_is_active_ramdisk()` | None | None | NO | Validates mount point with st_dev check |
| Paths bootstrap in AO | **READY** | `autonomous_orchestrator.py` | `initialize()` lines 11460-11504 | None | None | NO | Imports from paths.py and calls cleanup functions at boot |

**AO initialize() bootstrap order (confirmed):**
1. MLX metal memory limit set (lines 11422-11433)
2. Lazy module loading — light in parallel, heavy sequential (lines 11441-11450)
3. `from paths import ...` (line 11460)
4. `assert_ramdisk_alive()` (line 11466)
5. FD telemetry + RSS baseline (lines 11469-11477)
6. `cleanup_stale_lmdb_locks(LMDB_ROOT)` (line 11495)
7. `cleanup_stale_sockets(SOCKETS_ROOT)` (line 11501)
8. `atexit.register(cleanup_fallback)` (line ~11509)

## 3. LMDB Stale-Lock Cleanup

| ITEM | READYNESS | SSOT_FILE | SSOT_FUNCTION | DUP_LOCS | PRE-REQ_FIX | TOUCH_AO | NOTES |
|---|---|---|---|---|---|---|---|
| LMDB lock cleanup | **READY** | `paths.py` | `cleanup_stale_lmdb_locks()` lines 208-250 | None | None | NO | Deletes only `lock.mdb`, never `data.mdb` |
| Socket cleanup | **READY** | `paths.py` | `cleanup_stale_sockets()` lines 278-303 | None | None | NO | Probes with connect() before unlink |
| Boot call site | **READY** | `autonomous_orchestrator.py` | `initialize()@11495` and `@11501` | None | None | NO | Called once at boot, results stored in instance vars |

## 4. Session Lifecycle

**Callers of `close()` (1441 total):** Most are on `aiohttp.ClientSession` instances. Session lifecycle is NOT centralized — each component manages its own session.

| ITEM | READYNESS | SSOT_FILE | SSOT_FUNCTION | DUP_LOCS | PRE-REQ_FIX | TOUCH_AO | NOTES |
|---|---|---|---|---|---|---|---|
| Session management | **PARTIAL** | `coordinators/fetch_coordinator.py` | `_build_session()` / `_fetch_with_curl()` | 4× ClientSession in fetch_coordinator; tor_transport separately | Extract `_session_factory()` helper | NO | Tor transport has its own session at line 555-556 |
| Tor session | **READY** | `transport/tor_transport.py` | `TorTransport.start()` line 51-97 | None | None | NO | aiohttp_socks.SocksConnector with rdns=True |

## 5. Graceful Shutdown Order

**Two `shutdown_all()` definitions — SAME NAME, different classes:**

| Location | Class | Lines | What it closes |
|---|---|---|---|
| `shutdown_all@12204` | `FullyAutonomousOrchestrator` | 12204-12263 | research_mgr, model_manager, metadata_cache, MLX cache, autonomy_monitor, source_bandit |
| `shutdown_all@22198` | `_LRUDict` (helper) | 22198-22209 | SearXNG client only |

**No CONFLICT** — different classes. The `_LRUDict.shutdown_all()` only closes SearXNG.
**Primary shutdown sequence** (lines 12204-12263):
1. `_research_mgr.shutdown_all()`
2. `model_manager.release_all()`
3. `metadata_cache.close()`
4. `mx.clear_cache()`
5. Cancel `_autonomy_monitor_task`
6. `_source_bandit.close()`

**Called from:** `cleanup()@11762 → shutdown_all@11860` (via `shutdown_all@12204`)

## 6. Memory Pressure Hook

| ITEM | READYNESS | SSOT_FILE | SSOT_FUNCTION | DUP_LOCS | PRE-REQ_FIX | TOUCH_AO | NOTES |
|---|---|---|---|---|---|---|---|
| Memory pressure reactor | **READY** | `autonomous_orchestrator.py` | `_autonomy_monitor_task` + `_check_emergency_brake` | None | None | NO | EMA monitoring, debounce, RSS thresholds 70%/80%/60% |
| MLX memory helpers | **READY** | `utils/mlx_memory.py` | `get_mlx_memory_pressure()` | None | None | NO | Returns pressure enum; called by hermes3_engine |
| MLX cache lifecycle | **READY** | `utils/mlx_memory.py` + `brain/hermes3_engine.py` | `clear_mlx_cache()`, `unload()` | None | None | NO | clear_mlx_cache called from _apply_profile and _aggressive_gc |

## 7. Thermal Hook

| ITEM | READYNESS | SSOT_FILE | SSOT_FUNCTION | DUP_LOCS | PRE-REQ_FIX | TOUCH_AO | NOTES |
|---|---|---|---|---|---|---|---|
| Thermal monitoring | **PARTIAL** | `autonomous_orchestrator.py` | `_autonomy_monitor_task` (no thermal-specific logic) | None | Add thermal sensor reading to monitor loop or create `utils/thermal.py` | NO | `ThermalState` class exists at line 275 but is minimal |

## 8. Transport Bootstrap

| ITEM | READYNESS | SSOT_FILE | SSOT_FUNCTION | DUP_LOCS | PRE-REQ_FIX | TOUCH_AO | NOTES |
|---|---|---|---|---|---|---|---|
| Tor transport start | **READY** | `transport/tor_transport.py` | `TorTransport.start()` line 51-97 | None | None | NO | Creates SOCKS5 connector with rdns=True; registers handler |
| Fetch coordinator session | **PARTIAL** | `coordinators/fetch_coordinator.py` | `_build_session()` / `init_session_manager()` | 4× ClientSession | Extract `_session_factory()` | NO | `init_session_manager` at line 401-410 |

## 9. Evidence Flush Lifecycle

| ITEM | READYNESS | SSOT_FILE | SSOT_FUNCTION | DUP_LOCS | PRE-REQ_FIX | TOUCH_AO | NOTES |
|---|---|---|---|---|---|---|---|
| EvidenceLog async init | **READY** | `evidence_log.py` | `EvidenceLog.initialize()` line 270-283 | None | None | NO | Initializes SQLite WAL, runs migrations |
| EvidenceLog flush worker | **READY** | `evidence_log.py` | `_flush_worker()` line 343-376 | None | None | NO | asyncio.Queue(maxsize=500), bounded ring buffer |
| EvidenceLog sync close | **READY** | `evidence_log.py` | `__del__` line 262-268 + `close()` | None | None | NO | aclose() is idempotent; called on GC or explicit close |

## 10. MLX Cache Lifecycle

| ITEM | READYNESS | SSOT_FILE | SSOT_FUNCTION | DUP_LOCS | PRE-REQ_FIX | TOUCH_AO | NOTES |
|---|---|---|---|---|---|---|---|
| MLX cache clear | **READY** | `utils/mlx_memory.py` | `clear_mlx_cache()` line 59-85 | None | None | NO | Called from _apply_profile and _aggressive_gc |
| MLX memory snapshot | **READY** | `utils/mlx_memory.py` | `format_mlx_memory_snapshot()` | hermes3_engine calls it | None | NO | Used in _run_sustain_inference |
| MLX limits config | **READY** | `utils/mlx_memory.py` | `configure_mlx_limits()` | hermes3_engine calls it | None | NO | Used in _run_sustain_inference |

## 11. Single Source of Truth Summary Table

| Area | SSOT File | SSOT Function | Readiness |
|---|---|---|---|
| Paths / RAMDISK | `paths.py` | Module constants + `_is_active_ramdisk()` | ✅ READY |
| LMDB/Socket cleanup | `paths.py` | `cleanup_stale_lmdb_locks()`, `cleanup_stale_sockets()` | ✅ READY |
| Memory pressure | `autonomous_orchestrator.py` | `_autonomy_monitor_task` | ✅ READY |
| MLX cache | `utils/mlx_memory.py` | `clear_mlx_cache()`, `configure_mlx_limits()` | ✅ READY |
| Evidence flush | `evidence_log.py` | `EvidenceLog._flush_worker()` | ✅ READY |
| Transport (Tor) | `transport/tor_transport.py` | `TorTransport.start()` | ✅ READY |
| Session mgmt | `coordinators/fetch_coordinator.py` | `_build_session()` | ⚠️ PARTIAL — 4× ClientSession |
| Thermal | `autonomous_orchestrator.py` | `_autonomy_monitor_task` | ⚠️ PARTIAL — no thermal-specific logic |
| uvloop | **NONE** | **MISSING** | ❌ MISSING — no __main__.py |

## 12. DO NOT GROW Files

These files are already at or near capacity — v12 features must NOT be added here:

- `autonomous_orchestrator.py`: 30558 LOC
- `tests/test_autonomous_orchestrator.py`: 22154 LOC
- `knowledge/persistent_layer.py`: 3575 LOC
- `coordinators/memory_coordinator.py`: 2776 LOC
- `knowledge/atomic_storage.py`: 2742 LOC
- `layers/stealth_layer.py`: 2662 LOC
- `intelligence/stealth_crawler.py`: 2637 LOC
- `knowledge/graph_rag.py`: 2549 LOC
- `brain/hypothesis_engine.py`: 2516 LOC
- `brain/inference_engine.py`: 2370 LOC
- `enhanced_research.py`: 2306 LOC
- `intelligence/relationship_discovery.py`: 2279 LOC
- `intelligence/document_intelligence.py`: 2110 LOC
- `layers/coordination_layer.py`: 2081 LOC
- `intelligence/pattern_mining.py`: 2020 LOC

## 13. Pre-Implementation Requirements (Before Any v12 Feature Sprint)

| Priority | Requirement | Status |
|---|---|---|
| **[CRITICAL]** | Find actual CLI entry point (`if __name__ == '__main__'` or console_scripts) — needed for uvloop.install() placement | MISSING |
| **[CRITICAL]** | Create `__main__.py` if no entry point found — uvloop MUST be installed before any async code | MISSING |
| **[HIGH]** | Extract `_session_factory()` in fetch_coordinator from 4× ClientSession() | PARTIAL |
| **[HIGH]** | Add thermal monitoring to `_autonomy_monitor_task` or create `utils/thermal.py` | PARTIAL |
| **[MEDIUM]** | Refactor 20× `Path.home()/.hledac` in AO to use paths.py imports | PARTIAL |

## 14. Mandatory Conclusions

**Q1: Jediný správný entrypoint pro uvloop?**
→ `__main__.py` NEEXISTUJE. Musí být vytvořen. Nejprve najít existující CLI entry (hledat `if __name__ == '__main__'` v projektu).

**Q2: Jediný správný entrypoint pro RAMdisk/paths bootstrap?**
→ `autonomous_orchestrator.py` `initialize()` line 11419-11510. Importuje z `paths.py`, volá `assert_ramdisk_alive()`, `cleanup_stale_lmdb_locks()`, `cleanup_stale_sockets()` v DOKONALÉM pořadí.

**Q3: Jediný správný entrypoint pro stale-lock cleanup?**
→ `paths.py` funkce `cleanup_stale_lmdb_locks()` a `cleanup_stale_sockets()`. Volány z `AO.initialize()@11495` a `@11501`.

**Q4: Které shutdown_all je kanonické a které je residue?**
→ `shutdown_all@12204` v `FullyAutonomousOrchestrator` je **kanonické** (complete). `shutdown_all@22198` v `_LRUDict` je **NE-konfliktní helper** — jen zavírá SearXNG. Není to residue, je to legitimní helper metoda jiné třídy.

**Q5: Které existující funkce se musí sjednotit dřív než začne v12?**
1. Session factory: 4× `ClientSession()` v fetch_coordinator → 1× `_session_factory()` helper
2. Thermal monitoring: žádná dedicated thermal.py → přidat do `utils/thermal.py` nebo rozšířit `_autonomy_monitor_task`
3. `__main__.py`: neexistuje → vytvořit pro uvloop.install()

**Q6: Které soubory jsou DO NOT GROW?**
→ `autonomous_orchestrator.py` (30558 LOC), `knowledge/persistent_layer.py`, `coordinators/memory_coordinator.py`, `knowledge/atomic_storage.py`, `layers/stealth_layer.py`, `intelligence/stealth_crawler.py`, `knowledge/graph_rag.py`

**Q7: Jaké minimální pre-refaktory jsou nutné?**
1. Najít CLI entry point / vytvořit `__main__.py` pro uvloop
2. Session factory extraction v fetch_coordinator
3. Thermal monitoring integration
4. (Nice-to-have) Refaktorovat Path.home()/.hledac v AO na paths.py imports
