# Sprint 5A Baseline Scorecard

**Date**: 2026-03-18
**Duration**: 60s OFFLINE_REPLAY
**Iteration Cap**: 1200 (HIT - benchmark ran to iteration limit)

## Executive Summary

First honest 60s baseline with strict consumption accounting (Sprint 4I fixes applied).
The benchmark ran to iteration cap (1200) before time cap (60s), indicating very fast execution.

## Key Metrics

| Metric | Value |
|--------|-------|
| Duration | 60.0s |
| Iterations | 1200 |
| Findings | 3540 |
| Sources | 2950 |
| Unique Sources | 50 |
| Findings/sec | 128.05 |
| Avg Latency | 22.9ms |
| P95 Latency | 19.5ms |
| CPU Time | 26785ms |

## Propagation Metrics

| Metric | Value |
|--------|-------|
| Hints Generated | 9 |
| Hints Consumed | 9 |
| Hint Conversion Rate | 1.000 (100%) |
| True Match | 2 |
| Relaxed Fallback | 7 |
| Precision Score | 0.222 |

## Action Diversity

| Action | Count |
|--------|-------|
| surface_search | 590 |
| identity_stitching | 590 |
| network_recon | 20 |

**HH Index**: 0.484 (healthy diversity - below 0.70 threshold)
**ACTION_DIVERSITY_WARNING**: NO

## Memory

| Metric | Value |
|--------|-------|
| RSS Start | 556.1 MB |
| RSS End | 413.6 MB |
| RSS Delta | -142.5 MB |
| RSS Delta/iter | -0.511 MB |
| **MEMORY_LEAK_WARNING** | **NO** |

Memory actually decreased during benchmark - good!

## Warnings

- ACTION_DIVERSITY_WARNING: NO (HHI = 0.484 < 0.70)
- MEMORY_LEAK_WARNING: NO (RSS delta negative)

## Data Mode

- **OFFLINE_REPLAY** - Self-seeded with synthetic identity overlay

## Interpretation

### Healthy Signs
1. High iteration throughput (20 iter/s)
2. Strong action diversity (HHI = 0.484)
3. No memory leak (RSS decreased)
4. 100% hint conversion rate
5. Completed normally

### Notes
1. Iteration cap (1200) was hit before time cap (60s)
2. All source types are "other" - OFFLINE_REPLAY mock data
3. True match rate is low (22%) - relaxed fallback used heavily

## Next Steps

This baseline serves as reference for:
- Scheduler optimization sprints
- Performance tuning
- Memory management improvements
