# F025 — Active Runtime Reality Inventory
**Date:** 2026-04-01
**Scope:** `/hledac/universal/` hot path scan
**Method:** Direct file read + grep call-sites

---

## 1. Executive Summary

### Current Hot Path Truth
Dnes běží **DVA oddělené režimy**, nikdy společně:

| Režim | Entry | SprintScheduler? | Lifecycle? |
|-------|-------|------------------|------------|
| **Passive** (default) | `_run_public_passive_once()` | **NE** | **NE** |
| **Sprint** (`--sprint`) | `_run_sprint_mode()` | **NE** (HYPOTHESIS — not instantiated) | ANO (utils verze) |

**Critical finding:** `SprintScheduler` v `runtime/sprint_scheduler.py` (62,759 bytes) **není nikdy vytvořen** v `__main__.py`. Grep `SprintScheduler` v `__main__.py` → **0 matchí pro instantiation**. Pouze comment reference na řádku 2686.

### Unplugged Modules (velké, ne na hot path)
- `runtime/sprint_scheduler.py` — 62,759 bytes, NIKDY neimportován v production hot path
- `runtime/sprint_lifecycle.py` — `run_warmup()` voláno pouze v `_run_sprint_mode()` (sprint režim)
- `runtime/windup_engine.py` — `run_windup()` voláno pouze v `_run_sprint_mode()`
- `export/sprint_exporter.py` — `export_sprint()` voláno pouze v testu `test_e2e_dry_run.py`

---

## 2. Current Hot Path Truth

### Default Path (NO `--sprint` flag)
```python
# __main__.py:2771
asyncio.run(_run_public_passive_once(_get_and_clear_signal_flag))
```

**Funkce:** `_run_public_passive_once()` (line 355)
**Delegation:**
```python
# __main__.py:443-448
from .pipeline.live_public_pipeline import async_run_live_public_pipeline
from .pipeline.live_feed_pipeline import async_run_default_feed_batch
configure_default_bootstrap_patterns_if_empty()
web_result = await async_run_live_public_pipeline(...)
feed_result = await async_run_default_feed_batch(...)
```
**Lifecycle:** Žádná (pouze signal-driven sleep loop)
**Store:** `create_owned_store()` — DuckDBShadowStore

### Sprint Path (`--sprint` flag)
```python
# __main__.py:2767-2768
asyncio.run(_run_sprint_mode(sprint_target, duration_s=sprint_duration, install_signal_handlers=True))
```

**Funkce:** `_run_sprint_mode()` (line 2379)
**Lifecycle:** `utils.sprint_lifecycle.SprintLifecycleManager` (line 2406)
**Pipeline:** `async_run_default_feed_batch()` every 60s (line 2515)
**UMA:** `UMAAlarmDispatcher` (line 2446)

---

## 3. Runtime Path Matrix

| Komponenta | Passive (default) | Sprint (`--sprint`) | Voláno z __main__.py |
|------------|-------------------|---------------------|----------------------|
| `_run_public_passive_once()` | ✅ ANO | ❌ NE | ✅ line 2771 |
| `_run_sprint_mode()` | ❌ NE | ✅ ANO | ✅ line 2767 |
| `SprintScheduler` | ❌ NE | ❌ NE (not instantiated) | ❌ 0 matches |
| `utils/sprint_lifecycle.SprintLifecycleManager` | ❌ NE | ✅ ANO | ✅ line 2406 |
| `runtime/sprint_lifecycle.run_warmup()` | ❌ NE | ⚠️ planned, not called | ❌ |
| `runtime/windup_engine.run_windup()` | ❌ NE | ⚠️ planned, not called | ❌ |
| `export/sprint_exporter.export_sprint()` | ❌ NE | ❌ NE | ❌ test only |
| `async_run_live_public_pipeline()` | ✅ ANO | ❌ NE | ✅ line 443 |
| `async_run_default_feed_batch()` | ✅ ANO | ✅ ANO | ✅ line 2480 |
| `create_owned_store()` | ✅ ANO | ✅ ANO | ✅ line 2485 |
| `UMAAlarmDispatcher` | ❌ NE | ✅ ANO | ✅ line 2446 |

---

## 4. Lifecycle Reality

### Dvě verze lifecycle manageru

