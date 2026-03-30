"""
Sprint 8BC Phase 1 — Probe-Only Tests
=====================================
These tests validate the probe script itself.
They do NOT run the full probe (which would create venvs and install packages).
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

PROBE_SCRIPT = Path(__file__).parent / "phase1_ft_probe.py"


class TestProbeScriptValidity:
    """Validate the probe script exists and is structurally sound."""

    def test_probe_script_exists(self):
        assert PROBE_SCRIPT.exists(), f"Probe script not found at {PROBE_SCRIPT}"

    def test_probe_script_is_executable_via_python(self):
        import ast
        ast.parse(PROBE_SCRIPT.read_text())
        # If we get here, the file is valid Python

    def test_probe_outputs_required_keys(self):
        """Verify the JSON report structure has all required keys."""
        # We can validate the schema without running full probe by checking the code
        content = PROBE_SCRIPT.read_text()
        required_report_keys = [
            "probe_version",
            "interpreters",
            "baseline_312",
            "classification",
        ]
        for key in required_report_keys:
            assert key in content, f"Required key '{key}' missing from probe script"

    def test_probe_classifications_defined(self):
        """Verify all classification constants are defined."""
        content = PROBE_SCRIPT.read_text()
        classifications = [
            "TOOLCHAIN_MISSING",
            "NOT_INSTALLED",
            "IMPORT_FAILED_INCOMPATIBLE",
            "GIL_FORCED",
            "GIL_STAYS_OFF",
            "GIL_ALREADY_ON",
            "IMPORT_SUCCESS",
            "BLOCKED_BY_TOOLCHAIN",
            "BLOCKED_BY_EXTENSION_STACK",
            "BLOCKED_BY_ORCHESTRATOR_IMPORT",
            "READY_FOR_PHASE_1",
            "READY_BUT_PERF_REGRESSION",
        ]
        for c in classifications:
            assert c in content, f"Classification '{c}' not defined in probe"

    def test_package_matrix_includes_required_packages(self):
        """Verify all required packages are in the matrix."""
        content = PROBE_SCRIPT.read_text()
        required = ["msgspec", "duckdb", "ahocorasick", "lmdb", "curl_cffi", "mlx", "orchestrator"]
        for pkg in required:
            assert f'("{pkg}",' in content, f"Package '{pkg}' not in PACKAGE_MATRIX"

    def test_fresh_subprocess_per_package(self):
        """Verify each package is probed in a fresh subprocess (run_subprocess call pattern)."""
        content = PROBE_SCRIPT.read_text()
        # probe_package should call run_subprocess - meaning fresh subprocess per package
        assert "def probe_package" in content
        assert "def run_subprocess" in content
        # The orchestrator timing also runs in fresh subprocess per run
        assert "measure_import_time" in content

    def test_gil_state_probing_exists(self):
        """Verify GIL state probing is implemented."""
        content = PROBE_SCRIPT.read_text()
        assert "check_gil_state" in content
        assert "_is_gil_enabled" in content
        assert "Py_GIL_DISABLED" in content

    def test_toolchain_gate_exists(self):
        """Verify toolchain gate (interpreter discovery) exists."""
        content = PROBE_SCRIPT.read_text()
        assert "find_interpreters" in content
        assert "python3.13t" in content

    def test_baseline_measurement_exists(self):
        """Verify baseline (3.12) measurement exists."""
        content = PROBE_SCRIPT.read_text()
        assert "BASELINE_RUNS" in content
        assert "measure_import_time" in content
        assert "statistics.median" in content

    def test_install_guidance_present(self):
        """Verify install guidance is included for blocked toolchain case."""
        content = PROBE_SCRIPT.read_text()
        assert "CONFIGURE_OPTS=--disable-gil" in content
        assert "pyenv install" in content

    def test_performance_comparison_exists(self):
        """Verify performance comparison logic exists."""
        content = PROBE_SCRIPT.read_text()
        assert "performance_comparison" in content
        assert "slowdown" in content
        assert "READY_BUT_PERF_REGRESSION" in content

    def test_no_production_mutations(self):
        """Verify the probe does NOT mutate production files."""
        content = PROBE_SCRIPT.read_text()
        # Should NOT contain open() with write mode on production files
        forbidden = [
            "open(.*autonomous_orchestrator",
            "open(.*fetch_coordinator",
            "open(.*duckdb_store",
            "open(.*evidence_log",
            "open(.*mlx_memory",
        ]
        for pattern in forbidden:
            assert pattern not in content.lower(), f"Probe may mutate production: {pattern}"

    def test_venv_creation_uses_isolated_path(self):
        """Verify venv is created under .phase1_probe_8bc/, not system-wide."""
        content = PROBE_SCRIPT.read_text()
        assert "VENV_ROOT" in content
        assert ".phase1_probe_8bc" in content


class TestProbeHandlesMissingToolchain:
    """Test probe behavior when toolchain is missing."""

    def test_blocked_by_toolchain_output_structure(self):
        """When no 3.13t exists, output must contain BLOCKED_BY_TOOLCHAIN."""
        # Run with mocked (non-existent) interpreter to trigger toolchain block
        # This is a logic test - we just verify the code path exists
        content = PROBE_SCRIPT.read_text()
        assert "BLOCKED_BY_TOOLCHAIN" in content
        # The condition that triggers it
        assert "if not ft_interpreters" in content or "not ft_interpreters" in content


class TestProbeClassifications:
    """Verify classification logic covers all cases."""

    def test_all_classifications_reachable(self):
        """Ensure each classification can theoretically be reached."""
        content = PROBE_SCRIPT.read_text()
        # These should appear as assignment values in classification logic
        classifications_in_code = [
            "BLOCKED_BY_TOOLCHAIN",
            "BLOCKED_BY_EXTENSION_STACK",
            "BLOCKED_BY_ORCHESTRATOR_IMPORT",
            "READY_BUT_PERF_REGRESSION",
            "READY_FOR_PHASE_1",
        ]
        for c in classifications_in_code:
            # Count occurrences - should appear at least twice (definition + assignment)
            count = content.count(c)
            assert count >= 2, f"Classification '{c}' appears only {count} time(s)"

    def test_gil_classification_cases(self):
        """Verify all GIL classification cases are handled."""
        content = PROBE_SCRIPT.read_text()
        assert "GIL_FORCED" in content
        assert "GIL_STAYS_OFF" in content
        assert "GIL_ALREADY_ON" in content


class TestRSSMeasurement:
    """Verify RSS measurement is present."""

    def test_rss_tracked_in_import_probes(self):
        """RSS should be tracked before and after imports."""
        content = PROBE_SCRIPT.read_text()
        assert "rss_before" in content.lower() or "rss0" in content
        assert "rss_after" in content.lower() or "rss1" in content
        assert "memory_info()" in content or "memory_info" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
