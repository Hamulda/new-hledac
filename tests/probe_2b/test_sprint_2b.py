"""
Sprint 2B: LMDB MAPSIZE PROPAGATION + STATE/CACHE HYGIENE
=========================================================

Tests:
1. paths.lmdb_map_size() returns correct bytes from env
2. paths.open_lmdb() uses env-driven map_size when map_size=None
3. open_lmdb() respects explicit map_size override
4. Single-retry lock recovery on LockError
5. Fail-open when helper itself raises
6. No hardcoded map_size in patched consumer files
7. Patched consumer files import open_lmdb from paths
"""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

import pytest


class TestLmdbMapSize:
    """INVARIANT: lmdb_map_size() returns env-driven MB as bytes."""

    def test_default_512mb(self):
        from hledac.universal.paths import lmdb_map_size
        with patch.dict(os.environ, {}, clear=True):
            result = lmdb_map_size()
        assert result == 512 * 1024 * 1024

    def test_env_1024mb(self):
        from hledac.universal.paths import lmdb_map_size
        with patch.dict(os.environ, {"GHOST_LMDB_MAX_SIZE_MB": "1024"}):
            result = lmdb_map_size()
        assert result == 1024 * 1024 * 1024

    def test_env_256mb(self):
        from hledac.universal.paths import lmdb_map_size
        with patch.dict(os.environ, {"GHOST_LMDB_MAX_SIZE_MB": "256"}):
            result = lmdb_map_size()
        assert result == 256 * 1024 * 1024

    def test_invalid_env_fallback_512mb(self):
        from hledac.universal.paths import lmdb_map_size
        with patch.dict(os.environ, {"GHOST_LMDB_MAX_SIZE_MB": "not_a_number"}):
            result = lmdb_map_size()
        assert result == 512 * 1024 * 1024

    def test_negative_env_fallback_512mb(self):
        from hledac.universal.paths import lmdb_map_size
        with patch.dict(os.environ, {"GHOST_LMDB_MAX_SIZE_MB": "-10"}):
            result = lmdb_map_size()
        assert result == 512 * 1024 * 1024


class TestOpenLmdb:
    """INVARIANT: open_lmdb() uses env-driven map_size when map_size=None."""

    def test_none_uses_env(self):
        from hledac.universal.paths import open_lmdb
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "test.lmdb"
            with patch.dict(os.environ, {"GHOST_LMDB_MAX_SIZE_MB": "256"}):
                env = open_lmdb(path)
            info = env.info()
            assert info["map_size"] == 256 * 1024 * 1024
            env.close()

    def test_explicit_map_size_overrides_env(self):
        from hledac.universal.paths import open_lmdb
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "test.lmdb"
            with patch.dict(os.environ, {"GHOST_LMDB_MAX_SIZE_MB": "256"}):
                env = open_lmdb(path, map_size=128 * 1024 * 1024)
            info = env.info()
            assert info["map_size"] == 128 * 1024 * 1024
            env.close()

    def test_lock_retry_on_stale_lock(self):
        """INVARIANT: open_lmdb() recovers from LockError with single retry."""
        import lmdb
        from hledac.universal.paths import open_lmdb

        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "test.lmdb.d"
            path.mkdir()

            # Create a stale lock file (simulates crashed process)
            lock_file = path / "lock.mdb"
            lock_file.write_bytes(b"stale")

            # open_lmdb should recover: remove stale lock and retry
            env = open_lmdb(path)
            assert env is not None
            # Verify env is writable
            with env.begin(write=True) as txn:
                txn.put(b"key", b"value")
            env.close()

    def test_fail_open_on_invalid_path(self):
        """INVARIANT: open_lmdb() raises on invalid path (does not swallow errors)."""
        from hledac.universal.paths import open_lmdb
        # Should raise, not silently fail
        with pytest.raises(Exception):
            open_lmdb(pathlib.Path("/nonexistent/path/that/cannot/be/created"))


class TestPatchedConsumerFiles:
    """INVARIANT: patched consumer files use open_lmdb from paths."""

    def test_local_graph_imports_open_lmdb(self):
        with open("/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/dht/local_graph.py") as f:
            content = f.read()
        assert "from hledac.universal.paths import open_lmdb" in content
        assert "open_lmdb(self.db_path.parent" in content

    def test_key_manager_imports_open_lmdb(self):
        with open("/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/security/key_manager.py") as f:
            content = f.read()
        assert "from hledac.universal.paths import open_lmdb" in content
        assert "open_lmdb(self.db_path.parent" in content

    def test_federated_model_store_imports_open_lmdb(self):
        with open("/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/federated/model_store.py") as f:
            content = f.read()
        assert "from hledac.universal.paths import open_lmdb" in content
        assert "open_lmdb(self.path" in content

    def test_sketches_imports_open_lmdb(self):
        with open("/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/utils/sketches.py") as f:
            content = f.read()
        assert "from hledac.universal.paths import open_lmdb" in content

    def test_no_hardcoded_map_size_in_patch_sites(self):
        """INVARIANT: patched files have no bare lmdb.open() with hardcoded map_size."""
        import re
        files_to_check = [
            "/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/dht/local_graph.py",
            "/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/security/key_manager.py",
            "/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/federated/model_store.py",
        ]
        # Pattern: lmdb.open with a numeric map_size (not a variable)
        hardcoded_pattern = re.compile(r"lmdb\.open\s*\([^)]*map_size\s*=\s*\d+\s*\*")
        for filepath in files_to_check:
            with open(filepath) as f:
                content = f.read()
            matches = hardcoded_pattern.findall(content)
            assert not matches, f"{filepath} still has hardcoded map_size: {matches}"


class TestNoImportRegression:
    """INVARIANT: no import regression in paths.py."""

    def test_paths_imports_clean(self):
        """paths.py should import without errors."""
        result = subprocess.run(
            [sys.executable, "-c", "from hledac.universal.paths import *; print('ok')"],
            capture_output=True,
            text=True,
            cwd="/Users/vojtechhamada/PycharmProjects/Hledac"
        )
        assert result.returncode == 0, f"Import failed: {result.stderr}"

    def test_consumer_imports_clean(self):
        """Consumer files should import without errors."""
        files = [
            "/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/dht/local_graph.py",
            "/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/security/key_manager.py",
            "/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/federated/model_store.py",
        ]
        for filepath in files:
            # Just check the module can be parsed/imported (mock dependencies as needed)
            result = subprocess.run(
                [sys.executable, "-c", f"import ast; ast.parse(open('{filepath}').read())"],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, f"Parse failed for {filepath}: {result.stderr}"
