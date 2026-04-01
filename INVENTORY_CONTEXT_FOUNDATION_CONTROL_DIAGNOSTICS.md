# INVENTORY REPORT: Context, Foundation, Control, Diagnostics, Public API Planes
**Sprint**: INVENTORY_SCAN
**Datum**: 2026-04-01
**Scope**: `hledac/universal/` — ABSOLUTNÍ HRANICE

---

## 1. Executive Summary

Systém obsahuje **3 konkurenční implementace** `ResearchContext` napříč různými jmennými prostory, **1 helper model** (`research_context.py`), **silné oddělení** Foundation vs Control plane, a **zralou diagnostics/export** rovinu. Klíčové riziko: shadow `ResearchContext` v `coordinators/research_coordinator.py` a `orchestrator/request_router.py` — ty nejsou `research_context.py`.

---

## 2. Canonical Candidates by Plane

### 2.1 Context Plane

| Symbol | File | Canonical? | Reasoning |
|--------|------|------------|-----------|
| `ResearchContext` | `research_context.py:154` | **CANONICAL** | Pydantic model s 410 lines, re-export v `__init__.py:101`, použit v testech |
| `Entity` | `research_context.py:107` | **CANONICAL** | Sub-model ResearchContext |
| `Hypothesis` | `research_context.py:125` | **CANONICAL** | Sub-model ResearchContext |
| `BudgetState` | `research_context.py:48` | **CANONICAL** | Sub-model ResearchContext |
| `ResearchContext` | `coordinators/research_coordinator.py:60` | **SHADOW** | Jiný `@dataclass` context, NENÍ research_context.py |
| `ResearchContext` | `orchestrator/request_router.py:31` | **SHADOW** | Jiný lightweight context pro routing |

### 2.2 Foundation Plane (primitives, no business logic)

| Symbol | File | Authority |
|--------|------|-----------|
| `get_uma_snapshot` | `utils/uma_budget.py:219` | **CANONICAL** — jediná implementace |
| `get_uma_usage_mb` | `utils/uma_budget.py:157` | **CANONICAL** |
| `get_uma_pressure_level` | `utils/uma_budget.py:173` | **CANONICAL** |
| `is_uma_warn/critical/emergency` | `utils/uma_budget.py:201-216` | **CANONICAL** |
| `UmaWatchdog` | `utils/uma_budget.py:299` | **CANONICAL** — async watchdog s debounce |
| `sample_uma_status` | `core/resource_governor.py:320` | **CANONICAL** — UMAStatus factory |
| `evaluate_uma_state` | `core/resource_governor.py:256` | **CANONICAL** — threshold mapping |
| `should_enter_io_only_mode` | `core/resource_governor.py:281` | **CANONICAL** — hysteresis logic |
| `UMAAlarmDispatcher` | `core/resource_governor.py:412` | **CANONICAL** — push callbacks |
| `set_thread_qos` | `core/resource_governor.py:546` | **CANONICAL** — M1 QoS |
| `lmdb_map_size` | `paths.py:156` | **CANONICAL** — env-driven config |
| `open_lmdb` | `paths.py:188` | **CANONICAL** — lock recovery |
| `get_sprint_parquet_dir` | `paths.py:259` | **CANONICAL** |
| `get_ioc_db_path` | `paths.py:273` | **CANONICAL** |

### 2.3 Control Plane (state machines, gates, budgets)

| Symbol | File | Authority |
|--------|------|-----------|
| `ResourceGovernor` | `core/resource_governor.py:142` | **CANONICAL** — memory gatekeeper |
| `Priority` (enum) | `core/resource_governor.py:135` | **CANONICAL** |
| `UMAStatus` | `core/resource_governor.py:108` | **CANONICAL** — frozen dataclass |
| `_telemetry` (module-level) | `core/resource_governor.py:100` | **CANONICAL** — transition counters |
| `MetricsRegistry` | `metrics_registry.py:78` | **CANONICAL** — Prometheus-style |
| `ToolExecLog` | `tool_exec_log.py:87` | **CANONICAL** — hash-chain audit |
| `CapabilityRegistry` | `capabilities.py:82` | **CANONICAL** — capability tracking |
| `CapabilityRouter` | `capabilities.py:196` | **CANONICAL** — routing decisions |
| `ModelLifecycleManager` | `capabilities.py:279` | **CANONICAL** — phase enforcement |

### 2.4 Diagnostics / Probe / Export Plane

| Symbol | File | Authority |
|--------|------|-----------|
| `smoke_runner.py` | `smoke_runner.py:1` | **CANONICAL** — tiny budgets, mock_network |
| `export/__init__.py` | `export/__init__.py:1` | **CANONICAL** — namespace facade |
| `render_diagnostic_markdown` | `export/markdown_reporter.py` | **CANONICAL** |
| `render_jsonld` | `export/jsonld_exporter.py` | **CANONICAL** |
| `render_stix_bundle` | `export/stix_exporter.py` | **CANONICAL** |
| `_boot_telemetry` | `__main__.py:55` | **CANONICAL** — O(1) boot buffer |
| `get_boot_telemetry` | `__main__.py:63` | **CANONICAL** |
| `_preflight_check` | `__main__.py:77` | **CANONICAL** — graceful degradation |
| `get_runtime_status` | `__main__.py:117` | **CANONICAL** — status snapshot |

