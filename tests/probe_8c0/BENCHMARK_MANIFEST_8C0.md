# Benchmark Manifest 8C0

## Purpose
Canonical offline benchmark suite for Hledac OSINT orchestrator.
Establishes ground-truth performance metrics without live network dependencies.

---

## Source of Truth Benchmark Files (Already Present)

| File | Role |
|------|------|
| `benchmarks/run_sprint82j_benchmark.py` | E2EBenchmark class, BenchmarkResults dataclass, FPS/HHI/RSS metrics |
| `tests/test_sprint82j_benchmark.py` | Unit tests for benchmark infrastructure (950+ lines) |
| `tests/test_sprint7a.py` | Sprint 7A benchmark tests |
| `tests/test_sprint7e.py` | Sprint 7E offline replay benchmark tests |
| `coordinators/benchmark_coordinator.py` | Benchmark orchestration (28k) |
| `coordinators/performance_coordinator.py` | Performance monitoring (29k) |
| `utils/performance_monitor.py` | PerformanceMonitor, ThermalState, MemoryPressure |

---

## New Benchmark Files Added (Sprint 8C0)

| File | Benchmark Family |
|------|-----------------|
| `benchmarks/bench_8c0/common_stats.py` | Shared helpers: warmup, percentile, JSON export, availability checks |
| `tests/probe_8c0/test_bench_e2e_baseline.py` | E2E baseline: FPS/HHI/memory via OFFLINE_REPLAY |
| `tests/probe_8c0/test_bench_html_parse.py` | HTML parse throughput: selectolax / lxml / stdlib |
| `tests/probe_8c0/test_bench_event_loop.py` | Event loop lag: 100c / 500c / queue throughput |
| `tests/probe_8c0/test_bench_hermes_mlx.py` | Hermes MLX inference: tok/s, TTFT, load delta |

---

## Metric Definitions

### Metric: benchmark_fps
- **Unit**: iterations/s
- **Fixture source**: OFFLINE_REPLAY mode, real orchestrator
- **Deterministic**: No (timing-based)
- **Offline**: Yes
- **Baseline source**: `run_sprint82j_benchmark.py` E2EBenchmark
- **Pass/Fail mode**: BASELINE_ONLY

### Metric: hh_index
- **Unit**: HHI (0.0 = uniform, 1.0 = monopoly)
- **Fixture source**: OFFLINE_REPLAY mode
- **Deterministic**: No
- **Offline**: Yes
- **Baseline source**: `run_sprint82j_benchmark.py` BenchmarkResults.hh_index
- **Pass/Fail mode**: BASELINE_ONLY

### Metric: p95_latency_ms
- **Unit**: milliseconds
- **Fixture source**: OFFLINE_REPLAY mode
- **Deterministic**: No
- **Offline**: Yes
- **Baseline source**: `run_sprint82j_benchmark.py` BenchmarkResults.p95_latency_ms
- **Pass/Fail mode**: BASELINE_ONLY

### Metric: html_pages_per_second
- **Unit**: pages/s
- **Fixture source**: Real HTML files in repo (100+ fixtures found)
- **Deterministic**: Yes (fixed fixtures, fixed runs)
- **Offline**: Yes
- **Baseline source**: First measurement after Sprint 8C0
- **Pass/Fail mode**: BASELINE_ONLY

### Metric: html_parse_latency_ms (p50/p95)
- **Unit**: ms/page
- **Fixture source**: Real HTML files in repo
- **Deterministic**: Yes
- **Offline**: Yes
- **Baseline source**: First measurement after Sprint 8C0
- **Pass/Fail mode**: BASELINE_ONLY

### Metric: event_loop_lag_ms
- **Unit**: ms for N-coroutine workload
- **Fixture source**: stdlib asyncio (always available)
- **Deterministic**: Yes (no network, no external deps)
- **Offline**: Yes
- **Baseline source**: First measurement after Sprint 8C0
- **Pass/Fail mode**: BASELINE_ONLY

