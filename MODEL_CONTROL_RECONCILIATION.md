# MODEL_CONTROL_RECONCILIATION
**Audit date:** 2026-04-01 (updated)
**Sprint:** 8TF
**Scope:** model/control plane split — runtime-wide vs windup-local vs structured-generation + Phase Drift Guard
**Files:** `brain/model_manager.py`, `brain/model_lifecycle.py`, `capabilities.py`, `model_lifecycle.py` (root stub), `runtime/windup_engine.py`, `brain/model_phase_facts.py`

---

## 1. Ptačí perspektiva — Model/Control Split

```
RUNTIME-WIDE MODEL PLANE
│
├── ModelManager (singleton)              ← runtime-wide acquire/load owner
│   ├── _load_model_async()              Hermes/ModernBERT/GLiNER
│   ├── _release_current_async()
│   ├── _cleanup_memory_async()          gc.collect + mx.clear_cache
│   ├── with_phase()                    phase→model mapping (PHASE_MODEL_MAP)
│   ├── get_embedder()                  ANE vs MLX selection
│   └── PHASE_MODEL_MAP
│
├── capabilities.ModelLifecycleManager    ← phase enforcer FACADE (Sprint 8ME)
│   ├── enforce_phase_models()           BRAIN/TOOLS/SYNTHESIS/CLEANUP
│   ├── _active_models                   Set[Capability]
│   └── load_model_for_task()            single-model constraint
│   │
│   │ Authority note: this is a FACADE — does NOT load/unload directly.
│   │ Delegates to CapabilityRegistry.load/unload, NOT to ModelManager.
│   │ Future: may delegate to ModelManager.with_phase() after seam extraction.
│
└── brain/model_lifecycle.py (module-level)
    ├── unload_model()                   engine.unload() delegát (7K SSOT)
    ├── load_model()                     idempotent state-tracked
    ├── ensure_mlx_runtime_initialized()  delegates to mlx_cache.init_mlx_buffers()
    ├── emergency flags/callbacks         watchdog → safe seam pattern
    └── _lifecycle_state                  O(1) shadow-state

WINDUP-LOCAL MODEL PLANE
│
└── runtime/windup_engine.py
    ├── own: ModelLifecycle() instance    ← isolated from runtime-wide
    ├── own: SynthesisRunner(ModelLifecycle)
    └── owns structured-generate lifecycle

STRUCTURED-GENERATION SIDECAR
│
└── brain/model_lifecycle.ModelLifecycle (class)
    ├── _discover_model_path()           3-tier Qwen/SmolLM discovery
    ├── structured_generate()            Outlines json_schema → primary path
    └── unload()                         QoS USER_INITIATED → BACKGROUND
```

---

## 2. Migration Matrix

### Role: runtime-wide acquire/load owner

| | Detail |
|---|---|
| **Current owner** | `brain/model_manager.py::ModelManager` — singleton, `_load_model_async()` |
| **Future owner** | ModelManager remains canonical; seam extraction to `runtime/windup_engine.py` |
| **Migration blocker** | `windup_engine.py` creates its own `ModelLifecycle()` — not wired to singleton |
| **Removal precondition** | All consumers (Hermes3Engine, windup) must use `get_model_manager()` |

### Role: runtime-wide unload/cleanup owner

| | Detail |
|---|---|
| **Current owner** | `brain/model_manager.py::ModelManager` — `_release_current_async()` + `_cleanup_memory_async()` |
| **Secondary owner** | `brain/model_lifecycle.py::unload_model()` — delegates to `engine.unload()` (7K SSOT) |
| **Future owner** | ModelManager primary; `engine.unload()` as secondary cleanup for Hermes |
| **Migration blocker** | None |
| **Removal precondition** | ModelManager must fully cover unload path |

### Role: phase/model enforcer

