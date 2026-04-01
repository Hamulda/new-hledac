# INVENTORY_RUNTIME — Sprint 8SC Inventory Scan
**Datum:** 2026-03-31
**Scope:** boot, runtime, control, assembly plane
**Allowed root:** `/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/`

---

## 1. Executive Summary

Runtime spine projektu Hledac Universal se skládá ze **DVOU ODDĚLENÝCH běhových cest**, které se nikde nekříží:

| Režim | Entry point | Kanónické rutiny |
|--------|-------------|------------------|
| **Public Passive** | `__main__._run_public_passive_once()` | `async_run_live_public_pipeline` + `async_run_default_feed_batch` |
| **Sprint Mode** | `__main__._run_sprint_mode()` | `SprintLifecycleManager` + `async_run_default_feed_batch` |
| **Deprecated** | `autonomous_orchestrator.py` | FACADE → `legacy/autonomous_orchestrator.py` |

**Důležité:** `runtime/sprint_scheduler.py` je KATALOGIZOVÁN JAKO UNPLUGGED — není volán z `__main__.py`.

---

## 2. Canonical Authorities

### 2.1 Boot Authority
| Soubor | Funkce | Role |
|--------|--------|------|
| `__main__.py:189` | `_run_boot_guard()` | LMDB lock cleanup — FIRST SYNC BOOT STEP |
| `__main__.py:2713` | `main()` | Synchronous entry, orchestruje boot flow |
| `knowledge/lmdb_boot_guard.py` | `cleanup_stale_lmdb_lock()` | Safe stale-lock recovery (Sprint 8AG) |

### 2.2 Lifecycle Authority
| Soubor | Třída | Role |
|--------|-------|------|
| `runtime/sprint_lifecycle.py` | `SprintLifecycleManager` | 6-phase state machine: BOOT→WARMUP→ACTIVE→WINDUP→EXPORT→TEARDOWN |
| `utils/sprint_lifecycle.py` | N/A | DEPRECATED — starší verze bez `SprintLifecycleManager` |
| `runtime/sprint_scheduler.py` | `SprintScheduler` | UNPLUGGED — existuje, není volán |

### 2.3 Memory/UMA Authority
| Soubor | Role |
|--------|------|
| `core/resource_governor.py` | **Canonical** — `evaluate_uma_state()`, `UMAAlarmDispatcher`, thresholds 6.0/6.5/7.0 GiB |
| `runtime/sprint_scheduler.py` | Odkazuje na `resource_governor` |

### 2.4 Storage Authority
| Soubor | Funkce | Role |
|--------|--------|------|
| `knowledge/duckdb_store.py` | `create_owned_store()` | Canonical — RAMDISK-first, async init |
| `knowledge/lmdb_kv.py` | LMDB wrapper | Pro IOC metadata, persistent dedup |
| `knowledge/lmdb_boot_guard.py` | Lock cleanup | Boot hygiene |

### 2.5 Pipeline Authority
| Soubor | Funkce | Role |
|--------|--------|------|
| `pipeline/live_public_pipeline.py` | `async_run_live_public_pipeline()` | Web search → pattern → DuckDB |
| `pipeline/live_feed_pipeline.py` | `async_run_default_feed_batch()` | RSS/Atom → pattern → DuckDB |

### 2.6 Config/Paths Authority
| Soubor | Role |
|--------|------|
| `paths.py` | **Canonical** — RAMDISK paths SSOT, `open_lmdb()`, `assert_ramdisk_alive()` |
| `config.py` | `UniversalConfig`, `M1Presets`, `ResearchPresets` |
| `ARCHITECTURE_MAP.py` | Live architecture doc (18k+ řádků) — popisuje stav ke dni 2026-03-31 |

---

## 3. Split Authorities / Ownership Conflicts

### 3.1 SPRINT LIFECYCLE DUALITY — HIGH
```
runtime/sprint_lifecycle.py    [CANONICAL] — SprintLifecycleManager, 6-phase
utils/sprint_lifecycle.py      [OLD] — begin_sprint(), bez manageru
```
**Konflikt:** Dva různé moduly definují sprint lifecycle sémantiku.
**Most:** `runtime/sprint_scheduler.py` používá `_LifecycleAdapter` pro bridge.

