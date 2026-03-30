# Sprint 8BL — Surgical Integration Map Audit

## 1. Executive Summary
- Audit only, no production edits.
- GOAL: exact integration seams, not new-file-first thinking.
- KEY FINDING: ALL 4 gather() calls in AO already have return_exceptions=True — async sanitation for gather is DONE.

## 2. AO Control-Plane Hotspots (line-level)

| Pattern | Count | Status |
|---|---|---|
| shutdown_all defs | 2 | ⚠️ CONFLICT: lines 12204 and 22198 |
| asyncio.gather (ALL have return_exceptions) | 4 | ✅ ALREADY SAFE |
| Path.home() | 20 | ⚠️ UNSAFE: should use paths.py |
| .hledac hardcoded | 21 | ⚠️ DUPLICITY: not via paths.py |

## 3. Critical Lifecycle Caller Map

### initialize — 158 call sites
- `enhanced_research.py` :: `_get_archive_resurrector@404` → `initialize@410`
- `enhanced_research.py` :: `_get_stealth_scraper@425` → `initialize@431`
- `enhanced_research.py` :: `_get_data_leak_hunter@446` → `initialize@452`
- `autonomous_orchestrator.py` :: `_dlh_check_batch@6084` → `initialize@6107`
- `autonomous_orchestrator.py` :: `initialize@11419` → `initialize@11530`
- `autonomous_orchestrator.py` :: `initialize@11419` → `initialize@11531`
- `autonomous_orchestrator.py` :: `initialize@11419` → `initialize@11533`
- `autonomous_orchestrator.py` :: `initialize@11419` → `initialize@11534`
- `autonomous_orchestrator.py` :: `initialize@11419` → `initialize@11535`
- `autonomous_orchestrator.py` :: `initialize@11419` → `initialize@11536`
- `autonomous_orchestrator.py` :: `analyze_comprehensive@15633` → `initialize@15653`
- `autonomous_orchestrator.py` :: `analyze_comprehensive@15633` → `initialize@15656`
- `autonomous_orchestrator.py` :: `research_autonomous@15826` → `initialize@15838`
- `autonomous_orchestrator.py` :: `research_autonomous@15826` → `initialize@15841`
- `autonomous_orchestrator.py` :: `transition_to_synthesis@18356` → `initialize@18381`
- ... +143 more

### shutdown_all — 5 call sites
- `autonomous_orchestrator.py` :: `cleanup@11762` → `shutdown_all@11860`
- `autonomous_orchestrator.py` :: `shutdown_all@12204` → `shutdown_all@12219`
- `layers/layer_manager.py` :: `cleanup@894` → `shutdown_all@896`
- `tests/test_autonomous_orchestrator.py` :: `test_shutdown_all@16633` → `shutdown_all@16662`
- `tests/test_autonomous_orchestrator.py` :: `test_monitor_cleanup@18928` → `shutdown_all@18937`

### research — 22 call sites
- `enhanced_research.py` :: `stealth_research@1519` → `research@1555`
- `enhanced_research.py` :: `enhanced_research@2193` → `research@2218`
- `autonomous_orchestrator.py` :: `extreme_research@15858` → `research@15887`
- `autonomous_orchestrator.py` :: `_execute_standard_research_fallback@16090` → `research@16108`
- `autonomous_orchestrator.py` :: `autonomous_research@30298` → `research@30327`
- `orchestrator_integration.py` :: `research_with_meta_reasoning@457` → `research@469`
- `orchestrator_integration.py` :: `research_with_meta_reasoning@457` → `research@485`
- `orchestrator_integration.py` :: `research_with_meta_reasoning@457` → `research@499`
- `orchestrator_integration.py` :: `research_with_swarm@512` → `research@524`
- `orchestrator_integration.py` :: `research_with_validation@606` → `research@617`
- `orchestrator_integration.py` :: `research_with_validation@606` → `research@640`
- `orchestrator_integration.py` :: `integrated_research@690` → `research@732`
- `tests/test_sprint43.py` :: `test_memory_leak@219` → `research@233`
- `tests/test_sprint43.py` :: `test_stress_no_exceptions@243` → `research@256`
- `tests/tool_schema_validation.py` :: `test_valid_plan_executes@121` → `research@123`
- ... +7 more

