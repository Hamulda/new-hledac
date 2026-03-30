# Ghost Invariants — Sprint 7A

**Active Date:** Sprint 7A
**Status:** Enforced

---

## Always-On Rules (no toggles, no feature flags)

| Rule | Reason | Exception |
|------|--------|-----------|
| `asyncio.gather(...)` **always** uses `return_exceptions=True` | Prevents one failure from cancelling all siblings | Never |
| After every `gather()`: call `_check_gathered(results, logger, context)` | Filters exceptions, logs them, passes only valid results downstream | Never |
| Prefer `asyncio.timeout()` over `asyncio.wait_for()` for **new code** | More idiomatic, clearer cancellation semantics | When already changing async flow in existing code |
| `time.monotonic()` for **all intervals and cooldowns** | `time.time()` can jump backwards (NTP, suspend) | Never |
| `loop.getaddrinfo()` for DNS resolution in async context | `socket.getaddrinfo()` blocks the event loop | Never |
| `asyncio.to_thread()` is **forbidden** for CoreML and DuckDB | Offloading to thread pool defeats the purpose of ANE/GPU acceleration | Never |
| `requests` library is **forbidden** in async context | Blocking I/O — use `aiohttp` or `curl_cffi` | Never |
| `bare except:` is **forbidden** | Always catch `Exception` or specific subtypes | Never |
| Use `msgspec.structs.replace()` to update frozen structs | The only correct way to update `frozen=True` msgspec structs | Never |

---

## Helper APIs

### `_check_gathered(results, logger=None, context="")`

Defined in `utils/async_helpers.py`. Call this **immediately** after every `asyncio.gather(return_exceptions=True)` call.

```python
results = await asyncio.gather(*tasks, return_exceptions=True)
valid_results = _check_gathered(results, logger, context="MyOperation")
```

### `async_getaddrinfo(host, port, *, family=0, type_=0, proto=0, timeout=5.0)`

Defined in `utils/async_helpers.py`. Drop-in replacement for `socket.getaddrinfo()` in async contexts.

### `monotonic_ms() -> float`

Defined in `utils/async_helpers.py`. Returns `time.monotonic() * 1000.0`.

---

## Exception Hierarchy (Sprint 7A)

```
GhostBaseException
├── TransportException          # HTTP/transport layer errors
├── TimeoutException            # Async timeout errors
├── ParseException              # Parsing/serialization errors
├── CheckpointCorruptException   # Checkpoint file corrupted/unreadable
└── SprintTimeoutException      # Sprint exceeded time budget
```

Defined in `utils/exceptions.py`.

---

## PersistentActorExecutor — Worker Thread → Event-Loop Bridge (Sprint 7A)

Bridge worker-thread → event-loop **must** use `loop.call_soon_threadsafe(fut.set_result, result)` or `loop.call_soon_threadsafe(fut.set_exception, exc)`.

```python
# Correct — uses call_soon_threadsafe
loop.call_soon_threadsafe(fut.set_result, result)
loop.call_soon_threadsafe(fut.set_exception, exc)

# Forbidden — no `await loop.run_in_executor()` on CoreML/DuckDB paths
await loop.run_in_executor(None, fn)  # blocked — do NOT use for ANE/GPU
```

Defined in `utils/thread_pools.py`.

---

## Sprint Context & Lifecycle (Sprint 7A)

Use `SprintContext` (`utils/sprint_context.py`) with `sprint_scope()` context manager:

```python
from utils.sprint_context import SprintContext, sprint_scope, update_phase

ctx = SprintContext(sprint_id="7a", target="osint", phase="active", transport="curl_cffi")
with sprint_scope(ctx):
    # context is active
    updated = update_phase(ctx, "windup")  # msgspec.structs.replace()
```

Canonical LMDB keys for `maybe_resume()`:
- `b"sprint:last_phase"` — phase string
- `b"sprint:current_id"` — sprint id string

---

## TokenBucket SSOT (Sprint 7A)

Use `TokenBucket` from `utils/rate_limiters.py` as the canonical rate limiter.

Properties:
- async-safe (`asyncio.Lock`)
- `time.monotonic()` for refill intervals
- Gaussian jitter ±15 %
- `set_rate()` for dynamic adjustment

```python
from utils.rate_limiters import TokenBucket, get_limiter

bucket = get_limiter("shodan_api")
await bucket.acquire()
bucket.set_rate(2.0)
```

---

## Fire-and-Forget Tracking