**`utils/sprint_lifecycle.py` (18,595 bytes) — STARŠÍ verze**
- Dataclass-based: `@dataclass class SprintLifecycleManager`
- API: `start()`, `tick()`, `remaining_time()`, `should_enter_windup()`, `request_abort()`
- Enum: `SprintPhase` (BOOT, WARMUP, ACTIVE, WINDUP, EXPORT, TEARDOWN)
- Používá: `runtime/sprint_scheduler.py` (pro adaptaci)

**`runtime/sprint_lifecycle.py` (14,363 bytes) — NOVĚJŠÍ verze**
- Class-based: `class SprintLifecycleManager`
- Async-native: `_windown_task`, `_uma_watchdog`, `register_signal_handlers()`
- Hooks: `_on_windup`, `_on_export`, `_on_teardown`
- Checkpoint seam: `get_checkpoint_seam()`, `load_from_checkpoint()`
- **Používá:** `_run_sprint_mode()` v `__main__.py` (import na line 2406)

### `_LifecycleAdapter` v runtime/sprint_scheduler.py
```python
# runtime/sprint_scheduler.py:56-100
class _LifecycleAdapter:
    """Bridges runtime/ vs utils/ sprint_lifecycle API"""
    # runtime: start(), tick(), remaining_time()
    # utils: begin_sprint(), is_active, remaining_time property
```
**Purpose:** Normalizuje rozdíly mezi oběma verzemi pro `SprintScheduler`

---

## 5. Export/Report Reality

### `export/sprint_exporter.py` (4,811 bytes)
```python
async def export_sprint(scheduler: "SprintScheduler", scorecard: dict, sprint_id: str) -> dict:
    # 1. JSON report → ~/.hledac/reports/{sprint_id}_report.json
    # 2. Seed tasks → next sprint
```
**Status:** VOLÁNO POUZE v testu `test_e2e_dry_run.py` (line 67)
**Production:** NIKDY nevoláno z `__main__.py`

### `export/markdown_reporter.py` (18,187 bytes)
```python
def render_diagnostic_markdown(report: dict) -> str:
    # Zero LLM / Zero model runtime
    # Deterministic, side-effect-free
```
**Status:** Importováno v `__main__.py`? HYPOTHESIS — needs verification
**Used by:** `ObservedRunReport` formatting in `_run_observed_default_feed_batch_once()`

### `export/stix_exporter.py` (17,742 bytes)
**Status:** UNPLUGGED — žádný call-site v __main__.py

### `export/jsonld_exporter.py` (16,315 bytes)
**Status:** UNPLUGGED — žádný call-site v __main__.py

### `_print_scorecard_report()` v __main__.py
```python
# __main__.py:2600
await _print_scorecard_report(target, store_instance, sprint_report=windup_report)
```
**Status:** Voláno pouze v `_run_sprint_mode()` WINDUP phase
**Implementation:** Reading offset 2598-2600 — not yet read, HYPOTHESIS: exports to markdown/JSON

---

## 6. Extraction Map from __main__.py

### SprintScheduler — kde by měl být
**Current:** `runtime/sprint_scheduler.py` existuje, **NENÍ v __main__.py**
**Should be in:** `_run_sprint_mode()` kolem line 2415 (after lifecycle init)

**Missing call-site:**
```python
# After line 2415, after lifecycle creation:
scheduler = SprintScheduler(
    lifecycle=lifecycle,  # utils/sprint_lifecycle.SprintLifecycleManager
    store=store_instance,
)
```

### run_warmup() — kde by měl být
**Current:** `runtime/sprint_lifecycle.py:274` — defined, **NIKDY nevoláno**
**Call-site应该在:** `_run_sprint_mode()` WARMUP phase (after `lifecycle.mark_warmup_done()`)

**Missing call-site:**
```python
# After line 2433 (lifecycle.mark_warmup_done()):
warmup_result = await run_warmup(scheduler, {})
```

### run_windup() — kde by mělo být
**Current:** `runtime/windup_engine.py:31` — defined, **NIKDY nevoláno z __main__.py**
**Call-site应该在:** `_run_sprint_mode()` WINDUP phase

**Missing call-site:**
```python
# After line 2526 (lifecycle.request_windup()):
t_active_end = time.monotonic()
scorecard = await run_windup(scheduler, target, t_warmup_end, t_active_end)
```

### export_sprint() — kde by mělo být
**Current:** `export/sprint_exporter.py:21` — defined, **NIKDY nevoláno z __main__.py**
**Call-site应该在:** `_run_sprint_mode()` EXPORT phase