| | Detail |
|---|---|
| **Current owner** | `capabilities.py::ModelLifecycleManager` — `enforce_phase_models(phase_name)` |
| **Classification** | **Facade/compat shim** (Sprint 8ME) — does NOT load models directly |
| **Delegation** | Through `CapabilityRegistry.load/unload`, NOT through ModelManager |
| **PHASE_MODEL_MAP** | PLAN/DECIDE/SYNTHESIZE→Hermes, EMBED/DEDUP/ROUTING→ModernBERT, NER/ENTITY→GLiNER |
| **Future owner** | `ModelManager.with_phase()` — same logic already exists in ModelManager |
| **Migration blocker** | PHASE_MODEL_MAP duplicated between ModelManager and ModelLifecycleManager |
| **Removal precondition** | ModelLifecycleManager refactored to delegate to ModelManager.with_phase() |

### Role: structured-generation sidecar

| | Detail |
|---|---|
| **Current owner** | `brain/model_lifecycle.py::class ModelLifecycle` |
| **Model used** | Qwen2.5-0.6B or SmolLM2-135M (separate from Hermes/ModernBERT/GLiNER) |
| **Generation paths** | Outlines json_schema dict (primary) → mlx_lm.generate + regex fallback |
| **Future owner** | ModelLifecycle remains; windup-local isolation is intentional |
| **Migration blocker** | None — windup-local is by design |
| **Removal precondition** | N/A |

### Role: windup-local model world

| | Detail |
|---|---|
| **Current owner** | `runtime/windup_engine.py` — creates own `ModelLifecycle()` + `SynthesisRunner` |
| **Future owner candidate** | Seam extraction → shared `ModelManager` singleton |
| **Migration blocker** | Circular import risk: `windup_engine.py` cannot directly import `ModelManager` |
| **Removal precondition** | Resolve: how to share singleton without circular deps |

---

## 2b. Phase/Model Mapping Drift — Three Independent Phase Systems (Sprint 8TF)

**KRITICKÝ NÁLEZ:** Existují TŘI ODLIŠNÉ phase naming systémy, které NIKDY nemapují 1:1.

| Phase System | Zdroj | Fáze | Model(y) | Poznámka |
|---|---|---|---|---|
| **Workflow-level** (Layer 1) | `ModelManager.PHASE_MODEL_MAP` | PLAN | hermes | workflow精细 |
| | | DECIDE | hermes | |
| | | SYNTHESIZE | hermes | liší se od coarse-grained SYNTHESIS |
| | | EMBED | modernbert | |
| | | DEDUP | modernbert | |
| | | ROUTING | modernbert | |
| | | NER | gliner | |
| | | ENTITY | gliner | |
| **Coarse-grained** (Layer 2) | `capabilities.py::enforce_phase_models()` | BRAIN | hermes |ÚPLNĚ jiný string |
| | | TOOLS | (release hermes) |ÚPLNĚ jiný string |
| | | SYNTHESIS | hermes | "SYNTHESIS" ≠ "SYNTHESIZE" |
| | | CLEANUP | (release all) | |
| **Windup-local** (Layer 3) | `windup_engine.py` | SYNTHESIS runner | Qwen/SmolLM | vlastní izolovaný model |
| **types.py** | `OrchestratorState` | PLANNING/BRAIN/EXECUTION/SYNTHESIS | — | vlastní strings, částečně překrývají coarse-grained |

**Závěr:** Tyto tři phase systémy jsou SEMANTICKY ODLIŠNÉ a NESMĚJÍ být smazány do jednoho.
- `capabilities.py::enforce_phase_models()` používá coarse-grained (BRAIN/TOOLS/SYNTHESIS/CLEANUP)
- `ModelManager.PHASE_MODEL_MAP` používá workflow-level (PLAN/DECIDE/SYNTHESIZE/EMBED/...)
- `windup_engine.py` používá vlastní SYNTHESIS runner s Qwen modelem

---

## 3. Internal Role Split — `brain/model_lifecycle.py`