### async_initialize — 9 call sites
- `tests/test_sprint8as_duckdb_async/test_duckdb_async_safety.py` :: `test_async_calls_preserve_memory_mode_state@132` → `async_initialize@138`
- `tests/test_sprint8as_duckdb_async/test_duckdb_async_safety.py` :: `test_async_insert_does_not_block_event_loop@167` → `async_initialize@174`
- `tests/test_sprint8as_duckdb_async/test_duckdb_async_safety.py` :: `test_batch_chunks_large_input@210` → `async_initialize@217`
- `tests/test_sprint8as_duckdb_async/test_duckdb_async_safety.py` :: `test_batch_empty_list_returns_zero@244` → `async_initialize@247`
- `tests/test_sprint8as_duckdb_async/test_duckdb_async_safety.py` :: `test_aclose_is_idempotent@263` → `async_initialize@266`
- `tests/test_sprint8as_duckdb_async/test_duckdb_async_safety.py` :: `test_no_op_after_aclose@273` → `async_initialize@276`
- `tests/test_sprint8as_duckdb_async/test_duckdb_async_safety.py` :: `test_healthcheck_returns_true_when_healthy@340` → `async_initialize@342`
- `tests/test_sprint8as_duckdb_async/test_duckdb_async_safety.py` :: `test_healthcheck_returns_false_when_closed@347` → `async_initialize@349`
- `knowledge/analytics_hook.py` :: `_worker@157` → `async_initialize@171`


## 4. Surgical Patch Map (v12 items)

| PLAN_ITEM | READYNESS | BEST_EXISTING_FUNCTION | BEST_FILE | PRE-REFACTOR | TOUCH_AO | NOTES |
|---|---|---|---|---|---|---|
| unified_path_management | PARTIAL | paths.py constants | paths.py | Audit 20× Path.home() in AO | YES-minimal | AO __init__ assigns 20× Path.home() directly; refactor to import from paths.py |
| lmdb_stale_lock_auto_recovery | READY | cleanup_stale_lmdb_locks() | paths.py | None | NO | Fully implemented; paths.py:208 |
| session_management_unification | PARTIAL | _fetch_with_curl / _build_session | coordinators/fetch_coordinator.py | Extract _session_factory() helper | NO | 4× ClientSession(); 1 helper needed |
| async_sanitation | READY | gather() calls | autonomous_orchestrator.py | None — all already safe | NO | All 4 gather() have return_exceptions=True; time.sleep=0 in AO |
| duckdb_persistent_path_hardening | READY | DuckDBShadowStore._resolve_paths() | knowledge/duckdb_store.py | None | NO | Already imports from paths.py line 309 |
| bounded_queue_backpressure | READY | asyncio.Queue(maxsize=...) | autonomous_orchestrator.py | None | NO | Already maxsize=20/100/500 |
| uvloop_activation | MISSING | uvloop.install() | __main__.py or autonomous_orchestrator.py | Find single entrypoint | MAYBE | 0 uvloop install calls found; needs __main__ or bootstrap |
| url_dedup_frontier | READY | RotatingBloomFilter + _processed_urls | coordinators/fetch_coordinator.py | None | NO | Already implemented via url_dedup.py |
| graceful_shutdown_order | CONFLICT | shutdown_all() | autonomous_orchestrator.py | UNIFY 2× shutdown_all at lines 12204 and 22198 | YES | Two separate implementations; must merge before v12 |
| memory_pressure_reactor | READY | _autonomy_monitor_task + _check_emergency_brake | autonomous_orchestrator.py | None | NO | EMA monitoring, debounce, RSS thresholds already present |
| thermal_monitor | PARTIAL | _autonomy_monitor_task | autonomous_orchestrator.py | Extract thermal logic from monitor loop | NO | No dedicated thermal.py; add to utils/ not macos/ |
| mlx_memory_manager | READY | format_mlx_memory_snapshot + configure_mlx_limits | brain/hermes3_engine.py | None | NO | Already in hermes3_engine.py |
| kv_cache_manager | PARTIAL | _compress_kv_cache + _get_prefix_cache | brain/hermes3_engine.py | None | NO | Already exists; verify integration with model_manager |
| ane_embedder_integration | PARTIAL | get_embedder() + can_use_ane() | brain/ane_embedder.py | Verify ANE availability detection | NO | brain/ane_embedder.py exists 3443B; integration via model_manager |
| hermes_lazy_loading | READY | ensure_loaded() + unload() | brain/hermes3_engine.py | None | NO | Lazy loading via mlx_lm.generate with lazy model loading |
| fetch_transport_routing | READY | SocksConnector + curl_cffi | coordinators/fetch_coordinator.py | None | NO | Already supports curl_cffi + aiohttp + socks5 |
| dns_privacy | READY | rdns=True in tor_transport | transport/tor_transport.py | None | NO | tor_transport.py line 555: rdns=True |

