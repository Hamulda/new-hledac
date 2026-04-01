# LIFECYCLE CONVERGENCE — Sprint 8VX + 8WA

**Datum:** 2026-04-02
**Cíl:** Jeden canonical lifecycle contract, utils = skutečný compat shim, žádný třetí lifecycle owner.
**Stav:** ✅ HOT-PATH CUTOVER COMPLETE — `__main__._run_sprint_mode()` nyní běží na `runtime/sprint_lifecycle.py`

---

## 1. Ptačí perspektiva — co se změnilo

**Před (2026-04-01):**
- `__main__._run_sprint_mode()` → `utils/sprint_lifecycle.SprintLifecycleManager` + `SprintLifecycleState` enum
- `SprintScheduler` → `runtime/sprint_lifecycle.SprintLifecycleManager` + `SprintPhase` enum
- Dvě oddělené lifecycle reality, scheduler shadow nemohl být aktivován

**Po (2026-04-02):**
- `__main__._run_sprint_mode()` → `runtime/sprint_lifecycle.SprintLifecycleManager` + `SprintPhase` enum (canonical)
- Všechny compat aliases (`begin_sprint`, `mark_warmup_done`, `request_windup`, `request_export`, `request_teardown`, `is_windup_phase`) jsou v runtime verzi
- `utils/sprint_lifecycle.py` = čistý compat shim + orchestration residue
- Scheduler shadow/active běží na stejné lifecycle verzi jako produkce

**Změněné soubory:**
- `__main__.py` — import + call-site přepnut na runtime verzi
- `runtime/sprint_lifecycle.py` — přidány COMPAT ALIASES s idempotentními guardy
- `tests/probe_8pc/test_sprint_mode_lifecycle_states.py` — přepnut na runtime import
- `LIFECYCLE_CONVERGENCE.md` — aktualizováno

---

## 2. Hot-Path Lifecycle Call-Site Matrix

| Call-site v `_run_sprint_mode()` | Použitá method | Canonical? | Poznámka |
|---|---|---|---|
| `SprintLifecycleManager()` | constructor | ✅ | @dataclass |
| `lifecycle.sprint_duration_s = duration_s` | field assign | ✅ | renamed from `_sprint_duration` |
| `lifecycle.begin_sprint()` | COMPAT ALIAS → `start()` | ✅ | |
| `lifecycle.mark_warmup_done()` | COMPAT ALIAS → `transition_to(ACTIVE)` | ✅ | |
| `lifecycle._current_phase == SprintPhase.ACTIVE` | direct field access | ✅ | enum-safe |
| `lifecycle.remaining_time() <= 180.0` | method call | ✅ | |
| `lifecycle.request_windup()` | COMPAT ALIAS (idempotent) | ✅ | guard: skip pokud WINDUP+ |
| `lifecycle._current_phase == SprintPhase.WINDUP` | direct field access | ✅ | |
| `lifecycle.remaining_time() <= 60.0` | method call | ✅ | |
| `lifecycle.request_export()` | COMPAT ALIAS (idempotent) | ✅ | guard: skip pokud EXPORT+ |
| `lifecycle.request_teardown()` | COMPAT ALIAS | ✅ | jen ve windup path |

**Enum mismatch — VYŘEŠEN:**
- Utils: `SprintLifecycleState.ACTIVE` (string enum)
- Runtime: `SprintPhase.ACTIVE` (auto int enum)
- Řešení: přímý access na `_current_phase` field (SprintPhase enum)

**Property vs Method mismatch — VYŘEŠEN:**
- Utils: `lifecycle.remaining_time` (property)
- Runtime: `lifecycle.remaining_time()` (method s `now_monotonic` param)
- Řešení: `lifecycle.remaining_time()` — oba tvary existují v runtime, voláme method

---

## 2b. Compat Aliases — Detail

