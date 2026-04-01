# F025 — Context / Foundation / Control Plane Inventory

**Sprint:** F025
**Date:** 2026-04-01
**Scope:** `hledac/universal/` (FILESYSTEM BOUNDARY enforced)
**Status:** INVENTORY COMPLETE

---

## 1. Executive Summary

| Plane | Canonical Carrier | Status |
|-------|------------------|--------|
| Context | `research_context.py::ResearchContext` | ✅ HOT — primary context dataclass |
| Foundation | `utils/uma_budget.py`, `utils/mlx_cache.py`, `resource_allocator.py` | ⚠️ SPLIT — dual UMA authority |
| Control | `core/resource_governor.py`, `metrics_registry.py`, `evidence_log.py`, `tool_exec_log.py` | ⚠️ FRAGMENTED — overlapping governance |
| Diagnostics | `export/`, `evidence_log.get_summary/verify_all`, `metrics_registry.flush` | ✅ EXISTING |
| Public API | `__init__.py` (PEP 562 lazy) | ✅ EXISTS — compat shims everywhere |

**Critical finding:** Hidden split authority between `uma_budget.py` and `resource_governor.py` on UMA state truth. Both modules compute overlapping memory pressure semantics with different thresholds and no arbitration layer.

---

## 2. Context Plane

### Canonical Context Carrier: `research_context.py`

**File:** `hledac/universal/research_context.py` (~410 lines)

| Class | Type | Purpose |
|-------|------|---------|
| `ResearchContext` | Pydantic BaseModel | Primary context carrier — query, iteration, budgets, entities, hypotheses, errors |
| `BudgetState` | Pydantic BaseModel | Per-request budget: max_iterations, max_time_minutes, max_tokens, max_api_calls + consumed counters |
| `Entity` | Pydantic BaseModel | Discovered entity with entity_id, name, entity_type, confidence, source_urls |
| `Hypothesis` | Pydantic BaseModel | Research hypothesis with status, supporting/contradicting evidence |
| `ErrorRecord` | Pydantic BaseModel | Error with severity (LOW/MEDIUM/HIGH/CRITICAL), component, message, traceback |
| `EntityType` | Enum | PERSON, ORGANIZATION, LOCATION, CONCEPT, TECHNOLOGY, EVENT, SOURCE, UNKNOWN |
| `HypothesisStatus` | Enum | PENDING, TESTING, CONFIRMED, REJECTED, UNCERTAIN |
| `ErrorSeverity` | Enum | LOW, MEDIUM, HIGH, CRITICAL |

**Key methods on ResearchContext:**
- `add_entity()`, `add_hypothesis()`, `add_error()`, `add_visited_url()`
- `increment_iteration()`
- `get_entities_by_type()`, `get_pending_hypotheses()`, `get_confirmed_hypotheses()`
- `to_hermes_prompt()` → formats context for LLM
- `to_summary_dict()` → structured export dict

**Verdict:** ✅ CANONICAL — `ResearchContext` is the only first-class context carrier. All orchestrator coordinators and agents should receive a `ResearchContext` instance, not raw dicts.

### Context Consumption Points (grep evidence)

| File | Usage |
|------|-------|
| `orchestrator/research_manager.py` | Creates/updates ResearchContext per research run |
| `coordinators/research_coordinator.py` | Passes ResearchContext to sub-operations |
| `enhanced_research.py` | Uses ResearchContext for state management |
| `autonomous_orchestrator.py` | Stores evidence in ResearchContext |

**⚠️ DEPRECATION CANDIDATE:** `research_context.py` also exports `to_hermes_prompt()` which formats raw context for an LLM — this is a presentation concern that doesn't belong in a data model. Should be moved to a presenter/formatter layer.

---

## 3. Foundation Plane

**Definition:** Concurrency primitives, cache management, rate limiting, memory accounting primitives, executor pools.

### 3.1 Memory / UMA Primitives

#### `utils/uma_budget.py` (~423 lines)

**Status:** CANONICAL FOUNDATION — Unified Memory Budget Accountant (Sprint 1B)

