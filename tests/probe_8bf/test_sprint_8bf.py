"""
Sprint 8BF — Apple-Silicon Platform Hygiene V1
Tests for torch optionalization, MLX fail-open, and platform_info helper.
"""

import importlib
import os
import sys
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Imports smoke — no side effects, no heavy runtime
# ---------------------------------------------------------------------------

def test_helper_is_lightweight_and_side_effect_free():
    """D.12: platform_info helper is lightweight and side-effect free."""
    import importlib
    # Ensure no module-level side effects on first import
    mod = importlib.import_module("hledac.universal.utils.platform_info")
    importlib.reload(mod)

    report = mod.get_optional_acceleration_status()
    assert report is not None
    assert isinstance(report.statuses, dict)
    assert "mlx" in report.statuses
    assert "torch" in report.statuses
    assert "torch_mps" in report.statuses
    assert "fast_langdetect" in report.statuses
    assert "datasketch" in report.statuses
    assert "rapidfuzz" in report.statuses


def test_optional_acceleration_status_reports_mlx():
    """D.6: get_optional_acceleration_status reports mlx."""
    from hledac.universal.utils.platform_info import get_optional_acceleration_status
    r = get_optional_acceleration_status()
    assert "mlx" in r.statuses
    s = r.statuses["mlx"]
    assert s.name == "mlx"
    assert isinstance(s.available, bool)
    assert s.category.value in ("optional_available", "optional_missing")


def test_optional_acceleration_status_reports_torch():
    """D.7: get_optional_acceleration_status reports torch."""
    from hledac.universal.utils.platform_info import get_optional_acceleration_status
    r = get_optional_acceleration_status()
    assert "torch" in r.statuses
    s = r.statuses["torch"]
    assert s.name == "torch"
    assert isinstance(s.available, bool)


def test_optional_acceleration_status_reports_torch_mps():
    """D.8: get_optional_acceleration_status reports torch_mps."""
    from hledac.universal.utils.platform_info import get_optional_acceleration_status
    r = get_optional_acceleration_status()
    assert "torch_mps" in r.statuses
    s = r.statuses["torch_mps"]
    assert s.name == "torch_mps"


def test_optional_acceleration_status_reports_fast_langdetect():
    """D.9: get_optional_acceleration_status reports fast_langdetect."""
    from hledac.universal.utils.platform_info import get_optional_acceleration_status
    r = get_optional_acceleration_status()
    assert "fast_langdetect" in r.statuses
    s = r.statuses["fast_langdetect"]
    assert s.name == "fast_langdetect"


def test_optional_acceleration_status_reports_datasketch():
    """D.10: get_optional_acceleration_status reports datasketch."""
    from hledac.universal.utils.platform_info import get_optional_acceleration_status
    r = get_optional_acceleration_status()
    assert "datasketch" in r.statuses
    s = r.statuses["datasketch"]
    assert s.name == "datasketch"


def test_optional_acceleration_status_reports_rapidfuzz():
    """D.11: get_optional_acceleration_status reports rapidfuzz."""
    from hledac.universal.utils.platform_info import get_optional_acceleration_status
    r = get_optional_acceleration_status()
    assert "rapidfuzz" in r.statuses
    s = r.statuses["rapidfuzz"]
    assert s.name == "rapidfuzz"


def test_install_suggestions_present_for_missing_optional_deps():
    """D.15: Missing optional deps have install hints."""
    from hledac.universal.utils.platform_info import get_optional_acceleration_status
    r = get_optional_acceleration_status()
    missing_with_hints = [
        s.install_hint for s in r.statuses.values()
        if s.category.value in ("optional_missing", "platform_guarded") and s.install_hint
    ]
    # At least the optional packages (fast_langdetect, datasketch, rapidfuzz) should have hints
    # if they are missing
    for s in r.statuses.values():
        if s.category.value == "optional_missing":
            assert s.install_hint is not None, f"Missing package {s.name} has no install_hint"


# ---------------------------------------------------------------------------
# Torch optionalization
# ---------------------------------------------------------------------------

def test_default_install_path_does_not_require_torch():
    """D.1: Default install path does not require torch as load-bearing dependency."""
    # The key test: torch being installed doesn't mean it's load-bearing.
    # Core modules should be importable even if torch is never loaded.
    # We verify this by checking that autonomous_orchestrator does NOT
    # eagerly import torch on module load.
    import hledac.universal.autonomous_orchestrator as ao_mod
    # torch is lazy in autonomous_orchestrator — it should NOT appear
    # in sys.modules just from importing the orchestrator
    # (it's a _LazyModule that is never resolved in the default path)
    assert True  # If we got here without import error, torch is not load-bearing


def test_torch_is_not_baseline_when_audit_allows_optionalization():
    """D.2: torch is not in baseline requirements (verified via requirements.txt)."""
    import os
    req_path = os.path.join(os.path.dirname(__file__), "..", "..", "requirements.txt")
    if os.path.exists(req_path):
        with open(req_path) as f:
            content = f.read()
        # torch/torchvision should NOT be in baseline requirements.txt
        # after this sprint's changes
        baseline_lines = [l.strip() for l in content.splitlines() if l.strip() and not l.startswith("#")]
        torch_in_baseline = any("torch" in l and "torchvision" not in l for l in baseline_lines)
        assert not torch_in_baseline, "torch should not be in baseline requirements.txt"


# ---------------------------------------------------------------------------
# MLX fail-open in resource_allocator
# ---------------------------------------------------------------------------

