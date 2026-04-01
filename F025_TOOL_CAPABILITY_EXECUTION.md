# F025: Tool / Capability / Execution Triad Inventory

**Datum:** 2026-04-01
**Složka:** `/hledac/universal/`
**Status:** Inventory scan — implicit contracts identified, gaps catalogued

---

## 1. Executive Summary

### Triad Truth Owners (dnes)

| Role | Canonical Surface | Modul |
|------|------------------|-------|
| **Capability Truth Owner** | `CapabilityRegistry` + `CapabilityRouter` + `ModelLifecycleManager` | `capabilities.py` |
| **Execution-Control Surface** | `ToolRegistry` + `execute_with_limits()` + `CostModel` | `tool_registry.py` |
| **Action Execution Backend** | `GhostExecutor` + `ActionType` enum | `execution/ghost_executor.py` |

### Klíčové nálezy

1. **GhostExecutor a ToolRegistry jsou paralelní, nesourodé systémy** — GhostExecutor používá vlastní `ActionType` enum (17 akcí), zatímco ToolRegistry používá `Tool` s Pydantic schématy. Neexistuje žádný bridging mechanismus.

2. **AutonomousAnalyzer rozhoduje o tool selection izolovaně** — `_detect_tools()` v `autonomous_analyzer.py` provádí keyword-based tool detection, ale nevolá `CapabilityRouter.route()` ani `ToolRegistry`.

3. **ModelLifecycleManager má striktní phase enforcement** — BRAIN → TOOLS → SYNTHESIS → CLEANUP lifecycle, ale ToolRegistry nemá žádné povědomí o těchto fázích.

4. **Rate limiting je duplikován** — `ToolRegistry.validate_call()` kontroluje rate limits, ale `GhostExecutor._actions` používá Python `dict` bez rate limitů.

5. **Audit trail je oddělený** — `AuditLogger` v `security/audit.py` je samostatný systém, `GhostLayer` má vlastní `_action_count`, `ToolRegistry` nemá žádný audit hook.

---

## 2. Capability Plane

### 2.1 Canonical Components

**Soubor:** `capabilities.py`

```python
# Řádek 29-71: Capability enum — 22 capabilities
class Capability(Enum):
    GRAPH_RAG = "graph_rag"
    ENTITY_LINKING = "entity_linking"
    RERANKING = "reranking"
    STEALTH = "stealth"
    TEMPORAL = "temporal"
    CRYPTO_INTEL = "crypto_intel"
    HERMES = "hermes"
    MODERNBERT = "modernbert"
    GLINER = "gliner"
    # ... 14 dalších

# Řádek 82-194: CapabilityRegistry
class CapabilityRegistry:
    _status: Dict[Capability, CapabilityStatus]
    _loaded: Set[Capability]
    register() / is_available() / load() / unload()

# Řádek 196-277: CapabilityRouter
class CapabilityRouter:
    SOURCE_CAPABILITIES: Dict[str, Set[Capability]]  # source → capabilities mapping
    DEPTH_CAPABILITIES: Dict[str, Set[Capability]]  # depth → capabilities mapping
    route(analysis, strategy, depth, profile) → Set[Capability]

# Řádek 279-369: ModelLifecycleManager
class ModelLifecycleManager:
    enforce_phase_models(phase_name: str)  # BRAIN → TOOLS → SYNTHESIS → CLEANUP
    load_model_for_task(capability: Capability)  # single-model constraint
```

### 2.2 Capability Registry Truth

| Aspekt | Status | Detail |
|--------|--------|--------|
| Registry storage | ✅ | `_status: Dict[Capability, CapabilityStatus]` |
| Lazy loading | ✅ | `loader: Callable[[], Awaitable[bool]]` |
| Availability check | ✅ | `is_available()` — cached in `_loaded` |
| Phase enforcement | ✅ | `ModelLifecycleManager.enforce_phase_models()` |
| Source-to-cap mapping | ✅ | `SOURCE_CAPABILITIES` dict |
| Depth-to-cap mapping | ✅ | `DEPTH_CAPABILITIES` dict |
| Profile-based routing | ✅ | stealth / thorough / default |
| Tool-cost integration | ❌ | Neexistuje bridge na `ToolRegistry.CostModel` |
| Audit hook | ❌ | Žádný audit při load/unload |

