import importlib.util, json, os, subprocess, sys
from pathlib import Path

ROOT = Path("tests/probe_8bg")
out = {}

def run_py(code, cwd=None):
    r = subprocess.run([sys.executable, "-c", code], text=True, capture_output=True, cwd=cwd)
    return {"rc": r.returncode, "stdout": r.stdout[-12000:], "stderr": r.stderr[-12000:]}

moe_router_path = os.environ.get("MOE_ROUTER_PATH", "").strip()
out["moe_router_path"] = moe_router_path

if moe_router_path:
    code = f"""
import importlib.util, pathlib, sys
p = pathlib.Path({moe_router_path!r}).resolve()
spec = importlib.util.spec_from_file_location("probe_moe_router", p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print("OK")
"""
    out["moe_router_import"] = run_py(code)
else:
    out["moe_router_import"] = {"rc": 1, "stdout": "", "stderr": "MOE_ROUTER_NOT_FOUND"}

# AO import - best-effort, never hack sys.path
out["ao_import_pkg"] = run_py(
    "import time; t=time.perf_counter(); import hledac.universal.autonomous_orchestrator as ao; print(f'elapsed={time.perf_counter()-t:.3f}')"
)
out["ao_import_local"] = run_py(
    "import time; t=time.perf_counter(); import autonomous_orchestrator as ao; print(f'elapsed={time.perf_counter()-t:.3f}')"
)

ROOT.joinpath("imports_313t_summary.json").write_text(json.dumps(out, indent=2))
print(json.dumps(out, indent=2))