| Symbol | Type | Purpose |
|--------|------|---------|
| `get_uma_snapshot()` | function | Full memory snapshot: system RAM + MLX active/peak/cache |
| `get_uma_usage_mb()` | function | system_used + mlx_active |
| `get_uma_pressure_level()` | function | Returns (pct, "normal"/"warn"/"critical"/"emergency") |
| `is_uma_warn()` | function | True if >= 6.0 GB |
| `is_uma_critical()` | function | True if >= 6.5 GB |
| `is_uma_emergency()` | function | True if >= 7.0 GB |
| `format_uma_budget_report()` | function | Human-readable UMA budget report |
| `UmaWatchdog` | class | Async polling watchdog with debounce callbacks (on_warn/on_critical/on_emergency) |
| `UmaWatchdogCallbacks` | class | Callback interface for UmaWatchdog |

**UMA thresholds (M1 8GB):**
```
WARN = 6.0 GB   (6,144 MB)
CRITICAL = 6.5 GB (6,656 MB)
EMERGENCY = 7.0 GB (7,168 MB)
```

**Design notes:**
- Lazy psutil import (no module-level `import psutil`)
- Lazy MLX import (`_get_mlx_core()`)
- `UmaWatchdog` polls every 0.5s, debounces callbacks 2s, runs in own asyncio.Task
- No shared state with `resource_governor.py`

**Verdict:** ✅ FOUNDATION AUTHORITY — `uma_budget.py` is the canonical UMA accountant.

#### `utils/mlx_cache.py`

**File:** `hledac/universal/utils/mlx_cache.py`

| Symbol | Type | Purpose |
|--------|------|---------|
| `get_metal_limits_status()` | function | Returns {cache_limit_bytes, wired_limit_bytes} from MLX metal surface |
| `get_mlx_cache_size_mb()` | function | Current MLX cache size in MB |
| `clear_mlx_cache()` | function | mx.metal.clear_cache() wrapper with platform guard |

**Verdict:** ✅ FOUNDATION HELPER — MLX-specific cache operations.

#### `utils/mlx_memory.py`

**File:** `hledac/universal/utils/mlx_memory.py`

Parallel/duplicate MLX memory tracking — investigation needed to determine if redundant with `mlx_cache.py`.

#### `resource_allocator.py` (~366 lines)

**File:** `hledac/universal/resource_allocator.py`

| Symbol | Type | Purpose |
|--------|------|---------|
| `ResourceAllocator` | class | Predictive RAM allocator with MLX linear regression |
| `ResourceExhausted` | exception | Raised when resources cannot be allocated |
| `ResourceBudget` | dataclass | RAM/time budget per request |
| `get_memory_pressure_level()` | function | Returns "normal"/"warn"/"critical" (duplicates uma_budget!) |
| `get_recommended_concurrency()` | function | Returns concurrency limits dict per pressure level |
| `get_adaptive_concurrency()` | function | Returns int 1-3 based on memory pressure |
| `AdaptiveSemaphore` | class | asyncio.Semaphore with adaptive limit based on memory pressure |
| `get_mlx_memory_mb()` | function | MLX cache/active memory in MB |
| `clear_mlx_cache_if_needed()` | function | Conditional MLX cache clear |

**Key constants:**
```python
MAX_CONCURRENT = 3
MAX_RAM_GB = 5.5
EMERGENCY_RAM_GB = 6.2
WARMUP_QUERIES = 5
```

**Verdict:** ⚠️ FOUNDATION + CONTROL SPLIT — `ResourceAllocator` is a foundation concurrency primitive, BUT `get_memory_pressure_level()` is a DUPLICATE of `uma_budget.get_uma_pressure_level()`. Same semantics, different module.

**Hidden authority conflict:** `get_adaptive_concurrency()` and `AdaptiveSemaphore` in `resource_allocator.py` make concurrency decisions based on memory pressure, while `UmaWatchdog` in `uma_budget.py` makes different decisions based on the same memory pressure. No arbitration layer.

### 3.2 Concurrency Primitives

#### `utils/async_utils.py`

| Symbol | Type | Purpose |
|--------|------|---------|
| `bounded_map()` | function | Map with bounded concurrency |
| `map_as_completed()` | function | Map with as-completed semantics |
| `bounded_gather()` | function | Gather with concurrency limit |
| `TaskResult` | type alias | Result of async task |

