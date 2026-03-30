#!/usr/bin/env python3
"""
Sprint 8BD Phase 1 — Python 3.14 free-threaded truth probe.
Runs in FRESH SUBPROCESS per package. Captures GIL state, RSS, stderr.
"""

import sys
import os
import json
import subprocess
import statistics
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────────

REPO_ROOT = Path("/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal")
PROBE_DIR = REPO_ROOT / "tests" / "probe_8bd"
VENV_FT   = REPO_ROOT / ".phase1_probe_8bd" / "venv_ft"

PACKAGES = [
    "msgspec",
    "duckdb",
    "pyahocorasick",
    "lmdb",
    "curl_cffi",
    "mlx",
]

ORCHESTRATOR_PATH = "hledac.universal.autonomous_orchestrator"


# ── Helpers ───────────────────────────────────────────────────────────────────

def run_fresh(python: str, code: str, *, capture_stderr=True) -> dict:
    """Run code in a fresh subprocess, return dict with timing, stdout, stderr, rc."""
    import time, psutil, os as _os
    proc = psutil.Process(_os.getpid())
    rss_before = proc.memory_info().rss // (1024 * 1024)

    gil_before = None
    gil_after  = None

    probe_code = f"""
import sys, sysconfig, os, time, psutil
p = psutil.Process(os.getpid())
rss0 = p.memory_info().rss // (1024*1024)

gil_fn = getattr(sys, "_is_gil_enabled", None)
gil_before = gil_fn() if gil_fn else "NOT_SUPPORTED"

t0 = time.perf_counter()
try:
{chr(10).join("    " + line for line in code.splitlines())}
    dt = time.perf_counter() - t0
    success = True
    error = None
except Exception as e:
    dt = time.perf_counter() - t0
    success = False
    error = repr(e)

gil_after = gil_fn() if gil_fn else "NOT_SUPPORTED"
rss1 = p.memory_info().rss // (1024*1024)

import json as _json
print(_json.dumps({{
    "success": success,
    "dt": dt,
    "error": error,
    "gil_before": gil_before,
    "gil_after": gil_after,
    "rss_before": rss0,
    "rss_after": rss1,
}}))
"""

    stderr_capture = subprocess.PIPE if capture_stderr else subprocess.DEVNULL
    try:
        r = subprocess.run(
            [python, "-c", probe_code],
            capture_output=True,
            text=True,
            timeout=120,
        )
        stdout = r.stdout.strip()
        stderr = r.stderr.strip()
        rc = r.returncode
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "TIMEOUT", "dt": None,
                "gil_before": None, "gil_after": None, "rss_before": None, "rss_after": None,
                "stdout": "", "stderr": "TIMEOUT", "rc": -1}

    # Parse JSON result from stdout
    result = {"rc": rc, "stdout": stdout, "stderr": stderr}
    try:
        parsed = json.loads(stdout)
        result.update(parsed)
    except json.JSONDecodeError:
        result["parse_error"] = stdout[:500]

    return result


def get_interpreter_info(python: str) -> dict:
    """Get version and GIL info for an interpreter."""
    code = """
import sys, sysconfig, json
gil_fn = getattr(sys, "_is_gil_enabled", None)
info = {
    "version": sys.version,
    "version_info": list(sys.version_info[:3]),
    "executable": sys.executable,
    "gil_enabled": gil_fn() if gil_fn else "NOT_SUPPORTED",
    "Py_GIL_DISABLED": sysconfig.get_config_var("Py_GIL_DISABLED"),
    "has_free_threading": sysconfig.get_config_var("Py_GIL_DISABLED") == 1,
}
print(json.dumps(info))
"""
    r = subprocess.run([python, "-c", code], capture_output=True, text=True, timeout=10)
    try:
        return json.loads(r.stdout.strip())
    except json.JSONDecodeError:
        return {"raw_stdout": r.stdout, "raw_stderr": r.stderr, "rc": r.returncode}


