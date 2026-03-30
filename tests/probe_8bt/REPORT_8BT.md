# SPRINT 8BT — OPSEC LEAK AUDIT REPORT
## Probe: TempFiles, External Binaries, Raw FD Leaks

**Date:** 2026-03-24
**Scope:** `hledac/universal/` — READ-ONLY probe, no production edits

---

## EXECUTIVE SUMMARY

| Category | Status | Risk |
|----------|--------|------|
| `tempfile` SSD leaks | ❌ CRITICAL | HIGH |
| External binaries OPSEC | ⚠️ MODERATE | MEDIUM |
| Raw FD leaks | ✅ CLEAN | LOW |

**Primary Finding:** `config/paths.py` defines proper RAMDISK paths but **`tempfile.tempdir` is NEVER set**. All `tempfile` calls without explicit `dir=` write to system tempdir (`/tmp` on macOS) → **direct SSD leak**.

---

## 1. TEMPFILE AUDIT

### Finding: `tempfile.tempdir` Not Configured

`config/paths.py` exports:
- `RAMDISK_ROOT` = `/Volumes/ghost_tmp` (if active) or `~/.hledac_fallback_ramdisk`
- `FALLBACK_ROOT`
- `CACHE_ROOT`, `LMDB_ROOT`, `EVIDENCE_ROOT`, etc.

**BUT:** No code ever sets `tempfile.tempdir = RAMDISK_ROOT` or `tempfile.tempdir = str(FALLBACK_ROOT)`.

**Impact:** Every `tempfile.NamedTemporaryFile()` or `tempfile.mkdtemp()` without explicit `dir=` writes to `/tmp` on macOS → physical SSD I/O.

---

### Critical: SSD Leaks Detected

#### 1. `security/vault_manager.py` — 4 instances

| Line | Call | Issue |
|------|------|-------|
| 106 | `tempfile.NamedTemporaryFile(delete=False, suffix='.zip')` | No `dir=` → SSD |
| 132 | `tempfile.NamedTemporaryFile(delete=False, suffix='.zip')` | No `dir=` → SSD |
| 259 | `tempfile.NamedTemporaryFile(delete=False, suffix='.zip')` | No `dir=` → SSD |
| 303 | `tempfile.NamedTemporaryFile(delete=False, suffix='.zip')` | No `dir=` → SSD |

**All 4** are used for intermediate encrypted ZIP operations in `LootManager`.

#### 2. `tools/osint_frameworks.py` — 1 instance

| Line | Call | Issue |
|------|------|-------|
| 30 | `tempfile.NamedTemporaryFile(suffix='', delete=False)` | No `dir=` → SSD |

Used for `theHarvester` output file (`-f` flag). TheHarvester writes JSON/XML to this file.

#### 3. `autonomous_orchestrator.py` — 1 instance

| Line | Call | Issue |
|------|------|-------|
| 12286 | `tempfile.mkdtemp(prefix="hledac_seed_")` | No `dir=` → SSD |

Used for seed RNG state directory. This is **especially problematic** — cryptographic seed material written to SSD.

---

### Correct Usage Found

#### `autonomous_orchestrator.py` line 8836 — CORRECT ✅

```python
with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as f:
```

Uses explicit `dir=path.parent` (project parent directory, not system temp).

---

## 2. EXTERNAL BINARIES AUDIT

### `tools/osint_frameworks.py` — OSINT Tools

| Tool | Output Method | Config Paths | Status |
|------|--------------|-------------|--------|
| `theHarvester` | File (`-f` flag) | Temp file on SSD (no `dir=`) | ⚠️ MODERATE |
| `sherlock` | stdout JSON (`--json`) | None | ✅ OK |
| `maigret` | stdout JSON (`-j`) | None | ✅ OK |

**Issue:** `theHarvester` output file is created on SSD. No `TMPDIR` override or `dir=` param.

**External config paths in theHarvester:**
- Default config: `~/.theHarvester/` — **OPSEC risk** (not RAMDISK)
- No mechanism detected to redirect to RAMDISK

### `security/self_healing.py` — CI/CD Health Checks

Uses `asyncio.create_subprocess_exec` for:
- `flake8`, `mypy`, `safety`, `bandit`, `pytest`, `black`, `find`

**All pipes consumed via `await process.communicate()`** — no FD leaks.

**Config paths:**
- `bandit -f json` → stdout only, no config file leak
- `safety check --json` → stdout only
- `theHarvester` (if called from self-healing) → same SSD leak issue

---

## 3. FD LEAK SCANNER

### All `asyncio.create_subprocess_exec` calls — CLEAN ✅

All 20+ instances across the codebase properly:
1. Set `stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE`
2. Call `.communicate()` or `await asyncio.wait_for(process, timeout=...)`

### `subprocess.Popen` — Found Only in Test/Bak Files

