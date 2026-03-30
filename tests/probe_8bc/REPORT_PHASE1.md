# Sprint 8BC Phase 1 Report — Free-Threaded Python 3.13 Readiness
**Date:** 2026-03-23
**Probe script:** `tests/probe_8bc/phase1_ft_probe.py`
**Tests:** `tests/probe_8bc/test_phase1_ft_probe.py` — 17/17 passed

---

## Executive Summary

**Classification: `BLOCKED_BY_TOOLCHAIN`**

No free-threaded Python 3.13 interpreter is available on this M1 MacBook.

---

## Toolchain Findings

| Interpreter | Path | Free-Threaded? | Py_GIL_DISABLED |
|---|---|---|---|
| `python3.13t` | NOT FOUND | — | — |
| `pyenv-3.13.0` | `~/.pyenv/versions/3.13.0/bin/python` | **NO** | `0` (GIL enabled) |
| `system python3.11` | `.venv/bin/python3` | N/A (3.11) | `None` |
| `current` | `.venv/bin/python3` (3.11.8) | N/A (3.11) | `None` |

**Root cause:** Python 3.13.0 installed via pyenv is a standard build, NOT a free-threaded (`--disable-gil`) build. There is no `python3.13t` binary anywhere on the system.

---

## 3.12 Baseline (5 runs, current interpreter)

| Metric | Value |
|---|---|
| Median import time | **1.091s** |
| Stdev | 0.096s |
| Min | 0.957s |
| Max | 1.214s |
| RSS delta (start→import) | 16 MB → 150 MB (+134 MB) |

```json
{
  "python": "3.11.8",
  "executable": "/Users/vojtechhamada/PycharmProjects/Hledac/.venv/bin/python3",
  "median": 1.091417,
  "stdev": 0.096,
  "rss_samples_mb": [[16, 150], [16, 150], [16, 150], [16, 150], [16, 150]]
}
```

---

## Package Matrix — NOT PROBED

Since no free-threaded interpreter exists, the package matrix (msgspec, duckdb, ahocorasick, lmdb, curl_cffi, mlx, orchestrator) was **not** probed. The probe exits early at the toolchain gate.

---

## Install Guidance

To enable Sprint 8BC Phase 1, install a free-threaded Python build:

### Option 1: pyenv (recommended for development)
```bash
# Install Python 3.13 with free-threading enabled
CONFIGURE_OPTS=--disable-gil pyenv install -v 3.13.0

# After installation, the binary will be named python3.13t
~/.pyenv/versions/3.13.0/bin/python3.13t -VV
```

### Option 2: Official Python macOS installer
```
https://www.python.org/ftp/python/3.13.0/
Python 3.13.0 macOS universal2 installer (includes free-threaded variant)
```

### Verify free-threaded build
```python
import sys, sysconfig
assert sysconfig.get_config_var("Py_GIL_DISABLED") == 1, "Not free-threaded!"
assert hasattr(sys, "_is_gil_enabled"), "No GIL introspection API!"
```

---

## Files Created

```
hledac/universal/
├── tests/probe_8bc/
│   ├── phase1_ft_probe.py       # Main probe script (probe-only, safe)
│   ├── test_phase1_ft_probe.py  # 17 validation tests (all pass)
│   └── REPORT_PHASE1.md         # This report
```

---

## Next Steps

1. **Install free-threaded Python** via `CONFIGURE_OPTS=--disable-gil pyenv install -v 3.13.0`
2. **Re-run Phase 1 probe** — it will create an isolated venv under `.phase1_probe_8bc/` and probe the package matrix
3. **Await classification:** `READY_FOR_PHASE_1`, `READY_BUT_PERF_REGRESSION`, `BLOCKED_BY_EXTENSION_STACK`, or `BLOCKED_BY_ORCHESTRATOR_IMPORT`

Phase 2 (entity ingest, Aho expansion, MCTS) remains **deferred** until Phase 1 truth is established.

---

## Probe Invariants Enforced

| Test | Description |
|---|---|
| `test_probe_script_exists` | Probe script is present |
| `test_probe_script_is_executable_via_python` | Valid Python syntax |
| `test_probe_outputs_required_keys` | JSON has required structure |
| `test_probe_classifications_defined` | All 8 classification codes defined |
| `test_package_matrix_includes_required_packages` | 7 packages in matrix |
| `test_fresh_subprocess_per_package` | Isolation via subprocess-per-package |
| `test_gil_state_probing_exists` | `sys._is_gil_enabled()` + `Py_GIL_DISABLED` checked |
| `test_toolchain_gate_exists` | Interpreter discovery present |
| `test_baseline_measurement_exists` | 5-run baseline with median/stdev |
| `test_install_guidance_present` | pyenv + installer guidance present |
| `test_performance_comparison_exists` | Slowdown detection + `READY_BUT_PERF_REGRESSION` |
| `test_no_production_mutations` | No production file writes |
| `test_venv_creation_uses_isolated_path` | Venv under `.phase1_probe_8bc/` |
| `test_blocked_by_toolchain_output_structure` | Early exit with guidance |
| `test_all_classifications_reachable` | All 5 outcomes reachable |
| `test_gil_classification_cases` | All GIL states handled |
| `test_rss_tracked_in_import_probes` | RSS before/after tracked |