| Role | Function/Class | Note |
|---|---|---|
| **Unload helper** | `unload_model()` | Delegates to `engine.unload()` (7K SSOT), fail-open |
| **Emergency seam** | `request_emergency_unload()`, `is_emergency_unload_requested()`, `set_emergency_callback()` | Watchdog flag + safe callback pattern |
| **Lifecycle shadow-state** | `_lifecycle_state`, `_current_model_ref`, `get_model_lifecycle_status()` | O(1), side-effect free |
| **MLX lazy init** | `_get_mlx()`, `ensure_mlx_runtime_initialized()` | Delegates to `mlx_cache.init_mlx_buffers()` |
| **Preload hint** | `preload_model_hint()` | Placeholder for future predictive preload |
| **Structured-generation sidecar** | `class ModelLifecycle` | Qwen/SmolLM, windup-local, async `structured_generate()` + `unload()` |

---

## 4. Canonical Owners — Final Classification

| Component | Classification | Reason |
|---|---|---|
| `ModelManager` (singleton) | **Canonical owner** | Single acquire/load/unload instance |
| `capabilities.ModelLifecycleManager` | **Facade/compat shim** | Does NOT load directly; orchestrates via CapabilityRegistry |
| `brain/model_lifecycle.py::ModelLifecycle` | **Sidecar** | Windup-local, legitimate isolation |
| `brain/model_lifecycle.py::unload_model()` | **Donor helper** | 7K SSOT delegator, fail-open |
| `root model_lifecycle.py` | **Deprecated re-export stub** | `from brain.model_lifecycle import *`, dormant |

---

## 5. Pre-Seam Scaffold (Sprint 8ME)

**What was added:** Authority note in `capabilities.py::ModelLifecycleManager.__doc__`

**What was NOT added (guardrails respected):**
- No new model abstraction
- No new subsystem
- No consumer rewiring
- No changes to `runtime/windup_engine.py`, `__main__.py`, `runtime/sprint_scheduler.py`

**Minimal compatibility alias:** `root model_lifecycle.py` remains as deprecated re-export stub (no change needed).

---

## 5b. Phase Drift Guard (Sprint 8TF)

**What was added:**
- Phase layer authority notes in all three key modules
- `brain/model_phase_facts.py` — tiny pure facts helper (Sprint 8TF)

**Tiny pre-seam helper (`brain/model_phase_facts.py`):**
- Pure facts: `WORKFLOW_PHASES`, `COARSE_GRAINED_PHASES` frozensets
- `get_phase_layer(phase)` → 1 (workflow) / 2 (coarse) / 0 (unknown)
- `is_workflow_phase()`, `is_coarse_grained_phase()`, `is_same_layer()`
- NO new model subsystem, NO orchestrating class, NO cross-plane API

**What was NOT added (guardrails respected):**
- No runtime/windup_engine.py changes
- No new model subsystem
- No __main__.py or sprint_scheduler.py changes
- No consumer rewiring
- No unified phase map

**Drift risks explicitly documented:**
- `SYNTHESIZE` (Layer 1) vs `SYNTHESIS` (Layer 2) — false equivalence
- `PLAN` (Layer 1) vs `BRAIN` (Layer 2) — false equivalence
- `EMBED` (Layer 1) vs `TOOLS` (Layer 2) — false equivalence

**Authority note locations (Sprint 8TF):**
| File | Location | Note |
|------|----------|------|
| `brain/model_manager.py` | `PHASE_MODEL_MAP` comment | Layer 1 authority |
| `capabilities.py` | `ModelLifecycleManager.__doc__` | Three Phase Layers + drift risk |
| `brain/model_lifecycle.py` | module docstring | Phase Layers warning |
| `brain/model_phase_facts.py` | module docstring | Pre-seam scaffold purpose |

---

## 6. types.py OrchestratorState — Fourth Phase System

`types.py::OrchestratorState` has its own strings: `IDLE/PLANNING/BRAIN/EXECUTION/SYNTHESIS/ERROR`.

- `PLANNING` ≠ `PLAN` (different string)
- `SYNTHESIS` coincidentally matches Layer 2 `SYNTHESIS` (different semantics)
- `BRAIN` coincidentally matches Layer 2 `BRAIN` (different semantics)

