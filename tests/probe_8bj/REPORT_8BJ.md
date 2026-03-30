# Sprint 8BJ — Runtime / Infra / OPSEC Readiness Audit

## 1. Executive Summary
- Analytický sprint — žádné produkční editace
- Cíl: posoudit připravenost na Ghost Prime v12 bez duplikace nebo spaghetti kódu
- 11 226 Python souborů skenováno (vč. venv), cca 500+ uvnitř hledac/universal

## 2. Co už existuje (overlap_map)
- **path_management**: přítomno v 43 souborech
- **rate_limiting**: přítomno v 285 souborech
- **frontier**: přítomno v 111 souborech
- **session_factory**: přítomno v 46 souborech
- **shutdown**: přítomno v 69 souborech
- **memory_pressure**: přítomno v 71 souborech

## 3. High-risk plan assumptions — ověření proti realitě

| Assumption | Status | Detail |
|---|---|---|
| paths.py je single source of truth | **PARTIAL** | paths.py je SATĚ autorita pro RAMDISK/DB/LMDB/EVIDENCE/KEYS/TOR/NYM/RUNS/SOCKETS/CACHE, ale AO má ještě 20+ `Path.home() / '.hledac'` inline |
| LMDB stale-lock recovery existuje | **READY** | paths.py: `cleanup_stale_lmdb_locks()` + `cleanup_stale_sockets()` plně implementováno |
| Session lifecycle centralizován | **PARTIAL** | fetch_coordinator.py: 4× `aiohttp.ClientSession()`, transport/tor_transport.py samostatně, chybí jednotná session factory |
| Queue backpressure přítomno | **READY** | asyncio.Queue s maxsize=20/100/500 všude |
| Shutdown ordering encoded | **PARTIAL** | shutdown_all() existuje 2× (AO 12204 + 22198), volá research_mgr + model_manager + metadata_cache + MLX cache |
| UVLoop entrypoint | **MISSING** | 0 explicitních uvloop.Install() volání |
| DNS privacy (rdns) | **READY** | tor_transport.py: `rdns=True` při SOCKS connector |

## 4. Duplication Matrix (top 5)
### path_management (43 files)
- `autonomous_orchestrator.py`
- `paths.py`
- `coordinators/fetch_coordinator.py`
- `tools/document_metadata_extractor.py`
- `tools/source_bandit.py`
- `intelligence/document_intelligence.py`
- `dht/local_graph.py`
- `network/jarm_fingerprinter.py`
- `network/tor_manager.py`
- `network/ct_log_scanner.py`
- ... +33 more
### rate_limiting (285 files)
- `captcha_solver.py`
- `enhanced_research.py`
- `autonomous_orchestrator.py`
- `config.py`
- `paths.py`
- `model_lifecycle.py`
- `run_comprehensive_tests.py`
- `tool_registry.py`
- `deep_probe.py`
- `__init__.py`
- ... +275 more
### frontier (111 files)
- `enhanced_research.py`
- `autonomous_orchestrator.py`
- `deep_probe.py`
- `metrics_registry.py`
- `evidence_log.py`
- `types.py`
- `capabilities.py`
- `autonomous_analyzer.py`
- `smoke_runner.py`
- `research/parallel_scheduler.py`
- ... +101 more
### session_factory (46 files)
- `autonomous_orchestrator.py`
- `deep_probe.py`
- `orchestrator_integration.py`
- `coordinators/security_coordinator.py`
- `coordinators/fetch_coordinator.py`
- `tools/paywall.py`
- `tools/deep_research_sources.py`
- `tools/darknet.py`
- `tools/searxng_client.py`
- `transport/tor_transport.py`
- ... +36 more
### shutdown (69 files)
- `autonomous_orchestrator.py`
- `paths.py`
- `run_comprehensive_tests.py`
- `research/parallel_scheduler.py`
- `coordinators/claims_coordinator.py`
- `coordinators/security_coordinator.py`
- `coordinators/graph_coordinator.py`
- `coordinators/fetch_coordinator.py`
- `coordinators/performance_coordinator.py`
- `coordinators/research_coordinator.py`
- ... +59 more
### memory_pressure (71 files)
- `captcha_solver.py`
- `autonomous_orchestrator.py`
- `config.py`
- `model_lifecycle.py`
- `metrics_registry.py`
- `types.py`
- `capabilities.py`
- `tot_integration.py`
- `coordinators/memory_coordinator.py`
- `coordinators/research_optimizer.py`
- ... +61 more

## 5. Minimal-Edit Integration Map
### 0_paths_unification
- ✅ `paths.py` (file)
- ✅ `autonomous_orchestrator.py` (file)
- ✅ `evidence_log.py` (file)
### 0_lmdb_recovery
- ✅ `autonomous_orchestrator.py` (file)
- ❌ `knowledge/lmdb_kv.py` (missing)
### 0_session_mgmt
- ✅ `coordinators/fetch_coordinator.py` (file)
- ✅ `transport/tor_transport.py` (file)
### 0_async_sanitation
- ✅ `autonomous_orchestrator.py` (file)
- ✅ `coordinators/fetch_coordinator.py` (file)
### 0_uvloop_entrypoint
- ✅ `autonomous_orchestrator.py` (file)
### 2_2_memory_pressure_reactor_candidate_points
- ✅ `autonomous_orchestrator.py` (file)
- ✅ `utils/` (dir)
- ❌ `macos/` (missing)
### 2_3_thermal_monitor_candidate_points
- ✅ `autonomous_orchestrator.py` (file)
- ✅ `utils/` (dir)
- ❌ `macos/` (missing)
### 2_9_graceful_shutdown_candidate_points
- ✅ `autonomous_orchestrator.py` (file)
- ❌ `opsec/` (missing)
- ✅ `security/` (dir)
### 2_14_transport_routing_candidate_points
- ✅ `coordinators/fetch_coordinator.py` (file)
- ✅ `transport/` (dir)
### 2_15_dns_privacy_candidate_points
- ✅ `transport/` (dir)
- ✅ `utils/` (dir)
- ❌ `opsec/` (missing)

