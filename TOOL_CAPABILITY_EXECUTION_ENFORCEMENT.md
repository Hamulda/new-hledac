# Tool Capability Execution Enforcement — Sprint 8VF

## Bird's Eye View

### Execution Plane Authority Matrix (Sprint 8VF)

| Komponenta | Role | Canonical? | Donor/Compat? | Audit? |
|------------|------|------------|---------------|--------|
| `ToolRegistry` | Execution control + capability enforcement | ✅ **ANO** | ❌ | ❌ |
| `GhostExecutor` | Legacy action executor (ActionType-based) | ❌ | ✅ **ANO** | ❌ |
| `ToolExecLog` | Hash-chain audit pro tool invocations | ❌ | ❌ | ✅ **ANO** |
| `CapabilityRouter` | Signal → Capability mapping (doporučení, ne enforcement) | ❌ | ❌ | ❌ |

### Component Boundaries

```
ToolRegistry (canonical)
├── execute_with_limits(available_capabilities=...) — capability gate
├── check_capabilities() — enforcement hook
├── validate_call() — rate limit check
└── _execute_handler() — async/sync handler dispatch
    ⚠️ NO audit/logging — use ToolExecLog for that

GhostExecutor (donor/compat)
├── execute(action, params) — SEPARATE execution path
├── ActionType enum (NOT Tool model)
├── _actions dict (NOT _tools registry)
└── ⚠️ NOT canonical — migration candidate

ToolExecLog (audit)
├── log() — append-only hash-chain event
├── ToolExecEvent.correlation — run_id, branch_id, provider_id, action_id
└── ⚠️ NOT execution authority — instrumentation only

CapabilityRouter (signal mapping)
├── route(AnalyzerResult/dict) → Set[Capability]
└── ⚠️ Recommendation only — no enforcement here
```

### Role Seams (Sprint 8VF)

```
GhostExecutor.execute()
    ↓ SEPARATE PATH (not through ToolRegistry)
    ↓ ActionType handlers live here
    ↓ Migration target: ToolRegistry as Tool handlers

ToolRegistry.execute_with_limits()
    ↓ CANONICAL (all tool execution goes here)
    ↓ check_capabilities() gate
    ↓ Rate limits enforced
    ↓ Future: wrapped by ToolExecLog for correlation

ToolExecLog.log()
    ↓ AUDIT ONLY (wrap ToolRegistry calls)
    ↓ Hash-chain for tamper-evidence
    ↓ correlation dict for run/branch/action tracking
```

---

## Bird's Eye View (Legacy — Probes Still Valid)

### Current Triad State (Post-Sprint 8TD)

