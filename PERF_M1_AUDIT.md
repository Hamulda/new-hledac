# Performance & M1 8GB + Test Gaps Audit
## hledac/universal/

---

## C1. Import-Time Hot List

**Top heavy importers when loading `autonomous_orchestrator`:**

| Module | Cumulative Time | Recommendation |
|--------|----------------|----------------|
| `mlx_lm` | 1.4s | Lazy load in `_load_model()` |
| `transformers` | 928ms | Lazy load in action handlers |
| `sklearn.ensemble` | 901ms | Lazy load in resource_allocator |
| `torch` | 836ms | Lazy load - only for MPS checks |
| `mlx.nn` | 200ms | Lazy load in MLX actions |
| `pandas` | 520ms | Lazy load in data science modules |

**Issue:** These are imported at module level in:
- `hledac/universal/autonomous_orchestrator.py` (lines 388-850+ lazy loaders exist but still eager import torch/transformers)
- `hledac/universal/coordinators/resource_allocator.py` (imports sklearn at top)

---

## C2. Memory Hotspots

### Unbounded Structures (GOOD - bounded):
- `evidence_log.py`: Ring buffer `deque(maxlen=100)` ✅
- `_execution_history`: `deque(maxlen=100)` ✅
- `_attribution_ring`: `deque(maxlen=200)` ✅
- `_simhash_fingerprints`: `_LRUDict(maxsize=10_000)` ✅
- `_MAX_BLACKLIST_SIZE = 50_000` ✅

### Potential Memory Issues:
1. **file_cache in structure_map** - No explicit max size bound in `build_structure_map()`
   - Location: `tools/content_miner.py:1184` - `state: Persistent state (file_cache LRU, prev_edges)`
   - Needs: explicit `maxlen` or periodic cleanup

2. **SQLite batch queue** - `asyncio.Queue(maxsize=500)` in EvidenceLog
   - Location: `evidence_log.py:215` - could grow unbounded if flush worker lags

---

## C3. Event-Loop Hazards

### Sync I/O in Async (BLOCKING RISKS):

| Location | Issue | Severity |
|----------|-------|----------|
| `autonomous_orchestrator.py:2255` | Uses `await asyncio.to_thread(_call)` ✅ OK | - |
| `autonomous_orchestrator.py:1998` | Uses `await asyncio.to_thread()` ✅ OK | - |
| `autonomous_orchestrator.py:11503` | `loop.run_in_executor(None, _extract)` ✅ OK | - |

**Concerns:**
- Only **6 usages** of `to_thread`/`run_in_executor` for 192 async defs
- Many async methods may do CPU-heavy work without proper threading

### Heavy CPU without to_thread (NEEDS REVIEW):
- `_mlx_post_action_cleanup()` - calls `mx.eval([])` + `mx.metal.clear_cache()` 
- `_analyze_input()` - CoreML classification (should be async)
- `content_miner.py` - regex/AST parsing in async flows

---

## C4. Resource Gating Consistency

**`_memory_pressure_ok()` usage locations:**

| Line | Context | Status |
|------|---------|--------|
| 2206 | Before `mlx_post_action_cleanup` | ✅ Checked |
| 2380 | Before `run_meta_optimizer` | ✅ Checked |
| 2912 | Before `structure_map_warming` | ✅ Checked |

**Consistency: GOOD** - All 3 heavy operations check memory pressure.

**Priority levels implemented:**
1. MLX Metal memory (3.5GB peak, 2.5GB active) 
2. Wired memory (macOS 15+)
3. sysctlbyname kern.memorystatus_level
4. psutil virtual_memory (1.5GB available)
5. resource.getrusage (fallback)

---

## E1. Test Gaps - M1-Specific Branches

### Existing M1 Tests:
- `test_sprint53.py`: MPS ELA/stego tests (6 tests)
- `test_sprint66/test_capability_prober.py`: `test_has_ane`, `test_has_metal`
- `test_sprint68/test_memory_pressure.py`: Basic detection
- `test_sprint71/test_mps_graph.py`: MPS graph tests

### Missing Coverage:

| Branch | Location | Gap |
|--------|----------|-----|
| `mx.metal.get_wired_memory()` | `autonomous_orchestrator.py:1913` | No test for macOS 15+ wired memory |
| `platform.system() != 'Darwin'` | `autonomous_orchestrator.py:1525` | Non-Darwin fallback not tested |
| `sys.platform == "darwin"` | `autonomous_orchestrator.py:1951` | Memory calculation for non-macOS |
| `mlx_lm` load failures | Lazy loaders | No mock tests for model load failures |
| `_structure_map_should_run` | `autonomous_orchestrator.py:2210` | Circuit breaker + cooldown logic untested |
| EvidenceLog encryption | `evidence_log.py:283` | No test for encrypt_at_rest=True |

---

## E2. Flaky Pattern Risks

1. **Timestamp-dependent tests** - Structure map scheduling uses `time.monotonic()`, should be mockable
2. **Network-dependent tests** - Blacklist refresh, DNS monitoring require network
3. **MPS availability** - Tests skip if `not torch.backends.mps.is_available()`

---

## Determinism Strategy

1. **Use `time.monotonic()` not `time.time()`** - Already done in structure_map
2. **Mock `_memory_pressure_ok()`** - Return fixed values for predictable tests
3. **Seed random** - For entropy/jitter in tests: `random.seed(42)`
4. **Isolate network** - Use `responses` library or local fixtures
5. **Circuit breaker cooldown** - Mock `time.monotonic()` in scheduling tests

---

## Summary Recommendations

### HIGH PRIORITY:
1. ✅ **EvidenceLog**: Ring buffer + encryption - well bounded
2. ⚠️ **structure_map file_cache**: Add explicit LRU bound
3. ⚠️ **Import lazy loading**: Move torch/transformers to action-level imports

### MEDIUM PRIORITY:
4. Add tests for non-Darwin platforms (CI)
5. Add test for `mlx.metal.get_wired_memory()` path
6. Increase `to_thread` usage for CPU-heavy async methods

### LOW PRIORITY:
7. Test encryption path in EvidenceLog
8. Mock-based tests for circuit breaker logic
