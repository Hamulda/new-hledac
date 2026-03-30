# Sprint 8BD Phase 1 Report — Python 3.14 Free-Threaded Truth

**Datum:** 2026-03-23
**Interpretr:** Python 3.14.2 free-threading build (pyenv 3.14t)
**Build:** `CONFIGURE_OPTS="--disable-gil" pyenv install -v 3.14t`
**Venv:** `.phase1_probe_8bd/venv_ft` (874 MB)

---

## 1. Toolchain — INSTALLED ✅

```
~/.pyenv/versions/3.14.2t/bin/python3.14t
Python 3.14.2 free-threading build (main, Mar 23 2026, 14:29:55) [Clang 17.0.0]
gil_enabled: False  ← VERIFIED
Py_GIL_DISABLED: 1  ← VERIFIED
has_free_threading: True
```

---

## 2. Package Install Matrix

| Package | cp314t wheel | cp314 wheel | Source build | Installed | Classification |
|---------|-------------|-------------|-------------|-----------|----------------|
| msgspec | ✅ `cp314t` | — | — | 0.20.0 | INSTALLED ✅ |
| duckdb | ✅ `cp314t` | — | fails (pyenv build deps) | 1.5.0.dev44 | INSTALLED ✅ |
| pyahocorasick | — | `cp314` | ✅ succeeds | 2.3.0 | INSTALLED ✅ |
| lmdb | ✅ `cp314t` | — | — | 1.8.1 | INSTALLED ✅ |
| curl_cffi | — | — | ❌ PermissionError `/Users/runner` | — | **INSTALL_FAILED_NO_WHEEL** |
| mlx | — | `cp314` | not attempted (ABI mismatch) | — | **INSTALL_FAILED_NO_WHEEL** |

**Venv size:** 874 MB (with torch, numpy, pandas, etc.)

---

## 3. GIL State Transition Matrix

| Package | GIL before | GIL after | Classification |
|---------|-----------|-----------|----------------|
| msgspec | False | **False** | `GIL_STAYS_OFF` ✅ |
| duckdb | False | **True** | `GIL_FORCED_BY_EXTENSION` ❌ |
| lmdb | False | **True** | `GIL_FORCED_BY_EXTENSION` ❌ |
| torch | False | **False** | `GIL_STAYS_OFF` ✅ |
| pyahocorasick | False | False* | `GIL_STAYS_OFF` ✅ |

*Not measured individually — confirmed via orchestrator chain

### GIL Forced By Extension — Critical Finding

Both **duckdb** and **lmdb** extensions unconditionally re-enable the GIL when loaded:

```
RuntimeWarning: The global interpreter lock (GIL) has been enabled to load
module '_duckdb', which has not declared that it can run safely without
the GIL.

RuntimeWarning: The global interpreter lock (GIL) has been enabled to load
module 'lmdb.cpython', which has not declared that it can run safely without
the GIL. To override this behavior and keep the GIL disabled (at your own
risk), run with PYTHON_GIL=0 or -Xgil=0.
```

**Workaround:** `-Xgil=0` flag forces GIL off after extension loading, but this is fragile and not guaranteed stable.

---

## 4. Orchestrator Import

### Baseline (current interpreter — 3.11.8)
```
median=1.156s stdev=0.063s min=1.031s max=1.179s
RSS: ~150 MB
```

### Free-threaded (3.14.2t)

**BLOCKED** — `moe_router.py` line 69: `class RouterMLP(nn.Module)` fails with:
```
AttributeError: 'NoneType' object has no attribute 'Module'
```

**Root cause:**
```python
try:
    import mlx.core as mx
    import mlx.nn as nn       # ← shadows torch.nn
    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False
    mx = None
    nn = None                  # ← nn = None
                                   # Later: class RouterMLP(nn.Module) → None.Module
```

Since `mlx` is unavailable (no cp314t wheel), `nn = None`, and `torch.nn.Module` is shadowed by the `nn` from the failed mlx import.

