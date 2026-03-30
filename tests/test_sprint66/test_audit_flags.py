import subprocess
import sys
from pathlib import Path


def test_audit_flags():
    """Run audit_flags.py and verify it passes."""
    # Find universal directory
    current = Path(__file__).resolve()
    while current.name != "universal" and current.parent != current:
        current = current.parent
    assert current.name == "universal", "Could not find universal directory"
    script = current / "tools" / "audit_flags.py"

    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=str(current.parent)
    )
    assert result.returncode == 0, f"Flag audit failed:\n{result.stdout}\n{result.stderr}"