```
tests/probe_8bo/boundary_audit.json:322489
tests/probe_8bk/model_data_hits.json (x3, comments only)
```

No production `subprocess.Popen` without `.wait()` or `.communicate()` detected.

---

## 4. DETAILED FINDINGS

### CRITICAL (Fix Immediately)

| ID | File | Line | Issue | Fix |
|----|------|------|-------|-----|
| T-1 | `security/vault_manager.py` | 106,132,259,303 | `NamedTemporaryFile` SSD leak | Add `dir=str(RAMDISK_ROOT)` or `dir=str(FALLBACK_ROOT)` |
| T-2 | `autonomous_orchestrator.py` | 12286 | `mkdtemp` SSD leak (crypto seed!) | Add `dir=str(RAMDISK_ROOT)` |
| T-3 | `tools/osint_frameworks.py` | 30 | `NamedTemporaryFile` SSD leak | Add `dir=str(RAMDISK_ROOT)` |

### MODERATE (Fix Soon)

| ID | File | Line | Issue | Fix |
|----|------|------|-------|-----|
| X-1 | `tools/osint_frameworks.py` | theHarvester | Config `~/.theHarvester/` on SSD | Set `XDG_CONFIG_HOME` or `--config` flag to RAMDISK |

### LOW (Good Hygiene)

| ID | File | Line | Issue | Fix |
|----|------|------|-------|-----|
| G-1 | All `tempfile` users | — | `tempfile.tempdir` never set globally | Add `tempfile.tempdir = str(RAMDISK_ROOT)` in `paths.py` init |

---

## 5. RECOMMENDED FIXES

### Fix 1: Global `tempfile.tempdir` in `paths.py`

After `RAMDISK_ROOT` initialization in `paths.py`, add:

```python
import tempfile as _tempfile
_tempfile.tempdir = str(RAMDISK_ROOT)
```

This ensures **all** `tempfile` calls without explicit `dir=` go to RAMDISK.

### Fix 2: Fix `security/vault_manager.py` (4 sites)

```python
# Before
with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_file:

# After
from paths import RAMDISK_ROOT
with tempfile.NamedTemporaryFile(delete=False, suffix='.zip', dir=str(RAMDISK_ROOT)) as temp_file:
```

### Fix 3: Fix `autonomous_orchestrator.py:12286`

```python
# Before
temp_dir = tempfile.mkdtemp(prefix="hledac_seed_")

# After
from paths import RAMDISK_ROOT
temp_dir = tempfile.mkdtemp(prefix="hledac_seed_", dir=str(RAMDISK_ROOT))
```

### Fix 4: Fix `tools/osint_frameworks.py:30`

```python
# Before
with tempfile.NamedTemporaryFile(suffix='', delete=False) as f:
    out_file = f.name

# After
from paths import RAMDISK_ROOT
with tempfile.NamedTemporaryFile(suffix='', delete=False, dir=str(RAMDISK_ROOT)) as f:
    out_file = f.name
```

### Fix 5: External tool environment override

For `theHarvester` in `osint_frameworks.py`:

```python
import os
from paths import RAMDISK_ROOT

env = os.environ.copy()
env['XDG_CONFIG_HOME'] = str(RAMDISK_ROOT / 'config')
env['TMPDIR'] = str(RAMDISK_ROOT)

proc = await asyncio.create_subprocess_exec(
    'theHarvester', '-d', target, '-b', 'all', '-f', out_file,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    env=env
)
```

---

## 6. INVARIANTS VERIFIED

| Test | Result | Evidence |
|------|--------|----------|
| `tempfile.tempdir` not set globally | ❌ FAIL | No `tempfile.tempdir =` anywhere |
| All `tempfile` have `dir=` | ❌ FAIL | 6 instances without `dir=` |
| External tools config on RAMDISK | ❌ FAIL | `~/.theHarvester/` on SSD |
| `subprocess.Popen` FD cleanup | ✅ PASS | All use `.communicate()` |
| `asyncio.create_subprocess_exec` FD cleanup | ✅ PASS | All use `.communicate()` or `wait()` |

---

## 7. CONCLUSION

**Immediate action required** to close the SSD leak vector. The `paths.py` RAMDISK infrastructure is correctly implemented, but `tempfile.tempdir` was never wired up. Without this single line, all tempfile operations without explicit `dir=` leak to SSD.

**Priority order:**
1. Add `tempfile.tempdir = str(RAMDISK_ROOT)` to `paths.py` (one line, closes most leaks)
2. Fix `vault_manager.py` 4 instances (crypto material on SSD is critical)
3. Fix `autonomous_orchestrator.py:12286` (crypto seed on SSD)
4. Fix `osint_frameworks.py:30` (OPSEC research data)
5. Wire `XDG_CONFIG_HOME` for theHarvester

**FD leaks: CLEAN** — no remediation needed.