**Missing call-site:**
```python
# After line 2595 (lifecycle.request_export()):
export_result = await export_sprint(scheduler, scorecard, sprint_id=f"sprint_{int(time.time())}")
```

---

## 7. Unplugged But Important Modules

| Modul | Size | Důvod unplugged | Authority status |
|-------|------|-----------------|------------------|
| `runtime/sprint_scheduler.py` | 62,759 B | Not instantiated in any path | HYPOTHESIS: planned for sprint mode |
| `runtime/windup_engine.py` | 8,902 B | Not called from __main__.py | ARCHITECTURE_MAP: "exists but NOT wired" |
| `export/sprint_exporter.py` | 4,811 B | Only called in test_e2e_dry_run.py | ARCHITECTURE_MAP: export plane |
| `export/stix_exporter.py` | 17,742 B | No call-site found | UNPLUGGED |
| `export/jsonld_exporter.py` | 16,315 B | No call-site found | UNPLUGGED |
| `brain/gnn_predictor.py` | ? | Imported in windup_engine, not on passive path | Part of WINDUP plane |
| `brain/ane_embedder.py` | ? | Imported in windup_engine | Part of WINDUP plane |
| `brain/synthesis_runner.py` | ? | Called in `_windup_synthesis()` | Part of WINDUP plane |
| `brain/hypothesis_engine.py` | ? | Called in `_windup_synthesis()` | Part of WINDUP plane |

---

## 8. Authority Conflicts

### Conflict 1: runtime vs utils sprint_lifecycle
| Aspekt | `runtime/sprint_lifecycle.py` | `utils/sprint_lifecycle.py` |
|--------|------------------------------|----------------------------|
| Style | Class-based async-native | Dataclass-based sync |
| API | `start()`, `tick()` returns phase | `begin_sprint()`, `tick()` returns float |
| Used by | `_run_sprint_mode()` | `SprintScheduler` (unplugged) |
| Authority | **RUNTIME TRUTH** (in sprint mode) | **LEGACY** |

**Conflict:** `SprintScheduler` imports `utils/sprint_lifecycle` ale `_run_sprint_mode()` používá `utils` přímo
**Resolution needed:** Který je "canonical"? runtime verze má async hooks a checkpoint seam

### Conflict 2: WINDUP plane — planned vs actual
| Komponenta | ARCHITECTURE_MAP říká | Realita |
|------------|----------------------|---------|
| `windup_engine.run_windup()` | "exists but NOT wired" | DEFINED ale NOT CALLED |
| `export_sprint()` | export plane | DEFINED ale NOT CALLED |
| `_print_scorecard_report()` | ? | CALLED v `_run_sprint_mode()` |

**HYPOTHESIS:** `_run_sprint_mode()` má vestavěný windup/synthesis flow (`_windup_synthesis()`) který duplicituje `windup_engine.run_windup()`

### Conflict 3: SprintScheduler lifecycle adapter
| Aspekt | Reality |
|--------|---------|
| `_LifecycleAdapter` exists | ✅ Yes, in runtime/sprint_scheduler.py:56 |
| Wraps which lifecycle? | Both — detects via `hasattr` |
| Used by SprintScheduler | SprintScheduler is UNPLUGGED |
| SprintScheduler used by | UNKNOWN (no call-sites found) |

---

## 9. Top 20 Konkrétních Ticketů

### F0.25 — Sprint Mode Wire-Up (HIGHEST PRIORITY)
**Problém:** `_run_sprint_mode()` references `scheduler` variable that doesn't exist
```
__main__.py:2546: if hasattr(scheduler, "_ioc_graph"):
__main__.py:2547:     gs = scheduler._ioc_graph.stats()
__main__.py:2555: connected = scheduler._ioc_graph.find_connected(...)
```
**Akce:** Instantiate `SprintScheduler` v `_run_sprint_mode()` a pass do windup synthesis

### F0.25b — Wire `run_warmup()` do `_run_sprint_mode()`
**Problém:** `run_warmup()` defined ale nikdy nevoláno
**Location:** `runtime/sprint_lifecycle.py:274`
**Akce:** Call after `lifecycle.mark_warmup_done()` (line 2433)

### F0.25c — Wire `run_windup()` do `_run_sprint_mode()`
**Problém:** `windup_engine.run_windup()` defined ale not called from __main__.py
**Location:** `runtime/windup_engine.py:31`
**Akce:** Replace `_windup_synthesis()` inline call nebo refactor

