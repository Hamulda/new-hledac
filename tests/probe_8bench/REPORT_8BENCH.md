# REPORT 8BENCH — Benchmark Suite Analysis for Hledac v12

**Date**: 2026-03-24  
**Scope**: `/hledac/universal`  
**Status**: ANALYSIS COMPLETE

---

## 1. INVENTORY SUMMARY

| Category | Count | Notes |
|----------|-------|-------|
| **Total benchmark files found** | 47 | Across 203 scanned files |
| Orphan standalone scripts | 18 | sprint4c_*, sprint5r_*, sprint6* — ad-hoc timing scripts |
| Integrated benchmark modules | 3 | benchmark_coordinator, performance_coordinator, performance_monitor |
| Test benchmark files | 26 | pytest-based, some in CI |
| **Actively used in CI** | 4 | test_sprint82j (64 tests), test_sprint7a (11), test_sprint7e, test_sprint7g |
| Fully automated offline | 2 | run_sprint82j_benchmark.py + test_sprint82j_benchmark.py |

### Key Finding: Fragmentation

The benchmark infrastructure is **fragmented across 3 waves**:
1. **Early sprint scripts** (sprint4c–sprint6e): Orphan standalone scripts, no CI, manual execution
2. **Mid-period integration** (benchmark_coordinator, performance_monitor): Part of orchestrator, not isolated
3. **Recent E2E** (run_sprint82j_benchmark.py): Most mature, 64 pytest tests, OFFLINE_REPLAY capable

---

## 2. WHAT EXISTS vs WHAT'S MISSING

### EXISTS (4 categories)

| Category | Status | Evidence |
|----------|--------|----------|
| E2E FPS/throughput | ✅ EXISTS | `benchmark_fps = iterations/research_loop_elapsed_s` in run_sprint82j_benchmark.py |
| E2E latency (p95) | ✅ EXISTS | `p95_latency_ms` field, measured per action |
| E2E memory (RSS) | ✅ EXISTS | `rss_start_mb`, `rss_peak_mb`, `rss_delta_mb` |
| E2E concentration (HHI) | ✅ EXISTS | `hh_index` Herfindahl-Hirschman Index |
| System thermal/memory pressure | ✅ EXISTS | `ThermalState`, `MemoryPressure` enums in performance_monitor.py |
| Token throughput (MLX) | ⚠️ PARTIAL | `avg_tokens_per_sec` in PerformanceMetrics, but no isolated Hermes benchmark |

### MISSING (7 categories) — CRITICAL GAPS

| Category | Priority | Missing Metrics |
|----------|----------|-----------------|
| **HTML parsing** | 🔴 HIGH | selectolax vs BS4 pages/s — not isolated |
| **HTTP client** | 🔴 HIGH | httpx vs curl_cffi vs aiohttp req/s — not isolated |
| **Hermes MLX** | 🔴 HIGH | tok/s at batch=1/8, TTFT, KV cache hit rate, speculative decoding |
| **DuckDB/LMDB** | 🟡 MEDIUM | FTS latency, write IOPS, RAMdisk vs SSD |
| **Async I/O** | 🟡 MEDIUM | event loop lag at 100/500/1000 coroutines, uvloop speedup |
| **OPSEC crypto** | 🔴 HIGH | secure_zero MB/s, argon2id latency, AES-GCM throughput |
| **ANE/CoreML** | 🟡 MEDIUM | ANE embedder throughput vs CPU baseline |

---

## 3. TOP 5 MOST CRITICAL MISSING MEASUREMENTS

1. **Hermes 3B tokens/sec at batch=1**  
   Without this, we cannot measure MLX inference speedup from v12 sprints  
   **Impact**: Sprint 0.4 (MLX optimization) has no measurable definition of done

2. **HTML parse throughput (selectolax vs BS4)**  
   Sprint 0.2 claims 4× speedup but no isolated benchmark proves it  
   **Impact**: Cannot verify selectolax migration claim

3. **Event loop lag at 100 coroutines**  
   Sprint 0.1 (uvloop) promises 60% reduction but no before/after  
   **Impact**: Cannot verify uvloop migration benefit

4. **secure_zero throughput**  
   OPSEC sprint (0.12) claims 5× improvement but nothing measures it  
   **Impact**: Cannot verify memory sanitization performance

5. **E2E findings/minute**  
   Already measured (~30 fpm baseline from Sprint 5A), but not tracked per sprint  
   **Impact**: No visibility into end-to-end productivity changes

---

## 4. CURRENT BASELINE NUMBERS

| Metric | Value | Source | Date |
|--------|-------|--------|------|
| benchmark_fps | 115+ | test_sprint82j (64 tests) | 2026-03 |
| findings_per_minute | ~30 fpm | Sprint 5A offline | 2026-03-18 |
| hh_index | 0.484 | Sprint 5A | 2026-03-18 |
| p95_latency_ms | ~20ms | Sprint 5A | 2026-03-18 |
| RSS delta | -613 MB | Sprint 5A (decreasing = good) | 2026-03-18 |
| Data mode | OFFLINE_REPLAY | 2950 synthetic packets | — |