### 2.3 Gaps v Capability Plane

| Gap | Severity | Popis |
|-----|----------|-------|
| Chybí `CapabilityLifecycleManager` | HIGH | ModelLifecycleManager pouze modely, ne obecné capabilities |
| ToolRegistry nezná capabilities | HIGH | Duplicitní tool definitions bez capability awareness |
| Audit trail nemá capability events | MEDIUM | Load/unload není auditováno |
| No capability budgets | MEDIUM | Žádný mechanismus pro capability-based rate limiting |

---

## 3. Tool Registry / Execution-Control Plane

### 3.1 Canonical Components

**Soubor:** `tool_registry.py`

```python
# Řádek 44-79: RiskLevel + CostModel
class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class CostModel(BaseModel):
    ram_mb_est: int
    time_ms_est: int
    network: bool
    network_cost: int
    risk_level: RiskLevel
    to_hermes_hint() → dict

# Řádek 102-108: BudgetLimits
class BudgetLimits(BaseModel):
    max_ram_mb: int = 2048
    max_time_ms: int = 300000
    max_network_calls: int = 50

# Řádek 199-214: RateLimits
class RateLimits(BaseModel):
    max_calls_per_run: int
    max_parallel: int

# Řádek 222-258: Tool definition
class Tool(BaseModel):
    name: str
    description: str
    args_schema: type[BaseModel]
    returns_schema: type[BaseModel]
    cost_model: CostModel
    rate_limits: RateLimits
    handler: Callable
    to_tool_card() → hermes hint

# Řádek 266-650: ToolRegistry
class ToolRegistry:
    _tools: dict[str, Tool]
    _call_counts: dict[str, int]
    _semaphores: dict[str, asyncio.Semaphore]
    register() / get_tool() / list_tools()
    validate_args() / validate_call()
    execute_with_limits(tool_name, args, timeout_ms) → Any
    estimate_plan_cost(tool_names) → CostSummary
    get_tools_by_risk(max_risk) → list[Tool]
    get_network_tools() → list[Tool]
```

### 3.2 Execution Control Truth

| Aspekt | Status | Detail |
|--------|--------|--------|
| Tool registration | ✅ | `register()` s uniqueness constraint |
| Schema validation | ✅ | Pydantic `validate_args()` |
| Rate limit enforcement | ✅ | `validate_call()` + semaphore v `execute_with_limits()` |
| Cost estimation | ✅ | `estimate_plan_cost()` |
| Risk filtering | ✅ | `get_tools_by_risk()` |
| Hermes tool cards | ✅ | `to_tool_card()` |
| Audit trail | ❌ | Žádné audit hooks |
| Capability awareness | ❌ | Tool nemá `required_capabilities` |
| Phase awareness | ❌ | Tool execution nezná BRAIN/TOOLS/SYNTHESIS fáze |

### 3.3 Registered Tools

```python
# Z create_default_registry() — řádek 1006-1106
web_search          # CostModel(ram=50, time=2000, network=True, risk=MEDIUM)
entity_extraction   # CostModel(ram=100, time=500, network=False, risk=LOW)
academic_search     # CostModel(ram=50, time=3000, network=True, risk=MEDIUM)
file_read           # CostModel(ram=10, time=100, network=False, risk=LOW)
file_write          # CostModel(ram=10, time=100, network=False, risk=MEDIUM)
python_execute      # CostModel(ram=50, time=1000, network=False, risk=HIGH)
dns_tunnel_check    # CostModel(ram=30, time=5000, network=False, risk=LOW)
# Plus inference_engine (internal)
```

### 3.4 Gaps v Execution-Control Plane

