import pytest
import sys

pytestmark = pytest.mark.skipif(
    sys.version_info[:2] != (3, 12),
    reason="Sprint 8BA requires python3 3.12"
)
