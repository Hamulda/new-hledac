# Tool Capability Execution Enforcement — Sprint 8TD

## Bird's Eye View

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
| INTEGRATION NOTE in docstring | ✅ Present | `ghost_executor.py:66-79` |
| Separate action model | ✅ Verified | ActionType enum vs Tool model |
| Not referenced as canonical | ✅ Verified | Docs say "ToolRegistry is canonical" |
| GhostExecutor remains donor/compat | ✅ Enforced | Intentional boundary for future migration |

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
| GhostExecutor donor/compat boundary | ✅ Docstring | ✅ Verified | `test_ghost_executor_is_donor_compat` |

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

## Next Migration Step After Sprint 8TD

Before integrating with SprintScheduler dispatch:

1. **Scheduler sprint** (unblocks primary call-site wiring)
   - When scheduler is refactored, it becomes the canonical consumer
2. **Populate more `required_capabilities`** for high-priority tools
3. **GhostExecutor migration** plan (separate sprint)
4. **tool_exec_log integration** — wrap ToolRegistry calls for audit correlation

---

## Files Changed in Sprint 8TD

| File | Change |
|------|--------|
| `TOOL_CAPABILITY_EXECUTION_ENFORCEMENT.md` | Updated: call-site audit, bypass debt matrix, next steps | |