### F0.25d — Wire `export_sprint()` do `_run_sprint_mode()`
**Problém:** `export_sprint()` defined, called only in test
**Location:** `export/sprint_exporter.py:21`
**Akce:** Call in EXPORT phase after `lifecycle.request_export()`

### F0.25e — Resolve `utils` vs `runtime` sprint_lifecycle duality
**Problém:** Dvě verze lifecycle manageru
**Akce:** Decide canonical version; deprecate one

### F0.25f — `_print_scorecard_report()` definition scan
**Problém:** Not yet read; called at __main__.py:2600
**Akce:** Find definition; determine if it should use `export/sprint_exporter`

### F0.4a — Passive path: confirm `markdown_reporter` usage
**Problém:** `export/markdown_reporter.py` — is it imported anywhere in passive path?
**Akce:** Grep for `markdown_reporter|render_diagnostic_markdown` v __main__.py

### F0.4b — Sprint mode: extract `_windup_synthesis()` vs `windup_engine.run_windup()` overlap
**Problém:** Both do GNN + synthesis; potential duplication
**Akce:** Compare function signatures and consolidate

### F0.4c — Export plane: stix/jsonld unplugged
**Problém:** `stix_exporter.py` a `jsonld_exporter.py` existují ale nemají call-sites
**Akce:** Decide: implement call-sites nebo remove from codebase

### F0.4d — Passive path `_run_public_passive_once()`: lifecycle check
**Problém:** No lifecycle tracking in passive path
**Akce:** Consider if passive path needs lifecycle awareness

### F5Aa — SprintScheduler: actual usage path discovery
**Problém:** 62KB module, 0 instantiation call-sites found
**Akce:** Determine if this is dead code or planned for future sprint mode

### F5Ab — `SprintScheduler._LifecycleAdapter` cleanup
**Problém:** Adapter bridges two lifecycle APIs but SprintScheduler is unplugged
**Akce:** If SprintScheduler stays unplugged, adapter is dead code

### F5Ac — `_windup_synthesis()` inline vs `windup_engine.run_windup()` extraction
**Problém:** `_windup_synthesis()` (line 2623) is inline in __main__.py; `windup_engine.run_windup()` is separate
**Akce:** Decide if windup_engine.run_windup() should be called instead

### F5Ba — ANE embedder warmup in sprint mode
**Problém:** `__main__.py:2437-2443` calls ANE warmup but in wrong place (before WARMUP phase done)
**Akce:** Move to after `run_warmup()` completes

### F5Bb — DuckPGQ IOC graph access in sprint mode
**Problém:** `__main__.py:2546-2556` assumes `scheduler._ioc_graph` but scheduler not instantiated
**Akce:** Either instantiate SprintScheduler or access graph via store_instance

### F5Bc — HypothesisEngine in windup_synthesis
**Problém:** `__main__.py:2678-2684` creates HypothesisEngine but doesn't store results
**Akce:** Persist hypotheses to store or discard

### F5Ca — `export_report()` call from synthesis_runner
**Problém:** `_windup_synthesis()` calls `export_report()` from `brain.synthesis_runner`
**Akce:** Verify `export_report` writes to correct location; consider using `sprint_exporter`

### F5Cb — `maybe_resume()` checkpoint seam
**Problém:** `runtime/sprint_lifecycle.py:469` has `maybe_resume()` but no call-site in __main__.py
**Akce:** Wire into `_run_sprint_mode()` boot phase

### F5Cc — `UmaWatchdog` vs `UMAAlarmDispatcher` duality
**Problém:** Both monitor UMA; `SprintLifecycleManager` starts watchdog (line 245 in runtime/sprint_lifecycle.py), `_run_sprint_mode()` starts AlarmDispatcher (line 2446 in __main__.py)
**Akce:** Consolidate to single UMA monitoring mechanism

### F5Cd — `run_warmup()` preflight dependency on `__main__`
**Problém:** `runtime/sprint_lifecycle.py:286-289` imports `_preflight_check` z `__main__`
```python
from __main__ import _preflight_check
preflight = await _preflight_check()
```
**Akce:** Extract `_preflight_check` to utils module to break circular dependency

---

## 10. Exit Criteria

