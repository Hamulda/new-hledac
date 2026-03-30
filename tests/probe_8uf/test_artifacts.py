"""Test artifact cleanup (Sprint 8UF B.7)."""
import os
import pytest


class TestArtifacts:
    """Artifact cleanup tests."""

    def test_duckdb_new_files_removed(self):
        """duckdb_store.py.new and .new2 should not exist."""
        base = "knowledge"
        assert not os.path.exists(os.path.join(base, "duckdb_store.py.new")), \
            "knowledge/duckdb_store.py.new should be deleted"
        assert not os.path.exists(os.path.join(base, "duckdb_store.py.new2")), \
            "knowledge/duckdb_store.py.new2 should be deleted"

    def test_gitignore_has_py_new_pattern(self):
        """Check .gitignore contains *.py.new pattern."""
        if os.path.exists(".gitignore"):
            content = open(".gitignore").read()
            assert "*.py.new" in content, ".gitignore should contain *.py.new pattern"
            assert "*.py.new2" in content, ".gitignore should contain *.py.new2 pattern"
            assert "*.py.bak" in content, ".gitignore should contain *.py.bak pattern"

    def test_deprecation_warning_in_persistent_layer(self):
        """persistent_layer.py should have DeprecationWarning."""
        path = "knowledge/persistent_layer.py"
        if os.path.exists(path):
            content = open(path).read()
            assert "DeprecationWarning" in content, \
                "persistent_layer.py should contain DeprecationWarning"

    def test_deprecation_warning_in_atomic_storage(self):
        """atomic_storage.py should have DeprecationWarning."""
        path = "knowledge/atomic_storage.py"
        if os.path.exists(path):
            content = open(path).read()
            assert "DeprecationWarning" in content, \
                "atomic_storage.py should contain DeprecationWarning"