def probe_package(python: str, package: str) -> dict:
    """Run import probe for a single package in fresh subprocess."""
    code = f"import {package}"
    result = run_fresh(python, code)

    # Classify result
    if result.get("rc", 0) != 0 or not result.get("success"):
        stderr = result.get("stderr", "")
        stdout = result.get("stdout", "")
        if "No module named" in stderr or "No module named" in stdout:
            classification = "NOT_INSTALLED"
        elif "not find" in stderr.lower() or "not found" in stderr.lower():
            classification = "TOOLCHAIN_MISSING"
        elif "unable to find" in stderr.lower():
            classification = "INSTALL_FAILED_NO_WHEEL"
        elif "incompatible" in stderr.lower() or "incompatible" in stdout.lower():
            classification = "IMPORT_FAILED_INCOMPATIBLE"
        elif result.get("error") == "TIMEOUT":
            classification = "TIMEOUT"
        else:
            classification = "IMPORT_FAILED_OTHER"
    else:
        # Check GIL state
        gil_before = result.get("gil_before")
        gil_after  = result.get("gil_after")
        if gil_before == "NOT_SUPPORTED":
            classification = "GIL_ALREADY_ON"
        elif gil_after == "NOT_SUPPORTED":
            classification = "GIL_ALREADY_ON"
        elif gil_before is False and gil_after is True:
            classification = "GIL_FORCED_BY_EXTENSION"
        elif gil_before is False and gil_after is False:
            classification = "GIL_STAYS_OFF"
        elif gil_before is True and gil_after is True:
            classification = "GIL_ALREADY_ON"
        else:
            classification = f"GIL_TRANSITION_{gil_before}_TO_{gil_after}"

    result["classification"] = classification
    result["package"] = package
    result["python"] = python
    return result


def lmdb_operational_probe(python: str) -> dict:
    """Minimal read/write LMDB operational probe in a temp directory."""
    code = """
import tempfile, os, sys, json
try:
    import lmdb
except ImportError as e:
    print(json.dumps({"success": False, "error": repr(e)}))
    sys.exit(0)

tmpdir = tempfile.mkdtemp()
db_path = os.path.join(tmpdir, "probe.lmdb")
try:
    env = lmdb.open(db_path, max_dbs=1)
    with env.begin(write=True) as txn:
        txn.put(b"key1", b"value1")
        txn.put(b"key2", b"value2")
    with env.begin() as txn:
        val1 = txn.get(b"key1")
        val2 = txn.get(b"key2")
    env.close()
    success = val1 == b"value1" and val2 == b"value2"
    print(json.dumps({"success": success, "error": None if success else "value mismatch"}))
finally:
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)
"""
    r = subprocess.run([python, "-c", code], capture_output=True, text=True, timeout=30)
    try:
        return json.loads(r.stdout.strip())
    except json.JSONDecodeError:
        return {"success": False, "error": r.stdout[:200], "stderr": r.stderr[:200]}


def orchestrator_import_probe(python: str, n_runs: int = 5) -> dict:
    """5-run orchestrator import probe with RSS and timing."""
    code = """
import time, psutil, os
p = psutil.Process(os.getpid())
rss0 = p.memory_info().rss // (1024*1024)
t = time.perf_counter()
import hledac.universal.autonomous_orchestrator
dt = time.perf_counter() - t
rss1 = p.memory_info().rss // (1024*1024)
print(f"{dt:.6f}|{rss0}|{rss1}")
"""
    timings, rss_samples = [], []
    all_stderr = []

    for _ in range(n_runs):
        r = subprocess.run(
            [python, "-c", code],
            capture_output=True, text=True, timeout=60,
        )
        stderr = r.stderr.strip()
        if stderr:
            all_stderr.append(stderr)

        # Extract timing line (may be prefixed with Warning)
        for line in r.stdout.strip().split("\n"):
            if "|" in line:
                parts = line.split("|")
                if len(parts) == 3:
                    try:
                        dt, r0, r1 = parts
                        timings.append(float(dt))
                        rss_samples.append((int(r0), int(r1)))
                    except ValueError:
                        pass

    if not timings:
        return {
            "success": False,
            "error": "no valid timing samples",
            "all_stderr": all_stderr[:3],
            "runs": [],
            "median": None,
            "stdev": None,
        }

    return {
        "success": True,
        "runs": timings,
        "median": statistics.median(timings),
        "stdev": statistics.stdev(timings) if len(timings) > 1 else 0.0,
        "min": min(timings),
        "max": max(timings),
        "rss_samples_mb": rss_samples,
        "all_stderr": all_stderr[:5],
        "n_runs": len(timings),
    }