**Note**: Full 60s × 3 repeatability benchmark (run_sprint_5a_r3_benchmark.py) was not re-executed in this analysis session — requires 3+ minutes dedicated hardware time.

---

## 5. RECOMMENDED BENCHMARKS TO WRITE BEFORE FIRST v12 SPRINT

Without baselines, sprints cannot demonstrate progress. **Write these FIRST**:

### Phase 1 — Critical Path (write before Sprint 0.1)

| Benchmark | File | Runtime | Why First |
|-----------|------|---------|-----------|
| `hermes_tok_per_sec` | test_bench_hermes.py | 10s | All inference sprints need this |
| `html_parse_throughput` | test_bench_parse.py | 3s | Sprint 0.2 (selectolax) depends on it |
| `event_loop_lag_100c` | test_bench_async.py | 5s | Sprint 0.1 (uvloop) depends on it |

### Phase 2 — Before Sprint 0.4 (MLX)

| Benchmark | File | Runtime | Why First |
|-----------|------|---------|-----------|
| `hermes_ttft_latency` | test_bench_hermes.py | 5s | TTFT prefill measurement |
| `kv_cache_hit_rate` | test_bench_hermes.py | 10s | KV cache sprint depends |
| `mx_clear_cache_latency` | test_bench_mlx.py | 2s | Memory cleanup sprint |
| `uma_footprint_delta` | test_bench_system.py | 10s | M1 memory constraint |

### Phase 3 — Before Sprint 0.9 (Storage)

| Benchmark | File | Runtime | Why First |
|-----------|------|---------|-----------|
| `duckdb_fts_latency` | test_bench_storage.py | 3s | DuckDB FTS sprint |
| `lancedb_search_latency` | test_bench_storage.py | 3s | Vector search sprint |
| `url_dedup_throughput` | test_bench_storage.py | 2s | Bloom filter sprint |

### Phase 4 — Before Sprint 0.12 (OPSEC)

| Benchmark | File | Runtime | Why First |
|-----------|------|---------|-----------|
| `secure_zero_throughput` | test_bench_opsec.py | 2s | Memory sanitization |
| `argon2id_latency` | test_bench_opsec.py | 2s | KDF tuning |
| `aes_gcm_throughput` | test_bench_opsec.py | 2s | Crypto optimization |

---

## 6. CI INTEGRATION RECOMMENDATION

### Current CI State

Only 4 test files actively run in CI:
- `tests/test_sprint82j_benchmark.py` — 64 tests, E2E benchmark infrastructure
- `tests/test_sprint7a.py` — 11 tests, FPS truth
- `tests/test_sprint7e.py` — FPS breakdown tests
- `tests/test_sprint7g.py` — hot path tests

### Recommended CI Pipeline for v12

```yaml
# .github/workflows/benchmark.yml
name: v12 Benchmark Suite
on: [push, pull_request]
jobs:
  bench-fast:
    runs-on: macos-latest  # M1 for ANE/MLX tests
    steps:
      - uses: actions/checkout@v4
      - name: Run fast isolated benchmarks
        run: |
          pytest tests/probe_8bench/test_bench_*.py -q --tb=short
        timeout-minutes: 10
  bench-e2e:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run E2E 60s benchmark
        run: |
          python benchmarks/run_sprint82j_benchmark.py --duration 60 --offline
        timeout-minutes: 5
  bench-memory:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run 30min memory leak check
        run: |
          python benchmarks/run_sprint82j_benchmark.py --duration 1800 --memory-monitor
        timeout-minutes: 35
```

### Baseline Storage

Store baseline JSON in repo at `tests/probe_8bench/baselines/`:
- `baseline_v12_sprint0.json` — before any v12 sprint
- Updated after each sprint with new measured values

---

## 7. ARTIFACTS PRODUCED

All artifacts in `tests/probe_8bench/`:

| File | Purpose |
|------|---------|
| `benchmark_inventory.json` | 47 benchmark files with metadata |
| `baseline_results.json` | Current baseline numbers from Sprint 5A/7A/82J |
| `gap_analysis.json` | 7 missing categories, 40+ missing metrics |
| `proposed_suite.json` | 30 proposed benchmarks with pass thresholds |
| `sprint_benchmark_map.json` | v12 sprint → benchmark → expected delta mapping |
| `REPORT_8BENCH.md` | This summary report |

---

## 8. CONCLUSION

**Before v12 begins**: Write the 10 Phase 1+2 benchmarks from Section 5.  
**Without baselines**: v12 sprints have no measurable definition of done.  
**Current infrastructure**: Adequate for E2E FPS/HHI/latency, but critical gaps in isolated component benchmarks (parsing, HTTP, inference, OPSEC).

**Priority action**: Create `tests/probe_8bench/test_bench_hermes_tok_per_sec.py` to establish MLX inference baseline before the first MLX optimization sprint.
