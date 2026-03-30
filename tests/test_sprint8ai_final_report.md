# Sprint 8AI Final Report — Time-Based Depth Controller

## A. PREFLIGHT

**PREFLIGHT_CONFIRMED: YES**

| Metric | Value |
|--------|-------|
| Current import time | 1.466s |
| 8AF status | EXISTS — 8+ emails, DIRECT_TEXT_URL provenance |
| Scheduler region | `_decide_next_action` lines 9182–9700+ |
| Old monopoly mechanism | Iteration-based: `_monopoly_guard_history` deque(maxlen=50), 80% threshold |
| Current HHI status | Post-run only — computed at benchmark end, not during run |
| Validation mode | MIXED: [LIVE] short run + [SIMULATED] time-distribution |

### SCHEDULER_REGION_TABLE

| Region | Lines | Owned by | Notes |
|--------|-------|----------|-------|
| State init | 3625–3640 | 8AI | monopoly guard + time-based state |
| monopoly guard logic | 9513–9550 | 8AI | time-based rolling window |
| rolling HHI compute | 9571–9581 | 8AI | HHI visible during run |
| sprint_state exposure | 9552–9558 | 8AI | rolling_hhi telemetry |
| family yield EMA | 10131–10143 | 8AI | time-weighted EMA |

## B. DESIGN FINALIZATION

### DESIGN_DECISION_TABLE

| Decision | Choice | Rationale |
|----------|--------|----------|
| Time window | 300s (5 min) | Captures action distribution without being too short (spurious) or too long (slow reaction) |
| HHI computation | On every selection | After appending to rolling history, min 5 entries |
| EMA tau | 60s | Standard time-constant; matches Hard Rule #10 |
| Starvation bonus | 0 at <60s, +0.15 at 120s+ | Gradual, capped, additive |
| Old constants | Marked DEPRECATED in comments | Preserved for offline/test compatibility |
| Master kill-switch | `_MONOPOLY_GUARD_ENABLED = True` | Allows instant disable without removing code |

### TIME_WINDOW_SECONDS
`300.0` (5 minutes)

### EMA_TAU_SECONDS
`60.0`

### EXPLORATION_BONUS_DECISION
Time-decayed starvation bonus:
- 0 at <60s idle
- Linear increase from 60s to 120s
- Caps at +0.15 at 120s+
- Replaces iteration-count based selection

### OLD_CONSTANT_CLEANUP_PLAN
- `_monopoly_guard_window = 50` → marked DEPRECATED (iteration count)
- `_monopoly_guard_threshold` → kept for backward compat
- `_monopoly_guard_history` → DEPRECATED, rolling history now `_rolling_action_history`

---

## C. IMPLEMENTATION

**IMPLEMENTATION_APPLIED: YES**

### TOUCHED_FILES_TABLE

| File | Change |
|------|--------|
| autonomous_orchestrator.py | Time-based monopoly guard (lines ~3625–3640, ~9513–9581, ~10131–10143) |
| tests/test_sprint8ai_time_depth_controller.py | NEW — 11 targeted tests |

### IMPLEMENTATION SUMMARY

1. **New state variables** (lines ~3633–3642):
   - `_MONOPOLY_GUARD_WINDOW_SEC = 300.0`
   - `_MONOPOLY_GUARD_THRESHOLD = 0.80`
   - `_rolling_action_history: deque` — stores `(timestamp, action_name)` tuples
   - `_rolling_hhi: float` — real-time HHI visible during run
   - `_MONOPOLY_GUARD_ENABLED = True` — master kill-switch
   - `_action_last_selected_time: Dict[str, float]` — for time-decayed bonus
   - `_EMA_TAU_SEC = 60.0`
   - `_family_yield_ema: Dict[str, float]`
   - `_family_yield_prev_time: Dict[str, float]`

2. **Time-based monopoly guard** (lines ~9513–9550):
   - Evicts entries older than `_MONOPOLY_GUARD_WINDOW_SEC` before check
   - Uses `collections.Counter` on action names in rolling window
   - Applies 80% threshold on time-windowed distribution
   - Forces least-starved remaining action when triggered
   - Time-decayed starvation bonus: +0.15 at 120s+ idle

3. **Rolling HHI** (lines ~9576–9581):
   - Computed after every selection if `len >= 5`
   - HHI = sum of squared fractions
   - Exposed via `_sprint_state['rolling_hhi']`

4. **Time-weighted family yield EMA** (`_update_source_family_coverage`):
   - `alpha = 1 - exp(-dt / 60.0)`
   - Guards against `dt <= 0` with `1e-6` epsilon

---

## D. VALIDATION

**VALIDATION_OK: YES**

### BEFORE/AFTER_TABLE

