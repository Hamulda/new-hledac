# RUNTIME_EXTRACTION_MAP — Sprint 8SC
**Datum:** 2026-03-31
**Focus:** `__main__.py` extraction pro budoucí refaktor

---

## 1. __main__.py Entry Paths (2781 lines total)

### 1.1 Synchronous Entry
```
main()  [line 2713]
  ├─ Logging basicConfig setup
  ├─ setproctitle "kernel_worker" [Sprint 7C]
  ├─ CLI parsing: --sprint TARGET [DURATION]
  ├─ _run_boot_guard() [SYNC, KRITICKÉ]
  ├─ asyncio.run(_run_public_passive_once)  [bez --sprint]
  └─ asyncio.run(_run_sprint_mode)          [s --sprint]
```

### 1.2 Async Entry Points
```
_run_async_main(stop_flag)  [line 239]
  ├─ Benchmark mode probe
  ├─ AsyncExitStack LIFO teardown
  └─ Signal wait loop

_run_public_passive_once(stop_flag)  [line 355]
  ├─ AsyncExitStack owned resources
  ├─ async_get_aiohttp_session()
  ├─ create_owned_store() → async_initialize()
  ├─ configure_default_bootstrap_patterns_if_empty()
  ├─ async_run_live_public_pipeline()
  ├─ async_run_default_feed_batch()
  └─ Signal wait loop

_run_sprint_mode(target, duration_s)  [line 2379]
  ├─ SprintLifecycleManager lifecycle
  ├─ _preflight_check()
  ├─ UMAAlarmDispatcher monitoring
  ├─ create_owned_store()
  ├─ Pipeline runs loop (every 60s during ACTIVE)
  ├─ WINDUP: _windup_synthesis()
  ├─ EXPORT: _print_scorecard_report()
  └─ TEARDOWN: dispatcher.stop()

_run_observed_default_feed_batch_once()  [line 1257]
  ├─ _UmaSampler peak tracking
  ├─ Per-source: async_run_live_feed_pipeline()
  ├─ Dedup before/after snapshots
  ├─ diagnose_end_to_end_live_run()
  └─ _build_observed_run_report() → ObservedRunReport
```

---

## 2. Sprint Kernel Modules

### 2.1 sprint_kernel.py — BUDOUCÍ
**Doporučený obsah extraction:**

```
Sprint Kernel = minimum viable runtime spine

__main__.py obsahuje:
  ✓ Boot guard (_run_boot_guard)
  ✓ Signal handlers (_install_signal_teardown)
  ✓ AsyncExitStack LIFO teardown backbone
  ✓ Boot telemetry (_boot_record, get_boot_telemetry)
  ✓ Runtime truth recording (_record_runtime_truth)
  ✓ Preflight check (_preflight_check)
  ✓ UmaSampler (_UmaSampler)

Plus z core/resource_governor.py:
  ✓ evaluate_uma_state()
  ✓ UMAAlarmDispatcher
  ✓ Thresholds 6.0/6.5/7.0 GiB

Plus z runtime/sprint_lifecycle.py:
  ✓ SprintLifecycleManager
  ✓ 6-phase state machine
```

**EVIDENCE — __main__.py line 189:**
```python
def _run_boot_guard(lmdb_root: Optional[pathlib.Path] = None) -> tuple[int, str]:
    """Run LMDB boot guard (8AG) synchronously."""
    # Called BEFORE asyncio.run()
    # FIRST boot step
```

**EVIDENCE — __main__.py line 154:**
```python
def _install_signal_teardown(loop: "asyncio.AbstractEventLoop") -> None:
    """Install SIGINT/SIGTERM handlers that schedule loop.stop()."""
```

**EVIDENCE — __main__.py line 239:**
```python
async def _run_async_main(stop_flag: Callable[[], bool]) -> None:
    """Main async entry point with AsyncExitStack-backed teardown."""
    exit_stack: Optional[contextlib.AsyncExitStack] = None
    try:
        exit_stack = contextlib.AsyncExitStack()
        await exit_stack.__aenter__()
        # LIFO teardown: duckdb_close → atomic_flush → persistent_close → sprint_lifecycle
```

