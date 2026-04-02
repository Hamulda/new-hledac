# MODEL_CONTROL_RECONCILIATION
**Audit date:** 2026-04-02
**Sprint:** F6.5 (Ownership Closure)
**Scope:** model/control plane split — runtime-wide vs windup-local vs structured-generation + Phase Drift Guard
**Files:** `brain/model_manager.py`, `brain/model_lifecycle.py`, `capabilities.py`, `model_lifecycle.py` (root stub), `runtime/windup_engine.py`, `brain/model_phase_facts.py`

---

## 1. Ptačí perspektiva — Proč ownership closure, ne model rewrite

Aktuální architektura F6.5 je **správně nakreslená** — všechny role už jsou přidělené a označené. Co chybělo:
- Některé authority notes byly neúplné nebo duplikované
- `MODEL_CONTROL_RECONCILIATION.md` nebyl aktualizovaný na poslední sprint
- Neexistovaly testy, které by invariants explicitně ověřovaly
- Chyběla explicitní ochrana proti "capability layer becomes third model truth"

Cíl F6.5: **uzamknout stávající architekturu, ne přepisovat**. Malé, disciplinované změny.

---

## 2. Model-Control Ownership Matrix (F6.5)

| Responsibility | Current Owner | Canonical Owner | Compat/Debt Path | Blocker | Removal Condition |
|---|---|---|---|---|---|
| **Runtime-wide acquire/load owner** | `brain/model_manager.py::ModelManager` (singleton) | ModelManager | — | — | — |
| **Runtime-wide unload/cleanup owner** | `ModelManager._release_current_async()` + `model_lifecycle.unload_model()` | ModelManager primary; `unload_model()` as 7K SSOT delegát | — | — | — |
| **Phase enforcer (coarse-grained)** | `capabilities.py::ModelLifecycleManager` | ModelLifecycleManager (FACADE only) | Future: delegate to `ModelManager.with_phase()` | PHASE_MODEL_MAP duplication | After seam extraction |
| **Capability registry** | `capabilities.py::CapabilityRegistry` | CapabilityRegistry | — | — | — |
| **MLX lazy init helper** | `model_lifecycle._get_mlx()` | `mlx_cache.init_mlx_buffers()` | — | — | — |
| **Emergency seam** | `model_lifecycle.request_emergency_unload()` | model_lifecycle (watchdog flag) | — | — | — |
| **Lifecycle shadow-state** | `model_lifecycle._lifecycle_state` | model_lifecycle (O(1), side-effect free) | — | — | — |
| **Structured-generation sidecar** | `brain/model_lifecycle::class ModelLifecycle` | ModelLifecycle (windup-local) | — | — | — |
| **Windup-local model world** | `runtime/windup_engine.py` | windup_engine (isolated) | — | Circular import | Future seam extraction |
| **Phase facts helper** | `brain/model_phase_facts.py` | model_phase_facts (read-only) | — | — | — |

---

## 3. Three Independent Phase Systems (F6.5 — LOCKED)

**KRITICKÝ NÁLEZ:** Existují TŘI ODLIŠNÉ phase naming systémy, které NIKDY nemapují 1:1.

| Phase System | Zdroj | Fáze | Model(y) | Poznámka |
|---|---|---|---|---|
| **Layer 1 — Workflow-level** | `ModelManager.PHASE_MODEL_MAP` | PLAN | hermes | workflow精细 |
| | | DECIDE | hermes | |
| | | SYNTHESIZE | hermes | **liší se od Layer 2 SYNTHESIS** |
| | | EMBED | modernbert | |
| | | DEDUP | modernbert | |
| | | ROUTING | modernbert | |
| | | NER | gliner | |
| | | ENTITY | gliner | |
| **Layer 2 — Coarse-grained** | `capabilities.py::enforce_phase_models()` | BRAIN | hermes |ÚPLNĚ jiný string |
| | | TOOLS | (release hermes) |ÚPLNĚ jiný string |
| | | SYNTHESIS | hermes | "SYNTHESIS" ≠ "SYNTHESIZE" |
| | | CLEANUP | (release all) | |
| **Layer 3 — Windup-local** | `windup_engine.py` | SYNTHESIS runner | Qwen/SmolLM | vlastní izolovaný model |
| **Fourth namespace** | `types.py::OrchestratorState` | IDLE/PLANNING/BRAIN/EXECUTION/SYNTHESIS/ERROR | — | vlastní strings, částečně překrývají coarse-grained |