**Verdict:** ✅ FOUNDATION HELPER — standard async concurrency primitives.

#### `utils/thread_pools.py`

Thread pool executor management.

#### `utils/executors.py`

Executor pool management.

#### `utils/async_helpers.py`

Async helper utilities.

### 3.3 Rate Limiting

#### `utils/rate_limiter.py` + `utils/rate_limiters.py`

**Status:** DUPLICATE MODULES — two rate limiter implementations exist.

| File | Status |
|------|--------|
| `utils/rate_limiter.py` | Exported from `__init__.py` |
| `utils/rate_limiters.py` | Unclear if used or dead code |

**Verdict:** ⚠️ CONSOLIDATION NEEDED — determine which is canonical.

### 3.4 Bloom Filter (URL Dedup Only)

#### `utils/bloom_filter.py`

| Symbol | Type | Purpose |
|--------|------|---------|
| `BloomFilter` | class | Basic bloom filter |
| `ScalableBloomFilter` | class | ⚠️ DEPRECATED — use RotatingBloomFilter |
| `RotatingBloomFilter` | class | Bounded URL dedup only (MAX_INSERTIONS=50000) |
| `create_url_deduplicator()` | function | Factory for URL dedup bloom filter |

**Invariants enforced:**
- `RotatingBloomFilter` MAX_INSERTIONS=50000, rotation_count capped at 1000
- URL dedup ONLY via `RotatingBloomFilter` — never `Set[str]` or `ScalableBloomFilter`

**Verdict:** ✅ FOUNDATION HELPER — canonical URL dedup.

---

## 4. Control Plane

**Definition:** Runtime governance, metrics collection, audit logging, resource gate, alarms.

### 4.1 Resource Governor

#### `core/resource_governor.py` (~572 lines)

**File:** `hledac/universal/core/resource_governor.py`

| Symbol | Type | Purpose |
|--------|------|---------|
| `UMAStatus` | frozen dataclass | Unified UMA snapshot (rss_gib, system_used_gib, state, io_only) |
| `Priority` | Enum | CRITICAL, HIGH, NORMAL, LOW |
| `ResourceGovernor` | class | Async context manager for resource reservation |
| `evaluate_uma_state()` | function | Maps system_used_gib → "ok"/"warn"/"critical"/"emergency" |
| `should_enter_io_only_mode()` | function | Hysteresis-based I/O-only mode gate |
| `sample_uma_status()` | function | One-shot UMA status snapshot |
| `get_uma_telemetry()` | function | Read-only telemetry (transition counts) |
| `UMAAlarmDispatcher` | class | Push-based async callbacks on CRITICAL/EMERGENCY |
| `set_thread_qos()` | function | M1 QoS class setter via ctypes syscall |

**UMA thresholds (M1 8GB) — identical to uma_budget.py:**
```
WARN = 6.0 GiB
CRITICAL = 6.5 GiB
EMERGENCY = 7.0 GiB
HYSTERESIS_EXIT = 5.8 GiB
```

**Verdict:** ⚠️ CONTROL PLANE AUTHORITY with FOUNDATION LEAK — `evaluate_uma_state()` and `should_enter_io_only_mode()` are FOUNDATION-LEVEL pure functions that DUPLICATE `uma_budget.get_uma_pressure_level()`. The `UMAAlarmDispatcher` is a Control-plane alarm, but the state it monitors comes from a split foundation authority.

**Key structural issue:**
```
resource_governor.sample_uma_status()
  └── _get_metal_limits_status_8ab()  ← imports from utils.mlx_cache
  └── psutil.virtual_memory()         ← own psutil call
  └── _update_io_only_latch_with_lock() ← thread-safe hysteresis

uma_budget.get_uma_usage_mb()
  └── psutil.virtual_memory()         ← own psutil call
  └── get_mlx_memory_mb()             ← own MLX call
```

Both call `psutil.virtual_memory()` independently. No shared sampling.

### 4.2 Metrics Registry

#### `metrics_registry.py` (~292 lines)

**File:** `hledac/universal/metrics_registry.py`

