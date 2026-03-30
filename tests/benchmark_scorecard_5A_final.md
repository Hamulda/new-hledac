# Sprint 5A Final Baseline Scorecard

**Date**: 2026-03-18
**Duration**: 60s × 3 runs
**Mode**: OFFLINE_REPLAY
**Seed**: 42 (deterministic)

## Executive Summary

Sprint 5A-R3 dokončuje finální baseline closure.
Opraveny 3 kritické anomálie z předchozích sprintů:
1. p95 latency reservoir reset mezi běhy
2. Deterministic seed aplikován (42)
3. Consumed counter reset mezi běhy

## Key Metrics (per run)

| Metric | Run 1 | Run 2 | Run 3 | Mean |
|--------|-------|-------|-------|------|
| Duration | 60.3s | 60.3s | 60.4s | - |
| Iterations | 2866 | 2103 | 1654 | 2208 |
| Findings | 8550 | 6311 | 4962 | 6608 |
| Sources | 7125 | 5260 | 4135 | 5507 |
| HH Index | 0.494 | 0.500 | 0.500 | 0.498 |
| Avg Latency | 20.8ms | 28.4ms | 36.1ms | - |
| P95 Latency | 28.9ms | 46.8ms | 60.2ms | - |
| RSS Delta | -382.2MB | -289.8MB | -290.5MB | - |

## Propagation Metrics

| Metric | Run 1 | Run 2 | Run 3 | Mean |
|--------|-------|-------|-------|------|
| Hints Generated | 9 | 9 | 9 | - |
| Hints Consumed | 9 | 9 | 9 | - |

## Repeatability

| Metric | Value |
|--------|-------|
| Findings Min | 4962 |
| Findings Max | 8550 |
| Findings Mean | 6608 |
| Findings Stdev | 1812.3 |
| Variability | 27.4% |
| Verdict | MODERATE |

## Warnings

- ACTION_DIVERSITY_WARNING: NO (HHI = 0.498)
- MEMORY_LEAK_WARNING: NO

## Baseline Truth

- **Time-based**: YES (asyncio.timeout 65s)
- **Iteration cap**: 5000 (soft safety net, not hit)
- **Deterministic seed**: YES (42)
- **Consumed regression**: FIXED (reset between runs)
- **p95 latency**: FIXED (reset reservoir between runs)

## Next Steps

This baseline serves as reference for:
- Scheduler optimization sprints
- Performance tuning
- Memory management improvements