**F6.5 LOCK:** Tyto tři phase systémy jsou SEMANTICKY ODLIŠNÉ a NESMĚJÍ být smazány do jednoho.
- `capabilities.py::enforce_phase_models()` používá coarse-grained (BRAIN/TOOLS/SYNTHESIS/CLEANUP)
- `ModelManager.PHASE_MODEL_MAP` používá workflow-level (PLAN/DECIDE/SYNTHESIZE/EMBED/...)
- `windup_engine.py` používá vlastní SYNTHESIS runner s Qwen modelem

---

## 4. F6.5 Hard Invariants (Uzamčené)

| # | Invariant | enforcement | Blocker pokud porušeno |
|---|---|---|---|
| 1 | acquire ≠ phase enforcement | ModelManager is sole acquire owner | capability layer becomes third model truth |
| 2 | unload ≠ phase policy | ModelManager._release_current_async() is sole unload owner | unload path fragmentation |
| 3 | workflow phases (Layer 1) ≠ coarse phases (Layer 2) | `is_same_layer()` guard | implicit phase string mapping |
| 4 | SYNTHESIZE (Layer 1) ≠ SYNTHESIS (Layer 2) | `model_phase_facts` constants | false equivalence |
| 5 | capability layer MUST NOT become model truth | ModelLifecycleManager FACADE notes | third model truth |
| 6 | windup-local model world ≠ runtime-wide model plane | isolated `ModelLifecycle()` instance | model plane conflation |

---

## 5. Internal Role Split — `brain/model_lifecycle.py` (F6.5)

| Role | Function/Class | Canonical Owner | Note |
|---|---|---|---|
| **Unload helper (7K SSOT)** | `unload_model()` | engine.unload() (delegát) | fail-open |
| **Emergency seam** | `request_emergency_unload()` | model_lifecycle (watchdog flag) | safe callback pattern |
| **Lifecycle shadow-state** | `_lifecycle_state`, `get_model_lifecycle_status()` | model_lifecycle | O(1), side-effect free |
| **MLX lazy init** | `_get_mlx()`, `ensure_mlx_runtime_initialized()` | mlx_cache.init_mlx_buffers() | delegát |
| **Preload hint** | `preload_model_hint()` | placeholder | future predictive preload |
| **Structured-generation sidecar** | `class ModelLifecycle` | ModelLifecycle (windup-local) | Qwen/SmolLM, async |

---

## 6. Authority Note Locations (F6.5)

| File | Location | Note |
|---|---|---|
| `brain/model_manager.py` | `PHASE_MODEL_MAP` comment block | Layer 1 authority + F6.5 ownership declaration |
| `capabilities.py` | `ModelLifecycleManager.__doc__` | FACADE + coarse-grained enforcer + hard invariants |
| `brain/model_lifecycle.py` | module docstring | F6.5 multi-role table + hard invariants |
| `brain/model_phase_facts.py` | module docstring | read-only facts helper |

---

## 7. capabilities.py::ModelLifecycleManager — FACADE Proof

ModelLifecycleManager **NENÍ** load owner. Důkaz:

```python
# ModelLifecycleManager.__init__拿走 registry
def __init__(self, registry: CapabilityRegistry):
    self.registry = registry  # ← pouze CapabilityRegistry reference

# load_model_for_task deleguje přes registry
async def load_model_for_task(self, capability: Capability) -> bool:
    success = await self.registry.load(capability)  # ← delegace, ne vlastní load
    if success:
        self._active_models.add(capability)
```

ModelLifecycleManager **NIKDY** nedělá:
- Přímé volání `ModelManager.load_model()`
- Vytváření model engine instancí
- Držení model references
- Správu MLX buffer initialization

---

## 8. types.py OrchestratorState — Fourth Phase System (F6.5)

`types.py::OrchestratorState` má vlastní strings: `IDLE/PLANNING/BRAIN/EXECUTION/SYNTHESIS/ERROR`.

- `PLANNING` ≠ `PLAN` (different string)
- `SYNTHESIS` coincidentally matches Layer 2 `SYNTHESIS` (different semantics)
- `BRAIN` coincidentally matches Layer 2 `BRAIN` (different semantics)

