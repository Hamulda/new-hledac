# Shadow Scheduler Inputs — Sprint 8VK

## Ptačí perspektiva: Proč teď a ještě ne parity mode

**Správný čas pro shadow inputs scaffold:**
- Existují typed contracts: `ExportHandoff`, `AnalyzerResult`, `BranchDecision`, `RunCorrelation`
- Existují seams: `RunCorrelation`, `ExportHandoff`, compat export seam
- Graph capability facts existují jako `DuckPGQGraph.stats()` output
- Model/control split facts existují jako `AnalyzerResult.to_capability_signal()`
- Lifecycle je izolovaný v `SprintLifecycleManager` — lze číst bez scheduleru

**Ještě NE parity mode, protože:**
- Scheduler cutover nebyl proveden — `SprintScheduler.run()` není v `__main__.py` aktivní cestou
- Parity mode vyžaduje, aby shadow scheduler dokázal plně nahradit dnešní `__main__.py` řízení
- To vyžaduje: (a) scheduler aktivní模式, (b) parity verification, (c) rollback plán
- My jsme PŘED cutover — pouze připravujeme inputs scaffold

**Klíčový důvod:** Shadow inputs scaffold můžeme aktivovat bez změny runtime behavior. Parity mode by vyžadoval flag přepnutí a potenciální divergenci.

---

## Inventory budoucích shadow inputs

| Input | Current Producer | Current Shape | Typed/Shared Contract | Compat Seam Today | Future Owner |
|-------|-----------------|--------------|----------------------|-------------------|--------------|
| `lifecycle_snapshot` | `SprintLifecycleManager.snapshot()` | `dict` (raw) | ✅ `WorkflowPhase`, `ControlPhase`, `WindupLocalPhase` (new in 8VK) | N/A — pure read | `runtime/sprint_lifecycle.py` |
| `export_handoff` | `windup_engine.run_windup()` → `scorecard` | `dict` + `ExportHandoff.from_windup()` | ✅ `ExportHandoff` (types.py) | `scorecard["top_graph_nodes"]` | `export/COMPAT_HANDOFF.py` |
| `graph_summary` | `duckdb_store._ioc_graph.stats()` | `dict` (DuckPGQGraph) | ✅ `GraphSummaryBundle` (new in 8VK) | `scorecard["top_graph_nodes"]` | `knowledge/duckdb_store.py` |
| `graph_backend_capabilities` | `duckdb_store._ioc_graph` | backend str + feature flags | ⚠️ partial (`pgq_active`, `backend` str) | N/A | `knowledge/graph_layer.py` |
| `model/control_facts` | `AutonomousAnalyzer.analyze()` → `AnalyzerResult` | `AnalyzerResult` + `.to_capability_signal()` | ✅ `ModelControlFactsBundle` (new in 8VK) | `AutoResearchProfile.to_dict()` | `autonomous_analyzer.py` / `capabilities.py` |
| `provider_recommendation_facts` | `CapabilityRegistry` (capabilities.py) | `CapabilityStatus` dicts | ❌ NOT TYPED — compat `dict` only | N/A | `capabilities.py` (future) |
| `branch_decision_facts` | N/A (future scheduler) | `BranchDecision` (types.py) | ✅ `BranchDecision` (types.py) | N/A — future | `types.py` (already typed) |
| `top_nodes_facts` | `DuckPGQGraph.get_top_nodes_by_degree()` | `list` of node dicts | ✅ via `GraphSummaryBundle` | `scorecard["top_graph_nodes"]` | `knowledge/duckdb_store.py` |
| `ranked_parquet_path` | `windup_engine.run_windup()` | `str` path or `None` | ✅ via `ExportHandoff.ranked_parquet` | `scorecard["ranked_parquet"]` | `export/COMPAT_HANDOFF.py` |

---

## Phase systems — explicitně oddělené

### 1. `workflow_phase`
- **Canonical owner:** `SprintLifecycleManager` (`runtime/sprint_lifecycle.py`)
- **Values:** `BOOT | WARMUP | ACTIVE | WINDUP | EXPORT | TEARDOWN`
- **Rídí:** temporální postup sprintu (kdy se co děje)
- **V tomto scaffoldu:** `WorkflowPhase` dataclass (frozen)

### 2. `control_phase`
- **Canonical owner:** `SprintLifecycleManager.recommended_tool_mode()`
- **Values:** `normal | prune | panic`
- **Rídí:** resource governance (jak intenzivně se to děje)
- **V tomto scaffoldu:** `ControlPhase` dataclass (frozen)

### 3. `windup_local_phase` (pokud relevantní)
- **Canonical owner:** `windup_engine.run_windup()` — future
- **Values:** `synthesis | structured | minimal`
- **Rídí:** synthesis režim uvnitř WINDUP fáze
- **V tomto scaffoldu:** `WindupLocalPhase` dataclass (frozen)

**GUARDRAIL:** `workflow_phase`, `control_phase`, `windup_local_phase` jsou VŽDY oddělené dataclasses. NIKDY neslité do jednoho `phase` pole.

---

## Feature flag vocabulary (scaffold only, NOT activated)

