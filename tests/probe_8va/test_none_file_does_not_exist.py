"""
Sprint 8VA: None file does not exist in project root.
Verifies no stale None file exists from prior errors.
"""

import os
import pytest

ROOT = "/Users/vojtechhamada/PycharmProjects/Hledac"


class TestNoneFileDoesNotExist:
    """Verify None file is not present in project root."""

    def test_none_file_does_not_exist(self):
        """Stale None file should not exist in root."""
        none_path = os.path.join(ROOT, "None")
        assert not os.path.exists(none_path), f"Stale None file found at {none_path}"
