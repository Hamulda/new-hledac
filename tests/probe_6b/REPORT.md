# Sprint 6B Final Report — Apple-Silicon Hardening + Torch Eviction + AFM Probe

## 1. Executive Summary

Sprint 6B implemented Apple-Silicon hardening, lazy torch eviction, and Apple Foundation Models probe for Hledac v18 on M1 8GB UMA.

**Status**: ✅ COMPLETE — 32 tests passed, all benchmark gates passed

---

## 2. Changes Implemented

### 2.1 Apple Foundation Models Probe (`brain/apple_fm_probe.py`)
- New fail-open probe for Apple Foundation Models
- macOS version gate: requires 14.0+ (Sonoma)
- ARM64 check: fails on x86_64
- Correctness validation via arithmetic probe
- `AFMProbeResult` dataclass with fields: `available`, `macos_version`, `is_apple_silicon`, `correctness_valid`, `error`
- `is_afm_available()` boolean convenience API
- `get_nl_framework_available()` for NaturalLanguage framework detection

### 2.2 MLX Buffer Initialization (`utils/mlx_cache.py`)
- Added `_MLX_CACHE_LIMIT = 2684354560` (2.5 GB)
- Added `_MLX_WIRED_LIMIT = 2684354560` (2.5 GB)
- `init_mlx_buffers()` sets `mx.metal.set_cache_limit()` and `mx.metal.set_wired_limit()`
- Called at module load time (line 172)
- `_MLX_INITIALIZED` flag prevents double initialization

### 2.3 UMA Budget Thresholds (`utils/uma_budget.py`)
- `_WARN_THRESHOLD_MB = 6_144` (6.0 GB)
- `_CRITICAL_THRESHOLD_MB = 6_656` (6.5 GB)
- `_EMERGENCY_THRESHOLD_MB = 7_168` (7.0 GB) — NEW
- `is_uma_emergency()` function — NEW
- `get_uma_snapshot()` includes `emergency_threshold_mb` and `is_emergency`

### 2.4 Torch Eviction (No Changes Required)
All torch imports already use lazy pattern via sentinel functions:
- `ner_engine.py`: `_get_torch()` with `_TORCH_AVAILABLE` sentinel
- `stego_detector.py`: `_check_mps_available()` lazy MPS check
- `stealth_layer.py`: torch import inside `AdvancedCaptchaSolver._run_transforms_ocr_sync()`
- `moe_router.py`: `import torch.nn as _torch_nn` inside `RouterMLP.__init__()`

---

## 3. Test Suite Results

### 3.1 probe_6b Test Suite (32 tests)
| File | Tests | Status |
|------|-------|--------|
| `test_apple_fm_probe.py` | 9 | ✅ PASS |
| `test_mlx_cache_limits.py` | 5 | ✅ PASS |
| `test_qos_constants.py` | 3 | ✅ PASS |
| `test_torch_eviction.py` | 6 | ✅ PASS |
| `test_uma_budget_thresholds.py` | 9 | ✅ PASS |
| **Total** | **32** | ✅ **PASS** |

### 3.2 Benchmark Gates
| Suite | Tests | Status |
|-------|-------|--------|
| `test_ao_canary.py` | 27 | ✅ PASS |
| `probe_8c2/test_research_effectiveness.py` | 36 | ✅ PASS |
| `probe_8c3/test_8c3_schema.py` | 13 | ✅ PASS |
| **Total** | **76** | ✅ **PASS** |

*Note: probe_8c0 has pre-existing import errors (`ModuleNotFoundError: No module named 'benchmarks'`) unrelated to Sprint 6B changes.*

---

## 4. Verification

### 4.1 Torch Lazy Loading
```
torch in sys.modules before any hledac import: False
torch in sys.modules after hledac imports: False
```
✅ Torch NOT eagerly loaded

### 4.2 Import Time
```
Import time: 1.108s
```
✅ Acceptable (Pillow/lxml heavy imports dominate)

### 4.3 MLX Buffer Initialization
```
INFO:hledac.universal.utils.mlx_cache:MLX buffers initialized: cache=2560MB, wired=2560MB
```
✅ 2.5GB cache and wired limits confirmed

---

## 5. Files Modified/Created

| File | Action | Lines |
|------|--------|-------|
| `hledac/universal/brain/apple_fm_probe.py` | CREATED | 131 |
| `hledac/universal/utils/mlx_cache.py` | MODIFIED | +13 |
| `hledac/universal/utils/uma_budget.py` | MODIFIED | +18 |
| `hledac/universal/tests/probe_6b/__init__.py` | CREATED | — |
| `hledac/universal/tests/probe_6b/test_apple_fm_probe.py` | CREATED | 131 |
| `hledac/universal/tests/probe_6b/test_mlx_cache_limits.py` | CREATED | 56 |
| `hledac/universal/tests/probe_6b/test_qos_constants.py` | CREATED | 59 |
| `hledac/universal/tests/probe_6b/test_torch_eviction.py` | CREATED | 113 |
| `hledac/universal/tests/probe_6b/test_uma_budget_thresholds.py` | CREATED | 106 |

---

## 6. Sprint Metadata

- **Started**: 2026-03-24
- **Completed**: 2026-03-24
- **Total Tests Added**: 32
- **Tests Passing**: 32/32
- **Benchmark Gates Passing**: 76/76
- **Breaking Changes**: None
- **Performance Impact**: None (torch lazy loading reduces initial import)

---

## 7. Deferred Items

None.

---

*Generated: 2026-03-24*