| Symbol | Type | Purpose |
|--------|------|---------|
| `MetricSnapshot` | dataclass | Single metric snapshot with ts, name, value, labels |
| `MetricsRegistry` | class | In-memory counters/gauges + periodic JSONL flush |
| `create_metrics_registry()` | function | Factory |
| `METRIC_NAMES` | frozenset | Bounded metric name set |

**Design:**
- FLUSH_EVENTS = 100 OR FLUSH_SECONDS = 60
- MAX_SNAPSHOTS = 100 (ring buffer)
- Bounded metric names — no arbitrary labels
- JSONL persistence to `logs/metrics.jsonl`

**Verdict:** ✅ CONTROL PLANE — canonical metrics surface.

### 4.3 Evidence Log

#### `evidence_log.py` (~1297 lines)

**File:** `hledac/universal/evidence_log.py`

| Symbol | Type | Purpose |
|--------|------|---------|
| `EvidenceEvent` | Pydantic BaseModel | Event with type, payload, content_hash, chain_hash |
| `EvidenceLog` | class | Append-only evidence log with hash chain |
| `create_decision_event()` | method | Creates bounded decision ledger events |

**Event types:** tool_call, observation, synthesis, error, decision, evidence_packet

**Design:**
- Ring buffer MAX_RAM_EVENTS = 100
- JSONL persistence to `EVIDENCE_ROOT/{run_id}.jsonl`
- SQLite async batching (WAL mode, 50-record batches)
- Content hash per event + hash chain for tamper evidence
- `_trim_payload()` — strips fulltexts, stores previews only
- Shadow analytics hook for DuckDB (GHOST_DUCKDB_SHADOW=1)

**Verdict:** ✅ CONTROL PLANE — canonical evidence log.

### 4.4 Tool Exec Log

#### `tool_exec_log.py` (~343 lines)

**File:** `hledac/universal/tool_exec_log.py`

| Symbol | Type | Purpose |
|--------|------|---------|
| `ToolExecEvent` | dataclass | Tool execution event with input/output hashes |
| `ToolExecLog` | class | Append-only hash-chain log for tool invocations |

**Design:**
- NEVER stores raw tool inputs/outputs — hashes only
- SHA256 hash chain for tamper evidence
- Ring buffer MAX_RAM_EVENTS = 100
- JSONL persistence to `logs/tool_exec.jsonl`
- Batched fsync every 25 events

**Verdict:** ✅ CONTROL PLANE — forensic audit log for tools.

### 4.5 Smoke Runner

#### `smoke_runner.py` (~292 lines)

**File:** `hledac/universal/smoke_runner.py`

| Symbol | Type | Purpose |
|--------|------|---------|
| `SmokeConfig` | dataclass | Hard-coded tiny budgets (MAX_URLS=3, MAX_DEEP_READS=1, MAX_RUNTIME_SECS=20) |
| `SmokeRunResult` | dataclass | Bounded smoke run result |
| `run_smoke()` | function | Sync smoke test runner |
| `check_resume_eligibility()` | function | Check if run can be resumed |

**Verdict:** ✅ CONTROL PLANE — diagnostic probe/harness.

---

## 5. Diagnostics / Probe / Reporting Plane

### 5.1 Export Namespace

#### `export/__init__.py` + `export/markdown_reporter.py`, `jsonld_exporter.py`, `stix_exporter.py`, `sprint_exporter.py`

**File:** `hledac/universal/export/`

| Exporter | Function |
|----------|----------|
| Markdown | `render_diagnostic_markdown()`, `render_diagnostic_markdown_to_path()` |
| JSON-LD | `render_jsonld()`, `render_jsonld_str()`, `render_jsonld_to_path()` |
| STIX | `render_stix_bundle()`, `render_stix_bundle_json()`, `render_stix_bundle_to_path()` |
| Sprint | `sprint_exporter` (Sprint-specific format) |

**Shared:** `normalize_export_input()`, `normalize_report_input()`

**Verdict:** ✅ DIAGNOSTICS — canonical export surface.

### 5.2 Evidence Log Query Methods