```
┌─────────────────────────────────────────────────────────────────────┐
│  AutonomousAnalyzer                          (analyzer)            │
│  - AutonomousAnalyzer.analyze() → AutoResearchProfile               │
│  - AutoResearchProfile → AnalyzerResult (from_profile)             │
│  - AnalyzerResult.to_capability_signal() → capability signal dict   │
│  STATUS: ✅ Full output shape exists                              │
└────────────────────────────┬────────────────────────────────────────┘
                           │ AnalyzerResult
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  CapabilityRouter                                (router)           │
│  - route(AnalyzerResult) → Set[Capability]                         │
│  - TOOL_CAPABILITIES: tool → required capabilities mapping         │
│  - SIGNAL_KEYS: canonical capability signal interface               │
│  STATUS: ✅ Produces usable capability set                         │
└────────────────────────────┬────────────────────────────────────────┘
                           │ Set[Capability]
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ToolRegistry                                    (registry/execution) │
│  - Tool.required_capabilities: populated for representative tools   │
│  - check_capabilities(tool, available_caps) → pass/fail             │
│  - execute_with_limits(..., available_capabilities=...) → enforced│
│  STATUS: ✅ Real enforcement hook with end-to-end probe tests     │
│           ⚠️  None-skip emits DeprecationWarning (Sprint 8SG)     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Call-Site Propagation Matrix

### Confirmed Call-Sites (Real Usage)

| File | Function | Uses execute_with_limits | Passes available_capabilities | Status |
|------|----------|-------------------------|-------------------------------|--------|
| `legacy/autonomous_orchestrator.py:20074` | `_ToolRegistryManager.execute()` | ✅ Yes | ❌ `None` (legacy) | **OUT OF SCOPE** — legacy code |
| `coordinators/performance_coordinator.py:612` | `AsyncOptimizer.execute_with_limits()` | ✅ Yes (local) | N/A (local method) | **OUT OF SCOPE** — different class |

### No Real Call-Sites (Scaffold Only)

| File | Function | Uses ToolRegistry | Notes |
|------|----------|-------------------|-------|
| `discovery/ti_feed_adapter.py` | `register_task()` | ✅ Uses decorator | Task registration only, NOT execution |
| `runtime/sprint_scheduler.py:1081` | `get_task_handler()` | ✅ Uses lazy load | Returns handler, NOT execution |
| `brain/inference_engine.py:2345,2361` | `create_inference_tool()` | ✅ Imports Tool class | Creates Tool, doesn't execute |

**Conclusion**: `execute_with_limits(..., available_capabilities=...)` has ZERO real call-sites in non-legacy, non-scheduler code. The enforcement hook exists but is not yet wired into any production call-site.

---

## One-Call-Site Wiring Matrix (Sprint 8TD Finding)

| Candidate | Blast Radius | Safety | Verdict |
|-----------|-------------|--------|---------|
| `runtime/sprint_scheduler.py` | HIGH | ❌ FORBIDDEN | Guardrail: nesahej na scheduler |
| `__main__.py` | HIGH | ❌ FORBIDDEN | Guardrail: nesahej na __main__ |
| `enhanced_research.py` | HIGH | ❌ FORBIDDEN | Guardrail: nesahej na enhanced |
| `windup_engine.py` | HIGH | ❌ FORBIDDEN | Guardrail: nesahej na windup |
| `legacy/autonomous_orchestrator.py` | MEDIUM | ⚠️ Legacy | Legacy code, mimo scope migrace |
| `execution/ghost_executor.py` | MEDIUM | ✅ Safe | Donor/compat, ne executor authority |
| `tool_exec_log.py` | LOW | ✅ Safe | Instrumentace, ne executor |

**No safe primary call-site exists in non-legacy, non-scheduler, non-stealth-heavy code.**

**Sprint 8TD Decision**: Instead of wiring a suboptimal call-site, sprint focuses on:
1. None-skip containment verification (already done Sprint 8SG)
2. Test suite hardening proving the full canonical path works
3. Bypass debt matrix formalization
4. Enforcement doc update for future scheduler integration

---

## End-to-End Enforcement Path (Verified by Probe Tests)

The complete path is verified by `tests/probe_8se/test_capability_enforcement.py`:

```
AnalyzerResult.from_profile(profile)
    ↓
AnalyzerResult.to_capability_signal()  → signal dict
    ↓
CapabilityRouter.route(signal_or_analyzer_result)  → Set[Capability]
    ↓
[convert Capability enum to string set]
    ↓
ToolRegistry.execute_with_limits(
    tool_name,
    args,
    available_capabilities={"reranking", "entity_linking"}
)
    ↓
ToolRegistry.check_capabilities(tool_name, available_caps)
    ↓
RuntimeError("Capability check failed: Tool 'academic_search' requires...")
```

**Verified by these probe tests:**
- `test_analyzer_result_to_capability_signal_*` — AnalyzerResult signal production
- `test_capability_router_route_analyzer_result_*` — Router produces correct caps
- `test_check_capabilities_pass` / `test_check_capabilities_fail` — Registry gate works
- `test_execute_with_limits_enforces_capabilities` — Full execution path blocked
- `test_execute_with_limits_skips_when_none` — None-skip backward compat
- `test_e2e_analyzer_to_registry_success` — **End-to-end success case**
- `test_e2e_analyzer_to_registry_capability_fail` — **End-to-end fail case**
- `test_e2e_analyzer_to_registry_none_skip_compat` — **None-skip compat case**

---

## None-Skip Containment (Sprint 8SG)

### Mechanism
```python
# tool_registry.py:648-665
if available_capabilities is not None:
    satisfied, reason = self.check_capabilities(tool_name, available_capabilities)
    if not satisfied:
        raise RuntimeError(f"Capability check failed: {reason}")
