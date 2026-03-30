"""Set up path for tests."""
import sys
import os

# Ensure we're running from the universal directory
_universal_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _universal_dir not in sys.path:
    sys.path.insert(0, _universal_dir)