When using `asyncio.create_task()` without `await`, the task **must** be stored in a tracked collection (list, deque, set) to prevent silent task abandonment on cancellation.

```python
self._background_tasks: Set[asyncio.Task] = set()

async def spawn(self, coro):
    task = asyncio.create_task(coro)
    self._background_tasks.add(task)
    task.add_done_callback(self._background_tasks.discard)
    return task
```

---

## Bounded Collections

Every unbounded `list` used as a queue or accumulator **must** be bounded via `deque(maxlen=N)` or explicit eviction policy.

| Collection | Max Size | Eviction |
|------------|----------|----------|
| Task tracking | 1000 | drop oldest |
| Result cache | 5000 | LRU evict |
| Pending operations | 2000 | drop lowest priority |

---

## Teardown Order (LIFO)

Shutdown must proceed in reverse-initialization order (LIFO). RAMdisk → LMDB → Thread pools → Event loop.

---

## Planner / Lifecycle Coupling Rules (Sprint 8E)

### P1: Planner NEIMPORTUJE SprintLifecycleManager
Planner moduly NESMÍ importovat `utils.sprint_lifecycle`. Time-budget signál se předává jako argument `time_budget: float`, ne jako přímé volání `remaining_time`.

### P2: evidence_log je dummy placeholder dokud není AO-wired
V `cost_model.py:19` je `EvidenceLog = None`. Toto NESMÍ být nahrazeno skutečnou implementací bez AO witness. Jakýkoli evidence_log stub musí být fail-open.

### P3: ResourceGovernor je jediná runtime brána
Planner komunikuje se systémem POUZE přes `ResourceGovernor.can_afford_sync()` a `governor.reserve()`. Žádné přímé volání psutil/mx.metal mimo Governor.

### P4: AdaptiveCostModel.update() musí být volán po dokončení úlohy
`AdaptiveCostModel.update()` existuje, ale NENÍ nikdy voláno. Toto JE insertion point pro budoucí sprint (Sprint 8G).

### P5: SLM model loading je vždy lazy
`SLMDecomposer._load_model()` musí zůstat lazy — žádné eager loading při importu. Model se načítá až při prvním `decompose()` volání.

---

## Safe-Clear / Emergency Rules (Sprint 8E)

### E1: mx.eval() PŘED mx.clear_cache()
V jakémkoli MLX planner kódu (cost_model, slm_decomposer) VŽDY volej `mx.eval([])` před `mx.metal.clear_cache()`. Jinak je clear_cache placebo.

### E2: TaskCache close() při shutdown
`TaskCache` implementuje `async def close()`. Toto MUSÍ být zavoláno při plánovač shutdown, aby se LMDB env korektně uzavřelo.

### E3: Beam width limit je hard limit
`anytime_beam_search` má `beam_width=5` (hardcoded). NESMÍ být zvýšen bez explicitní analýzy paměťového dopadu pro M1 8GB.

### E4: psutil virtual_memory() pouze mimo hot-path
`SLMDecomposer.decompose()` volá `psutil.virtual_memory()` pro rozhodování o paralerismu. Toto NESMÍ být voláno na plánovacím hot-path (expand/heuristic).

---

## "Nový soubor jen pro unikátní subsystem" pravidlo (Sprint 8E)

Každý nový soubor v `planning/` musí obsahovat unikátní, jasně ohraničenou funkcionalitu, která:
1. Nepřekrývá existující modul (žádný `cost_model_*.py`, `*_backup.py`)
2. Má jasně definovaný public API (jedna třída / jedna sada funkcí)
3. Je testovatelný izolovaně bez AO
4. Nemá přímou závislost na `autonomous_orchestrator.py`

**Příklad správného nového souboru:**
- `planning/prioritizator.py` — priority scoring pro task queue
- `planning/heuristics.py` — sdílené heuristické funkce

**Příklad ŠPATNÉHO nového souboru:**
- `planning/cost_model_v2.py` — duplikát existujícího
- `planning/htn_planner_hack.py` — patch bez samostatného smyslu

---

## References

- Sprint 6A/7A Spec: `GHOST_INVARIANTS.md` (this file)
- Async helpers: `utils/async_helpers.py`
- Exceptions: `utils/exceptions.py`
- Sprint context: `utils/sprint_context.py`
- Sprint lifecycle: `utils/sprint_lifecycle.py`
- Thread pools: `utils/thread_pools.py`
- Rate limiters: `utils/rate_limiters.py`