### 3.2 AUTONOMOUS ORCHESTRATOR DUALITY — CRITICAL
```
__main__.py                    → pipeline/ → duckdb_store (AKTIVNÍ)
autonomous_orchestrator.py     → DEPRECATED FACADE → legacy/autonomous_orchestrator.py
legacy/autonomous_orchestrator.py → 31k lines God Object (DEPRECATED)
```
**Konflikt:** Dva oddělené systémy sdílející stejný package.
**Aktivní path:** NEPOUŽÍVÁ `FullyAutonomousOrchestrator`.

### 3.3 CONFIG SSOT — MEDIUM
```
config.py    — UniversalConfig, M1Presets, ResearchPresets
paths.py     — Path SSOT (RAMDISK, LMDB, SOCKETS)
ARCHITECTURE_MAP.py — popisuje intended architekturu (ne vždy aktuální)
```
**Konflikt:** `config.py` a `paths.py` nejsou formálně propojeny — různí autoři, různá logika.

### 3.4 COORDINATOR DUALITY — MEDIUM
```
coordinators/__init__.py        [ACTIVE] — 20 coordinators
legacy/coordinators/            [DEPRECATED] — přesunuto 2025-02-14
```
**Konflikt:** Dvě coordinator domény.

---

## 4. Runtime Hot Path

### 4.1 Public Passive Mode
```
main()
  └─ _run_boot_guard()                    [SYNC, FIRST]
  └─ asyncio.run(_run_public_passive_once(stop_flag))
       ├─ AsyncExitStack.__aenter__()
       ├─ async_get_aiohttp_session()     [lazy singleton]
       ├─ create_owned_store() → async_initialize()
       ├─ configure_default_bootstrap_patterns_if_empty()
       ├─ async_run_live_public_pipeline() [web search]
       ├─ async_run_default_feed_batch()  [RSS feeds]
       └─ while not stop_flag(): sleep(0.5)  [signal wait]
       └─ AsyncExitStack.__aexit__()       [LIFO cleanup]
```

### 4.2 Sprint Mode
```
main() with --sprint TARGET
  └─ _run_boot_guard()                    [SYNC]
  └─ asyncio.run(_run_sprint_mode(TARGET, DURATION))
       ├─ SprintLifecycleManager.start() → WARMUP
       ├─ _preflight_check()
       ├─ UMAAlarmDispatcher.start()       [memory monitoring]
       ├─ create_owned_store()
       ├─ while ACTIVE:
       │    ├─ async_run_default_feed_batch() [every 60s]
       │    ├─ lifecycle.tick()
       │    └─ check windup condition (T-3min)
       ├─ WINDUP: _windup_synthesis()
       │    ├─ SynthesisRunner.synthesize_findings()
       │    ├─ HypothesisEngine.generate_sprint_hypotheses()
       │    └─ export_report()
       ├─ EXPORT: _print_scorecard_report()
       └─ TEARDOWN: dispatcher.stop()
```

### 4.3 Observed Run (diagnostic mode)
```
_run_observed_default_feed_batch_once()
  ├─ _UmaSampler (peak UMA tracking)
  ├─ per-source: async_run_live_feed_pipeline()
  ├─ dedup_before/after snapshots
  ├─ diagnose_end_to_end_live_run()
  └─ _build_observed_run_report() → ObservedRunReport (msgspec.Struct)
```

---

## 5. Boot Path

```
1. python -m hledac.universal [--sprint TARGET [DURATION]]
          ↓
2. main() — sync entry
          ↓
3. _run_boot_guard() [SYNC, KRITICKÉ]
   └─ knowledge/lmdb_boot_guard.cleanup_stale_lmdb_lock()
   └─ Returns (removed_count, reason)
   └─ Abortuje pokud BootGuardError (live lock detected)
          ↓
4. asyncio.run() — vytváří event loop
          ↓
5a. _run_public_passive_once()  [bez --sprint]
    └─ AsyncExitStack (LIFO teardown backbone)
    └─ _install_signal_teardown() — SIGINT/SIGTERM

5b. _run_sprint_mode(TARGET)    [s --sprint]
    └─ SprintLifecycleManager (WARMUP→ACTIVE)
    └─ _install_signal_teardown() inside asyncio.run()
```