### F0.25 (Sprint Mode Wire-Up)
- [ ] `SprintScheduler` instantiated in `_run_sprint_mode()` around line 2415
- [ ] `run_warmup()` called after `lifecycle.mark_warmup_done()` (line ~2433)
- [ ] `run_windup()` called in WINDUP phase (line ~2526)
- [ ] `export_sprint()` called in EXPORT phase (line ~2595)
- [ ] `_run_sprint_mode()` completes without referencing undefined `scheduler` variable
- [ ] pytest `tests/probe_8vi/` passes

### F0.4 (Export/Report Plane)
- [ ] `render_diagnostic_markdown()` called from passive path OR removed from __main__.py imports
- [ ] `stix_exporter.py` and `jsonld_exporter.py` have documented call-sites OR removed
- [ ] `_print_scorecard_report()` definition verified and confirmed functional
- [ ] `export/sprint_exporter.py` confirmed as primary export mechanism

### F5A (SprintScheduler Authority)
- [ ] `SprintScheduler` has documented primary call-site (not just test)
- [ ] `_LifecycleAdapter` confirmed as necessary OR removed
- [ ] Canonical lifecycle version decided (runtime vs utils)
- [ ] `maybe_resume()` checkpoint wired into `_run_sprint_mode()` boot

### F5B (WINDUP Plane Integrity)
- [ ] `run_windup()` vs `_windup_synthesis()` overlap resolved (consolidate or document distinction)
- [ ] ANE warmup moved to correct phase
- [ ] `scheduler._ioc_graph` access replaced with store-based access
- [ ] HypothesisEngine results persisted

### F5C (Cleanup & Consistency)
- [ ] `UmaWatchdog` vs `UMAAlarmDispatcher` consolidated to single mechanism
- [ ] `_preflight_check` moved from `__main__` to utils to break circular dep in `run_warmup()`
- [ ] `export_report()` from synthesis_runner audited for correct output path
- [ ] All "planned but not wired" components either wired or marked deprecated

---

## What This Changes in the Master Plan

### 1. SprintScheduler is NOT on any hot path today
The 62KB `runtime/sprint_scheduler.py` module is **completely unplugged** from production execution. It exists as a design artifact but has zero instantiation in `__main__.py`. The sprint mode (`--sprint`) uses `utils/sprint_lifecycle.SprintLifecycleManager` directly, without going through SprintScheduler.

### 2. WINDUP plane is DOUBLE-WIRED
`windup_engine.run_windup()` is defined but never called. Instead, `_run_sprint_mode()` has its own inline `_windup_synthesis()` which performs similar work (GNN, ANE, synthesis, hypothesis). This is a design inconsistency — one should be removed or clearly delineated.

### 3. Export plane is TEST-ONLY
`export_sprint()` in `sprint_exporter.py` is called only from `test_e2e_dry_run.py`. Production uses `_print_scorecard_report()` (definition yet to be scanned). The markdown/stix/jsonld exporters are completely unplugged.

### 4. Passive path is the ACTUAL hot path
Default execution (`python -m hledac.universal`) goes through `_run_public_passive_once()` which delegates to two pipelines. No lifecycle, no sprint scheduler, no windup, no synthesis. This is a pure feed-processing run.

### 5. Sprint mode is INCOMPLETE
`_run_sprint_mode()` references a `scheduler` variable that is never instantiated (lines 2546-2556). The function cannot run as-is — it would crash with `NameError: name 'scheduler' is not defined`.

### 6. Two lifecycle managers create authority ambiguity
`utils/sprint_lifecycle.py` (older, dataclass) and `runtime/sprint_lifecycle.py` (newer, async-native) both exist. `_run_sprint_mode()` uses the utils version directly; `SprintScheduler` (when eventually instantiated) would use the utils version via adapter. The runtime version is used by `SprintLifecycleManager._start_uma_watchdog()` but this is only relevant if SprintScheduler were ever wired.

---

**Prepared by:** F025 Runtime Reality Inventory
**Files scanned:** `__main__.py`, `runtime/sprint_scheduler.py`, `runtime/sprint_lifecycle.py`, `runtime/windup_engine.py`, `utils/sprint_lifecycle.py`, `export/sprint_exporter.py`, `export/markdown_reporter.py`, `export/stix_exporter.py`, `export/jsonld_exporter.py`, `pipeline/live_public_pipeline.py`, `pipeline/live_feed_pipeline.py`, `paths.py`, `config.py`