| Gap | Severity | Popis |
|-----|----------|-------|
| Tool nemá capability requirements | HIGH | Tool ne deklaruje potřebné capabilities |
| Neexistuje tool-to-capability bridge | HIGH | `ToolRegistry` neimportuje `capabilities.py` |
| Phase-gated tool execution | HIGH | Není mechanismus pro BRAIN vs TOOLS fáze |
| Audit hooks chybí | MEDIUM | `execute_with_limits()` nemá audit logging |
| Budget enforcement | MEDIUM | `BudgetLimits` definován, ale nekontrolován |
| Hermes hints bez lifecycle context | MEDIUM | Hermesi se neposílá fáze/available caps |

---

## 4. Execution Backend Plane

### 4.1 Canonical Components

**Soubor:** `execution/ghost_executor.py`

```python
# Řádek 23-42: ActionType enum — 17 akcí
class ActionType(Enum):
    SCAN = "scan"
    GOOGLE = "google"
    DOWNLOAD = "download"
    SEARCH = "search"
    SMART_SEARCH = "smart_search"
    DEEP_READ = "deep_read"
    RESEARCH_PAPER = "research_paper"
    DEEP_RESEARCH = "deep_research"
    ANSWER = "answer"
    CRACK = "crack"
    FACT_CHECK = "fact_check"
    STEALTH_HARVEST = "stealth_harvest"
    OSINT_DISCOVERY = "osint_discovery"
    # atd.

# Řádek 62-186: GhostExecutor
class GhostExecutor:
    _actions: Dict[str, callable]  # action type → handler
    _network_driver: Optional[GhostNetworkDriver]
    _stealth_manager: Optional[StealthOrchestrator]
    _bloom_filter: Optional[ScalableBloomFilter]

    execute(action, params, context) → Dict[str, Any]
    # Akce: _action_search, _action_google, _action_deep_read,
    #        _action_archive_fallback, _action_fact_check,
    #        _action_stealth_harvest, _action_osint_discovery
```

**Soubor:** `layers/ghost_layer.py`

```python
# Řádek 35-523: GhostLayer
class GhostLayer:
    _ghost_director: Optional[GhostDirector]
    _vault: Optional[RamDiskVault]
    _loot_manager: Optional[LootManager]
    _system_context: Optional[SystemContext]

    execute_action(action_type, parameters, store_in_vault)
    _check_stagnation()  # anti-loop protection
    force_neural_cleanup()  # M1 memory guard

# Řádek 579-857: SystemContext (anti-VM)
class SystemContext:
    is_vm_environment() → bool
    force_neural_cleanup() → Dict  # MLX cache + GC
    activate_stealth_mode()
```

**Soubor:** `coordinators/execution_coordinator.py`

```python
# Řádek 62-994: UniversalExecutionCoordinator
class UniversalExecutionCoordinator:
    _ghost_director: Optional[GhostDirector]
    _parallel_executor: Optional[ParallelExecutionOptimizer]
    _ray_cluster: Optional[RayClusterManager]

    execute_action(action_type, payload)  # → GhostDirector
    execute_plan(plan)  # sequence of actions
    execute_batch(tasks, max_parallel)
    execute_with_fallback(task, fallback_chain)
    generate_with_speculative_decoding()
```

### 4.2 Execution Backend Truth

| Aspekt | Status | Detail |
|--------|--------|--------|
| Action dispatch | ✅ | `GhostExecutor._actions` dict routing |
| Async execution | ✅ | `async def execute()` |
| Network driver | ✅ | Lazy-loaded `GhostNetworkDriver` |
| Stealth mode | ✅ | `StealthOrchestrator` lazy load |
| Bloom filter dedup | ✅ | URL deduplikace |
| Anti-loop/stagnation | ✅ | `GhostLayer._check_stagnation()` |
| Fallback chain | ✅ | ghost → parallel → ray |
| Phase-gated execution | ❌ | Neexistuje |
| Capability gating | ❌ | GhostExecutor nevolá `CapabilityRegistry` |
| Rate limiting | ❌ | Používá Python dict, ne ToolRegistry semaphores |
| Audit trail | ⚠️ | `_action_count` v GhostLayer, bez perzistence |

### 4.3 Gaps v Execution Backend Plane