---

## 3. Authority Conflicts

### CONFLICT #1: `ResearchContext` Triple Definition
- **runtime status**: 3 různé definice v provozu
- **authority status**: `research_context.py` = canonical (declaráce v `__init__.py:101`)
- **replacement owner**: `research_context.py` — zůstává
- **removal precondition**: Odstranit shadow definice z `coordinators/research_coordinator.py:60` a `orchestrator/request_router.py:31` vyžaduje refaktoring těchto modulů na použití canonical ResearchContext

### CONFLICT #2: `UmaWatchdog` vs `UMAAlarmDispatcher`
- **runtime status**: Dvě různá UMA monitoring řešení
- **authority status**: `UmaWatchdog` (uma_budget.py:299) — Sprint 7F legacy; `UMAAlarmDispatcher` (resource_governor.py:412) — Sprint 8PC novější
- **replacement owner**: `UMAAlarmDispatcher` — novější architektura
- **removal precondition**: `UmaWatchdog` nelze odstranit dokud existují callery — nutno ověřit

### CONFLICT #3: `autonomous_orchestrator.py` facade
- **runtime status**: Deprecated facade v `autonomous_orchestrator.py:1`
- **authority status**: Legacy kód přesunut do `legacy/autonomous_orchestrator.py`
- **replacement owner**: `runtime/sprint_scheduler.py` — kanonická cesta
- **removal precondition**: Odstranit facade až všechny reference přejdou na novou cestu

---

## 4. Call-Site Truth Notes

### Evidence that `research_context.py` IS the canonical context carrier:
1. `__init__.py:101` re-exportuje `ResearchContext` z `research_context.py`
2. `__init__.py:221` opakuje export v `__all__`
3. Testy importují z `hledac.universal.research_context` (test_autonomous_orchestrator.py:7294)
4. Model má plnou implementaci: `to_hermes_prompt()`, `to_summary_dict()`, `add_entity()`, `add_hypothesis()`

### Evidence that `coordinators/research_coordinator.py:60` IS a different class:
```python
@dataclass
class ResearchContext:  # DIFFERENT from research_context.py
    query: str
    sources_used: List[str] = field(default_factory=list)
    # ... jiné fields než Pydantic model
```

### Evidence that `orchestrator/request_router.py:31` IS a different class:
```python
class ResearchContext:  # DIFFERENT from research_context.py
    def __init__(self, query: str, priority: int = 1):
        self.id = str(uuid.uuid4())
        self.query = query
        # ... lightweight routing context
```

---

## 5. Hidden Risks

### Risk #1: Shadow ResearchContext namespace pollution
- `coordinators/` a `orchestrator/` definují vlastní `ResearchContext`
- Moduly, které importují `from .research_context import` dostanou canonical verzi
- Moduly, které importují `from .coordinators.research_coordinator import ResearchContext` dostanou shadow verzi
- **Dopad**: Typová nekonzistence, možné chyby při předávání kontextu mezi vrstvami

### Risk #2: Dual UMA monitoring systems
- `UmaWatchdog` (uma_budget.py) a `UMAAlarmDispatcher` (resource_governor.py) běží paralelně
- Oba sledují UMA stav, ale různými mechanismy
- **Dopad**: Duplicitní callbacky, race conditions při hysteresis

### Risk #3: `autonomous_orchestrator.py` facade má zastaralé re-exporty
- `_for_export` v `autonomous_orchestrator.py:48-86` obsahuje symbols, které možná už neexistují v legacy modulu
- **Dopad**: Import errors pokud legacy modul nemá všechny uvedené symboly

### Risk #4: EvidenceLog a ToolExecLog jsou oddělené systémy
- `EvidenceLog` (evidence_log.py) — research evidence
- `ToolExecLog` (tool_exec_log.py) — tool execution tamper-evident log
- Oba mají hash-chain, ale nejsou propojeny
- **Dopad**: Forensic audit vyžaduje dva oddělené workflow

---

## 6. Recommended Canonical Owners

| Plane | Owner Module | Justification |
|-------|--------------|---------------|
| Context | `research_context.py` | Jediný Pydantic canonical model, re-export v __init__ |
| Foundation | `utils/uma_budget.py`, `core/resource_governor.py`, `paths.py` | Čisté funkce bez side effects |
| Control | `core/resource_governor.py`, `capabilities.py` | State machines, gates |
| Diagnostics | `smoke_runner.py`, `__main__.py` | Pre-flight, boot telemetry |
| Export | `export/__init__.py` | Namespace facade pro renderery |
| Config | `config.py`, `paths.py` | SSOT pro konfiguraci a cesty |

---

## 7. Top 15 Konkrétních Ticketů

