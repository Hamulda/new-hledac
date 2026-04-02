"""
Sprint 8VI §E: run_warmup() import and signature test.

Sprint 8VX §D: run_warmup() moved from runtime/sprint_lifecycle.py → __main__.py
This is orchestration, NOT lifecycle state machine.
"""


def test_run_warmup_in_main():
    """run_warmup() must be an async function in __main__.py (Sprint 8VX)."""
    import os
    import sys
    import importlib.util

    _ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
    _MAIN_PY = os.path.join(_ROOT, "hledac", "universal", "__main__.py")
    spec = importlib.util.spec_from_file_location("hledac.universal.__main__", _MAIN_PY)
    assert spec is not None, f"Could not load spec from {_MAIN_PY}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hledac.universal.__main__"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    assert hasattr(mod, "run_warmup"), "run_warmup must be in __main__.py (Sprint 8VX §D)"
    import asyncio
    assert asyncio.iscoroutinefunction(mod.run_warmup), "run_warmup must be async"


def test_runtime_sprint_lifecycle_has_no_warmup():
    """runtime/sprint_lifecycle must NOT have run_warmup (Sprint 8VX §D)."""
    import os
    import sys
    import importlib.util

    _ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
    _RT_PY = os.path.join(_ROOT, "hledac", "universal", "runtime", "sprint_lifecycle.py")
    spec = importlib.util.spec_from_file_location("hledac.universal.runtime.sprint_lifecycle", _RT_PY)
    assert spec is not None, f"Could not load spec from {_RT_PY}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hledac.universal.runtime.sprint_lifecycle"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    assert not hasattr(mod, "run_warmup"), "run_warmup must NOT be in runtime/sprint_lifecycle.py"