| Gap | Severity | Popis |
|-----|----------|-------|
| Action → Tool registry mismatch | CRITICAL | GhostExecutor má vlastní ActionType, ToolRegistry má Tool |
| Neexistuje action-to-tool mapper | CRITICAL | Nikde není definováno, že `SEARCH` = `web_search` |
| Capability gating neintegrváno | HIGH | GhostExecutor nevolá `CapabilityRegistry.is_available()` |
| Rate limiting je duplikovaný | HIGH | ToolRegistry má `validate_call()`, GhostExecutor nemá nic |
| Audit trail nesourodý | MEDIUM | GhostLayer._action_count vs AuditLogger |
| No tool cardinality enforcement | MEDIUM | GhostExecutor nemá `max_calls_per_run` |
| M1 memory pressure neovlivňuje execution | MEDIUM | `force_neural_cleanup()` existuje, ale není volán automaticky |

---

## 5. Triad Contract Gaps

### 5.1 Implicit Contracts (dnes fungující)

| Contract | Realizace |
|----------|-----------|
| Tool musí mít schema | `Tool.args_schema` (Pydantic) |
| Tool má cost model | `Tool.cost_model` |
| Tool má rate limits | `Tool.rate_limits` + semaphore |
| Model lifecycle má fáze | `ModelLifecycleManager.enforce_phase_models()` |
| Akce mají handlery | `GhostExecutor._actions` dict |
| Executor má fallback | `execute_with_fallback()` v ExecutionCoordinator |

### 5.2 Missing Contracts ( gaps mezi plane )

| Contract | Who Should Define | Who Should Enforce | Status |
|----------|-----------------|-------------------|--------|
| Tool vyžaduje Capability | `ToolRegistry` | `CapabilityRegistry` | ❌ |
| Action mapuje na Tool | `GhostExecutor` | `ToolRegistry` | ❌ |
| Tool execution respektuje fázi | `ModelLifecycleManager` | `ToolRegistry.execute_with_limits()` | ❌ |
| Tool execution auditován | `AuditLogger` | `ToolRegistry` | ❌ |
| Capability load triggeruje Tool load | `CapabilityRouter` | `GhostExecutor` | ❌ |
| Model phase gate ovlivňuje executor | `ModelLifecycleManager` | `GhostExecutor.execute()` | ❌ |
| Budget limit resetuje count | `BudgetLimits` | `ToolRegistry.validate_call()` | ❌ |

### 5.3 Policy / Tool Lookup / Action Dispatch / Action Execution Separation

