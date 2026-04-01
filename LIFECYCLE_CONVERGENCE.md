# LIFECYCLE CONVERGENCE — Sprint 8VX

**Datum:** 2026-04-01
**Cíl:** Jeden canonical lifecycle contract, utils = skutečný compat shim, žádný třetí lifecycle owner.

---

## 1. Ptačí perspektiva — proč je to kritická precondition

Dnes existují DVĚ verze `SprintLifecycleManager`:

| | `runtime/sprint_lifecycle.py` | `utils/sprint_lifecycle.py` |
|---|---|---|
| **Byte size** | 14 463 B | 18 595 B |
| **Design** | `@dataclass`, synchronní, fail-safe | `class`, async-native, hook-based |
| **Phase enum** | `SprintPhase` (auto ints) | `SprintLifecycleState` (string values) |
| **Canonical?** | ANO — označeno v RUNTIME_AUTHORITY_MAP | NE — legacy |
| **Voláno z `__main__.py`?** | ❌ NE | ✅ ANO |
| **Voláno z `SprintScheduler`?** | ✅ ANO (runtime verze) | ❌ NE |
| **Voláno z `shadow_inputs.py`?** | ✅ ANO | ❌ NE |

**Důsledek:** `__main__._run_sprint_mode()` běží na utils verzi, ale `SprintScheduler` (scheduler shadow i active) běží na runtime verzi. Lifecycle reality se rozcházejí. Jakékoliv budoucí scheduler napojení bude stát na dvojí realitě.

**Dále:** `run_warmup()` v runtime verzi je definován, ale NIKDY nevolán. Pre-flight běží přímo v `_run_sprint_mode()` (řádek 2404), ne jako lifecycle fáze.

**Bez konvergence:** Shadow scheduler nemůže být aktivován, protože čte z runtime verze, zatímco produkce běží na utils verzi.

---

## 2. Lifecycle Capability Matrix

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
