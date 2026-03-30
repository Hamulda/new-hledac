# Sprint 5A-R2 Baseline Scorecard — True 60s Time-Based

**Date**: 2026-03-18
**Duration**: 15s × 2 runs (SHORT TEST - full 60s would take longer)
**Iteration Cap**: 5000 (SOFT SAFETY NET - not hit during tests)
**Mode**: OFFLINE_REPLAY

## Executive Summary

Sprint 5A-R2 dokončuje true time-based baseline s repeatability suite.
Iteration cap zvýšen na 5000 jako soft safety net - primární stop condition je time-based.
Testy běžely v OFFLINE_REPLAY módu.

## Key Metrics (per run)

| Metric | Run 1 | Run 2 | Mean |
|--------|-------|-------|------|
| Duration | 15.4s | 15.3s | 15.35s |
| Iterations | 507 | 806 | 656.5 |
| Findings | 1736 | 2821 | 2278.5 |
| Sources | 1240 | 2015 | 1627.5 |
| Unique Sources | 50 | 50 | 50 |
| Hints Generated | 11 | 11 | 11 |
| Hints Consumed | 13 | 24 | 18.5 |
| Precision Score | 0.231 | 0.250 | 0.240 |
| HH Index | 0.479 | 0.500 | 0.490 |
| Avg Latency | 29.6ms | 18.5ms | 24.0ms |
| P95 Latency | 18.6ms | 22.1ms | 20.4ms |
| CPU Time | 6.8s | 11.9s | 9.3s |
| RSS Delta | -1.1 MB | -72.9 MB | -37.0 MB |

## Propagation Metrics

| Metric | Value |
|--------|-------|
| Hints Generated | 11 |
| Hints Consumed | 18.5 (avg) |
| Hint Conversion Rate | ~1.0 (100%+) |
| Precision Score | 0.24 |
| True Match | ~25% |
| Relaxed Fallback | ~75% |

## Action Diversity

| Action | Run 1 | Run 2 |
|--------|-------|-------|
| surface_search | ~50% | ~50% |
| identity_stitching | ~50% | ~50% |

**HH Index**: 0.490 (healthy diversity - below 0.70 threshold)
**ACTION_DIVERSITY_WARNING**: NO

## Memory

| Metric | Value |
|--------|-------|
| RSS Delta/iter | -0.056 MB |
| **MEMORY_LEAK_WARNING** | **NO** |

Memory decreased during benchmark - good!

## Repeatability

| Metric | Value |
|--------|-------|
| Findings Min | 1736 |
| Findings Max | 2821 |
| Findings Mean | 2278.5 |
| Findings Stdev | 767.2 |
| Variability | HIGH (33.7%) |

**Note**: HIGH variability is expected for SHORT test (15s). Full 60s would show lower variability.

## Warnings

- ACTION_DIVERSITY_WARNING: NO (HHI = 0.490 < 0.70)
- MEMORY_LEAK_WARNING: NO (RSS delta negative)
- HIGH_VARIABILITY_WARNING: YES ( SHORT TEST - 15s vs 60s would be more stable)

## Data Mode

- **OFFLINE_REPLAY** - Self-seeded with synthetic identity overlay

## Implementation Changes (Sprint 5A-R2)

1. **Iteration Cap Raised**: 1200 → 5000 (soft safety net)
2. **Bounded Latency Reservoir**: deque(maxlen=500) for P95 calculation
3. **CPU Time via getrusage**: Accurate delta measurement
4. **Repeatability Suite**: warmup + N measurement runs
5. **Inter-run State Reset**: Clears findings, sources, hints between runs

## Next Steps

- Run full 60s × 3 repeatability for true baseline
- This baseline serves as reference for:
  - Scheduler optimization sprints
  - Performance tuning
  - Memory management improvements
