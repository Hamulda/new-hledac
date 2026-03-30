"""
Sprint 8BD Phase 1 — pytest suite for free-threaded probe.
These are probe-only tests — no production code changes.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROBE_DIR = Path(__file__).parent
PROBE_SCRIPT = PROBE_DIR / "phase1_ft_probe_314.py"
REPORT_FILE = PROBE_DIR / "probe_result_314.json"
REPO_ROOT = Path("/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal")
VENV_FT = REPO_ROOT / ".phase1_probe_8bd" / "venv_ft"


class TestProbeStructure:
    """Verify probe script structure and required functions."""

    def test_probe_script_exists(self):
        assert PROBE_SCRIPT.exists(), f"Probe script not found: {PROBE_SCRIPT}"

    def test_probe_script_runs_without_error(self):
        """Run the probe script — it may fail but must not crash."""
        r = subprocess.run(
            [sys.executable, str(PROBE_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=600,
        )
        # We only care it doesn't crash; classification may vary
        assert r.returncode in (0, 1), f"Probe crashed: {r.stderr[:500]}"

    def test_report_json_is_valid(self):
        """Report JSON must be valid if produced."""
        if not REPORT_FILE.exists():
            pytest.skip("Report not yet produced")
        with open(REPORT_FILE) as f:
            data = json.load(f)
        assert "classification" in data
        assert data["classification"] in [
            "READY_FOR_PHASE_1",
            "READY_BUT_PERF_REGRESSION",
            "BLOCKED_BY_PERF_REGRESSION",
            "BLOCKED_BY_EXTENSION_STACK",
            "BLOCKED_BY_ORCHESTRATOR_IMPORT",
            "BLOCKED_BY_TOOLCHAIN",
        ]


class TestFreeThreadedInterpreter:
    """Verify free-threaded interpreter is properly installed and verified."""

    def test_ft_python_exists(self):
        candidates = [
            REPO_ROOT / ".phase1_probe_8bd" / "venv_ft" / "bin" / "python3.14t",
            Path.home() / ".pyenv" / "versions" / "3.14.2t" / "bin" / "python3.14t",
        ]
        found = any(p.exists() for p in candidates)
        assert found, f"No free-threaded Python found in {candidates}"

    def test_ft_python_has_gil_disabled(self):
        candidates = [
            REPO_ROOT / ".phase1_probe_8bd" / "venv_ft" / "bin" / "python3.14t",
            Path.home() / ".pyenv" / "versions" / "3.14.2t" / "bin" / "python3.14t",
        ]
        for p in candidates:
            if p.exists():
                r = subprocess.run(
                    [str(p), "-c",
                     "import sys, sysconfig; "
                     "assert sysconfig.get_config_var('Py_GIL_DISABLED') == 1, 'GIL not disabled'"],
                    capture_output=True, text=True, timeout=10,
                )
                if r.returncode == 0:
                    return  # PASS
        pytest.fail("No free-threaded Python with Py_GIL_DISABLED=1 found")


class TestPackageMatrix:
    """Verify package matrix captures all required fields."""

    def test_required_packages_in_matrix(self):
        if not REPORT_FILE.exists():
            pytest.skip("Report not yet produced")
        with open(REPORT_FILE) as f:
            data = json.load(f)
        matrix = data.get("package_matrix", {})
        required = ["msgspec", "duckdb", "pyahocorasick", "lmdb", "curl_cffi", "mlx"]
        for pkg in required:
            assert pkg in matrix, f"Package {pkg} missing from matrix"

    def test_each_package_has_classification(self):
        if not REPORT_FILE.exists():
            pytest.skip("Report not yet produced")
        with open(REPORT_FILE) as f:
            data = json.load(f)
        matrix = data.get("package_matrix", {})
        for pkg, results in matrix.items():
            for interpreter in ["current", "ft"]:
                if interpreter in results:
                    r = results[interpreter]
                    assert "classification" in r, f"{pkg}/{interpreter} missing classification"
                    assert r["classification"] is not None


class TestGILStateCapture:
    """Verify GIL state is captured for each package import."""

    def test_gil_before_after_captured(self):
        if not REPORT_FILE.exists():
            pytest.skip("Report not yet produced")
        with open(REPORT_FILE) as f:
            data = json.load(f)
        matrix = data.get("package_matrix", {})
        for pkg, results in matrix.items():
            for interpreter in ["current", "ft"]:
                if interpreter in results:
                    r = results[interpreter]
                    assert "gil_before" in r, f"{pkg}/{interpreter} missing gil_before"
                    assert "gil_after" in r, f"{pkg}/{interpreter} missing gil_after"


class TestStderrCapture:
    """Verify stderr warnings are captured."""

    def test_stderr_captured_per_package(self):
        if not REPORT_FILE.exists():
            pytest.skip("Report not yet produced")
        with open(REPORT_FILE) as f:
            data = json.load(f)
        matrix = data.get("package_matrix", {})
        for pkg, results in matrix.items():
            for interpreter in ["current", "ft"]:
                if interpreter in results:
                    r = results[interpreter]
                    assert "stderr" in r, f"{pkg}/{interpreter} missing stderr"


class TestLMDBOperational:
    """Verify LMDB has an operational read/write probe."""

    def test_lmdb_ft_has_operational_result(self):
        if not REPORT_FILE.exists():
            pytest.skip("Report not yet produced")
        with open(REPORT_FILE) as f:
            data = json.load(f)
        matrix = data.get("package_matrix", {})
        lmdb = matrix.get("lmdb", {})
        assert "ft_op" in lmdb, "LMDB operational probe result missing"
        op = lmdb["ft_op"]
        assert "success" in op, "LMDB operational probe missing 'success' field"


class TestOrchestratorImport:
    """Verify orchestrator import timing is captured."""

    def test_baseline_orchestrator_recorded(self):
        if not REPORT_FILE.exists():
            pytest.skip("Report not yet produced")
        with open(REPORT_FILE) as f:
            data = json.load(f)
        baseline = data.get("baseline_interpreter", {})
        orch = baseline.get("orchestrator", {})
        assert "median" in orch, "Baseline orchestrator median missing"
        assert "stdev" in orch, "Baseline orchestrator stdev missing"
        assert orch.get("success") is True or orch.get("median") is not None

    def test_ft_orchestrator_recorded(self):
        if not REPORT_FILE.exists():
            pytest.skip("Report not yet produced")
        with open(REPORT_FILE) as f:
            data = json.load(f)
        ft = data.get("ft_interpreter", {})
        if ft and ft.get("path"):
            orch = ft.get("orchestrator", {})
            if orch:
                assert "median" in orch, "FT orchestrator median missing"


class TestVenvSize:
    """Verify venv size is reported."""

    def test_venv_size_reported(self):
        if not REPORT_FILE.exists():
            pytest.skip("Report not yet produced")
        with open(REPORT_FILE) as f:
            data = json.load(f)
        assert "venv_size_mb" in data, "venv_size_mb missing from report"
        assert data["venv_size_mb"] >= 0


class TestPerformanceDelta:
    """Verify performance delta is computed."""

    def test_perf_delta_computed(self):
        if not REPORT_FILE.exists():
            pytest.skip("Report not yet produced")
        with open(REPORT_FILE) as f:
            data = json.load(f)
        if data.get("ft_interpreter") and data.get("baseline_interpreter"):
            delta = data.get("perf_delta_s")
            assert delta is not None, "perf_delta_s missing"


class TestClassification:
    """Verify final classification is valid."""

    def test_classification_is_valid(self):
        if not REPORT_FILE.exists():
            pytest.skip("Report not yet produced")
        with open(REPORT_FILE) as f:
            data = json.load(f)
        valid = {
            "READY_FOR_PHASE_1",
            "READY_BUT_PERF_REGRESSION",
            "BLOCKED_BY_PERF_REGRESSION",
            "BLOCKED_BY_EXTENSION_STACK",
            "BLOCKED_BY_ORCHESTRATOR_IMPORT",
            "BLOCKED_BY_TOOLCHAIN",
        }
        assert data.get("classification") in valid
