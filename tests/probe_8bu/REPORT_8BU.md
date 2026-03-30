# SPRINT 8BU — SILENT FAILURES & UNAWAITED COROUTINES PROBE REPORT

**Date**: 2026-03-24
**Scope**: `/hledac/universal/` — READ-ONLY probe
**New files**: `tests/probe_8bu/` only

---

## FINDING 1 — FIRE-AND-FORGET `asyncio.create_task` (GC Risk)

**3 instances found** where `asyncio.create_task()` result is not stored.

### CRITICAL: `autonomous_orchestrator.py:23635`
```python
asyncio.create_task(orch._enqueue_targets(packet_targets))
```
- **Context** (line 23632): `try: loop = asyncio.get_running_loop()` with bare `except Exception: pass`
- **Problem**: Task reference is immediately discarded. If GC runs before the coroutine completes, the task is **silently cancelled**. The `_enqueue_targets` call may silently drop target enqueues.
- **Evidence**: No task stored, no await, no collection.append.

### MODERATE: `autonomous_orchestrator.py:23748`
```python
asyncio.create_task(self._enqueue_targets(targets))
```
- **Same pattern** as above — `_enqueue_targets` fire-and-forget, wrapped in `try/except Exception: pass`.
- **Risk**: Race condition — if the loop is shutting down, targets are silently dropped.

### LOW: `text/unicode_analyzer.py:704`
```python
asyncio.create_task(self.cleanup())
```
- **Defensive**: Checked `if loop.is_running()` before creating task.
- However, `cleanup()` result is never awaited — if cleanup fails, silent.

---

## FINDING 2 — SILENT EXCEPTION SWALLOWING

**214 instances** of `except Exception: pass` with no logger and no raise.

### Top 5 Most Dangerous Silent Failures

| # | File:Line | Snippet | Risk |
|---|-----------|---------|------|
| 1 | `autonomous_orchestrator.py:4418` | `_run_structure_map_warming()` — warmup silently skipped | **HIGH**: Performance cliff |
| 2 | `autonomous_orchestrator.py:4629` | CoreML classifier — ANE silently falls back to Hermes | **HIGH**: Mis-routed classification |
| 3 | `autonomous_orchestrator.py:4871` | Evidence log structure — evidence silently dropped | **HIGH**: Completeness violation |
| 4 | `autonomous_orchestrator.py:3904` | `malloc_zone_pressure_relief` — memory relief silently fails | **HIGH**: M1 pressure undetected |
| 5 | `autonomous_orchestrator.py:23635` | `_enqueue_targets` in `try/except Exception: pass` | **HIGH**: Data loss |

### Pattern: Best-Effort Fallback Chains
Many silent failures chain multiple fallbacks:
```
CoreML → Hermes → MLX → None (all silent)
```

---

## FINDING 3 — EXCEPTION-PURGE CANDIDATES (22 Instances)

From Sprint 7B exception purge, **still present** in autonomous_orchestrator.py:

| Line | Function | Severity |
|------|----------|----------|
| 1079 | `_extract_targets_from_replay` | MODERATE |
| 1398 | `_extract_source_family` | MODERATE |
| 1437 | domain extraction | LOW |
| 1825 | memory pressure | LOW (defensive) |
| 3904 | malloc_zone_pressure_relief | HIGH |
| 4418 | structure_map_warming | HIGH |
| 4461 | thermal fallback | MODERATE |
| 4476 | sysctlbyname fallback | MODERATE |
| 4483 | psutil fallback | MODERATE |
| 4517 | resource.getrusage | LOW |
| 4532 | module-level cleanup | MODERATE |
| 4561 | CoreML fallback | HIGH |
| 4628 | CoreML path probe | HIGH |
| 4871 | evidence structure | HIGH |
| 4952 | evidence log | MODERATE |
| 5048 | None return | MODERATE |
| 5110 | capture_iter best-effort | LOW |
| 5158 | thermal level | LOW |
| 5167 | phase detection | LOW |
| 5175 | novelty detection | LOW |

---

## FINDING 4 — `utils/async_utils.py:188`
```python
asyncio.create_task(_worker(i, fn, args, kw))
```
- **Not stored** — fire-and-forget within `bounded_map`.
- Used in parallel task dispatch — if a worker fails, it fails silently.

---

## RISK CLASSIFICATION SUMMARY

| Risk Level | Count | Description |
|------------|-------|-------------|
| CRITICAL | 3 | Fire-and-forget tasks with data loss potential |
| HIGH | 9 | Silent failures in critical paths (warmup, CoreML, evidence) |
| MODERATE | ~30 | Silent fallbacks in non-critical paths |
| LOW | ~170 | Defensive best-effort guards (thermal, memory) |

---

## TOP 5 DANGEROUS SILENT FAILURES (Final Ranking)

1. **`autonomous_orchestrator.py:23635`** — `_enqueue_targets` fire-and-forget: packet targets silently dropped on GC
2. **`autonomous_orchestrator.py:4418`** — `_run_structure_map_warming` silently skipped: no warmup, performance cliff
3. **`autonomous_orchestrator.py:4629`** — CoreML classifier silently bypassed: ANE workloads routed to wrong backend
4. **`autonomous_orchestrator.py:4871`** — Evidence structure silently dropped: incomplete evidence graph
5. **`autonomous_orchestrator.py:23748`** — `_enqueue_targets` fire-and-forget (second instance): target enqueue race condition

---

## PROBE ARTIFACTS

- `tests/probe_8bu/REPORT_8BU.md` — This report
- Fire-and-forget count: **3**
- Silent exception count: **214**
- Exception-purge candidates (from Sprint 7B, still unpatched): **22**