| Method | Purpose |
|--------|---------|
| `get_summary(last_n=10)` | Formatted string summary for Hermes |
| `verify_all()` | Chain integrity verification |
| `query()` | Filtered query by event_type, confidence, timestamp |
| `get_statistics()` | Stats: total, RAM, dropped, type counts |
| `get_chain(event_id)` | Trace lineage of an event |

### 5.3 Metrics Registry Query Methods

| Method | Purpose |
|--------|---------|
| `flush(force=False)` | Force flush to disk |
| `get_summary()` | Counter/gauge counts |
| `tick()` | Capture current system metrics |

### 5.4 Tool Exec Log Query Methods

| Method | Purpose |
|--------|---------|
| `verify_all()` | Full chain verification |
| `get_head_hash()` | Current chain head |
| `get_stats()` | seq, ram_events, head_hash |

---

## 6. Public API / Facade Surface

### `__init__.py` (~597 lines)

**File:** `hledac/universal/__init__.py`

**Export strategy:** PEP 562 lazy imports via `__getattr__()` + `_LAZY_SUBPACKAGES` dict.

### 6.1 Direct (Non-Lazy) Exports

| Category | Symbols |
|----------|---------|
| Orchestrator | `AutonomousOrchestrator`, `FullyAutonomousOrchestrator`, `autonomous_research`, `create_autonomous_orchestrator` |
| Config | `UniversalConfig`, `create_config`, `load_config_from_file` |
| Types | `ResearchMode`, `OrchestratorState`, `ActionType`, `AgentState`, etc. (20+ types) |
| Research Context | `ResearchContext`, `BudgetState`, `Entity`, `EntityType`, `Hypothesis`, `HypothesisStatus`, `ErrorRecord`, `ErrorSeverity` |
| Evidence Log | `EvidenceLog`, `EvidenceEvent` |
| Capabilities | `Capability`, `CapabilityRegistry`, `CapabilityRouter`, `ModelLifecycleManager` |
| Coordinators | `UniversalCoordinator`, `UniversalResearchCoordinator`, `AgentCoordinationEngine`, `ResearchOptimizer`, `PrivacyEnhancedResearch`, etc. |
| Utils | `QueryExpander`, `ReciprocalRankFusion`, `IntelligentCache`, `RateLimiter`, `with_rate_limit` |

### 6.2 Lazy Exports (PEP 562)

| Symbol | Module | Status |
|--------|--------|--------|
| `PersistentKnowledgeLayer` | `.knowledge.persistent_layer` | LAZY — heavy (torch via graph_rag) |
| `GraphRAGOrchestrator` | `.knowledge.graph_rag` | LAZY — heavy (torch) |
| `KnowledgeGraphBuilder` | `.knowledge.graph_builder` | LAZY |
| `LightweightReranker` | `.tools` | LAZY — heavy (pandas) |
| `RustMiner` | `.tools` | LAZY |
| `SecurityGate` | `.security` | LAZY |
| `SerializedTreePlanner` | `.autonomy.planner` | LAZY |
| `IntegratedOrchestrator` | `.orchestrator_integration` | LAZY — optional dependency |
| `BudgetManager` | `.budget_manager` | LAZY — optional dependency |

### 6.3 Compatibility Aliases

| Alias | Canonical |
|-------|----------|
| `AutonomousOrchestrator` | `FullyAutonomousOrchestrator` |
| `UniversalResearchOrchestrator` | `FullyAutonomousOrchestrator` |
| `create_universal_orchestrator` | `autonomous_research` |

### 6.4 Availability Flags

| Flag | Value | Meaning |
|------|-------|---------|
| `UNIFIED_RESEARCH_AVAILABLE` | False (try/except) | UnifiedResearchEngine loaded |
| `ENHANCED_ORCHESTRATOR_AVAILABLE` | False (try/except) | Enhanced orchestrator loaded |
| `INTEGRATED_ORCHESTRATOR_AVAILABLE` | False (try/except) | IntegratedOrchestrator loaded |
| `BUDGET_MANAGER_AVAILABLE` | False (try/except) | BudgetManager loaded |
| `SUPREME_INTEGRATION_AVAILABLE` | **True** (hardcoded) | ⚠️ CONFUSING — always True despite try/except |

