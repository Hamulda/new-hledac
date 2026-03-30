# SPRINT 0A FINAL REPORT
## Bootstrap & Sanitation Phase

---

## 1. CO BYLO ZMĚNĚNO

### 1.1 paths.py — SSOT & Bootstrap
- **Přidáno `LIGHTRAG_ROOT`**: Path constant pro LightRAG storage
- **Přidán `_bootstrap_tempfile()`**: Nastavuje `tempfile.tempdir` na RAMDISK_ROOT (fail-open)
- **Přidána `get_lmdb_max_size_mb()`**: Env/config surface pro GHOST_LMDB_MAX_SIZE_MB (default 512MB)

### 1.2 vault_manager.py — Tempfile Sanitization
- **Přidán `_get_tempdir()`**: Lazy getter čtoucí `tempfile.gettempdir()` při volání
- **4× NamedTemporaryFile opraveno**: Všechna volání nyní používají `dir=_get_tempdir()`
- **Zajištěno**: Tempfile temp files jdou na RAMDISK/fallback místo system tmp

### 1.3 osint_frameworks.py — Tempfile Sanitization
- **1× NamedTemporaryFile opraveno**: Přidán `dir=tempfile.gettempdir()`

### 1.4 autonomous_orchestrator.py — Tempfile + BG Tasks
- **mkdtemp opraveno**: `tempfile.mkdtemp(prefix="hledac_seed_", dir=tempfile.gettempdir())`
- **BG tasks lifecycle**: `_bg_tasks` set s `add_done_callback` discard pattern existuje a funguje

### 1.5 global_scheduler.py — Bounded Registries
- **MAX_TASK_REGISTRY = 1000**: Nová konstanta
- **MAX_AFFINITY_ENTRIES = 5000**: Nová konstanta
- **_TASK_REGISTRY**: Změněno z `Dict` na `OrderedDict`
- **_LAST_WORKER_FOR_AFFINITY**: Změněno z `Dict` na `OrderedDict`
- **_bounded_put()**: Nová helper funkce pro FIFO eviction při překročení limitu
- **register_task()**: Nyní volá `_bounded_put()` místo přímého přiřazení
- **Affinity update**: Nyní volá `_bounded_put()` místo přímého přiřazení

### 1.6 key_manager.py — mlock Bootstrap
- **_HAS_MLOCK**: Nová globals flag
- **_try_mlock(buf)**: Nová bootstrap-safe funkce pro mlock key material
- **Fail-open**: Vrací `False` pokud mlock недоступен nebo selže
- **_generate_new_master_key()**: Volá `_try_mlock()` na key buffer před uložením

---

## 2. ZMĚNĚNÉ SOUBORY

| Soubor | Změny |
|--------|--------|
| `paths.py` | +LIGHTRAG_ROOT, +_bootstrap_tempfile(), +get_lmdb_max_size_mb() |
| `vault_manager.py` | +_get_tempdir(), 4× NamedTemporaryFile s dir= |
| `osint_frameworks.py` | 1× NamedTemporaryFile s dir= |
| `autonomous_orchestrator.py` | mkdtemp s dir=, bg_tasks pattern existuje |
| `global_scheduler.py` | Bounded OrderedDict registry + _bounded_put helper |
| `key_manager.py` | +_try_mlock() + mlock volání v _generate_new_master_key |

---

## 3. VZNIKLÉ TESTY

**Složka**: `tests/probe_0a/`

| Test | Invariant |
|------|-----------|
| `test_paths_ssot_bootstrap` | tempfile.tempdir wiring to RAMDISK |
| `test_paths_lmdb_max_size_env` | GHOST_LMDB_MAX_SIZE_MB env surface |
| `test_paths_lightrag_root_defined` | LIGHTRAG_ROOT defined |
| `test_paths_cleanup_stale_lmdb_locks` | cleanup_stale_lmdb_locks safe |
| `test_paths_cleanup_stale_sockets` | cleanup_stale_sockets safe |
| `test_paths_ramdisk_alive_check` | assert_ramdisk_alive() |
| `test_vault_manager_tempdir_wiring` | vault_manager _get_tempdir() |
| `test_osint_frameworks_tempfile_dir` | osint_frameworks dir= usage |
| `test_autonomous_orchestrator_mkdtemp_dir` | AO mkdtemp dir= usage |
| `test_scheduler_bounded_task_registry` | MAX_TASK_REGISTRY bounded |
| `test_scheduler_bounded_affinity` | MAX_AFFINITY_ENTRIES bounded |
| `test_scheduler_bounded_put_replaces_existing` | _bounded_put FIFO eviction |
| `test_mlock_fail_open` | mlock fail-open behavior |
| `test_mlock_no_python_str` | mlock never on Python str |
| `test_signal_handler_registration` | SIGINT/SIGTERM registration |
| `test_bg_tasks_add_done_callback` | bg_tasks cleanup pattern |
| `test_cleanup_fallback_artifacts_idempotent` | cleanup idempotent |
| `test_no_sync_blockers_in_async_import` | paths.py fast import |
| `test_config_from_env_modes` | config.from_env modes |

**19/19 testů prošlo**

---

## 4. ZNÁMÉ LIMITY

1. **SIGINT/SIGTERM handlery nejsou registrovány v autonomous_orchestrator.py**
   - Záměr: Sprint 0A pouze připravuje "smoke test" pro registraci
   - Plná integrace bude v dalším sprintu (spojení s shutdown cestou)

2. **mlock na M1 může selhat kvůli entitlements**
   - Fail-open design zajišťuje, že systém pokračuje i bez mlock

3. **tempfile.tempdir bootstrap funguje pouze pokud paths.py importuje první**
   - Lazy getter `_get_tempdir()` v vault_manager řeší timing problém

4. **No boot regression test nelze spustit bez full environment**
   - 19 probe testů ověřuje jednotlivé invarianty

---

## 5. CO ZŮSTÁVÁ NA DALŠÍ SPRINT

- [ ] Plná SIGINT/SIGTERM integrace do FullyAutonomousOrchestrator
- [ ] Volání `cleanup_stale_lmdb_locks()` při boot
- [ ] Test shutdown_all() prochází bez leaků
- [ ] env surface GHOST_LMDB_MAX_SIZE_MB skutečně použit v LMDB open()