**Boot hygiene invariants (Sprint 8AI):**
- `_run_boot_guard()` MUSÍ běžet SYNCHRONNĚ a PŘED `asyncio.run()`
- AsyncExitStack zajišťuje LIFO pořadí cleanup
- Signal handlers nikdy necleanují přímo — pouze nastavují flag

---

## 6. Lifecycle Reality

### 6.1 SprintLifecycleManager States
```
BOOT → WARMUP → ACTIVE → WINDUP → EXPORT → TEARDOWN
```
- **BOOT:** jen start time recording
- **WARMUP:** 5s, preflight checks, ANE warmup
- **ACTIVE:** hlavní smyčka, feed pipeline runs každých 60s
- **WINDUP:** T-3min, synthesis, circuit breaker stats
- **EXPORT:** scorecard, markdown report, episode persistence
- **TEARDOWN:** cleanup, dispatcher stop

### 6.2 Lifecycle Methods
| Metoda | Použití |
|--------|---------|
| `start()` | BOOT→WARMUP |
| `tick()` | auto-advance to WINDUP when T-3min |
| `remaining_time()` | časovač pro windup condition |
| `request_windup()` | manuální windup trigger |
| `mark_export_started()` | WINDUP→EXPORT |
| `mark_teardown_started()` | EXPORT→TEARDOWN |

### 6.3 UNPLUGGED: SprintScheduler
`runtime/sprint_scheduler.py::SprintScheduler.run()` existuje ale **NIKDE není volán z `__main__.py`**:
```
__main__.py: grep "SprintScheduler" → ZERO matches
```

---

## 7. Export/Path/Config Reality

### 7.1 Paths SSOT (`paths.py`)
```
RAMDISK_ROOT         = /Volumes/ghost_tmp (nebo ~/.hledac_fallback_ramdisk)
FALLBACK_ROOT        = Path.home() / ".hledac_fallback_ramdisk"
RAMDISK_ACTIVE       = bool — validováno při importu
CACHE_ROOT           = RAMDISK_ROOT / "cache"
DB_ROOT              = RAMDISK_ROOT / "db"
LMDB_ROOT            = DB_ROOT / "lmdb"
SPRINT_LMDB_ROOT     = LMDB_ROOT / "sprint"
EVIDENCE_ROOT        = RAMDISK_ROOT / "evidence"
KEYS_ROOT            = RAMDISK_ROOT / "keys" (mode 0o700)
SPRINT_STORE_ROOT    = ~/.hledac/sprints
IOC_DB_PATH          = ~/.hledac/ioc_graph.duckdb
```

### 7.2 Config SSOT (`config.py`)
```
UniversalConfig      = hlavní config class
M1Presets           = HERMES_MODEL, MODERNBERT_MODEL, GLINER_MODEL, limity
ResearchPresets     = QUICK, STANDARD, DEEP, EXTREME, AUTONOMOUS
create_config()      = factory function
for_mode()          = preset-based config builder
```

### 7.3 Konflikty mezi config a paths
- `paths.py` je čistě stdlib — žádné externí závislosti
- `config.py` závisí na `types.py` (ResearchMode, etc.)
- **Neexistuje formální SSOT pro celou konfiguraci** — dva oddělené systémy

---

## 8. Recommended Integration Order Changes

### HIGH PRIORITY — Fix Split Lifecycle

**Current:**
```
runtime/sprint_lifecycle.py    [CANONICAL]
utils/sprint_lifecycle.py      [OLD]
```

**Recommended:**
1. Odstranit `utils/sprint_lifecycle.py` nebo ho přejmenovat na `utils/sprint_lifecycle_legacy.py`
2. Zajistit, že všichni importéři `utils/sprint_lifecycle` přejdou na `runtime/sprint_lifecycle`
3. Ověřit přes `grep -r "from.*sprint_lifecycle import"` že všechny cesty jsou aktualizované

### HIGH PRIORITY — Wire SprintScheduler