## 6. Hidden Debt / Red Flags

### CRITICAL
1. **paths.py vs autonomous_orchestrator.py Path duplicity**: AO má 20+ `Path.home() / '.hledac'` inline, které nejdou přes paths.py autoritu. Ne kritická chyba, ale při přidání nové složky do paths.py se AO nedozví.
2. **2× shutdown_all() v AO**: shutdown_all() na řádku 12204 (model_mgr + metadata + MLX cache) a 22198 (SearXNG). Jsou to různé třídy? Zdá se že AO má 2 různé shutdown implementace — možná copy/paste residue.
3. **DuckDBShadowStore importuje z paths.py inline** (`from hledac.universal.paths import ...`) na řádku 309 — to je správné, žádná duplicita.

### MODERATE
4. **`time.sleep()` v async kontextu** (151 hitů v async_bugs): V async kódu je to špatně, ale některé usage můžou být v sync pomocných funkcích. Nutné ruční auditu každého případu.
5. **`gather()` bez `return_exceptions=True`** (151 hitů): Potenciál silent failure při paralelních operacích. Nutný audit site-by-site.
6. **uvloop: pouze 10 hitů**: 0 explicitních uvloop install, 0 runner. Pokud se má uvloop nasadit, je potřeba ho explicitně nainstalovat v __main__ entrypointu.

### LOW
7. **`setproctitle` pouze 4×**: Prozrazuje název procesu, ale nikde není vidět aktivní maskování process name.
8. **`macos/` dir neexistuje**: memory pressure a thermal monitoring jsou v autonomous_orchestrator.py a utils/. Nová složka by nebyla integrační bod — lepší je rozšířit utils/
9. **`opsec/` dir neexistuje**: OPSEC funkce jsou roztroušené v transport/, security/, stealth/. Žádný centralizovaný OPSEC modul.

## 7. Recommended Implementation Order

**Fáze 0 — Path/Storage Foundation** (před jakýmkoliv v12)
1. `paths.py` — ✅ SATĚ IMPLEMENTOVÁNO (Sprint 8AJ)
2. AO: odstranit duplicitní `Path.home() / '.hledac'` inline — PARTIAL (kontrola 20+ míst)
3. `cleanup_stale_lmdb_locks()` + `cleanup_stale_sockets()` — ✅ IMPLEMENTOVÁNO v paths.py

**Fáze 1 — Async Sanitation**
4. Audit `gather()` bez `return_exceptions=True` — ruční site-by-site
5. Nahradit `time.sleep()` v async kontextu za `asyncio.sleep()` — 151 hitů, nutný audit

**Fáze 2 — Shutdown & Resource**
6. Unifikovat 2× shutdown_all() v AO — 12204 vs 22198 — CONFLICT
7. Přidat `uvloop.install()` do `__main__` entrypointu — MISSING
8. Session factory v fetch_coordinator — PARTIAL (4× ClientSession)

**Fáze 3 — OPSEC Hardening**
9. `setproctitle` — není aktivně používán k maskování
10. DNS privacy — ✅ `rdns=True` v tor_transport již existuje

## 8. PLAN_ITEM Readiness Table

| PLAN_ITEM | READINESS | BEST INTEGRATION POINT | EXISTING SIMILAR | REQUIRED_FIXES | DUPLICATION_RISK | NOTES |
|---|---|---|---|---|---|---|
| 0_paths_unification | **PARTIAL** | paths.py | paths.py má vše, AO má duplicity | Audit 20+ Path.home() v AO | NÍZKÝ | paths.py je správně single source |
| 0_lmdb_recovery | **READY** | paths.py | cleanup_stale_lmdb_locks() | Žádné | ŽÁDNÝ | Plně implementováno |
| 0_session_mgmt | **PARTIAL** | coordinators/fetch_coordinator.py | aiohttp ClientSession | Unifikovat session factory | STŘEDNÍ | 4× ClientSession v jednom souboru |
| 0_async_sanitation | **PARTIAL** | autonomous_orchestrator.py | asyncio.sleep/Queue | Audit 151 time.sleep + gather sites | NÍZKÝ | Nutný ruční audit |
| 0_uvloop_entrypoint | **MISSING** | autonomous_orchestrator.py __main__ | Žádné | Přidat uvloop.install() | ŽÁDNÝ | Nejvýše 1 entrypoint |
| 2_2_memory_pressure_reactor | **READY** | autonomous_orchestrator.py | _autonomy_monitor_task | Žádné | ŽÁDNÝ | EMA monitoring, debounce |
| 2_3_thermal_monitor | **PARTIAL** | utils/ | Žádné | Nutná nová thermal.py v utils/ | ŽÁDNÝ | Chybí macos/ dir, existuje v AO |
| 2_9_graceful_shutdown | **PARTIAL** | autonomous_orchestrator.py | 2× shutdown_all() | Unifikovat 2× shutdown_all | STŘEDNÍ | CONFLICT: 2 různé implementace |
| 2_14_transport_routing | **READY** | coordinators/fetch_coordinator.py | SOCKS connector | Žádné | ŽÁDNÝ | curl_cffi + aiohttp + socks5 rdns |
| 2_15_dns_privacy | **READY** | transport/tor_transport.py | rdns=True | Žádné | ŽÁDNÝ | Tor transport plně implementován |