else:
    # Sprint 8SG: None-skip deprecation warning (controlled compat debt)
    import warnings
    warnings.warn(
        f"[TOOL REGISTRY] execute_with_limits(tool_name={tool_name!r}, "
        f"available_capabilities=None) — capability check SKIPPED. "
        f"This is backward-compatible None-skip. "
        f"Tool '{tool_name}' requires capabilities: {tool.required_capabilities}. "
        f"Pass available_capabilities as explicit set to enable enforcement.",
        DeprecationWarning,
        stacklevel=2,
    )
```

### Debt Status: Contained

| Item | Status | Evidence |
|------|--------|----------|
| None-skip warning | ✅ **DONE** (Sprint 8SG) | `test_none_skip_emits_deprecation_warning` |
| Warning contains required capabilities | ✅ **DONE** (Sprint 8SG) | `test_none_skip_warning_contains_required_capabilities` |
| None-skip compat path preserved | ✅ **DONE** (Sprint 8SG) | `test_none_skip_still_allows_compat_path` |
| None-skip detection via tests | ✅ Via tests | All `TestNoneSkipWarning` tests pass |

**Impact**: Any call-site passing `None` for `available_capabilities` now receives a clear DeprecationWarning indicating:
1. What tool is being called without capability enforcement
2. What capabilities that tool requires
3. How to fix it (pass explicit capability set)

---

## GhostExecutor Containment (Donor/Compat)

### Verified Boundaries

| Item | Status | Evidence |
|------|--------|----------|
| GhostExecutor NOT in ToolRegistry | ✅ Verified | `test_ghost_executor_not_in_tool_registry_canonical` |
| DONOR/COMPAT role in docstring | ✅ Present (Sprint 8VF) | `ghost_executor.py:62-84` |
| REMOVAL CONDITION documented | ✅ Added (Sprint 8VF) | Removal when all actions migrated to Tool |
| Separate action model | ✅ Verified | ActionType enum vs Tool model |
| Not referenced as canonical | ✅ Verified | Docs say "ToolRegistry is canonical" |
| GhostExecutor remains donor/compat | ✅ Enforced | Intentional boundary for future migration |

### Removal Condition (Sprint 8VF)

GhostExecutor je kandidát na deprecaci AŽ KDYŽ:
1. Všechny GhostExecutor akce (SCAN, GOOGLE, DEEP_READ, STEALTH_HARVEST, OSINT_DISCOVERY...) jsou migrtovány do ToolRegistry jako Tool handlery
2. Všechny call-sites používají ToolRegistry.execute_with_limits() místo GhostExecutor.execute()
3. GhostNetworkDriver, StealthOrchestrator jsou začleněny jako dependency injection přes ToolRegistry

### Future Owner (Sprint 8VF)

Future owner GhostExecutor komponent:
- **Pokud se migrace provede:** ToolRegistry převezme všechny akce jako Tool handlery
- **Pokud se migrace NEprovádí:** GhostExecutor zůstává jako izolovaný donor/compat backend, žádná nová integrace

### Surface Overlap (Documented, Not Fixed)

GhostExecutor actions like `stealth_harvest`, `osint_discovery` COULD be implemented as ToolRegistry tools in the future, but this would require:
1. Migrating from `ActionType` enum to `Tool` model
2. Registering handlers in `ToolRegistry`
3. Updating call-sites to use `execute_with_limits` instead of `GhostExecutor.execute()`

**This is intentional debt — not fixed in this sprint per guardrails.**

---

## Bypass Debt Matrix (Sprint 8TD)

| Bypass | Location | Why | Severity | Precondition |
|--------|----------|-----|----------|-------------|
| `execute_with_limits(None)` | `tool_registry.py:648` | Backward compat | **MEDIUM** | Warning now emitted (8SG) |
| GhostExecutor bypass | `ghost_executor.py` | Legacy compat | MEDIUM | Migrate to Tool-based |
| Scheduler bypass | `runtime/sprint_scheduler.py` | Guardrail | HIGH | Scheduler sprint |
| Legacy orchestrator | `legacy/autonomous_orchestrator.py:20074` | Legacy code | MEDIUM | Full migration |
| tool_exec_log candidate | `tool_exec_log.py` | Instrumentace, not executor | LOW | Future: wrap ToolRegistry calls |

### Why No Primary Call-Site Was Wired

| Candidate | Risk | Guardrail | Notes |
|-----------|------|-----------|-------|
| sprint_scheduler | HIGH blast | FORBIDDEN | Nesahej na scheduler |
| __main__ | HIGH blast | FORBIDDEN | Nesahej na __main__ |
| windup_engine | HIGH blast | FORBIDDEN | Nesahej na windup |
| enhanced_research | HIGH blast | FORBIDDEN | Nesahej na enhanced |
| legacy orchestrator | MEDIUM blast | Legacy scope | Mimo scope migrace |
| GhostExecutor | MEDIUM blast | Donor/compat | Ne executor authority |
| tool_exec_log | LOW blast | Instrumentace | Instrumentuje, neexecutuje |

---

## What Is Now Truly Enforced (vs. Scaffold)

| Item | Before | After | Evidence |
|------|--------|-------|----------|
| `check_capabilities()` method | ✅ Exists | ✅ Works | `test_check_capabilities_pass/fail` |
| `execute_with_limits()` capability gate | ✅ Hook exists | ✅ Tested | `test_execute_with_limits_enforces_capabilities` |
| Representative tools populated | ✅ 3 tools | ✅ Same | `test_required_capabilities_populated` |
| None-skip backward compat | ✅ Exists | ✅ Preserved | `test_none_skip_still_allows_compat_path` |
| None-skip deprecation warning | ❌ None | ✅ **Added** | `test_none_skip_emits_deprecation_warning` |
| End-to-end probe tests | ❌ None | ✅ Added | `TestEndToEndEnforcement` class (8 tests) |
| Real call-site propagation | ❌ None | ❌ None | Zero production call-sites |
| Bypass debt matrix formalization | ❌ None | ✅ **Formalized** | Updated in this sprint |
| GhostExecutor donor/compat boundary | ✅ Docstring | ✅ REMOVAL CONDITION + BOUNDARY SEAMS (Sprint 8VF) | `ghost_executor.py:62-84` |
| GhostExecutor future owner | ❌ None | ✅ **Added** (Sprint 8VF) | ToolRegistry as migration target |
| ToolExecLog correlation boundary | ✅ Docstring | ✅ **Clarified** (Sprint 8VF) | Correlation dict (run_id, branch_id, provider_id, action_id) |
| ToolRegistry canonical role seams | ✅ Docstring | ✅ **Explicit DO/DON'T** (Sprint 8VF) | `tool_registry.py:279-306` |

---

## What Changed in Sprint 8TD

### 1. Call-Site Audit
- Audited ALL call-sites that use `execute_with_limits()`
- ZERO safe primary call-sites found outside legacy/scheduler/stealth-heavy code
- Documented why no wiring was possible without violating guardrails

### 2. Bypass Debt Matrix Formalization
- Expanded bypass matrix to include `tool_exec_log` candidate
- Documented why each candidate is in/out of scope
- GhostExecutor boundary re-confirmed as donor/compat

### 3. Documentation Update
- Updated `TOOL_CAPABILITY_EXECUTION_ENFORCEMENT.md` with:
  - Sprint 8TD status and findings
  - One-call-site wiring matrix (all candidates documented)
  - Bypass debt matrix with formalization
  - Next steps for future scheduler integration

---

## Where Enforcement Is Used Today

| Dimension | Answer |
|-----------|--------|
| Production enforcement | ❌ **NOT YET** — zero wired call-sites |
| Enforcement hook | ✅ **EXISTS** — `execute_with_limits(available_capabilities=...)` |
| Enforcement works | ✅ **YES** — proven by probe tests |
| None-skip containment | ✅ **DONE** — DeprecationWarning emitted |
| GhostExecutor role | ✅ **DONOR/COMPAT** — not canonical authority |
| Bypasses remaining | ⚠️ **4 documented** — see bypass debt matrix |

---

## Next Migration Step After Sprint 8VF

Before integrating with SprintScheduler dispatch:

1. **Scheduler sprint** (unblocks primary call-site wiring)
   - When scheduler is refactored, it becomes the canonical consumer
2. **Populate more `required_capabilities`** for high-priority tools
3. **GhostExecutor migration** plan (separate sprint)
   - Current state: Donor/compat, REMOVAL CONDITION documented
   - Migration target: ToolRegistry as Tool handlers
   - Until then: GhostExecutor stays isolated as legacy backend
4. **tool_exec_log integration** — wrap ToolRegistry calls for audit correlation
   - Current state: AUDIT boundary clarified (Sprint 8VF)
   - Next step: Wire ToolExecLog.log() around execute_with_limits() calls

### Sprint 8VF Done
- Execution plane je teď explicitně pojmenovaný
- Canonical/donor/audit role jsou strukturované v kódu (ne jen docs)
- REMOVAL CONDITION a FUTURE OWNER zdokumentovány
- Žádný nový framework nevznikl

---

## Files Changed in Sprint 8VF

| File | Change |
|------|--------|
| `execution/ghost_executor.py` | DONOR/COMPAT role clarified, REMOVAL CONDITION added, BOUNDARY SEAMS explicit |
| `tool_registry.py` | Canonical execution-control surface role confirmed with boundary seams |
| `tool_exec_log.py` | AUDIT boundary clarified, correlation role documented |
| `TOOL_CAPABILITY_EXECUTION_ENFORCEMENT.md` | Authority matrix, component boundaries, role seams, removal condition, future owner |

---

## What Changed in Sprint 8VF

### 1. GhostExecutor Donor/Compat Boundary Zpřesnění
- Přidán REMOVAL CONDITION: kdy GhostExecutor becomes candidate for deprecation
- Přidán BOUNDARY SEAMS: explicitně odděleno od ToolRegistry (ActionType vs Tool model, _actions vs _tools)
- Přidán FUTURE OWNER: ToolRegistry jako cíl migrace
- execute() remains SEPARATE PATH from ToolRegistry.execute_with_limits()

### 2. ToolRegistry Canonical Role Potvrzena
- Přidán explicitní docstring s DO/DON'T seznamem
- Boundary seams: execute_with_limits, check_capabilities, validate_call, _execute_handler
- Related components: GhostExecutor (donor), ToolExecLog (audit), CapabilityRouter (signal)
- NO execution framework — zůstává jednoduchý registry

### 3. ToolExecLog Korelační Boundary Čitelnější
- Přidán explicitní CORRELATION BOUNDARY section
- ToolExecEvent.correlation dict dokumentován (run_id, branch_id, provider_id, action_id)
- Execution vs Audit separation clarified: ToolRegistry executes, ToolExecLog logs
- DO NOT: execute tools here, create parallel authority, store raw data

### 4. Dokumentace Aktualizována
- Authority matrix (4-row table)
- Component boundaries (ASCII diagram)
- Role seams (Sprint 8VF section)
- Removal condition (GhostExecutor)
- Future owner (GhostExecutor → ToolRegistry)

### 5. Testy Rozšířeny
- GhostExecutor není canonical execution authority ✅
- ToolRegistry zůstává canonical execution-control surface ✅
- tool_exec_log je instrumentation, ne execution ✅
- Korelační boundary čitelnější ✅

---

## Files Changed in Sprint 8VF

| File | Change |
|------|--------|
| `tool_registry.py` | Added optional exec_logger + correlation to execute_with_limits() as canonical audit hook |
| `tool_exec_log.py` | No changes (already correct audit boundary) |
| `tests/probe_8vf/test_tool_registry_audit.py` | 17 tests covering audit integration, correlation, hash-chain, canonical surface |
| `TOOL_CAPABILITY_EXECUTION_ENFORCEMENT.md` | This update: canonical audit path, hook point, what logs, what doesn't |

---

## Canonical Execution Audit Path (Sprint 8VF)

### Bird's Eye View

**Why this is audit wrapping, not a new execution framework:**

`execute_with_limits()` was already the sole canonical execution surface. Adding optional `exec_logger` support does NOT create a second execution authority — it adds an **optional side-effect** (audit logging) that:

1. Does NOT change execution behavior when `exec_logger=None`
2. Does NOT intercept or modify tool results
3. Does NOT enforce anything (ToolExecLog is AUDIT only)
4. Fails silently if logging fails (execution continues)

This is equivalent to adding logging to a function — it doesn't create a new function.

### Execution Audit Matrix

| Scenario | exec_logger behavior | What is logged |
|----------|---------------------|-----------------|
| Success (handler returns) | `log()` called with status="success" | input_hash, output_hash, error=None |
| Error inside handler | `log()` called with status="error" | input_hash, output_hash (or error bytes), error=Exception |
| TimeoutError | `log()` called with status="error" | input_hash, output_hash=b"", error=TimeoutError |
| CapabilityError (before semaphore) | `log()` NOT called | Audit happens AFTER semaphore entry |
| RateLimitError (before semaphore) | `log()` NOT called | Same as above |

### Canonical Audit Hook Point

```
execute_with_limits(tool_name, args, ...)
    │
    ├─ capability check (before semaphore)
    ├─ rate limit check (before semaphore)
    ├─ semaphore.acquire()
    │       │
    │       ├─ [success] result = await handler()
    │       │           │
    │       │           └─ finally: exec_logger.log(..., status="success")
    │       │
    │       └─ [error] raise ... (TimeoutError or handler exception)
    │                   │
    │                   └─ finally: exec_logger.log(..., status="error")
    │
    └─ return result