| Layer | Dnes | Mělo by být |
|-------|------|-------------|
| **Policy Decision** | `AutonomousAnalyzer._detect_tools()` |CapabilityRouter.route()` |
| **Tool Lookup** | `ToolRegistry.get_tool()` | Stejné |
| **Action Dispatch** | `GhostExecutor.execute()` | Přes ToolRegistry dispatch |
| **Action Execution** | `GhostExecutor._actions` handlers | V `Tool.handler` |
| **Audit/Logging** | GhostLayer._action_count, AuditLogger (oddělené) | Unified audit hook |
| **Rate/Cost/Risk** | `CostModel` + `RateLimits` + `validate_call()` | Stejné |

---

## 6. Current Call-Site Truth

### 6.1 Entry Points

| Entry Point | Soubor | Volá |
|-------------|--------|------|
| `python -m hledac.universal` | `__main__.py` | SprintScheduler, nikoliv GhostExecutor přímo |
| SprintScheduler.run() | `runtime/sprint_scheduler.py` | Lifecycle manager, feed processing |
| `deep_research()` | `enhanced_research.py:2225` | `UnifiedResearchEngine.deep_research()` |
| `enhanced_research()` | `enhanced_research.py:2193` | `EnhancedResearchOrchestrator.research()` |

### 6.2 Capability Plane Call-Sites

| Volá | Soubor:Řádek | Volaná funkce |
|------|-------------|---------------|
| `autonomous_analyzer.py:433` | `analyze()` | `_detect_tools()` — nesourodé s `CapabilityRouter` |
| `capabilities.py:372` | `create_default_registry()` | `CapabilityRegistry.register()` |
| `capabilities.py:221` | `CapabilityRouter.route()` | `SOURCE_CAPABILITIES`, `DEPTH_CAPABILITIES` lookup |
| `capabilities.py:287` | `ModelLifecycleManager.enforce_phase_models()` | Phase transitions |

### 6.3 Tool Registry Call-Sites

| Volá | Soubor:Řádek | Volaná funkce |
|------|-------------|---------------|
| `tool_registry.py:478` | `estimate_plan_cost()` | Sumarizuje CostModel |
| `tool_registry.py:519` | `validate_call()` | Rate limit check |
| `tool_registry.py:585` | `execute_with_limits()` | Hlavní dispatch s timeout/semaphore |
| `tool_registry.py:273` | `__init__()` | `_register_inference_tool()` |
| `tool_registry.py:339` | `__init__()` | `_register_dns_tunnel_tool()` |

### 6.4 Execution Backend Call-Sites

| Volá | Soubor:Řádek | Volaná funkce |
|------|-------------|---------------|
| `ghost_layer.py:281` | `_execute_via_director()` | `GhostDirector.execute_action()` |
| `execution_coordinator.py:290` | `_execute_ghost_director()` | GhostDirector mission |
| `execution_coordinator.py:648` | `execute_action()` | GhostDirector._act() |
| `ghost_executor.py:146` | `execute()` | Handler lookup + execution |

### 6.5 Audit Call-Sites

| Volá | Soubor:Řádek | Volaná funkce |
|------|-------------|---------------|
| `audit.py:152` | `log()` | Insert do SQLite |
| `audit.py:224` | `query()` | SELECT s filtry |
| `ghost_layer.py:262` | `_action_count++` | In-memory counter |

---

## 7. Hidden Overlaps / Shadow Modules

### 7.1 Tool Definition Overlap

| GhostExecutor Action | ToolRegistry Tool | Status |
|---------------------|-------------------|--------|
| `SEARCH` | `web_search` | ❌ Nemapováno |
| `GOOGLE` | `web_search` | ❌ Nemapováno |
| `DEEP_READ` | žádný | ❌ Chybí |
| `FACT_CHECK` | žádný | ❌ Chybí |
| `STEALTH_HARVEST` | žádný | ❌ Chybí |
| `OSINT_DISCOVERY` | žádný | ❌ Chybí |

### 7.2 Rate Limiting Overlap

| Komponenta | Rate Limit Mechanism | Status |
|------------|---------------------|--------|
| `ToolRegistry` | `validate_call()` + `_semaphores` | ✅ Primární |
| `GhostExecutor` | Žádný | ❌ Stín |
| `GhostLayer` | Žádný | ❌ Stín |

### 7.3 Cost Estimation Overlap

| Komponenta | Cost Model | Status |
|------------|-----------|--------|
| `ToolRegistry` | `CostModel(ram_mb_est, time_ms_est, network, risk)` | ✅ Primární |
| `GhostExecutor` | Žádný | ❌ Stín |

### 7.4 Audit Overlap

| Komponenta | Audit Mechanism | Status |
|------------|----------------|--------|
| `AuditLogger` | SQLite + `log()` | ✅ Primární |
| `GhostLayer` | `_action_count`, `_stagnation_events` | ❌ Stín |
| `ToolRegistry` | Žádný | ❌ Stín |

### 7.5 Tool Selection Overlap

| Komponenta | Selection Method | Status |
|------------|-----------------|--------|
| `AutonomousAnalyzer` | Keyword pattern matching | ❌ Shadow — nesourodé |
| `CapabilityRouter` | SOURCE_CAPABILITIES + DEPTH_CAPABILITIES | ✅ Kanonické |
| GhostExecutor | `_actions` dict | ❌ Shadow |

---

## 8. Canonical Candidates

### 8.1 Tool Registry Canonicalizace

**Candidate:** `ToolRegistry` jako jediný registry surface

```
ToolRegistry
├── register(tool: Tool)
├── get_tool(name: str) → Tool
├── list_tools() → list[Tool]
├── execute_with_limits(name, args) → result
├── validate_call(name) → (bool, reason)
├── estimate_plan_cost(names) → CostSummary
└── get_tool_cards_for_hermes() → list[dict]
```

### 8.2 Capability Registry Canonicalizace

**Candidate:** `CapabilityRegistry` + rozšíření o tool awareness

```
CapabilityRegistry
├── register(capability, available, loader)
├── is_available(capability) → bool
├── load(capability) → bool
├── get_required_capabilities(tool_name) → Set[Capability]  # NOVÉ
├── get_tools_for_capability(capability) → Set[str]  # NOVÉ
└── route(analysis, strategy, depth, profile) → Set[Capability]
```

### 8.3 ModelLifecycleManager Canonicalizace

**Candidate:** Rozšíření pro tool gating

```
ModelLifecycleManager
├── enforce_phase_models(phase: str)  # BRAIN/TOOLS/SYNTHESIS/CLEANUP
├── get_active_models() → Set[Capability]
├── load_model_for_task(capability) → bool
├── get_enabled_tools(phase) → Set[str]  # NOVÉ — fázová brána
└── can_execute_tool(tool_name) → bool  # NOVÉ — kontrola capability + fáze
```

### 8.4 GhostExecutor Deprecation Candidate

**Candidate:** Nahrazení `GhostExecutor._actions` za `ToolRegistry`

```python
# GhostExecutor by měl delegovat na ToolRegistry
class GhostExecutor:
    def __init__(self, registry: ToolRegistry):
        self._registry = registry

    async def execute(self, action: str, params: dict, context):
        # Map action → tool name
        tool_name = self._action_to_tool.get(action, action)
        return await self._registry.execute_with_limits(tool_name, params)
