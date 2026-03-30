# Sprint 8AB Final Report — Background Task Tracking Consistency + Shutdown Semantics Hardening

## A. PREFLIGHT AUDIT

### `_start_background_task()` INSPECTION (line 4473)
```python
def _start_background_task(self, coro, name: str) -> asyncio.Task:
    """Start a background task with proper tracking."""
    task = asyncio.create_task(coro, name=name)
    self._bg_tasks.add(task)
    task.add_done_callback(self._bg_tasks.discard)
    return task
```
- ✅ Accepts `name` parameter
- ✅ Passes `name` to `asyncio.create_task(..., name=name)`
- ✅ Adds to `_bg_tasks` set
- ✅ Adds `done_callback` to remove from `_bg_tasks` on completion
- ⚠️ Does NOT log exceptions — tasks that raise silently die (known limitation)

### CREATE_TASK_COUNT_TABLE (autonomous_orchestrator.py)

| Metric | Count |
|--------|-------|
| Total `asyncio.create_task()` calls | 13 |
| Via `_start_background_task()` helper | 1 (internal to helper itself) |
| Direct calls NOT via helper | 12 |
| Already manually added to `_bg_tasks` | 1 (thermal_monitor) |

### BACKGROUND_TASK_AUDIT_TABLE (autonomous_orchestrator.py)

| # | Line | Task Variable | Via Helper? | Long-lived? | In _bg_tasks? | Self-healing? | Should Migrate? | Risk if Changed |
|---|------|---------------|-------------|-------------|--------------|---------------|----------------|----------------|
| 1 | 4064 | `_collector_task` | NO | YES | NO (own teardown) | NO | **NO** | MEDIUM — own cleanup path via `_stop_collector()` |
| 2 | 4312 | `_warming_task` | NO | NO | NO | YES | **NO** | LOW — idempotent restart |
| 3 | 11117 | `_autonomy_monitor_task` | NO | YES | **NO** | NO | **YES** | HIGH — should be in _bg_tasks |
| 4 | 11597 | `task` (thermal_monitor) | NO | YES | **YES (manual)** | NO | **PARTIAL** | MEDIUM — already tracked, redundant manual pattern |
| 5 | 13256 | `_meta_optimizer_task` | NO | YES | NO | YES | **NO** | LOW — placeholder, self-healing restart |
| 6 | 13258 | `_dns_monitor_task` | NO | YES | NO | YES | **NO** | LOW — placeholder, self-healing restart |
| 7 | 14175 | `_federated_task` | NO | YES | NO | NO | **NO** | LOW — bounded by research lifecycle |
| 8 | 18182 | `_profile_task` | NO | YES | NO (orch ref) | NO | **NO** | LOW — separate orch reference |
| 9 | 23097 | (fire-and-forget) | N/A | NO | NO | NO | **NO** | NONE |
| 10 | 23210 | (fire-and-forget) | N/A | NO | NO | NO | **NO** | NONE |
| 11 | 23311 | (fire-and-forget) | N/A | NO | NO | NO | **NO** | NONE |
| 12 | 25357 | (batch as_completed) | N/A | NO | NO | NO | **NO** | NONE |

### OTHER PRIORITY FILES

| File | Task | Via Helper? | Long-lived? | In _bg_tasks? | Should Migrate? |
|------|------|-------------|-------------|--------------|----------------|
| monitoring_coordinator.py:238 | `_collection_task` | NO | YES | NO | **NO** — owns separate cleanup |
| hermes3_engine.py:282 | `_flush_task` | NO | YES | NO | **NO** — owns separate cleanup |
| evidence_log.py:282 | `_flush_task` | NO | YES | NO | **NO** — owns separate cleanup |
| prefetch_cache.py:28 | `_writer_task` | NO | YES | NO | **NO** — owns separate cleanup |
| prefetch_oracle.py:101 | `_expire_task` | NO | YES | NO | **NO** — owns separate cleanup |

### MIGRATION_CANDIDATES_TABLE

| Candidate | Line | Reason | Migration Path |
|-----------|------|--------|----------------|
| `_autonomy_monitor_task` | 11117 | Long-lived, not tracked, no separate teardown | `_start_background_task(self._autonomy_monitor_loop(), name="autonomy_monitor")` |

## B. MINIMAL SAFE MIGRATION

**MIGRATION_APPLIED: YES**

One migration was applied:

### `autonomous_orchestrator.py:11117` — `_autonomy_monitor_task`

**Problem:** Long-lived background task created with `asyncio.create_task()` directly, NOT tracked in `_bg_tasks`, no separate teardown path.

**Fix:** Changed from:
```python
self._autonomy_monitor_task = asyncio.create_task(
    self._autonomy_monitor_loop(),
    name="autonomy_monitor"
)
```
To:
```python
self._autonomy_monitor_task = self._start_background_task(
    self._autonomy_monitor_loop(),
    name="autonomy_monitor"
)
```