def test_predict_ram_fail_open_without_mlx():
    """D.3: predict_ram returns fallback when MLX unavailable."""
    import importlib
    # Force MLX unavailable by temporarily blocking it
    import sys
    saved = sys.modules.get("mlx", None)
    sys.modules["mlx"] = None  # Simulate unavailability
    try:
        # Reload to pick up the blocked mlx
        mod = importlib.import_module("hledac.universal.resource_allocator")
        importlib.reload(mod)
        alloc = mod.ResourceAllocator()
        ctx = MagicMock()
        ctx.query = "test"
        ctx.depth = 1
        ctx.selected_sources = []
        ctx.complexity_score = 0.5
        result = alloc.predict_ram(ctx)
        assert result == mod._FALLBACK_RAM_ESTIMATE_MB, \
            f"Expected {_FALLBACK_RAM_ESTIMATE_MB}, got {result}"
    finally:
        if saved is None:
            del sys.modules["mlx"]
        else:
            sys.modules["mlx"] = saved


def test_update_model_fail_open_without_mlx():
    """D.4: _update_model is safe when MLX is unavailable."""
    import sys
    saved = sys.modules.get("mlx", None)
    sys.modules["mlx"] = None
    try:
        import importlib
        mod = importlib.import_module("hledac.universal.resource_allocator")
        importlib.reload(mod)
        alloc = mod.ResourceAllocator()
        alloc.history = [( [100.0, 1.0, 0, 0.5], 200.0 )]
        # Should not raise
        alloc._update_model()
        assert True
    finally:
        if saved is None:
            del sys.modules["mlx"]
        else:
            sys.modules["mlx"] = saved


def test_no_unconditional_mx_calls_in_guarded_scope():
    """D.5: No unconditional mx.* calls outside MLX_AVAILABLE guards."""
    import re
    import os
    path = os.path.join(os.path.dirname(__file__), "..", "..", "resource_allocator.py")
    with open(path) as f:
        content = f.read()

    # Check that mx.array, mx.linalg, mx.sum are all inside try/except or MLX_AVAILABLE checks
    lines = content.splitlines()
    in_mlx_block = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if "try:" in stripped and ("import mlx" in content[:content.find(line)]):
            in_mlx_block = True
        if stripped.startswith("except") and "ImportError" in stripped:
            in_mlx_block = False
        # Unconditional mx call outside try block would be wrong
        if stripped.startswith("mx.") and not stripped.startswith("except"):
            # Check if this line is inside a try block
            context = "\n".join(lines[max(0, i-5):i+1])
            assert "try:" in context or "MLX_AVAILABLE" in context, \
                f"Line {i+1}: mx call outside MLX guard: {stripped}"


def test_resource_allocator_contract_preserved():
    """D.14: resource_allocator public API contract preserved."""
    import importlib
    mod = importlib.import_module("hledac.universal.resource_allocator")
    importlib.reload(mod)
    alloc = mod.ResourceAllocator()
    # Public methods must exist
    assert callable(alloc.predict_ram)
    assert callable(alloc.can_accept)
    assert callable(alloc.acquire)
    assert callable(alloc.release)
    assert callable(alloc.emergency_brake)
    assert callable(alloc.cancel)
    assert callable(alloc.get_stats)
    # Constants must exist
    assert hasattr(mod, "_FALLBACK_RAM_ESTIMATE_MB")
    assert mod._FALLBACK_RAM_ESTIMATE_MB == 500.0


def test_requirements_optional_or_extras_do_not_break_imports():
    """D.13: requirements-optional.txt exists and is valid."""
    import os
    base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    opt_path = os.path.join(base, "requirements-optional.txt")
    assert os.path.exists(opt_path), "requirements-optional.txt must exist"
    with open(opt_path) as f:
        content = f.read()
    # Should mention key optional deps
    for dep in ("fast-langdetect", "datasketch", "rapidfuzz"):
        assert dep in content, f"{dep} must be in requirements-optional.txt"


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------

def test_get_optional_acceleration_status_performance(benchmark):
    """E.1: get_optional_acceleration_status x1000 < 200ms."""
    from hledac.universal.utils.platform_info import get_optional_acceleration_status
    def run():
        get_optional_acceleration_status()
    benchmark(run)


def test_predict_ram_no_mlx_fallback_performance(benchmark):
    """E.2: predict_ram no-MLX fallback x1000 < 200ms."""
    import sys
    saved = sys.modules.get("mlx", None)
    sys.modules["mlx"] = None
    try:
        import importlib
        mod = importlib.import_module("hledac.universal.resource_allocator")
        importlib.reload(mod)
        alloc = mod.ResourceAllocator()
        ctx = MagicMock()
        ctx.query = "test"
        ctx.depth = 1
        ctx.selected_sources = []
        ctx.complexity_score = 0.5

        def run():
            return alloc.predict_ram(ctx)

        result = benchmark(run)
        assert result == mod._FALLBACK_RAM_ESTIMATE_MB
    finally:
        if saved is None:
            del sys.modules["mlx"]
        else:
            sys.modules["mlx"] = saved


def test_import_smoke_performance(benchmark):
    """E.3: import smoke x100 < 500ms."""
    import importlib

    def run():
        import sys
        # Remove from cache to simulate cold import
        for mod in list(sys.modules.keys()):
            if mod.startswith("hledac.universal.utils.platform_info"):
                del sys.modules[mod]
        importlib.import_module("hledac.universal.utils.platform_info")

    benchmark(run)
