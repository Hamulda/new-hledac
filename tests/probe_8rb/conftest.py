"""Sprint 8RB — pytest configuration."""
import sys
from pathlib import Path

# Ensure hledac.universal is on the path
_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