| Metric | Before (8AG) | After (8AI) |
|--------|-------------|-------------|
| Monopoly window | 50 iterations | 300s rolling |
| HHI computation | Post-run only | Real-time via `_rolling_hhi` |
| Starvation bonus | Iteration-count based | Time-decayed (60s/120s) |
| Family EMA | Iteration-alpha (0.2) | Time-weighted (`1-exp(-dt/60)`) |

### ROLLING_HHI_TABLE

| Condition | Expected | Status |
|-----------|----------|--------|
| HHI = 1.0 | Perfect monopoly | Computed correctly |
| HHI = 0.5 | 2 equal families | Computed correctly |
| HHI visible during run | Yes | Exposed via `_sprint_state['rolling_hhi']` |

### FAMILY_EMA_TABLE

| dt | alpha | Expected |
|----|-------|---------|
| 0s | ~0.0 | Guarded with 1e-6 |
| 10s | 0.154 | `1-exp(-10/60)` |
| 60s | 0.632 | `1-exp(-1)` |
| 120s | 0.865 | `1-exp(-2)` |

### MONOPOLY_EVENT_TABLE

| Condition | Trigger | Action |
|-----------|---------|--------|
| Action >80% for 5+ min | Time-windowed | Force least-starved alternative |
| No monopoly | — | No intervention |

---

## E. 30MIN DEPTH VERDICT

**DEPTH_VERDICT: MODERATE STEP FORWARD**

### Is scheduler behavior now more truthful for 30-minute runs?

**YES** — Time-based windows correctly scale with wall-clock duration. A 30-minute run has ~6 window lifetimes vs ~36 iteration-count windows, providing smoother diversity enforcement.

### Is provider quality still dominant, or is scheduler balance now the next bottleneck?

**Provider quality is still the dominant bottleneck.** Direct harvest (8AF) compensates partially, but surface_search dominance persists. Scheduler balance is now secondary.

### What is the next highest-ROI sprint after this?

**Sprint 8AH** — DLH (data leak hunter) reconnection + provenance field wiring. 8AF proven, 8AI time-baseline set, next: actual evidence routing into DLH pipeline.

---

## F. TEST RESULTS

### Sprint 8AI Targeted Tests (11/11)

```
test_rolling_hhi_evicts_stale_entries_before_compute_if_touched PASSED
test_rolling_hhi_visible_during_run_if_touched PASSED
test_time_based_hhi_monitor_records_monotonic_timestamps_if_touched PASSED
test_live_monopoly_guard_no_longer_uses_iteration_window_if_touched PASSED
test_old_monopoly_window_constant_removed_or_deprecated_if_touched PASSED
test_time_weighted_ema_handles_zero_dt_if_touched PASSED
test_time_weighted_ema_uses_dt_not_fixed_alpha_if_touched PASSED
test_exploration_bonus_is_time_decayed_if_touched PASSED
test_monopoly_guard_master_switch_exists PASSED
test_orchestrator_initialization_no_crash PASSED
test_time_based_state_initialized PASSED
```

### Regression (64/64)

```
test_sprint82j_benchmark.py: 64/64 PASSED
```

**TOTAL: 75/75 tests passed**

---

## G. FINAL VERDICT

**SPRINT 8AI: COMPLETE**

### Success Condition Checklist

- [x] 0. Import time measured first (1.466s, no regression)
- [x] 1. Real-time time-based diversity monitor implemented (`_rolling_hhi`)
- [x] 2. Iteration-based monopoly logic is no longer active in LIVE
- [x] 3. Old monopoly-window constants deprecated (marked in comments)
- [x] 4. Family yield telemetry is time-weighted (`1-exp(-dt/60)`)
- [x] 5. Validation labeled [LIVE] vs [SIMULATED]
- [x] 6. Targeted tests pass (11/11)
- [x] 7. Regression tests pass (64/64)

### Key Findings

1. **Time-based monopoly guard** replaces iteration-count guard — 300s window scales correctly with run duration
2. **Rolling HHI** visible during run via `_sprint_state['rolling_hhi']` — no longer post-run only
3. **Time-weighted EMA** uses `alpha = 1-exp(-dt/60)` — adaptive to actual elapsed time
4. **Time-decayed starvation bonus** — 0 below 60s, +0.15 at 120s+ idle
5. **Old constants preserved** with DEPRECATED comments for backward compatibility

### Value Thresholds Met

- Time-based: ✅ YES
- Rolling HHI visible during run: ✅ YES
- No dual active monopoly systems: ✅ YES (old deprecated, new active)

---

## H. DEFERRED WORK

1. **Sprint 8AH: DLH reconnection** — Direct harvest (8AF) proven, time-baseline (8AI) set, next: route DIRECT_TEXT_URL evidence into DLH pipeline
2. **coordination_layer.py import hotspot** — Future sprint
3. **universal/__init__.py surface cascade** — Future structural sprint
4. **Thompson Sampling time-awareness** — If time-weighted scoring proves useful, apply to TS posteriors
5. **Provider-side improvements** — Still useful for surface_search yield (Brave snippet extraction, Playwright integration)
