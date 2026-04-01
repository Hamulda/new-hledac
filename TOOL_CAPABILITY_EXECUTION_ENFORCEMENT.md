# Tool Capability Execution Enforcement — Sprint 8SF

## Bird's Eye View

### Current Triad State (Post-Sprint 8SF)

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
└─────────────────────────────────────────────────────────────────────┘
```

---

## Call-Site Propagation Matrix

### Confirmed Call-Sites (Real Usage)

| File | Function | Uses execute_with_limits | Passes available_capabilities | Status |
|------|----------|-------------------------|-------------------------------|--------|
| `legacy/autonomous_orchestrator.py:20074` | `_ToolRegistryManager.execute()` | ✅ Yes | ❌ `None` (legacy) | **OUT OF SCOPE** — legacy code |
| `performance_coordinator.py:612` | `AsyncOptimizer.execute_with_limits()` | ✅ Yes (local) | N/A (local method) | **OUT OF SCOPE** — different class |

### No Real Call-Sites (Scaffold Only)

| File | Function | Uses ToolRegistry | Notes |
|------|----------|-------------------|-------|
| `discovery/ti_feed_adapter.py` | `register_task()` | ✅ Uses decorator | Task registration only, NOT execution |
| `runtime/sprint_scheduler.py:1081` | `get_task_handler()` | ✅ Uses lazy load | Returns handler, NOT execution |
| `brain/inference_engine.py:2345,2361` | `create_inference_tool()` | ✅ Imports Tool class | Creates Tool, doesn't execute |

**Conclusion**: `execute_with_limits(..., available_capabilities=...)` has ZERO real call-sites in non-legacy, non-scheduler code. The enforcement hook exists but is not yet wired into any production call-site.

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

## None-Skip Containment

### Mechanism
```python
# tool_registry.py:648-651
if available_capabilities is not None:
    satisfied, reason = self.check_capabilities(tool_name, available_capabilities)
    if not satisfied:
        raise RuntimeError(f"Capability check failed: {reason}")
```
When `available_capabilities=None`, capability check is **silently skipped** (backward compatibility).

### Debt: Explicit Warning for None-Skip Path

| Item | Status | Notes |
|------|--------|-------|
| None-skip warning | ⚠️ **TODO** | No deprecation warning when `None` passed |
| None-skip detection | ✅ Via tests | `test_execute_with_limits_skips_when_none` |
| None-skip compat note | ✅ In doc | This section documents the debt |

**Impact**: Any call-site passing `None` for `available_capabilities` bypasses capability enforcement entirely. This is the current state of ALL real call-sites (none pass `available_capabilities`).

---

## GhostExecutor Containment (Donor/Compat)

### Verified Boundaries

| Item | Status | Evidence |
|------|--------|----------|
| GhostExecutor NOT in ToolRegistry | ✅ Verified | `test_ghost_executor_not_in_tool_registry_canonical` |
| INTEGRATION NOTE in docstring | ✅ Present | `ghost_executor.py:66-79` |
| Separate action model | ✅ Verified | ActionType enum vs Tool model |
| Not referenced as canonical | ✅ Verified | Docs say "ToolRegistry is canonical" |

### Surface Overlap (Documented, Not Fixed)

GhostExecutor actions like `stealth_harvest`, `osint_discovery` COULD be implemented as ToolRegistry tools in the future, but this would require:
1. Migrating from `ActionType` enum to `Tool` model
2. Registering handlers in `ToolRegistry`
3. Updating call-sites to use `execute_with_limits` instead of `GhostExecutor.execute()`

**This is intentional debt — not fixed in this sprint per guardrails.**

---

## Bypass Debt Matrix

| Bypass | Location | Why | Severity | Precondition |
|--------|----------|-----|----------|-------------|
| `execute_with_limits(None)` | `tool_registry.py:648` | Backward compat | **HIGH** | All call sites pass `None` |
| GhostExecutor bypass | `ghost_executor.py` | Legacy compat | MEDIUM | Migrate to Tool-based |
| Scheduler bypass | `runtime/sprint_scheduler.py` | Guardrail | HIGH | Scheduler sprint |
| Legacy orchestrator | `legacy/autonomous_orchestrator.py:20074` | Legacy code | MEDIUM | Full migration |

---

## What Is Now Truly Enforced (vs. Scaffold)

| Item | Before | After | Evidence |
|------|--------|-------|----------|
| `check_capabilities()` method | ✅ Exists | ✅ Works | `test_check_capabilities_pass/fail` |
| `execute_with_limits()` capability gate | ✅ Hook exists | ✅ Tested | `test_execute_with_limits_enforces_capabilities` |
| Representative tools populated | ✅ 3 tools | ✅ Same | `test_required_capabilities_populated` |
| None-skip backward compat | ✅ Exists | ✅ Documented | `test_execute_with_limits_skips_when_none` |
| End-to-end probe tests | ❌ None | ✅ Added | `TestEndToEndEnforcement` class |
| None-skip deprecation warning | ❌ None | ⚠️ Debt | Not implemented |
| Real call-site propagation | ❌ None | ❌ None | Zero production call-sites |

---

## Next Migration Step Before Scheduler Dispatch Integration

Before integrating with SprintScheduler dispatch:

1. **Wire ONE representative call-site** to pass `available_capabilities`
   - Candidate: `ti_feed_adapter.py` task handler (safe, non-scheduler, non-stealth)
2. **Add deprecation warning** when `None` passed to `execute_with_limits()`
3. **Populate more `required_capabilities`** for high-priority tools
4. **Deprecate None-skip** with `warnings.warn()`
5. **GhostExecutor migration** plan (separate sprint)

---

## Files Changed in Sprint 8SF

| File | Change |
|------|--------|
| `TOOL_CAPABILITY_EXECUTION_ENFORCEMENT.md` | Updated: call-site matrix, bypass debt, probe test evidence |
| `tests/probe_8se/test_capability_enforcement.py` | Added `TestEndToEndEnforcement` class with 3 probe tests |