## 5. DO NOT GROW List (≥1200 LOC within project)

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
- `forensics/metadata_extractor.py`: 1795 LOC
- `benchmarks/run_sprint82j_benchmark.py`: 1782 LOC
- `coordinators/security_coordinator.py`: 1690 LOC
- `utils/execution_optimizer.py`: 1628 LOC
- `knowledge/rag_engine.py`: 1576 LOC

## 6. 10 Safest Integration Points

1. `paths.py` — cleanup_stale_lmdb_locks, cleanup_stale_sockets, RAMDISK path constants
2. `coordinators/fetch_coordinator.py` — SOCKS connector, curl_cffi seam, ClientSession factory
3. `transport/tor_transport.py` — Tor transport, rdns=True DNS privacy
4. `knowledge/duckdb_store.py` — DuckDBShadowStore._resolve_paths() — already uses paths.py
5. `brain/hermes3_engine.py` — format_mlx_memory_snapshot, configure_mlx_limits, KV cache methods
6. `evidence_log.py` — asyncio.Queue(maxsize=500), bounded ring buffer
7. `utils/mlx_memory.py` — MLX memory helpers (7490 bytes — small, focused)
8. `brain/ane_embedder.py` — get_embedder, can_use_ane — 3443 bytes, focused
9. `coordinators/fetch_coordinator.py (url_dedup)` — RotatingBloomFilter integration
10. `autonomous_orchestrator.py (_autonomy_monitor_task)` — Memory reactor — already bounded with EMA/debounce

## 7. 10 Most Dangerous Places to Add Code

1. `autonomous_orchestrator.py` — 30558 LOC monolith — 20× Path.home(), 2× shutdown_all() CONFLICT
2. `knowledge/persistent_layer.py` — 3575 LOC — already near limit, high coupling
3. `coordinators/memory_coordinator.py` — 2776 LOC — complex memory management, avoid new features here
4. `knowledge/atomic_storage.py` — 2742 LOC — entity storage, already at capacity
5. `layers/stealth_layer.py` — 2662 LOC — layered architecture, risk of circular deps
6. `intelligence/stealth_crawler.py` — 2637 LOC — stealth/session management hub
7. `knowledge/graph_rag.py` — 2549 LOC — graph operations, avoid expanding
8. `brain/hypothesis_engine.py` — 2516 LOC — inference engine, already complex
9. `brain/inference_engine.py` — 2370 LOC — abductive reasoning, risk of feature creep
10. `intelligence/relationship_discovery.py` — 2279 LOC — igraph-based, already at capacity

## 8. Items That Should Integrate Into Existing Functions (Not New Modules)

- unified_path_management → extend paths.py, don't create new path_manager.py
- duckdb_persistent_path_hardening → DuckDBShadowStore._resolve_paths() already handles this
- bounded_queue_backpressure → asyncio.Queue(maxsize=...) already used everywhere
- async_sanitation → gather() already has return_exceptions; time.sleep=0 in AO
- mlx_memory_manager → brain/hermes3_engine.py functions already exist
- hermes_lazy_loading → ensure_loaded()/unload() already in hermes3_engine.py
- fetch_transport_routing → existing SOCKS connector in fetch_coordinator.py
- dns_privacy → tor_transport.py already has rdns=True
- ane_embedder_integration → brain/ane_embedder.py already exists

## 9. Items That Truly Require NEW Files

- uvloop_activation — needs __main__.py entrypoint or bootstrap.py (no existing entrypoint)
- thermal_monitor — new utils/thermal.py (macos/ doesn't exist; utils/ is correct home)
- graceful_shutdown_order — MUST refactor existing shutdown_all() before adding new shutdown logic

## 10. Pre-Implementation Requirements (Must-Fix Before v12 Sprinty)

- [CRITICAL] Unify 2× shutdown_all() in autonomous_orchestrator.py (lines 12204 vs 22198) — CONFLICT
- [CRITICAL] Refactor 20× Path.home()/.hledac in AO to import from paths.py — PARTIAL
- [HIGH] Find/add __main__.py entrypoint for uvloop.install() placement — MISSING
- [HIGH] Extract thermal monitoring from _autonomy_monitor_task into utils/thermal.py — PARTIAL
- [MEDIUM] Extract _session_factory() helper in fetch_coordinator.py from 4× ClientSession — PARTIAL