### 2.2 COULD be in sprint_kernel.py:
| Kód | Lokace | Důvod |
|------|--------|--------|
| Boot telemetry | `__main__.py:55-70` | O(1) append, fail-open |
| Runtime truth | `__main__.py:618-646` | Python interpreter facts |
| ObservedRunReport | `__main__.py:676-760` | msgspec.Struct, diagnostic only |
| Baseline comparison | `__main__.py:1004-1071` | Sprint 8AO baseline |
| Feed health classification | `__main__.py:1141-1190` | HealthKind enum |
| Diagnosis | `__main__.py:1074-1133` | diagnose_end_to_end_live_run |
| AsyncSessionFactory | `__main__.py:2038-2101` | aiohttp session singleton |

---

## 3. Sprint Scheduler Modules

### 3.1 sprint_scheduler.py — EXISTUJE (UNPLUGGED)
**Lokace:** `runtime/sprint_scheduler.py` (62,759 bytes)

**Doporučená integrace do `__main__.py`:**
```
_run_sprint_mode() currently does:
  - Direct while loop: while lifecycle.state == ACTIVE
  - Manual pipeline dispatch every 60s
  - Manual windup check: if lifecycle.remaining_time <= 180.0

SprintScheduler.run() provides:
  - Tier-aware source scheduling
  - Lifecycle-managed phases
  - Built-in pivot queue
  - DuckDB + LMDB + IOCGraph integrated
  - RL-adaptive priorities
```

**EVIDENCE — __main__.py line 2497:**
```python
while lifecycle.state == SprintLifecycleState.ACTIVE:
    await asyncio.sleep(1.0)
    # Check windup condition (T-3min remaining)
    if lifecycle.remaining_time <= 180.0:
        lifecycle.request_windup()
        break
```

**EVIDENCE — __main__.py line 2510:**
```python
# Run pipeline every 60s
now = time.monotonic()
if now - last_pipeline_time >= 60.0:
    if store_instance is not None:
        try:
            await async_run_default_feed_batch(...)
```

**PROBLÉM:** `runtime/sprint_scheduler.py` JE UNPLUGGED — není volán z `__main__.py`

### 3.2 Doporučené změny:
1. **WIRE SprintScheduler:** Nahradit `while ACTIVE` loop v `_run_sprint_mode()` voláním `SprintScheduler.run()`
2. **NEBO REMOVE:** Odstranit `runtime/sprint_scheduler.py` pokud není plánováno ho používat

---

## 4. Export Plane

### 4.1 Current Export Functions

| Funkce | Lokace | Výstup |
|--------|--------|--------|
| `_export_markdown_report()` | `__main__.py:2121` | `~/.hledac/reports/{sprint_id}.md` |
| `_print_scorecard_report()` | `__main__.py:2221` | Console + DuckDB upsert |
| `export_report()` | `brain/synthesis_runner.py` | JSON export |

### 4.2 Doporučená struktura export plane:
```
export/
  ├── markdown_exporter.py    # _export_markdown_report
  ├── scorecard_exporter.py   # _print_scorecard_report, scorecard persistence
  ├── episode_persister.py    # upsert_episode
  └── report_factory.py        # ObservedRunReport, synthesis reports
```

### 4.3 Export Pipeline:
```
WINDUP
  ├─ _windup_synthesis()
  │    ├─ SynthesisRunner.synthesize_findings()
  │    ├─ export_report() → JSON
  │    └─ HypothesisEngine.generate_sprint_hypotheses()
  │
EXPORT
  ├─ _print_scorecard_report()
  │    ├─ DuckDB: upsert_scorecard()
  │    ├─ DuckDB: upsert_episode()
  │    ├─ Markdown: _export_markdown_report()
  │    └─ ghost_global: upsert_global_entities()
```