def get_venv_size(venv_path: Path) -> int:
    """Get total size of venv in bytes."""
    if not venv_path.exists():
        return 0
    total = 0
    for dirpath, _, filenames in os.walk(venv_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total


def main():
    # ── 1. Current baseline interpreter ─────────────────────────────────────
    current_python = sys.executable
    print(f"\n{'='*70}")
    print(f"PHASE 1 FREE-THREADED PROBE — Sprint 8BD")
    print(f"{'='*70}")
    print(f"\n[1] CURRENT BASELINE INTERPRETER")
    print(f"    Python: {current_python}")

    baseline_info = get_interpreter_info(current_python)
    print(f"    Version: {baseline_info.get('version', 'N/A')}")
    print(f"    GIL enabled: {baseline_info.get('gil_enabled', 'N/A')}")
    print(f"    Py_GIL_DISABLED: {baseline_info.get('Py_GIL_DISABLED', 'N/A')}")

    # ── 2. Free-threaded interpreter ─────────────────────────────────────────
    ft_python = None

    # Try pyenv 3.14t first
    candidates = [
        "~/.pyenv/versions/3.14t/bin/python3.14t",
        "~/.pyenv/versions/3.14.2t/bin/python3.14t",
        "/Library/Frameworks/Python.framework/Versions/3.14t/bin/python3.14t",
    ]

    for cand in candidates:
        path = os.path.expanduser(cand)
        if os.path.isfile(path):
            ft_python = path
            break

    if not ft_python or not os.path.exists(ft_python):
        print(f"\n[2] FREE-THREADED INTERPRETER")
        print(f"    STATUS: NOT_FOUND")
        print(f"    Searched: {candidates}")
        print(f"\n    CLASSIFICATION: BLOCKED_BY_TOOLCHAIN")
        print(f"    Install still in progress or failed.")
        return

    print(f"\n[2] FREE-THREADED INTERPRETER")
    print(f"    Python: {ft_python}")

    ft_info = get_interpreter_info(ft_python)
    print(f"    Version: {ft_info.get('version', 'N/A')}")
    print(f"    GIL enabled: {ft_info.get('gil_enabled', 'N/A')}")
    print(f"    Py_GIL_DISABLED: {ft_info.get('Py_GIL_DISABLED', 'N/A')}")

    ft_gil = ft_info.get("gil_enabled")
    ft_free_threading = ft_info.get("has_free_threading", False)

    if not ft_free_threading:
        print(f"\n    WARNING: This interpreter does NOT have free-threading enabled!")
        print(f"    Py_GIL_DISABLED={ft_info.get('Py_GIL_DISABLED')}")

    # ── 3. Package probe matrix ───────────────────────────────────────────────
    print(f"\n[3] PACKAGE PROBE MATRIX")
    print(f"{'─'*70}")

    pkg_matrix = {}
    for pkg in PACKAGES:
        print(f"  Probing {pkg} on current interpreter...", end=" ", flush=True)
        r = probe_package(current_python, pkg)
        pkg_matrix[pkg] = {"current": r}
        print(f"[{r.get('classification','?')}]")

    if ft_python and ft_free_threading:
        print(f"\n  Probing {pkg} on free-threaded interpreter...", end=" ", flush=True)
        for pkg in PACKAGES:
            print(f"  Probing {pkg} on FT interpreter...", end=" ", flush=True)
            r = probe_package(ft_python, pkg)
            pkg_matrix[pkg]["ft"] = r
            print(f"[{r.get('classification','?')}]")

    # ── 4. LMDB operational probe ─────────────────────────────────────────────
    print(f"\n[4] LMDB OPERATIONAL PROBE")
    print(f"{'─'*70}")

    for python_name, python_path in [("current", current_python), ("ft", ft_python)]:
        if python_path:
            print(f"  {python_name}: ", end="", flush=True)
            op_result = lmdb_operational_probe(python_path)
            status = "PASS" if op_result.get("success") else f"FAIL ({op_result.get('error','')})"
            print(f"[{status}]")
            if python_name == "ft":
                pkg_matrix["lmdb"]["ft_op"] = op_result

    # ── 5. Venv size ──────────────────────────────────────────────────────────
    venv_size_bytes = get_venv_size(VENV_FT)
    venv_size_mb = venv_size_bytes / (1024 * 1024)

    print(f"\n[5] VENV SIZE")
    print(f"    {VENV_FT}: {venv_size_mb:.1f} MB")

    # ── 6. Orchestrator import ────────────────────────────────────────────────
    print(f"\n[6] ORCHESTRATOR IMPORT PROBE")
    print(f"{'─'*70}")

    print(f"  Current baseline (5 runs)...")
    baseline_orch = orchestrator_import_probe(current_python, n_runs=5)
    print(f"    median={baseline_orch.get('median'):.3f}s stdev={baseline_orch.get('stdev',0):.3f}s "
          f"min={baseline_orch.get('min',0):.3f}s max={baseline_orch.get('max',0):.3f}s")

    ft_orch = None
    ft_classification = "NOT_RUN"
    if ft_python and ft_free_threading:
        print(f"  Free-threaded (5 runs)...")
        ft_orch = orchestrator_import_probe(ft_python, n_runs=5)
        print(f"    median={ft_orch.get('median'):.3f}s stdev={ft_orch.get('stdev',0):.3f}s "
              f"min={ft_orch.get('min',0):.3f}s max={ft_orch.get('max',0):.3f}s")

        if ft_orch.get("success"):
            delta = ft_orch.get("median", 0) - baseline_orch.get("median", 0)
            if delta <= 0.2:
                ft_classification = "READY_FOR_PHASE_1"
            elif delta <= 0.5:
                ft_classification = "READY_BUT_PERF_REGRESSION"
            else:
                ft_classification = "BLOCKED_BY_PERF_REGRESSION"
        else:
            ft_classification = "BLOCKED_BY_ORCHESTRATOR_IMPORT"
    else:
        ft_classification = "BLOCKED_BY_TOOLCHAIN"

    # ── 7. Final report ───────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"FINAL CLASSIFICATION: {ft_classification}")
    print(f"{'='*70}")

    report = {
        "classification": ft_classification,
        "baseline_interpreter": {
            "path": current_python,
            **baseline_info,
            "orchestrator": baseline_orch,
        },
        "ft_interpreter": {
            "path": ft_python,
            **ft_info,
            "orchestrator": ft_orch,
        } if ft_python else None,
        "package_matrix": pkg_matrix,
        "venv_size_mb": venv_size_mb,
        "perf_delta_s": (
            (ft_orch.get("median", 0) - baseline_orch.get("median", 0))
            if ft_orch and baseline_orch else None
        ),
    }

    report_path = PROBE_DIR / "probe_result_314.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\nReport saved to: {report_path}")
    print(json.dumps(report, indent=2, default=str))

    return report


if __name__ == "__main__":
    main()