```

**Hook point is inside `async with semaphore:` block, wrapped in try/except/finally.**

### What IS Logged

- `input_hash`: SHA256 of serialized args (via orjson, sorted keys)
- `output_hash`: SHA256 of serialized result (or error dict)
- `output_len`: Actual output length (bounded to 1MB)
- `status`: "success" | "error" | "cancelled"
- `error_class`: Bounded error type (only safe classes, not full exception)
- `correlation`: run_id, branch_id, provider_id, action_id (echoed from input)
- Hash chain: tamper-evidence via SHA256 chain

### What is NOT Logged

- Raw inputs/outputs (hashes only — **security boundary**)
- Full exception messages (bounded error class only)
- Sensitive payload content
- Exception stack traces

### Correlation Keys Transfer

```
caller                                    execute_with_limits()
─────────────────────────────────────────────────────────────────
correlation = {run_id, branch_id, ...} → exec_logger.log(..., correlation=correlation)
                                             │
                                             └─ Stored in ToolExecEvent.correlation
```

Correlation is passed through `execute_with_limits(correlation=...)` → `exec_logger.log(..., correlation=...)`. No new correlation creation — keys come from call-site (e.g., SprintScheduler run context).

### Why execute_with_limits() Remains the Sole Canonical Surface

1. **Same method name** — no new entry point added
2. **Same signature** (plus optional parameters) — backward compatible
3. **Same enforcement** — capability checks, rate limits unchanged
4. **Same handler dispatch** — `_execute_handler()` unchanged
5. **exec_logger is optional** — passing `None` gives identical behavior to before

### Why This Doesn't Create a Second Execution Authority

| Property | ToolRegistry | ToolExecLog |
|----------|--------------|-------------|
| Executes tools? | YES | NO |
| Enforces capabilities? | YES | NO |
| Enforces rate limits? | YES | NO |
| Owns handler dispatch? | YES | NO |
| Records audit events? | NO | YES |
| Hash-chain tamper-evidence? | NO | YES |
| Is optional side-effect? | N/A | YES |

ToolExecLog is **instrumentation**, not execution. It wraps around execution to observe, not to control.

### Correlation Transfer Without New Execution Surface

```
Before (no audit):
  ToolRegistry.execute_with_limits(tool_name, args)

After (with audit):
  ToolRegistry.execute_with_limits(tool_name, args, exec_logger=logger, correlation={...})

ToolExecLog.log() is called as side-effect, NOT as separate execution path.
```

No new execution authority. No new entry point. No framework.

### Next Steps Before Scheduler Wiring

1. **Pass exec_logger from SprintScheduler context** — SprintScheduler already has run_id, pass it as correlation
2. **Wire exec_logger into SprintScheduler.run()** — pass ToolExecLog instance to execute_with_limits calls
3. **Verify hash-chain** — run `tool_exec_log.verify_all()` after sprint completion
4. **No changes to GhostExecutor** — remains donor/compat, out of canonical audit path

---

## Files Changed in Sprint 8TD

| File | Change |
|------|--------|
| `TOOL_CAPABILITY_EXECUTION_ENFORCEMENT.md` | Updated: call-site audit, bypass debt matrix, next steps | |