**Impact:**
- Task now appears in `_bg_tasks` for bulk cancellation
- Task is removed from `_bg_tasks` on completion via done_callback
- Existing cleanup path (line 11300-11313) now covers this task

### NOT MIGRATED (with justification)

| Task | Reason Not Migrated |
|------|---------------------|
| `_collector_task` | Own dedicated cleanup via `_stop_collector()` |
| `_warming_task` | Idempotent restart pattern (checks `None or done()`) |
| `_meta_optimizer_task` | Self-healing restart (checks `None or done()`) |
| `_dns_monitor_task` | Self-healing restart (checks `None or done()`) |
| `_federated_task` | Bounded by research lifecycle, no separate teardown needed |
| `_profile_task` | Separate orch reference pattern |
| thermal_monitor | Already manually added to `_bg_tasks` (acceptable pattern) |
| Lines 23097, 23210, 23311, 25357 | Short-lived fire-and-forget, bounded by timeout |

## C. SHUTDOWN / LIFECYCLE VALIDATION

**LIFECYCLE_VALIDATION_OK: YES**

| Check | Status |
|-------|--------|
| `_autonomy_monitor_task` enters `_bg_tasks` on start | ✅ Verified |
| Done callback removes task from `_bg_tasks` on completion | ✅ Verified |
| Bulk cancel (line 11300-11313) now reaches migrated task | ✅ Verified |
| No duplicate tracking (done_callback + manual add) | ✅ Verified |
| Task gets useful name (`"autonomy_monitor"`) | ✅ Verified |
| Existing cleanup flow preserved | ✅ Verified |

## D. TEST RESULTS

### Targeted Tests (10 tests)
```
test_autonomy_monitor_uses_helper PASSED
test_start_background_task_adds_to_bg_tasks PASSED
test_done_callback_removes_task PASSED
test_cleanup_cancels_tracked_tasks PASSED
test_no_duplicate_tracking_in_helper PASSED
test_fire_and_forget_not_migrated PASSED
test_collector_has_own_teardown PASSED
test_thermal_monitor_manually_tracked PASSED
test_meta_optimizer_is_self_healing PASSED
test_warming_task_is_idempotent_restart PASSED
```

**TESTS_PASSED: YES — 10/10**

### Regression Tests
| Suite | Passed | Total |
|-------|--------|-------|
| test_sprint82j_benchmark.py | 64 | 64 |
| test_sprint8b_timing.py | 19 | 19 |
| test_sprint8c_solutions.py | 15 | 15 |
| test_sprint8x_live_enrichment.py | 17 | 17 |
| test_sprint8v_content_enrichment.py | 14 | 14 |
| test_sprint8l_targeted.py | 10 | 10 |

**TOTAL: 139/139**

## E. FINAL VERDICT

**COMPLETE** — Sprint objectives met:

1. ✅ All relevant long-lived production tasks in autonomous_orchestrator.py audited and classified with evidence
2. ✅ One clearly safe candidate (`_autonomy_monitor_task`) migrated to `_start_background_task()`
3. ✅ Restart/self-healing paths verified not to escape tracking (self-healing tasks intentionally excluded)
4. ✅ Bulk cancel coverage validated for migrated task
5. ✅ Shutdown behavior preserved (no changes to cleanup flow)
6. ✅ Existing tests pass (139/139), targeted tests added (10/10)

## F. DEFERRED WORK

### Intentionally Skipped Task Systems
| System | Reason |
|--------|--------|
| `monitoring_coordinator._collection_task` | Own dedicated cleanup path |
| `hermes3_engine._flush_task` | Own dedicated cleanup path |
| `evidence_log._flush_task` | Own dedicated cleanup path |
| `prefetch_cache._writer_task` | Own dedicated cleanup path |
| `prefetch_oracle._expire_task` | Own dedicated cleanup path |
| `thermal_monitor` task | Already manually tracked in `_bg_tasks` (acceptable) |
| Self-healing tasks (`_meta_optimizer`, `_dns_monitor`) | Restart logic requires fresh `asyncio.create_task()` |

### Future Sprints
1. **Sprint 8AC**: Full `asyncio.get_running_loop()` migration across remaining async contexts (continuation of Sprint 8Z)
2. **Sprint 8AD**: `_processed_hashes` bounded-growth audit / cap test (memory-safety follow-up)
3. **Sprint 8AE**: `coordination_layer.py` import hotspot as future cold-start sprint
4. **Sprint 8AF**: Live-yield revalidation as a later separate sprint
5. **Hermes3 batch worker tracking**: `hermes3_engine._batch_worker_task` could potentially use unified tracking (but owns own cleanup, low priority)