| # | Ticket | Priority | Plane | Akce |
|---|--------|----------|-------|------|
| 1 | Odstranit shadow `ResearchContext` z `coordinators/research_coordinator.py:60` | **P0** | Context | Refaktorovat na použití `research_context.py` |
| 2 | Odstranit shadow `ResearchContext` z `orchestrator/request_router.py:31` | **P0** | Context | Refaktorovat na použití `research_context.py` |
| 3 | Deprecovat `UmaWatchdog` ve prospěch `UMAAlarmDispatcher` | **P1** | Foundation | Provést audit callerů, pak deprecate |
| 4 | Přesunout `autonomous_orchestrator.py` facade do legacy/ | **P1** | Control | Sprint 8VC již označeno za legacy |
| 5 | Sloučit `MetricsRegistry` a `ToolExecLog` do jednoho rozhraní | **P2** | Diagnostics | Zvážit common base pro forensic export |
| 6 | Ověřit že `EvidenceLog` používá canonical `ResearchContext` | **P2** | Context | grep audit importů |
| 7 | Přidat type hints pro `get_runtime_status` návratový typ | **P2** | Diagnostics | `TypedDict` nebo `Protocol` |
| 8 | Zkontrolovat `paths.py` vs `config.py` konzistenci | **P2** | Foundation | HAMADA TEST — `RAMDISK_ROOT` vs `vault_path` |
| 9 | Přidat `research_context.py` do `__all__` v `__init__.py` | **P3** | Context | Explicitnější API |
| 10 | Dokumentovat `smoke_runner.py` jako diagnostics entry point | **P3** | Diagnostics | Přidat docstring s příkladem |
| 11 | Deprecovat `model_lifecycle.py` — obsahuje pouze 2 řádky | **P3** | Control | Zbytkový kód z Sprint 8VC |
| 12 | Provést audit `legacy/` importů — ověřit že nic neimportuje z legacy | **P1** | Control | `sys.path` exclude funguje (Sprint 8VC) |
| 13 | Přidat `BudgetState` do `__all__` exportu | **P3** | Context | Sub-model důležitý pro external usage |
| 14 | Ověřit že `_preflight_check` se volá z `__main__.py` | **P3** | Diagnostics | Grep audit call sites |
| 15 | Přidat graceful degradation testy pro `UMAAlarmDispatcher` | **P2** | Control | Mock psutil failure |

---

## 8. Exit Criteria for Phases

### F0.25 — Context Isolation Complete
- [ ] `coordinators/research_coordinator.py:60` — `ResearchContext` refaktorován
- [ ] `orchestrator/request_router.py:31` — `ResearchContext` refaktorován
- [ ] Všechny importy `ResearchContext` jdou přes `research_context.py`
- [ ] Test: `pytest tests/test_autonomous_orchestrator.py::test_research_context_doesnt_emit_class_config_warnings` PASS

### F0.4 — Foundation/Control Boundary Secured
- [ ] `UmaWatchdog` deprecated, `UMAAlarmDispatcher` jediný monitoring
- [ ] `ResourceGovernor` má jasné hranice s `uma_budget.py`
- [ ] `CapabilityRegistry` plně integrován s `ModelLifecycleManager`
- [ ] Test: `pytest hledac/universal/ -m unit -q` PASS

### F5C — Diagnostics/Export Complete
- [ ] `smoke_runner.py` má dokumentovaný CLI entry point
- [ ] `export/__init__.py` obsahuje všechny renderery (markdown, jsonld, stix)
- [ ] `_preflight_check` volán z `__main__.py` entry point
- [ ] `_boot_telemetry` ring buffer plně funkční
- [ ] Test: `pytest tests/probe_8vd/ -q` PASS

### F17 — Public API Stabilization
- [ ] `__init__.py` re-exports jsou konsistentní
- [ ] `autonomous_orchestrator.py` facade plně přesunuta do legacy/
- [ ] Všechny `__all__` declaration jsou validní (import proof)
- [ ] Lazy exports (`__getattr__`) plně dokumentované
- [ ] Test: Import audit probe PASS

---

## What This Changes in the Master Plan

1. **Context plane clarification**: `research_context.py` je canonical — všechny ostatní `ResearchContext` definice jsou technický dluh vyžadující refaktoring

2. **Foundation/Control oddělení je funkční**: `uma_budget.py` + `paths.py` = pure foundation; `resource_governor.py` + `capabilities.py` = control

3. **Dual UMA monitoring je riziko**: `UmaWatchdog` a `UMAAlarmDispatcher` běží paralelně — nutná konsolidace

4. **Legacy burial je dokončeno**: `autonomous_orchestrator.py` je facade, skutečná implementace v `legacy/`

5. **Diagnostics rovina je zralá**: `smoke_runner.py`, `__main__.py` pre-flight, `export/` renderers — všechny konzistentní

6. **Config/Paths SSOT**: `paths.py` je jediný zdroj truth pro runtime paths; `config.py` je jediný zdroj pro application config