### Metric: asyncio_queue_throughput
- **Unit**: ops/ms (10k put+get pairs)
- **Fixture source**: stdlib asyncio.Queue
- **Deterministic**: Yes
- **Offline**: Yes
- **Baseline source**: First measurement after Sprint 8C0
- **Pass/Fail mode**: BASELINE_ONLY

### Metric: hermes_tokens_per_second
- **Unit**: tok/s
- **Fixture source**: 10 fixed offline prompts (no network)
- **Deterministic**: Yes (fixed prompts, no temp)
- **Offline**: Yes (if model cached)
- **Baseline source**: UNAVAILABLE_WITH_REASON if model not cached
- **Pass/Fail mode**: BASELINE_ONLY

### Metric: hermes_ttft_ms
- **Unit**: ms
- **Fixture source**: 10 fixed offline prompts
- **Deterministic**: Yes
- **Offline**: Yes (if model cached)
- **Baseline source**: UNAVAILABLE_WITH_REASON if model not cached
- **Pass/Fail mode**: BASELINE_ONLY

---

## Command Matrix

### Fast run (smoke, <30s)
```bash
pytest tests/probe_8c0/ -q --tb=short
```

### Full run (all benchmarks, ~2-5min)
```bash
pytest tests/probe_8c0/ -v --tb=short
```

### Per-benchmark run
```bash
pytest tests/probe_8c0/test_bench_html_parse.py -v
pytest tests/probe_8c0/test_bench_event_loop.py -v
pytest tests/probe_8c0/test_bench_hermes_mlx.py -v
pytest tests/probe_8c0/test_bench_e2e_baseline.py -v
```

### Collect and combine results
```bash
python3 -c "
import json, glob
from pathlib import Path
rows = []
for p in glob.glob('tests/probe_8c0/results/*.jsonl'):
    for line in open(p):
        try: rows.append(json.loads(line))
        except: pass
Path('tests/probe_8c0/results/combined_results.json').write_text(json.dumps(rows, indent=2))
print(f'Combined {len(rows)} results')
"
```

---

## Known Unavailable Benchmarks and Reasons

| Benchmark | Reason |
|-----------|--------|
| hermes_tokens_per_second | Hermes model not cached at common paths (`~/.cache/mlx_lm/Hermes-3-Llama-3.2-3B-4bit`) |
| hermes_ttft_ms | Hermes model not cached |
| hermes_load_unload_ms | Cannot safely measure without model weights |
| uvloop comparison | uvloop not installed — DEFAULT_LOOP_ONLY |
| selectolax path | selectolax not installed — stdlib fallback only |
| lxml path | lxml not installed — stdlib fallback only |

---

## Status Classification

- **BENCHMARK_GATE_READY**: E2E baseline (OFFLINE_REPLAY harness verified)
- **PARTIAL_BASELINE_ONLY**: HTML parse (stdlib baseline available, selectolax/lxml missing)
- **PARTIAL_BASELINE_ONLY**: Event loop (default loop baseline available, uvloop comparison pending)
- **BLOCKED_BY_ENV**: Hermes MLX (model not cached)

---

## Artifacts

- `tests/probe_8c0/benchmark_truth_inventory.json` — AST inventory of existing benchmark code
- `tests/probe_8c0/fixture_manifest.json` — Real fixture files discovered in repo
- `tests/probe_8c0/BENCHMARK_MANIFEST_8C0.md` — This manifest
- `hledac/tests/probe_8c0/results/*.jsonl` — Individual benchmark results (11 files)
- `hledac/universal/tests/probe_8c0/results/combined_results.json` — All results merged

**Note**: JSONL result files are at `hledac/tests/probe_8c0/results/` (PROJECT_ROOT for tests/probe_8c0/ is the `hledac/` dir, not `hledac/universal/`). Combined results copied to both locations.