| Flag | Description | Current Status |
|------|-------------|---------------|
| `legacy_runtime` | Dnešní runtime path (default) | ✅ Active |
| `scheduler_shadow` | Shadow mode — scheduler čte facts, žádné řízení | 📋 Scaffold ready |
| `scheduler_active` | Full scheduler-driven mode (future) | ❌ Not implemented |

Tyto flagi jsou pouze dokumentační v tomto scaffoldu. Aktivace půjde přes explicitní config flag.

---

## Co je hotové (8VK)

| Co | Status |
|----|--------|
| Shadow input dataclasses | ✅ `runtime/shadow_inputs.py` |
| Phase separation | ✅ `WorkflowPhase`, `ControlPhase`, `WindupLocalPhase` |
| Lifecycle collector | ✅ `collect_lifecycle_snapshot()` |
| Graph collector | ✅ `collect_graph_summary()` |
| Model/control collector | ✅ `collect_model_control_facts()` |
| Export handoff facts | ✅ `collect_export_handoff_facts()` |
| Feature flag vocabulary | ✅ `RuntimeMode` class (documentační) |
| SHADOW_SCHEDULER_INPUTS.md | ✅ Tento dokument |

---

## Co je typed

| Input | Typed Contract | File |
|-------|---------------|------|
| `lifecycle_snapshot` | ✅ `WorkflowPhase`, `ControlPhase`, `WindupLocalPhase` | `runtime/shadow_inputs.py` |
| `export_handoff` | ✅ `ExportHandoff` | `types.py` |
| `graph_summary` | ✅ `GraphSummaryBundle` | `runtime/shadow_inputs.py` |
| `model/control_facts` | ✅ `ModelControlFactsBundle` | `runtime/shadow_inputs.py` |
| `branch_decision_facts` | ✅ `BranchDecision` | `types.py` |
| `provider_recommendation` | ❌ dict only | `capabilities.py` |

---

## Co je compat

| Input | Compat Path | File |
|-------|-------------|------|
| Graph without typed graph | `duckdb_store._ioc_graph.stats()` → `GraphSummaryBundle` | `runtime/shadow_inputs.py` |
| Graph via scorecard | `scorecard["top_graph_nodes"]` → `GraphSummaryBundle.from_scorecard_top_nodes()` | `runtime/shadow_inputs.py` |
| Export without typed handoff | `scorecard` dict → `ExportHandoff.from_windup()` | `export/COMPAT_HANDOFF.py` |
| Model/control via profile | `AutoResearchProfile.to_dict()` → `ModelControlFactsBundle` | `runtime/shadow_inputs.py` |

---

## Co chybí do skutečného shadow parity mode

1. **Provider recommendation typed contract** — `CapabilityRegistry` nemá typed output, pouze `dict`
2. **BranchDecision fact collection** — `BranchDecision` existuje v types.py, ale není nikde produkovan dnes
3. **Parity verification tests** — probe testy porovnávající shadow inputs s actual runtime behavior
4. **Shadow mode activation mechanism** — žádný flag/ENV pro přepnutí do shadow režimu (správně — to přijde po cutover)
5. **Windup engine typed output** — `windup_engine.run_windup()` vrací `dict`, ne `ExportHandoff`

---

## Proč zatím není vhodné aktivovat parity mode

1. **Scheduler cutover nebyl proveden** — `SprintScheduler.run()` není v `__main__.py` aktivní cestou
2. **No rollback plan** — kdyby shadow mode selhal, není jasná cesta zpět
3. **Parity verification incomplete** — nemáme testy, které by ověřily že shadow scheduler produkuje stejné výsledky jako dnešní path
4. **Provider framework neexistuje** — `scheduler_active` režim by vyžadoval nový provider framework, který dnes neexistuje
5. **Zero-rewriting rule** — dnešní runtime nesmí být přepsán bez plné parity verifikace

---

## Změněné soubory

| Soubor | Change |
|--------|--------|
| `runtime/shadow_inputs.py` | 🆕 New — pure functions pro sběr shadow inputs |
| `SHADOW_SCHEDULER_INPUTS.md` | 🆕 New — dokumentace shadow scheduler inputs |

---

## Test/Probe Summary

Probe testy viz: `tests/probe_8vk/`

- `test_phase_systems_separated.py` — workflow_phase, control_phase, windup_local_phase jsou v oddělených polích
- `test_shadow_collectors_usable.py` — collectory lze volat bez side effects
- `test_export_handoff_as_shadow_input.py` — ExportHandoff lze použít jako shadow input
- `test_graph_summary_collector.py` — graph facts lze sbírat bez scheduleru
- `test_model_control_collector.py` — model/control facts lze sbírat z AnalyzerResult

---

## Invariants

| Test | Invariant |
|------|-----------|
| `test_phase_systems_separated` | `WorkflowPhase.phase`, `ControlPhase.mode`, `WindupLocalPhase.mode` jsou v oddělených polích |
| `test_no_new_scheduler_subsystem` | `shadow_inputs.py` nemá import na `sprint_scheduler` |
| `test_no_runtime_behavior_change` | collectory nemění žádný stav |
| `test_typed_contracts_respected` | ExportHandoff, AnalyzerResult použity kde existují |