**Note:** The file imports `torch.nn as nn` AFTER the mlx block, but class definition `class RouterMLP(nn.Module)` executes at class definition time — before the torch import can fix `nn`.

---

## 5. curl_cffi Failure Details

```
PermissionError: [Errno 13] Permission denied: '/Users/runner'
File "scripts/build.py", line 73, in download_libcurl
  os.makedirs(arch["libdir"], exist_ok=True)
```

Build script hardcodes `/Users/runner` path for curl target — requires root/CI environment.

**Classification:** `INSTALL_FAILED_NO_WHEEL`

---

## 6. mlx Failure Details

PyPI shows **no `cp314t` wheels** for mlx:
- Available: `cp310`, `cp311`, `cp312`, `cp313`, `cp314`
- `cp314` wheel exists but is **ABI-incompatible** with `cp314t` (free-threaded)

```
ERROR: mlx-0.31.1-cp314-cp314-macosx_15_0_arm64.whl is not a supported
wheel on this platform.
```

Attempted workarounds:
1. `--python-version 314` → not allowed without `--target`
2. `--target /tmp/...` → no cp314t version found
3. Direct URL install → same ABI rejection

**Classification:** `INSTALL_FAILED_NO_WHEEL`

---

## 7. Classification

### **BLOCKED_BY_EXTENSION_STACK**

**Reasoning:**

1. **Critical GIL violations** — duckdb and lmdb both unconditionally re-enable GIL. This means the free-threaded interpreter is effectively no longer free-threaded after these packages load.

2. **mlx unavailable** — No cp314t wheel exists. The mlx cp314 wheel is ABI-incompatible with cp314t. This blocks the orchestrator entirely because `nn = None` from the mlx except block shadows `torch.nn` before the class definition executes.

3. **curl_cffi unavailable** — No cp314t wheel, source build fails with permission error.

4. **Orchestrator cannot import** — Even with torch available (which keeps GIL off), the moe_router.py `class RouterMLP(nn.Module)` fails because `nn = None`.

### What Would Be Needed to Unblock

| Blocker | Solution | Effort |
|---------|----------|--------|
| mlx no cp314t | Wait for Apple to release mlx with free-threaded support, or use Python 3.13t with mlx | Days–weeks |
| duckdb/lmdb GIL forced | Patch extensions to support free-threaded, or use `-Xgil=0` workaround (fragile) | Weeks |
| curl_cffi no cp314t | Use `aiohttp` fallback, or wait for upstream cp314t wheel | Days |

### Alternative Path

Python 3.13t might be more viable — check if mlx provides `cp313t` wheels.

---

## 8. Performance Delta

Cannot measure — orchestrator import fails on FT interpreter.

---

## 9. Baseline (current) vs Free-threaded

| Metric | Current (3.11.8) | FT (3.14.2t) |
|--------|------------------|---------------|
| orchestrator median | **1.156s** | **N/A (blocked)** |
| GIL at import end | N/A | N/A (blocked) |
| RSS | ~150 MB | N/A |
| mlx available | yes | **no** |
| duckdb GIL-safe | yes | **no** |
| lmdb GIL-safe | yes | **no** |

---

## 10. Final Classification

```
BLOCKED_BY_EXTENSION_STACK
```

**Verdict:** Python 3.14 free-threaded is **NOT ready for Phase 1** on this codebase due to:

1. **mlx** — No cp314t wheel; ABI incompatible with cp314 wheel
2. **duckdb** — Re-enables GIL (`GIL_FORCED_BY_EXTENSION`)
3. **lmdb** — Re-enables GIL (`GIL_FORCED_BY_EXTENSION`)
4. **curl_cffi** — No cp314t wheel; source build fails with PermissionError
5. **Orchestrator** — `moe_router.py` crashes with `nn = None` due to mlx unavailability

**Recommendations:**
1. Probe Python 3.13t — it may have better wheel coverage for mlx and other packages
2. File upstream issues for duckdb/lmdb free-threaded support
3. Evaluate aiohttp-only transport (without curl_cffi) as interim workaround
4. Track https://github.com/python-free-threading/third-party-wheels for cp314t wheels