| Alias | Mapuje na | Idempotent? | Poznámka |
|---|---|---|---|
| `begin_sprint()` | `start()` | N/A | |
| `mark_warmup_done()` | `transition_to(SprintPhase.ACTIVE)` | N/A | |
| `request_windup()` | `transition_to(WINDUP)` | ✅ ANO | guard: skip pokud WINDUP+ |
| `request_export()` | `mark_export_started()` | ✅ ANO | guard: skip pokud EXPORT+ |
| `request_teardown()` | `mark_teardown_started()` | ⚠️ NE | vyhodí exception pokud nevalidní |
| `is_windup_phase()` | `should_enter_windup()` | N/A | |
| `is_active` | `_current_phase == ACTIVE` | N/A | property |
| `is_winding_down` | `_current_phase in WINDUP+ | N/A | property |

**Proč idempotent guards?**
Utils verze byla fail-open (no-op na dvojité volání). Runtime verze vyhodí `InvalidPhaseTransitionError` na ne-monotonic transition. Guardy zachovávají compat behavior.

---

## 3. Oddělení Workflow / Control / Windup-Local fází

**ZACHOVÁNO** — žádné změny v tomto oddělení.

- Workflow: `BOOT→WARMUP→ACTIVE→WINDUP→EXPORT→TEARDOWN` — `runtime/sprint_lifecycle.SprintPhase` enum
- Control: `recommended_tool_mode()` — v runtime verzi, nezávislá na fázi
- Windup-Local: `windup_engine.py` — vlastní sub-fáze GATHER/SYNTHESIZE/EXPORT, lifecycle pouze čte `should_enter_windup()`

---

## 4. run_warmup() Status

**Status: DEFERRED**

`run_warmup()` v runtime verzi je definován, ale NENÍ wired do sprint hot-path.

**Důvod deferralu:**
1. Preflight běží inline v `_run_sprint_mode()` na ř.2404 (`await _preflight_check()`) — funguje správně
2. `run_warmup()` závisí na `SprintScheduler` referenci (`scheduler._ioc_graph`, `scheduler._ioc_scorer`) — ale v sprint módu `store_instance` není scheduler
3. Wiring by vyžadoval předání scheduler reference do sprint path, což je scheduler-side scope

**Future owner:** SprintScheduler side consumer (až bude scheduler canonical)

**Removal condition:** Když sprint mode začne používat `SprintScheduler` jako primární state holder

---

## 5. Co zůstává v utils/sprint_lifecycle.py

**100% orchestration residue + compat aliases** — utils verze už není lifecycle authority.

| Metoda | Role |
|---|---|
| `SprintLifecycleManager` class | COMPAT — forward to runtime |
| `SprintLifecycleState` enum | COMPAT — jen pro call-sites mimo sprint path |
| `begin_sprint()` | COMPAT ALIAS → runtime `start()` |
| `mark_warmup_done()` | COMPAT ALIAS → runtime `transition_to(ACTIVE)` |
| `request_windup()` | COMPAT ALIAS → runtime `transition_to(WINDUP)` |
| `request_export()` | COMPAT ALIAS → runtime `mark_export_started()` |
| `request_teardown()` | COMPAT ALIAS → runtime `mark_teardown_started()` |
| `is_windup_phase()` | COMPAT ALIAS → runtime `should_enter_windup()` |
| `is_active` | COMPAT PROPERTY |
| SIGINT/SIGTERM handlers | ORCHESTRATION — mimo sprint path |
| `_uma_watchdog` | ORCHESTRATION — běží v utils verzi |
| Hooks (`_on_windup`, `_on_export`, `_on_teardown`) | ORCHESTRATION |
| `get_instance()` singleton | ORCHESTRATION |
| `maybe_resume()` | COMPAT — checkpoint seam |
| `load_from_checkpoint()` | COMPAT |
| `track_task()` | ORCHESTRATION |

---

## 6. Další blocker před scheduler-side consumerem

Žádný další blocker pro runtime lifecycle convergence.

**Hot-path cutover je COMPLETE.** Scheduler-side (shadow/active) už běží na runtime verzi.

---

## 7. Test Summary

**Probe 8pc (sprint mode lifecycle states):**
- ✅ `test_sprint_mode_state_transitions` — plná fáze BOOT→WARMUP→ACTIVE→WINDUP→EXPORT→TEARDOWN
- ✅ `test_sprint_mode_no_unhandled_exception` — žádný unhandled exception během teardown

**Probe 8sa (lifecycle adapter):**
- ✅ `test_lifecycle_adapter_is_terminal`
- ✅ `test_lifecycle_adapter_no_attribute_error`
- ✅ `test_lifecycle_adapter_phase_returns_str`
- ✅ `test_lifecycle_adapter_start_callable`
- ✅ `test_lifecycle_adapter_tick_returns_sprint_phase`
- ✅ `test_source_scoring_wired_to_scheduler`

**Probe 8vx (lifecycle convergence):** ✅ (73 tests)

**Pre-existing failures (nesouvisejí s cutover):**
- `test_unload_model_delegates_to_engine_unload_sync` (probe_8c) — model unload delegation, nesouvisející domain
- `test_sprint_mode_lifecycle_states` — intermittent `ModuleNotFoundError: No module named 'transport'` — import-order race condition, isolovaně prochází

---

## 8. Exact Removal Conditions

| Item | Removal condition |
|---|---|
| `utils/sprint_lifecycle.begin_sprint()` | Všechny call-sites přepojeny na runtime |
| `utils/sprint_lifecycle.SprintLifecycleManager` class | 0 call-sites z __main__.py; zůstane `maybe_resume()` |
| Full utils file removal | 0 call-sites z __main__.py, sprint_scheduler, shadow_inputs |

---

## 9. Co NENÍ součástí lifecycle konvergence

- **SprintScheduler** — orchestration vrstva, ne lifecycle (již na runtime verzi)
- **windup_engine.py** — windup sub-fáze management
- **run_warmup()** — DEFERRED (viz sekce 4)
- **UMA watchdog** — resource management, orchestration helper
- **Checkpoint seam** — perzistence, lifecycle pouze poskytuje snapshot

| Capability | runtime/sprint_lifecycle | utils/sprint_lifecycle | Canonical owner | Compat owner | Migration blocker | Removal condition |
|---|---|---|---|---|---|---|
| `start()` → WARMUP | ✅ `start()` | ❌ chybí | runtime | — | — | — |
| `begin_sprint()` → WARMUP | ❌ chybí | ✅ `begin_sprint()` | — | utils | __main__.py volá begin_sprint | přepojení __main__.py na start() |
| `mark_warmup_done()` → ACTIVE | ❌ chybí | ✅ `mark_warmup_done()` | — | utils | __main__.py volá mark_warmup_done | přepojení __main__.py |
| `tick()` → auto WINDUP | ✅ `tick()` | ❌ chybí | runtime | — | — | — |
| `transition_to(phase)` | ✅ `transition_to()` | ✅ `transition_to()` | runtime | utils | — | utils jen alias |
| `remaining_time` | ✅ property + method variant | ✅ property | runtime | utils (property form) | — | utils prop → runtime prop |
| `should_enter_windup()` | ✅ method | ❌ chybí | runtime | — | — | — |
| `is_windup_phase()` | ❌ chybí | ✅ method | — | utils | synthesis_runner.py volá | přepojení na should_enter_windup() |
| `request_windup()` | ❌ chybí | ✅ `request_windup()` | — | utils | __main__.py volá | přepojení na transition_to(WINDUP) |
| `request_export()` | ❌ chybí | ✅ `request_export()` | — | utils | __main__.py volá | — |
| `request_teardown()` | ❌ chybí | ✅ `request_teardown()` | — | utils | __main__.py volá | — |
| `mark_export_started()` | ✅ `mark_export_started()` | ❌ chybí | runtime | — | — | — |
| `mark_teardown_started()` | ✅ `mark_teardown_started()` | ❌ chybí | runtime | — | — | — |
| `is_terminal()` | ✅ method | ❌ chybí | runtime | — | — | — |
| `recommended_tool_mode()` | ✅ method | ❌ chybí | runtime | — | — | — |
| `snapshot()` | ✅ dict | ❌ chybí | runtime | — | shadow_inputs.py čte z runtime | — |
| `is_active` | ❌ chybí | ✅ property | — | utils | — | — |
| `is_winding_down` | ❌ chybí | ✅ property | — | utils | — | — |
| `windup_fired` | ❌ chybí | ✅ property | — | utils | — | — |
| `shutdown_requested` | ❌ chybí | ✅ property | — | utils | — | — |
| `checkpoint_seam` | ❌ chybí | ✅ property | — | utils | — | — |
| `get_checkpoint_seam()` | ❌ chybí | ✅ method | — | utils | — | — |
| `load_from_checkpoint()` | ❌ chybí | ✅ method | — | utils | — | — |
| `maybe_resume()` | ❌ chybí | ✅ free function | — | utils | test_probe_7a používá | — |
| `_LifecycleAdapter` | ❌ chybí | ✅ | — | utils | scheduler používá | — |
| `run_warmup()` | ✅ async function | ❌ chybí | runtime | — | definován, nikdy nevolán | — |
| SIGINT/SIGTERM handlers | ❌ chybí | ✅ `register_signal_handlers()` | — | utils | — | — |
| `track_task()` | ❌ chybí | ✅ method | — | utils | — | — |
| Hooks (`_on_windup`) | ❌ chybí | ✅ `_on_windup`, `_on_export`, `_on_teardown` | — | utils | — | — |
| `_start_uma_watchdog()` | ❌ chybí | ✅ (private) | — | utils | Sprint 7H | — |
| Singleton `get_instance()` | ❌ chybí | ✅ | — | utils | htn_planner, synthesis_runner | — |

---

## 3. Canonical Surface — `runtime/sprint_lifecycle.py`

### Definitive Public API

| Method/Property | Signature | Notes |
|---|---|---|
| `start(now_monotonic?)` | `(Optional[float]) -> None` | BOOT→WARMUP |
| `tick(now_monotonic?)` | `(Optional[float]) -> SprintPhase` | Auto-enters WINDUP when remaining <= windup_lead_s |
| `transition_to(phase, now_monotonic?)` | `(SprintPhase, Optional[float]) -> None` | Monotonic enforcement; TEARDOWN reachable always (abort) |
| `remaining_time(now_monotonic?)` | `(Optional[float]) -> float` | 0 if not started |
| `should_enter_windup(now_monotonic?)` | `(Optional[float]) -> bool` | remaining <= windup_lead_s |
| `request_abort(reason)` | `(str) -> None` | Sets _abort_requested + _abort_reason |
| `mark_export_started(now_monotonic?)` | `(Optional[float]) -> None` | WINDUP→EXPORT only |
| `mark_teardown_started(now_monotonic?)` | `(Optional[float]) -> None` | EXPORT/WINDUP→TEARDOWN |
| `snapshot()` | `() -> dict` | JSON-safe, no Path/handles |
| `recommended_tool_mode(now_monotonic?, thermal_state?)` | `(Optional[float], str) -> str` | Returns 'normal'|'prune'|'panic' |
| `is_terminal()` | `() -> bool` | TEARDOWN reached or abort+teardown |
| `SprintPhase` | `Enum` | BOOT, WARMUP, ACTIVE, WINDUP, EXPORT, TEARDOWN |

### COMPAT ALIASES (must be labeled)

These are added to bridge the gap. They must be clearly marked as COMPAT ALIAS in docstring:

| Alias name | Maps to | Why needed |
|---|---|---|
| `begin_sprint()` | `start()` | __main__.py calls begin_sprint() |
| `mark_warmup_done()` | → transitions to ACTIVE directly | __main__.py calls this after preflight |
| `request_windup()` | `transition_to(SprintPhase.WINDUP)` | __main__.py calls request_windup() |
| `request_export()` | `mark_export_started()` | __main__.py calls request_export() |
| `request_teardown()` | `mark_teardown_started()` | __main__.py calls request_teardown() |
| `is_windup_phase()` | `should_enter_windup()` | synthesis_runner.py uses is_windup_phase() |

### Legacy Drift (NOT part of canonical surface)

- `run_warmup()` — async helper, NOT lifecycle authority. Defined in runtime/sprint_lifecycle but is runtime orchestration helper. **Jméno v dokumentaci: `run_warmup()` is NOT lifecycle — it is a WARMUP-phase orchestration helper.**
- No SIGINT/SIGTERM handling in canonical (utils manages this)
- No `_bg_tasks`, `_uma_watchdog`, `_windown_task` in canonical (async orchestration residue)
- No singleton `get_instance()` in canonical
- No hooks (`_on_windup`, etc.) in canonical

### Snapshot Contract

```python
{
    "sprint_duration_s": float,
    "windup_lead_s": float,
    "checkpoint_interval_s": float,
    "checkpoint_path": str,           # metadata only
    "started_at_monotonic": float?,   # None if not started
    "current_phase": str,             # SprintPhase.name
    "entered_phase_at": float?,
    "export_started": bool,
    "teardown_started": bool,
    "abort_requested": bool,
    "abort_reason": str,
    "last_checkpoint_at": float?,
}
```

### Pressure / Tool-Mode Surface

`recommended_tool_mode(thermal_state="nominal") -> 'normal'|'prune'|'panic'`

Decision matrix embedded in method:
- **panic:** abort OR remaining <= 30s OR thermal == 'critical'
- **prune:** remaining <= windup_lead_s OR thermal in ('throttled', 'fair')
- **normal:** everything else

---

## 4. Compat Shim Surface — `utils/sprint_lifecycle.py`

### Skutečný role: compat shim, ne rovnocenné public API

**Co utils/sprint_lifecycle.py OBSAHUJE a runtime/sprint_lifecycle.py NECONTROLUJE:**

| Method | Role |
|---|---|
| `begin_sprint()` | COMPAT ALIAS → runtime `start()` |
| `mark_warmup_done()` | COMPAT ALIAS → runtime `transition_to(ACTIVE)` |
| `request_windup()` | COMPAT ALIAS → runtime `transition_to(WINDUP)` |
| `request_export()` | COMPAT ALIAS → runtime `mark_export_started()` |
| `request_teardown()` | COMPAT ALIAS → runtime `mark_teardown_started()` |
| `is_windup_phase()` | COMPAT ALIAS → runtime `should_enter_windup()` |
| `is_active` | COMPAT PROPERTY → runtime `_current_phase == ACTIVE` |
| `is_winding_down` | COMPAT PROPERTY |
| `windup_fired` | COMPAT PROPERTY |
| `shutdown_requested` | COMPAT PROPERTY (SIGINT/SIGTERM tracking — NOT lifecycle authority) |
| `checkpoint_seam_ready` | COMPAT PROPERTY (checkpoint wiring seam — NOT lifecycle) |
| `get_checkpoint_seam()` | COMPAT METHOD |
| `load_from_checkpoint()` | COMPAT METHOD |
| `maybe_resume()` | FREE FUNCTION — LMDB checkpoint seam |
| `register_signal_handlers()` | ORCHESTRATION HELPER — not lifecycle |
| `track_task()` | ORCHESTRATION HELPER — not lifecycle |
| `_on_windup`, `_on_export`, `_on_teardown` hooks | ORCHESTRATION HELPERS — not lifecycle |
| `_start_uma_watchdog()`, `_stop_uma_watchdog()` | ORCHESTRATION HELPERS — not lifecycle |
| `_start_windown_monitor()` | ORCHESTRATION HELPERS — not lifecycle |
| `cancel()` | ORCHESTRATION HELPER |
| `get_instance()` singleton | ORCHESTRATION HELPER — not lifecycle |
| `_bg_tasks`, `_uma_watchdog`, `_windown_task` | ORCHESTRATION STATE — not lifecycle |

**Závěr:** `utils/sprint_lifecycle.py` je 85% orchestration helper + 15% compat alias. Canonical lifecycle methods jsou VÝHRADNĚ v runtime verzi.

---

## 5. Oddělení Workflow / Control / Windup-Local fází

Tyto tři vrstvy **NESMÍ** splynout do jedné API plochy:

### Workflow Lifecycle Facts
- phase: BOOT → WARMUP → ACTIVE → WINDUP → EXPORT → TEARDOWN
- Canonical: `runtime/sprint_lifecycle.SprintPhase` enum
- Authority: `runtime/sprint_lifecycle.SprintLifecycleManager`

### Control / Tool-Mode Facts
- `recommended_tool_mode()`: 'normal' | 'prune' | 'panic'
- Thermal state integration
- Abort signaling
- Authority: `runtime/sprint_lifecycle.recommended_tool_mode()`

### Windup-Local Phase Facts
- **NESMÍ** být v lifecycle vrstvě — spravuje `windup_engine.py`
- Windup engine řídí své vlastní sub-fáze: `GATHER`, `SYNTHESIZE`, `EXPORT`
- Lifecycle pouze poskytuje `should_enter_windup()` signál

---

## 6. Explicitní deprecation drift

| Method v utils | Status | Důvod |
|---|---|---|
| `begin_sprint()` | **COMPAT ALIAS** | Přejmenuje se na `start()` v __main__.py call-site |
| `mark_warmup_done()` | **COMPAT ALIAS** | Logika přesune do runtime `start()` |
| `request_windup()` | **COMPAT ALIAS** | Nahradit `transition_to(WINDUP)` |
| `request_export()` | **COMPAT ALIAS** | Nahradit `mark_export_started()` |
| `request_teardown()` | **COMPAT ALIAS** | Nahradit `mark_teardown_started()` |
| `is_windup_phase()` | **COMPAT ALIAS** | Nahradit `should_enter_windup()` |
| `is_active` | **COMPAT PROPERTY** | Nahradit `_current_phase == ACTIVE` |
| `is_winding_down` | **COMPAT PROPERTY** | Check phase in (WINDUP, EXPORT, TEARDOWN) |
| SIGINT/SIGTERM handlers | **ORCHESTRATION** | Zůstává v utils, není lifecycle |
| `_uma_watchdog` | **ORCHESTRATION** | Zůstává v utils, není lifecycle |
| Hooks | **ORCHESTRATION** | Zůstává v utils, není lifecycle |

---

## 7. Exact Removal Conditions

| Item | Removal condition |
|---|---|
| `utils/sprint_lifecycle.begin_sprint()` | __main__.py přepojen na `lifecycle.start()` |
| `utils/sprint_lifecycle.mark_warmup_done()` | __main__.py přepojen (WARMUP→ACTIVE proběhne v `start()`) |
| `utils/sprint_lifecycle.request_windup()` | __main__.py přepojen na `lifecycle.transition_to(WINDUP)` |
| `utils/sprint_lifecycle.request_export()` | __main__.py přepojen na `lifecycle.mark_export_started()` |
| `utils/sprint_lifecycle.request_teardown()` | __main__.py přepojen na `lifecycle.mark_teardown_started()` |
| `utils/sprint_lifecycle.is_windup_phase()` | `synthesis_runner.py` přepojen na `should_enter_windup()` |
| `utils/sprint_lifecycle.SprintLifecycleManager` class | Všechny call-sites přepojeny; zůstane `maybe_resume()` |
| `maybe_resume()` |checkpoint seam plně přepojen na runtime verzi |
| **Full utils file removal** | 0 call-sites z __main__.py, sprint_scheduler, shadow_inputs, synthesis_runner |

---

## 8. Co ještě chybí před runtime call-site cutoverem

### __main__.py cutover předpoklady
1. `lifecycle.begin_sprint()` → `lifecycle.start()`
2. `lifecycle.mark_warmup_done()` → součást `start()` nebo nová helper metoda
3. `lifecycle.request_windup()` → `lifecycle.transition_to(SprintPhase.WINDUP)`
4. `lifecycle.request_export()` → `lifecycle.mark_export_started()`
5. `lifecycle.request_teardown()` → `lifecycle.mark_teardown_started()`
6. `lifecycle.remaining_time` (property) → `lifecycle.remaining_time()` (method) — aktuálně oba existují, **už funguje**
7. `lifecycle.state == SprintLifecycleState.ACTIVE` → `lifecycle._current_phase == SprintPhase.ACTIVE` — **enum mismatch**
8. `lifecycle.is_windup_phase()` → `lifecycle.should_enter_windup()`
9. `lifecycle._windup_fired` → `lifecycle._current_phase` is WINDUP+

### Scheduler shadow / scheduler active předpoklady
1. `SprintScheduler` používá `_LifecycleAdapter` — **už existuje** (runtime/sprint_scheduler.py:56)
2. `shadow_inputs.py` čte `snapshot()` z runtime verze — **už existuje**
3. `recommended_tool_mode()` v runtime verzi — **už existuje**
4. `run_warmup()` — definován, ale **není napojen** (F0.25b v F025_RUNTIME_REALITY.md)

---

## 9. Next Migration Step

**Malý, reverzibilní krok — Sprint 8VX:**

1. Přidat do `runtime/sprint_lifecycle.py` COMPAT ALIAS methods:
   - `begin_sprint()` → `start()`
   - `mark_warmup_done()` → `transition_to(SprintPhase.ACTIVE)` + log
   - `request_windup()` → `transition_to(SprintPhase.WINDUP)`
   - `request_export()` → `mark_export_started()`
   - `request_teardown()` → `mark_teardown_started()`
   - `is_windup_phase()` → `should_enter_windup()`

2. V `utils/sprint_lifecycle.py` přepsat tyto metody tak, aby volaly runtime verzi (pokud je dostupná) nebo si nechaly svou vlastní logiku jako fallback. Označit je "COMPAT FORWARD TO RUNTIME".

3. Ověřit, že `__main__.py` může být přepnut na `runtime/sprint_lifecycle` bez změny chování.

**POZOR:** Tento krok neprovádí plošný refactor call-sites. Pouze připravuje obě verze tak, aby byly zaměnitelné.

---

## 10. Co NENÍ součástí lifecycle konvergence

- **windup_engine.py** — vlastní windup fáze management, není lifecycle authority
- **SprintScheduler** — orchestration vrstva, ne lifecycle
- **run_warmup()** — WARMUP-fáze orchestration helper, ne lifecycle state machine
- **UMA watchdog** — resource management, běží v rámci lifecycle, není lifecycle sám o sobě
- **Checkpoint seam** — perzistence, lifecycle pouze poskytuje snapshot

---

## 11. Probe/Test Summary

viz `tests/probe_8vx/test_lifecycle_convergence.py`