---

## 5. Special Diagnostic / Observed Run Paths

### 5.1 ObservedRunReport (msgspec.Struct)
**Lokace:** `__main__.py:676-760`

Použito pouze pro diagnostiku — **NENÍ součástí produkčního runtime**.

```python
class ObservedRunReport(msgspec.Struct, frozen=True, gc=False):
    # C.1: Batch totals
    started_ts: float
    finished_ts: float
    elapsed_ms: float
    total_sources: int
    completed_sources: int
    ...
    # C.3: UMA snapshot
    uma_snapshot: dict
    # Sprint 8BC: bounded sample
    sample_scanned_texts: tuple[str, ...]
    ...
```

### 5.2 Kdy se používá:
- `_run_observed_default_feed_batch_once()` — diagnostická verze feed pipeline
- `get_last_observed_run_report()` — getter pro testování
- `format_observed_run_summary()` — human-readable formatter

### 5.3 Doporučení:
**ponechat v `__main__.py`** — je to diagnostický nástroj, ne produkční kód.

---

## 6. Benchmark Path

### 6.1 Benchmark Probe
**Lokace:** `__main__.py:1981-2035`

```python
async def _run_benchmark_probe() -> Dict[str, Any]:
    """Run Sprint 0B benchmark probe tests."""
    # Check 1: uvloop availability
    # Check 2: flow_trace default-off
    # Check 3: flow_trace get_summary()
    # Check 4: Session factory singleton
    # Check 5: AsyncSessionFactory.get_session()
```

### 6.2 Aktivace:
```python
# __main__.py line 249
benchmark_mode = os.environ.get("HLEDAC_BENCHMARK", "0") == "1"
if benchmark_mode:
    results = await _run_benchmark_probe()
```

### 6.3 Doporučení:
**ponechat v `__main__.py`** — je to smoke test runner, ne produkční kód.

---

## 7. Dead Code / Suspicious Coupling

### 7.1 Dead Code Indicators

| Kód | Lokace | Indikátor |
|-----|--------|-----------|
| `SprintScheduler.run()` | `runtime/sprint_scheduler.py:421` | UNPLUGGED — grep "SprintScheduler" v __main__.py = 0 |
| `legacy/autonomous_orchestrator.py` | `legacy/` | 31k, not imported by __main__.py |
| `utils/sprint_lifecycle.py` | `utils/` | OLD version, není volán |
| `autonomous_orchestrator.py` | root | DEPRECATED facade, pouze backward compat |
| Brain moduly | `brain/` | Latent — pouze v WINDUP synthesis |

### 7.2 Suspicious Coupling

**Coupling A: `__main__.py` ↔ `runtime/sprint_scheduler`**
```
Evidence: __main__.py line 2546:
  if hasattr(scheduler, "_ioc_graph"):
      gs = scheduler._ioc_graph.stats()

ALE:
  scheduler Proměnná "scheduler" NENÍ definována v __main__.py scope!
  Toto je BUG — runtime error pokud by se tohle executing.
```
**Typ:** **SUSPECTED BUG** — proměnná `scheduler` není v lokálním scope

**Coupling B: `__main__.py` ↔ `utils/sprint_lifecycle`**
```
Evidence: __main__.py line 2406:
  from .utils.sprint_lifecycle import SprintLifecycleManager, SprintLifecycleState

ALE:
  runtime/sprint_lifecycle.py obsahuje SprintLifecycleManager
  utils/sprint_lifecycle.py obsahuje begin_sprint(),bez manageru
```
**Typ:** **AMBIGUOUS** — dvě různé verze

**Coupling C: `_windup_synthesis` ↔ `brain/hypothesis_engine`**
```
Evidence: __main__.py line 2678:
  from brain.hypothesis_engine import HypothesisEngine

Cesta:
  __main__._run_sprint_mode()
    └─ _windup_synthesis()
         └─ HypothesisEngine.generate_sprint_hypotheses()
```
**Typ:** **OK** — toto je legitimní coupling pro synthesis