```

---

## 9. Top 20 Konkrétních Ticketů

| # | Ticket | Zdroj Gap | Severity | Akce |
|---|--------|-----------|----------|------|
| 1 | GhostExecutor nemá rate limiting | Shadow overlap | CRITICAL | Přidat `ToolRegistry.validate_call()` do GhostExecutor |
| 2 | Action → Tool mapping chybí | Triad gap | CRITICAL | Vytvořit `_ACTION_TO_TOOL` dict v GhostExecutor |
| 3 | Tool nezná capability requirements | Tool-Registry gap | HIGH | Přidat `required_capabilities: Set[Capability]` do `Tool` |
| 4 | AutonomousAnalyzer nekonzistentní s CapabilityRouter | Shadow overlap | HIGH | AutonomousAnalyzer._detect_tools() má volat CapabilityRouter.route() |
| 5 | ModelLifecycleManager neovlivňuje Tool execution | Phase gap | HIGH | `enforce_phase_models()` má volat `ToolRegistry` disable/enable |
| 6 | AuditLogger nesleduje tool execution | Audit gap | HIGH | `execute_with_limits()` má volat `AuditLogger.log()` |
| 7 | BudgetLimits nekontrolovány při execute | Budget gap | MEDIUM | Přidat `BudgetLimits.can_fit(summary)` check |
| 8 | GhostLayer._action_count nemá perzistenci | Audit overlap | MEDIUM | Integrovat s AuditLogger |
| 9 | M1 memory pressure neovlivňuje executor | Memory gap | MEDIUM | Volat `SystemContext.force_neural_cleanup()` při pressure |
| 10 | Neexistuje tool execution phase gate | Phase gap | MEDIUM | Přidat `tool.phase_gates: Set[str]` do Tool |
| 11 | Neexistuje capability-based tool filter | Tool-Cap gap | MEDIUM | Přidat `ToolRegistry.get_tools_by_capability(cap)` |
| 12 | Tool nemá cost budgets per phase | Cost gap | MEDIUM | fáze × tool cost matrix |
| 13 | GhostExecutor.TODO akce neimplementovány | Incomplete impl | MEDIUM | Implementovat _action_scan, _action_download, etc. |
| 14 | dns_tunnel_check nemá audit | Audit gap | LOW | Přidat audit hook |
| 15 | inference_tool nemá capability awareness | Tool-Cap gap | LOW | Přidat `required_capabilities` |
| 16 | execute_batch nemá tool-level audit | Audit gap | LOW | AuditLogger.log() per batch item |
| 17 | Neexistuje tool timeout policy | Exec-control gap | LOW | Tool.timeout_ms vs CostModel.time_ms_est |
| 18 | RateLimits.max_parallel nekontrolováno v GhostExecutor | Rate overlap | LOW | GhostExecutor._semaphore = Semaphore(tool.rate_limits.max_parallel) |
| 19 | HERMES/MODERNBERT/GLINER capabilities nemají tool ekvivalent | Cap-Exec gap | MEDIUM | Definovat `hermes_search`, `modernbert_rerank`, `gliner_ner` tooly |
| 20 | execute_plan nemá capability check | Phase gap | MEDIUM | Před každou akcí zkontrolovat capabilities |

---

## 10. Exit Criteria

### F6 — Tool Registry & Capability Integration

| Criteria | Proof |
|----------|-------|
| `Tool.required_capabilities: Set[Capability]` přidáno do `Tool` | `grep -n "required_capabilities" tool_registry.py` |
| `ToolRegistry.execute_with_limits()` kontroluje capabilities | Přidat `is_available()` check |
| `CapabilityRouter.route()` vrací i tool names | Rozšířit return type |
| `AutonomousAnalyzer` používá `CapabilityRouter` místo shadow detection | Refaktor `_detect_tools()` |
| Test: capability unavailable → tool disabled | Unit test v `test_capability_tool_integration.py` |

### F6.5 — Execution Backend Canonicalization

| Criteria | Proof |
|----------|-------|
| GhostExecutor._ACTION_TO_TOOL map existuje | `grep -n "_ACTION_TO_TOOL" ghost_executor.py` |
| GhostExecutor deleguje na ToolRegistry pro known tools | Refaktor `execute()` |
| Rate limiting používá pouze ToolRegistry semaphores | Odstranit shadow rate limiting |
| GhostLayer audit integruje s AuditLogger | GhostLayer používá AuditLogger místo `_action_count` |
| Test: GhostExecutor.execute("web_search") → ToolRegistry | Integration test |

### F10.5 — Phase-Aware Execution Control

| Criteria | Proof |
|----------|-------|
| `ModelLifecycleManager.get_enabled_tools(phase)` existuje | `grep -n "get_enabled_tools" capabilities.py` |
| `ToolRegistry` má fázovou filtraci | `get_enabled_tools()` volána před `execute_with_limits()` |
| BudgetLimits kontrolovány v `execute_with_limits()` | Přidat `can_fit()` check |
| AuditLogger.track(tool_name, args, result) voláno | `grep -n "AuditLogger" tool_registry.py` |
| Test: BRAIN phase → TOOL executors disabled | Phase gating integration test |

---

## Recommended Dispatch Contract Implications

### Dispatch Contract: Policy → Registry → Executor

```
┌─────────────────────────────────────────────────────────────────────┐
│  POLICY DECISION                                                    │
│  AutonomousAnalyzer.analyze(query)                                 │
│  → AutoResearchProfile(tools, sources, privacy, depth, models)     │
│                                                                     │
│  SROUBOVÁNÍ:                                                        │
│  1. AutonomousAnalyzer._detect_tools()     →  CapabilityRouter.route()  │
│  2. CapabilityRouter.route()               →  Set[Capability] + Set[Tool]│
│  3. Tool.required_capabilities check       →  CapabilityRegistry.load()  │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│  TOOL REGISTRY (execution-control surface)                          │
│  ToolRegistry                                                       │
│  ├── Tool(name, args_schema, cost_model, rate_limits,               │
│  │         required_capabilities, phase_gates)                      │
│  ├── validate_call(tool_name)     → (bool, reason)                 │
│  ├── estimate_plan_cost(names)    → CostSummary                    │
│  ├── execute_with_limits(name, args, timeout_ms)                    │
│  │       ├── is_available(capabilities)   ← nový check             │
│  │       ├── validate_call()              ← rate limit              │
│  │       ├── check_budget()               ← nový check              │
│  │       ├── check_phase_gates()          ← nový check             │
│  │       ├── AuditLogger.log()            ← nový hook              │
│  │       └── semaphore.acquire() → handler() → semaphore.release() │
│  └── get_tools_by_capability(cap)  → Set[str]                      │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│  EXECUTION BACKEND (action execution)                                │
│  GhostExecutor                                                      │
│  ├── _ACTION_TO_TOOL: Dict[ActionType, str]  ← mapování             │
│  │       SEARCH         → web_search                                 │
│  │       DEEP_READ      → file_read + content_extractor             │
│  │       FACT_CHECK     → inference_tool (abductive)                │
│  │       STEALTH_HARVEST → stealth_crawler                          │
│  ├── execute(action, params, context)                              │
│  │       tool_name = _ACTION_TO_TOOL.get(action, action)            │
│  │       return await ToolRegistry.execute_with_limits(tool_name)   │
│  └── Lazy-loaded: GhostNetworkDriver, StealthOrchestrator         │
│                                                                     │
│  GhostLayer (wrapper)                                               │
│  ├── execute_action() → GhostExecutor.execute()                     │
│  ├── Anti-loop: _check_stagnation()                                 │
│  ├── Vault storage: _store_in_vault()                               │
│  └── Audit: AuditLogger.log() místo _action_count++               │
└─────────────────────────────────────────────────────────────────────┘
```

### Nové Kontrakty (konkrétní)

| Kontrakt | Definice | Enforcement |
|----------|---------|-------------|
| `Tool.required_capabilities: Set[Capability]` | Tool deklaruje potřebné capabilities | `execute_with_limits()` volá `CapabilityRegistry.is_available()` |
| `Tool.phase_gates: Set[str]` | Tool povolen pouze v určitých fázích | `ModelLifecycleManager.get_enabled_tools(phase)` |
| `_ACTION_TO_TOOL: Dict[ActionType, str]` | GhostExecutor akce → ToolRegistry tool name | GhostExecutor.execute() lookup |
| `AuditLogger.log(tool_name, args, result)` | Každé tool volání auditováno | `execute_with_limits()` volá jako poslední krok |
| `BudgetLimits.can_fit(CostSummary)` | Celkový plán musí fit do budget | Před `execute_with_limits()` v batchi |

### Implicit → Explicit Migrace

| Dnes | Po migraci |
|------|-----------|
| GhostExecutor._actions dict | `ToolRegistry` s `ActionType` mapping |
| ToolRegistry bez capability awareness | `Tool.required_capabilities: Set[Capability]` |
| AutonomousAnalyzer.shadow detection | `CapabilityRouter.route()` jednotný routing |
| GhostLayer._action_count | `AuditLogger.log()` s perzistencí |
| ModelLifecycleManager pouze modely | Rozšířen o `get_enabled_tools(phase)` |
| Rate limiting pouze v ToolRegistry | GhostExecutor deleguje na ToolRegistry semaphore |

---

## Shrnutí

**Tři pravdy dnes:**
1. **Capability truth:** `CapabilityRegistry` + `CapabilityRouter` + `ModelLifecycleManager` v `capabilities.py`
2. **Execution-control truth:** `ToolRegistry` + `execute_with_limits()` + `CostModel` v `tool_registry.py`
3. **Action execution truth:** `GhostExecutor` + `ActionType` v `execution/ghost_executor.py`

**Triáda funguje jen částečně** — ToolRegistry a GhostExecutor jsou paralelní systémy bez bridge. AutonomousAnalyzer je shadow system vůči CapabilityRouter. ModelLifecycleManager neovlivňuje Tool execution.

**Gap matrix:**
- CRITICAL: 2 (action-to-tool mapping, rate limiting shadow)
- HIGH: 5 (capability requirements, autonomous analyzer, phase gating, audit integration, budget enforcement)
- MEDIUM: 10
- LOW: 3