**⚠️ CRITICAL ISSUE:** `SUPREME_INTEGRATION_AVAILABLE = True` is hardcoded at module level regardless of whether Supreme components actually loaded. This is a living lie in the API contract.

### 6.5 Verdict: Public API

**Status:** FACADE — `__init__.py` is a facade with heavy use of lazy imports to defer heavy dependencies. The public API is real but loaded on-demand.

**Concerns:**
1. `SUPREME_INTEGRATION_AVAILABLE = True` hardcoded — API contract lie
2. Many compatibility aliases for renamed classes — creates confusion about which is current
3. Dual `FullyAutonomousOrchestrator` imports (v5 and v6 enhanced) with same class name

---

## 7. Hidden Authority Conflicts

### Conflict 1: Dual UMA State Authority

**Problem:** Two independent UMA state computations with identical thresholds.

```
uma_budget.py                    resource_governor.py
├── get_uma_pressure_level()     ├── evaluate_uma_state()
│   Returns: (pct, str)          │   Returns: str ("ok"/"warn"/"critical"/"emergency")
│   Thresholds: 6.0/6.5/7.0 GB   │   Thresholds: 6.0/6.5/7.0 GiB
│   psutil lazy import           │   psutil at module level
│   MLX lazy import             │   _get_mx() lazy
└── UmaWatchdog                  └── sample_uma_status()
    async polling 0.5s               UmaAlarmDispatcher
    debounce 2s                      async polling 5.0s
    on_warn/critical/emergency       register_callback(CRITICAL/EMERGENCY)
```

**Impact:**
- `resource_allocator.py::get_memory_pressure_level()` → calls `uma_budget.get_uma_pressure_level()`
- `resource_governor.py::evaluate_uma_state()` → independently computes same result
- `UMAAlarmDispatcher` monitors `sample_uma_status()` which calls `evaluate_uma_state()`
- `UmaWatchdog` monitors `get_uma_pressure_level()` independently

**No arbitration.** Two alarm systems watching two samplers of essentially the same hardware.

**Resolution required:** One canonical UMA sampler. Likely candidate: `uma_budget.py` (Sprint 1B, named "UnifiedMemoryBudgetAccountant") should be the FOUNDATION authority. `resource_governor.py` should delegate to it.

### Conflict 2: Adaptive Concurrency Split

**Problem:** `ResourceAllocator` and `resource_governor.py` both make concurrency decisions.

```
resource_allocator.py
├── get_adaptive_concurrency() → int 1-3
│   └── get_memory_pressure_level() → uma_budget
└── AdaptiveSemaphore
    └── asyncio.Semaphore with adaptive limit

resource_governor.py
└── ResourceGovernor.reserve() → async context manager
    └── can_afford_sync() → checks memory + GPU + thermal + ANE
```

**Impact:** `AdaptiveSemaphore` limits concurrency, but `ResourceGovernor.reserve()` gates operations independently. Two independent gates.

### Conflict 3: Rate Limiter Duplication

**Problem:** Two rate limiter modules.

```
utils/rate_limiter.py      utils/rate_limiters.py
├── RateLimiter            ├── (unknown)
├── RateLimitConfig        └── (unknown)
├── RateLimitExceeded
└── with_rate_limit()
```

**`__init__.py` exports from `rate_limiter.py` only.** `rate_limiters.py` may be dead code.

### Conflict 4: Dual MLX Memory Tracking

**Problem:** Multiple MLX memory tracking implementations.

```
uma_budget.py
└── get_mlx_memory_mb() → (active, peak, cache)

resource_allocator.py
└── get_mlx_memory_mb() → float (cache or active)

utils/mlx_cache.py
└── get_mlx_cache_size_mb(), get_metal_limits_status()

utils/mlx_memory.py
└── (parallel implementation, needs investigation)
```

---

## 8. Canonical Candidates