### 7.3 Mrtvý kód k odstranění:

1. **`runtime/sprint_scheduler.py` CELÝ** — UNPLUGGED
2. **`utils/sprint_lifecycle.py`** — duplikátní lifecycle
3. **`legacy/` adresář** — deprecated God Object
4. **`autonomous_orchestrator.py`** — deprecated facade
5. **`outdated/` adresář** — old orchestrator v2

---

## 8. Split-Ownership Summary

### 8.1 __main__.py Split Owners

| Funkce | Owner | Problematika |
|--------|-------|--------------|
| Boot | `__main__.py` | Canonical |
| Lifecycle | `runtime/sprint_lifecycle.py` | Ale `__main__.py` importuje i `utils/sprint_lifecycle` |
| Scheduler | `runtime/sprint_scheduler.py` | UNPLUGGED — není volán |
| Storage | `knowledge/duckdb_store.py` | Canonical — create_owned_store() |
| Pipeline | `pipeline/` | Canonical — voláno přímo |
| UMA | `core/resource_governor.py` | Canonical |
| Brain | `brain/` | Latent — voláno pouze v WINDUP |

### 8.2 Config/Paths Split

| Soubor | Owner | Konflikt |
|--------|-------|----------|
| `config.py` | UniversalConfig | Nezávislý na paths.py |
| `paths.py` | RAMDISK paths | Nezávislý na config.py |
| `ARCHITECTURE_MAP.py` | Docs | Popisuje intended vs actual |

---

## 9. Refaktor Doporučení

### Phase 1: Bug Fix
```
1. FIX: __main__.py line 2546 — "scheduler" undefined variable
   - Buď odstranit ten blok
   - Nebo správně definovat scheduler proměnnou
```

### Phase 2: Lifecycle Cleanup
```
2. REMOVE: utils/sprint_lifecycle.py
   - Zálohovat
   - Přesměrovat importy na runtime/sprint_lifecycle.py
   - Ověřit přes grep

3. DECIDE: runtime/sprint_scheduler.py
   - Buď WIRE do _run_sprint_mode()
   - Nebo REMOVE jako dead code
```

### Phase 3: Legacy Cleanup
```
4. REMOVE: legacy/autonomous_orchestrator.py (31k)
5. REMOVE: autonomous_orchestrator.py facade (98 lines)
6. REMOVE: outdated/ adresář
7. CLEANUP: __init__.py — remove dead re-exports
```

### Phase 4: Structural
```
8. CREATE: sprint_kernel.py
   - Boot guard + signal handlers + AsyncExitStack
   - Runtime telemetry + truth recording
   - ObservedRunReport factory

9. CREATE: sprint_export.py
   - Markdown exporter
   - Scorecard exporter
   - Episode persister
```

---

## 10. Souhrn pro Sprint Kernel Extraction

### Canonical Sprint Kernel (dnes v __main__.py):
```
✓ _run_boot_guard()           — LMDB hygiene
✓ _install_signal_teardown()   — Signal handlers
✓ AsyncExitStack              — LIFO teardown
✓ _boot_record()              — Boot telemetry
✓ _record_runtime_truth()      — Runtime facts
✓ _preflight_check()          — System checks
✓ _UmaSampler                 — Peak UMA tracking
✓ SprintLifecycleManager      — Lifecycle state machine
✓ UMAAlarmDispatcher          — Memory monitoring
```

### Should be in sprint_kernel.py:
```
✓ Všechno výše
✓ Plus: evaluate_uma_state() z core/resource_governor.py
✓ Plus: SprintLifecycleManager z runtime/sprint_lifecycle.py
```

### Should stay in __main__.py:
```
✗ CLI parsing (--sprint)
✗ Benchmark probe
✗ ObservedRunReport + diagnostics
✗ Export functions (_export_markdown_report, _print_scorecard_report)
```