This is a **fourth** phase namespace — should NOT be conflated with any of the three layers above.
Consumers needing to compare OrchestratorState values with model phases should use `model_phase_facts` helpers.

---

## 7. Seam Extraction Pre-conditions (`runtime/windup_engine.py`)

| # | Pre-condition | Status |
|---|---|---|
| 1 | ModelManager singleton accessible to `windup_engine` without circular imports | **Not resolved** |
| 2 | `windup_engine` stops creating its own `ModelLifecycle()` | **Not resolved** — `run_windup()` calls `SynthesisRunner(ModelLifecycle())` |
| 3 | Unified unload path — windup uses same unload as ModelManager | **Not resolved** — `_lifecycle.unload()` vs `ModelManager._cleanup_memory_async()` |
| 4 | Phase enforcer (ModelLifecycleManager) refactored to delegate to ModelManager | **Not resolved** — PHASE_MODEL_MAP duplication |

---

## 8. Root `model_lifecycle.py` — Stub Analysis

```python
# DEPRECATED — use brain.model_lifecycle
from brain.model_lifecycle import *  # noqa: F401, F403
__all__ = []  # prevent accidental star-imports
```

**Status:** Clean re-export stub. No cleanup needed. Dormant — does not affect runtime.
**Authority:** Does not need an authority note; its deprecation is self-explanatory.

---

## 8. Summary — Who Owns What Today

| Role | Owner |
|---|---|
| **Runtime-wide acquire/load owner** | `brain/model_manager.py::ModelManager` (singleton) |
| **Runtime-wide unload/cleanup owner** | `brain/model_manager.py::ModelManager` + `brain/model_lifecycle.py::unload_model()` (7K SSOT delegát) |
| **Phase enforcer** | `capabilities.py::ModelLifecycleManager` — **FACADE**, does NOT load directly |
| **Structured-generation sidecar** | `brain/model_lifecycle.py::class ModelLifecycle` (Qwen/SmolLM, windup-local) |
| **Windup-local model world** | `runtime/windup_engine.py` — isolated, creates own lifecycle |

---

## 9. What Still Blocks windup_engine.py Intervention

1. **Circular import risk** — `windup_engine` cannot directly import `ModelManager` singleton
2. **Isolated `ModelLifecycle()` instance** — `run_windup()` creates its own; not wired to runtime singleton
3. **Unified unload path missing** — `_lifecycle.unload()` (QoS-based) vs `ModelManager._cleanup_memory_async()` (gc+mx.clear_cache) are separate paths
4. **PHASE_MODEL_MAP duplication** — `ModelManager.PHASE_MODEL_MAP` and `ModelLifecycleManager` phase logic are not unified

## 10. Phase Layer Facts Reference (Sprint 8TF)

**Layer 1 — Workflow-level** (`ModelManager.PHASE_MODEL_MAP`):
```
PLAN, DECIDE, SYNTHESIZE → hermes
EMBED, DEDUP, ROUTING → modernbert
NER, ENTITY → gliner
```

**Layer 2 — Coarse-grained** (`ModelLifecycleManager`):
```
BRAIN → hermes loaded, others released
TOOLS → hermes released, on-demand
SYNTHESIS → hermes loaded, others released
CLEANUP → all released
```

**Layer 3 — Windup-local** (`windup_engine.SynthesisRunner`):
```
Own Qwen/SmolLM model, isolated from runtime-wide plane
```

**Fourth namespace** (`types.OrchestratorState`):
```
IDLE, PLANNING, BRAIN, EXECUTION, SYNTHESIS, ERROR
```

---

*Auditor: Claude Code / oh-my-claudecode*
*Sprint 8TF: Phase Drift Guard — authority notes + tiny pre-seam helper*
*Sprint 8ME: Pre-seam scaffold — phase enforcer facade documented*
*Sprint 8AT/8AX: Reuters seed removal, ENV BLOCKER resolved*
*Runtime/windup_engine.py NOT opened per sprint guardrails*
