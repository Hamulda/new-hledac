# Test Harness for Hledac — Sprint 3A

## Overview

This directory contains a multi-layered test strategy optimized for MacBook Air M1 8GB.

## Layer Architecture

```
┌─────────────────────────────────────────────────────────┐
│  PROBE GATE  (<1s)  - instant smoke, pure Python       │
├─────────────────────────────────────────────────────────┤
│  AO CANARY  (~10s)  - fast lifecycle checks            │
├─────────────────────────────────────────────────────────┤
│  PHASE GATE  (10-60s per sprint)  - per-sprint tests   │
├─────────────────────────────────────────────────────────┤
│  SPRINT SUITE  (5-15 min)  - full sprint coverage      │
├─────────────────────────────────────────────────────────┤
│  MANUAL / HEAVY  (15-60 min)  - integration/RAM       │
└─────────────────────────────────────────────────────────┘
         ⚠️  MEGA SUITE (10+ min) - last resort only
```

---

## Quick Start

### After Every Sprint Change

```bash
# 1. Probe gate (instant)
pytest tests/probe_*/ -m probe_gate -q

# 2. AO Canary (5-10s) — THE GATE
pytest tests/test_ao_canary.py -q

# 3. Phase gate (selected sprint tests)
pytest tests/test_sprint*.py -q
```

### Before Release

```bash
# Full sprint suite
pytest tests/test_sprint*.py -q

# Integration tests
pytest tests/test_e2e_pipeline.py -q
```

---

## Layer Details

### Probe Gate (`probe_*/`)
- **Duration**: <1 second
- **Purpose**: Pure Python smoke tests, no imports
- **Run**: `pytest tests/probe_*/ -m probe_gate -q`

### AO Canary (`test_ao_canary.py`) ⭐
- **Duration**: ~5-10 seconds
- **Purpose**: Fast, deterministic canary tests for core lifecycle
- **Coverage**:
  - Orchestrator instantiation and state
  - Windup gating seam
  - Checkpoint probe/save seam
  - Background task tracking
  - Shutdown unification
  - Remaining_time signal
  - Capability gating
  - Action registry
  - Budget manager
  - Knowledge layer
  - Model lifecycle
- **Run**: `pytest tests/test_ao_canary.py -q`

### Phase Gate (`test_sprint*.py`)
- **Duration**: 10-60 seconds per sprint file
- **Purpose**: Per-sprint focused tests
- **Run**: `pytest tests/test_sprint85.py -q` (specific sprint)
- **Run**: `pytest tests/test_sprint*.py -q` (all sprint tests)

### Sprint Suite
- **Duration**: 5-15 minutes total
- **Purpose**: Comprehensive sprint coverage
- **Run**: `pytest tests/test_sprint*.py -q`

### Manual / Heavy
- **Duration**: 15-60 minutes
- **Purpose**: Integration tests, model loading, RAM-intensive
- **Tests**:
  - `test_e2e_pipeline.py` — full pipeline
  - `e2e_autonomous_loop.py` — continuous loop
  - Model loading tests
  - Network tests (real HTTP, Tor)
  - Stress/chaos tests
- **Run**: Only when explicitly needed

---

## ⚠️ NEVER Run as Default

### Mega Suite (`test_autonomous_orchestrator.py`)
- **22,154 lines**, 291 test classes
- **Duration**: 10+ minutes on M1 8GB
- **Risk**: RAM exhaustion, thermal throttling

```bash
# DON'T run as gate!
pytest tests/test_autonomous_orchestrator.py -q  # ❌ NEVER
```

Only run when:
- All canary and phase tests pass
- You have explicit time budget
- Debugging specific orchestrator behavior

**Alternative**: Run individual classes:
```bash
pytest tests/test_autonomous_orchestrator.py::TestOrchestratorSmoke -q
pytest tests/test_autonomous_orchestrator.py::TestCapabilitySystem -q
```

---

## Test Organization

```
tests/
├── test_ao_canary.py          # ⭐ AO Canary Layer (NEW)
├── PHASE_GATES.py             # Phase gate definitions (NEW)
├── MEGA_SUITE_ANALYSIS.md     # Mega-suite structural analysis (NEW)
├── README.md                  # This file
├── conftest.py                # pytest bootstrap (cache root enforcement)
│
├── probe_*/                   # Probe smoke tests
│   ├── probe_imports_*.py
│   └── probe_compat_*.py
│
├── test_sprint41.py           # Sprint 41-60+ tests
├── test_sprint42.py
├── ...
├── test_sprint80.py
│
├── test_sprint66/             # Sprint subdirectories
├── test_sprint67/
├── ...
│
├── test_e2e_pipeline.py       # E2E integration
├── e2e_autonomous_loop.py    # Loop integration
│
└── test_autonomous_orchestrator.py  # ⚠️ MEGA SUITE (22k lines)
```

---

## Markers

Custom pytest markers defined in `PHASE_GATES.py`:

| Marker | Purpose |
|--------|---------|
| `probe_gate` | Instant smoke tests |
| `ao_canary` | AO canary tests |
| `phase_gate` | Per-sprint focused |
| `manual_only` | Manual/integration |

---

## Duration Estimates (M1 8GB)

| Layer | Duration | RAM Risk |
|-------|----------|----------|
| Probe Gate | <1s | None |
| AO Canary | 5-10s | None |
| Phase Gate | 10-60s | Low |
| Sprint Suite | 5-15min | Medium |
| Manual/Heavy | 15-60min | High |
| Mega Suite | 10-60min | Very High |

---

## File Reference

- **AO Canary**: `test_ao_canary.py` — 15 test classes, ~350 lines
- **Phase Gates**: `PHASE_GATES.py` — Marker definitions and usage guide
- **Mega Suite Analysis**: `MEGA_SUITE_ANALYSIS.md` — Structural breakdown
- **This README**: `README.md` — Complete usage guide

---

## Adding New Tests

### Canary Test Template

```python
class TestNewFeatureCanary:
    """Tests for new feature seam."""

    async def test_new_feature_exists(self):
        """Verify new feature attribute exists."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        orch = FullyAutonomousOrchestrator()
        assert hasattr(orch, '_new_feature')
```

### Phase Gate Template

```python
@pytest.mark.phase_gate
class TestSprintNNNewFeature:
    """Tests for Sprint NN new feature."""

    async def test_new_feature_works(self):
        ...
```

---

## Troubleshooting

### "Cannot access attribute" errors
- Use `hasattr()` checks first
- Use `getattr()` with default values
- Use `setattr()` for dynamic attributes
- Wrap in try/except for safety

### Slow tests
- Move heavy setup to fixtures
- Mock external calls (HTTP, MLX)
- Use `pytest.mark.slow` for tests >10s

### Memory issues
- Never run mega-suite as default
- Use `--maxprocesses=2` for parallel runs
- Clear MLX cache between test modules