| Concern | Canonical Owner | Evidence |
|---------|----------------|---------|
| Context carrier | `research_context.py::ResearchContext` | Primary Pydantic model, all orchestrators use it |
| Path truth | `paths.py` | Single Source of Truth, all consumers import from here |
| UMA accounting | `utils/uma_budget.py` | Named "UnifiedMemoryBudgetAccountant", Sprint 1B |
| Config truth | `config.py::UniversalConfig` | All config flows through here |
| Evidence log | `evidence_log.py::EvidenceLog` | Only append-only evidence log |
| Tool audit | `tool_exec_log.py::ToolExecLog` | Hash-chain forensic log |
| Metrics | `metrics_registry.py::MetricsRegistry` | Prometheus-style metrics |
| Export | `export/` namespace | Markdown, JSON-LD, STIX renderers |
| Concurrency primitives | `utils/async_utils.py` | bounded_map, bounded_gather |
| URL dedup | `utils/bloom_filter.py::RotatingBloomFilter` | Invariant enforced: URL dedup ONLY via this |
| Rate limit | `utils/rate_limiter.py::RateLimiter` | Exported from `__init__.py` |

### Dormant / Deprecated / Legacy Candidates

| Symbol | File | Status | Replacement Owner | Migration Blocker |
|--------|------|--------|-------------------|-------------------|
| `utils/rate_limiters.py` | utils/ | DORMANT? | `utils/rate_limiter.py` | Unknown if used |
| `utils/mlx_memory.py` | utils/ | UNKNOWN | `utils/mlx_cache.py` or `uma_budget.py` | Investigation needed |
| `ScalableBloomFilter` | utils/bloom_filter.py | DEPRECATED | `RotatingBloomFilter` | None |
| `EnhancedAutonomousOrchestrator` alias | __init__.py | LEGACY DONOR | `FullyAutonomousOrchestrator` (v6) | None |
| `SUPREME_INTEGRATION_AVAILABLE=True` | __init__.py | COMAT | Should reflect actual load status | Hardcoded lie |
| `to_hermes_prompt()` | research_context.py | LEGACY DONOR | Should be in presenter layer | None |

---

## 9. Top 20 Konkrétních Ticketů

| # | Ticket | Type | Priority |
|---|--------|------|----------|
| 1 | Resolve dual UMA authority — `resource_governor.evaluate_uma_state()` should delegate to `uma_budget.get_uma_pressure_level()`, remove duplicate psutil calls | Authority conflict | P0 |
| 2 | Consolidate `UMAAlarmDispatcher` and `UmaWatchdog` into single alarm system with unified sampling | Overlap | P0 |
| 3 | Fix `SUPREME_INTEGRATION_AVAILABLE = True` hardcoded lie in `__init__.py` | API contract | P0 |
| 4 | Investigate `utils/mlx_memory.py` vs `utils/mlx_cache.py` — determine if duplicate | Duplication | P1 |
| 5 | Audit `utils/rate_limiters.py` — determine if dead code or still needed | Dead code | P1 |
| 6 | Remove `ScalableBloomFilter` usage — replace with `RotatingBloomFilter` everywhere | Deprecation | P1 |
| 7 | Move `to_hermes_prompt()` out of `research_context.py` into a presenter layer | Code smell | P1 |
| 8 | Unify `get_mlx_memory_mb()` across `uma_budget.py`, `resource_allocator.py`, `mlx_cache.py` — single canonical MLX memory reporter | Duplication | P1 |
| 9 | `AdaptiveSemaphore` and `ResourceGovernor.reserve()` arbitration — decide which gates concurrency and which gates resource reservation | Authority split | P2 |
| 10 | Add `paths.py::EVIDENCE_ROOT` usage audit — ensure all evidence log paths go through canonical PATHS constants | Consistency | P2 |
| 11 | `resource_allocator.get_adaptive_concurrency()` should call `uma_budget.get_uma_pressure_level()` (already does) but document the dependency explicitly | Documentation | P2 |
| 12 | Add `__init__.py` audit — count compatibility aliases, document which is current | API clarity | P2 |
| 13 | Verify `tool_exec_log.py` and `evidence_log.py` are NOT used interchangeably — clarify roles | Confusion | P2 |
| 14 | `metrics_registry.py::METRIC_NAMES` audit — ensure all metrics emitted by orchestrator are in the bounded set | Robustness | P2 |
| 15 | Add `sample_uma_status()` call INTO `uma_budget.py` so it can be the single sampler, not duplicate | Architecture | P2 |
| 16 | Document `paths.py::open_lmdb()` lock recovery contract in `paths.py` docstring | Documentation | P3 |
| 17 | Investigate `smoke_runner.py` `FullyAutonomousOrchestrator` import — does it work with v6? | Compatibility | P3 |
| 18 | `EvidenceLog.create_decision_event()` kind validation — add audit of all callers to ensure valid kinds | Robustness | P3 |
| 19 | Add deprecation warning to `ScalableBloomFilter` constructor if still instantiable | Deprecation | P3 |
| 20 | `UmaWatchdog` uses polling — consider event-driven alternative (memory pressure notifications) for M1 | Optimization | P3 |