**Current:** `runtime/sprint_scheduler.py` existuje ale není volán

**Recommended:**
1. Rozhodnout: chceme `SprintScheduler.run()` integrovat do `_run_sprint_mode()` nebo ho odstranit?
2. Pokud ANO: nahradit přímý `async_run_default_feed_batch` loop voláním `SprintScheduler.run()`
3. Pokud NE: odstranit `runtime/sprint_scheduler.py` a označit jako deprecated

### MEDIUM PRIORITY — Config/Paths SSOT

**Current:** dva oddělené systémy

**Recommended:**
1. Vytvořit jednotný `RuntimeConfig` který zahrnuje paths i config
2. nebo explicitně dokumentovat, že `paths.py` je always-on infrastructure a `config.py` je volitelná overlay

### MEDIUM PRIORITY — Legacy Cleanup

**Current:** `legacy/autonomous_orchestrator.py` (31k lines) stále existuje

**Recommended:**
1. Zálohovat `legacy/` před odstraněním
2. Odstranit `legacy/` a přesměrovat všechny importy
3. Ověřit že `autonomous_orchestrator.py` facade už není potřeba

---

## 9. Rizika pro Apple Silicon / M1 8GB

### 9.1 Memory Budget
```
macOS base:              ~2.5 GiB
Orchestrator overhead:   ~1.0 GiB
Hermes-3 LLM (4bit):    ~2.0 GiB
KV cache:               ~0.75 GiB
---
TOTAL:                  ~6.25 GiB (BLÍZKO LIMITU 8 GiB)
```

### 9.2 Critical Risks
| Riziko | Pravděpodobnost | Dopad | Mitigace |
|--------|----------------|-------|----------|
| MLX + DuckDB současně | HIGH | OOM crash | `UMAAlarmDispatcher` s CRITICAL/EMERGENCY callbacks |
| hermes3 + slm_decomposer paralelně | HIGH | OOM | model_manager enforce 1-model-at-a-time |
| Swapování tiše | MEDIUM | výkon crash | `resource_governor` sleduje system_used_gib |
| LMDB lock desync | LOW | data loss | `lmdb_boot_guard` na boot |

### 9.3 Safety Features in Place
- `resource_governor.py:42` — thresholds 6.0/6.5/7.0 GiB
- `UMAAlarmDispatcher` — async callbacks při CRITICAL/EMERGENCY
- `mx.metal.clear_cache()` voláno v EMERGENCY callback
- `gc.collect()` voláno v EMERGENCY callback
- `duckdb_store` — RAMDISK-first, fail-safe degraded mode

### 9.4 NOT in Hot Path (Latent Capabilities)
```
brain/hermes3_engine.py       — ~75k, LLM inference, NOT called
brain/synthesis_runner.py     — ~41k, synthesis, called in WINDUP only
brain/inference_engine.py     — ~60k, abductive reasoning, NOT called
brain/hypothesis_engine.py    — ~98k, hypothesis testing, called in WINDUP
```

---

## 10. Souhrn

### Aktivní runtime spine:
1. `__main__.py` — entry point, boot, signal handlers, teardown
2. `runtime/sprint_lifecycle.py` — 6-phase state machine
3. `core/resource_governor.py` — UMA governance
4. `pipeline/live_public_pipeline.py` + `pipeline/live_feed_pipeline.py` — pipeline execution
5. `knowledge/duckdb_store.py` — canonical storage
6. `paths.py` — path SSOT

### Deprecated/unused:
1. `autonomous_orchestrator.py` — deprecated facade
2. `legacy/autonomous_orchestrator.py` — 31k God Object
3. `utils/sprint_lifecycle.py` — old version
4. `runtime/sprint_scheduler.py` — UNPLUGGED, existuje ale není volán
5. Brain moduly (hermes3, inference_engine, etc.) — latentní, mimo hot path

### Konflikty:
1. DUAL runtime paths — public passive vs sprint mode (nekříží se)
2. DUAL lifecycle — runtime/ vs utils/ sprint_lifecycle
3. Config split — config.py vs paths.py (oddělené SSOT)
4. Coordinator split — coordinators/ vs legacy/coordinators/