Toto je **čtvrtý** phase namespace — NESMÍ být zkonflontován s žádným ze tří layers výše.
Consumers porovnávající OrchestratorState s model phases musí použít `model_phase_facts` helpers.

---

## 9. Seam Extraction Pre-conditions (`runtime/windup_engine.py`)

| # | Pre-condition | Status |
|---|---|---|
| 1 | ModelManager singleton accessible to `windup_engine` without circular imports | **Not resolved** |
| 2 | `windup_engine` stops creating its own `ModelLifecycle()` | **Not resolved** — `run_windup()` calls `SynthesisRunner(ModelLifecycle())` |
| 3 | Unified unload path — windup uses same unload as ModelManager | **Not resolved** — `_lifecycle.unload()` vs `ModelManager._cleanup_memory_async()` are separate paths |
| 4 | Phase enforcer (ModelLifecycleManager) refactored to delegate to ModelManager | **Not resolved** — PHASE_MODEL_MAP duplication |

---

## 10. Root `model_lifecycle.py` — Stub Analysis

```python
# DEPRECATED — use brain.model_lifecycle
from brain.model_lifecycle import *  # noqa: F401, F403
__all__ = []  # prevent accidental star-imports
```

**Status:** Clean re-export stub. No cleanup needed. Dormant — does not affect runtime.
**Authority:** Does not need an authority note; its deprecation is self-explanatory.

---

## 11. Summary — Who Owns What Today (F6.5 Final)

| Role | Owner | Locked |
|---|---|---|
| **Runtime-wide acquire/load owner** | `brain/model_manager.py::ModelManager` (singleton) | ✅ |
| **Runtime-wide unload/cleanup owner** | `brain/model_manager.py::ModelManager` + `brain/model_lifecycle.py::unload_model()` (7K SSOT delegát) | ✅ |
| **Phase enforcer (coarse-grained)** | `capabilities.py::ModelLifecycleManager` — **FACADE**, does NOT load directly | ✅ |
| **Capability registry** | `capabilities.py::CapabilityRegistry` | ✅ |
| **Structured-generation sidecar** | `brain/model_lifecycle.py::class ModelLifecycle` (Qwen/SmolLM, windup-local) | ✅ |
| **Lifecycle shadow-state** | `brain/model_lifecycle.py::_lifecycle_state` | ✅ |
| **Emergency seam** | `brain/model_lifecycle.py::request_emergency_unload()` | ✅ |
| **Windup-local model world** | `runtime/windup_engine.py` — isolated, creates own lifecycle | ✅ |
| **Phase facts helper** | `brain/model_phase_facts.py` (read-only) | ✅ |

---

## 12. Co je už stabilní (F6.5)

- ModelManager singleton je jediný acquire/load owner
- ModelLifecycleManager je čistý FACADE bez load vlastnictví
- Phase layer separation je hardwarově enforced přes `model_phase_facts`
- Structured-generation sidecar je legitimně izolovaný (windup-local)
- Lifecycle shadow-state je O(1) a side-effect free
- Emergency seam je watchdog-safe pattern

---

## 13. Co zbývá před provider parity / scheduler další fází

| # | Task | Blocker | Priority |
|---|---|---|---|
| 1 | Resolve circular import pro windup_engine → ModelManager | Circular import risk | HIGH |
| 2 | Unified unload path pro windup-local a runtime-wide modely | Separate unload paths | HIGH |
| 3 | PHASE_MODEL_MAP deduplication mezi ModelManager a ModelLifecycleManager | Duplicated phase maps | MEDIUM |
| 4 | ModelLifecycleManager refactor na přímou delegaci na ModelManager.with_phase() | CapabilityRegistry round-trip | MEDIUM |

---

*Auditor: Claude Code / oh-my-claudecode*
*Sprint F6.5: Ownership Closure — explicitní uzamčení architecture*
*Sprint 8TF: Phase Drift Guard — authority notes + tiny pre-seam helper*
*Sprint 8TF-R: Phase Drift Guard enforcement helpers*
*Sprint 8ME: Pre-seam scaffold — phase enforcer facade documented*
*Runtime/windup_engine.py NOT modified per sprint guardrails*