---

## 10. Exit Criteria

### F0.25

- [ ] `uma_budget.py` confirmed as sole UMA state authority
- [ ] `resource_governor.py` DELEGATES to `uma_budget` for state, does not compute independently
- [ ] `UMAAlarmDispatcher` and `UmaWatchdog` consolidated or clearly separated with documented boundaries
- [ ] Dual MLX memory tracking resolved (pick one canonical `get_mlx_memory_mb()`)
- [ ] `SUPREME_INTEGRATION_AVAILABLE` reflects actual load status

### F0.3

- [ ] `ScalableBloomFilter` removed from `__all__` and replaced with `RotatingBloomFilter`
- [ ] `to_hermes_prompt()` moved to presenter layer
- [ ] `rate_limiters.py` audit complete — either removed or documented as canonical
- [ ] `utils/mlx_memory.py` audit complete — merged or documented as distinct

### F0.4

- [ ] `AdaptiveSemaphore` and `ResourceGovernor` concurrency gates arbitration complete
- [ ] `paths.py::EVIDENCE_ROOT` usage audit — all evidence paths through canonical constant
- [ ] `metrics_registry.py::METRIC_NAMES` coverage audit — all orchestrator metrics in bounded set
- [ ] Smoke runner compatibility with v6 orchestrator verified

### F5C

- [ ] All foundation functions (UMA, cache, concurrency) have single authoritative module
- [ ] Control plane components (governor, metrics, evidence, tool_exec) have clear separation of concerns
- [ ] Diagnostics plane (export/) has documented contract with no hidden dependencies

### F17

- [ ] `__init__.py` compatibility aliases reduced to minimum (max 3 legacy aliases)
- [ ] PEP 562 lazy loading documented and tested
- [ ] All dormant/dead code paths identified and removed or documented with removal preconditions
- [ ] Memory pressure event-driven notification (not polling) implemented as optimization

---

## What This Changes in the Master Plan

### Architectural Impact

1. **UMA State Truth is SPLIT** — The master plan assumed `uma_budget.py` was the canonical UMA authority, but `resource_governor.py` independently computes the same state. Any plan that says "uma_budget is the SSOT for memory pressure" is INCOMPLETE until F0.25 ticket #1 is resolved.

2. **Control Plane is FRAGMENTED** — The control plane was assumed to be unified under `ResourceGovernor`, but there are actually TWO independent alarm/watchdog systems (`UmaWatchdog` and `UMAAlarmDispatcher`) monitoring TWO independent samplers. This means runtime governance decisions may be inconsistent.

3. **Public API has Living Lies** — `SUPREME_INTEGRATION_AVAILABLE = True` regardless of actual state. Any code that branches on this flag may take the wrong path.

4. **Context Plane is CLEAN** — `ResearchContext` is unambiguously the canonical context carrier. No conflicts found.

5. **Foundation Plane has Hidden Splits** — Concurrency decisions are split between `ResourceAllocator`, `AdaptiveSemaphore`, and `ResourceGovernor` with no clear arbitration. The master plan should account for this three-way split.

### Recommended Plan Adjustments

1. **Before any runtime governance work:** Resolve ticket #1 (dual UMA authority) — this is a prerequisite for all control plane work.
2. **Before any public API documentation:** Fix ticket #3 (`SUPREME_INTEGRATION_AVAILABLE` hardcoded lie).
3. **The master plan's "unified surface" goal requires F0.25 first** — you cannot have a unified control plane when there are two independent alarm systems with different sampling intervals watching the same hardware.
