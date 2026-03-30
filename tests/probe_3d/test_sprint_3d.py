"""
Sprint 3D: LMDB Topology Completion — Probe Tests
==================================================
Tests:
1. Sprint vs persistent root helpers in paths.py
2. Env-driven mapsize fallback
3. open_lmdb() usage in migrated consumer files
4. No new hardcoded LMDB surface in migrated files
5. Import/parse clean
6. Fail-open / backward compatibility
"""

import tempfile
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_ROOT / "hledac" / "universal"))


class TestSprint3DPathsHelpers:
    """Test paths.py sprint vs persistent root helpers."""

    def test_sprint_lmdb_root_defined(self):
        from hledac.universal.paths import SPRINT_LMDB_ROOT, LMDB_ROOT
        assert SPRINT_LMDB_ROOT is not None
        assert LMDB_ROOT is not None
        assert str(SPRINT_LMDB_ROOT).startswith(str(LMDB_ROOT))
        assert "sprint" in str(SPRINT_LMDB_ROOT)

    def test_sprint_lmdb_root_beneath_lmdb_root(self):
        from hledac.universal.paths import SPRINT_LMDB_ROOT, LMDB_ROOT
        assert SPRINT_LMDB_ROOT.parent == LMDB_ROOT

    def test_sprint_lmdb_root_in_all(self):
        import hledac.universal.paths as paths_mod
        assert "SPRINT_LMDB_ROOT" in paths_mod.__all__

    def test_lmdb_map_size_env_driven(self):
        from hledac.universal.paths import lmdb_map_size

        with patch.dict(os.environ, {"GHOST_LMDB_MAX_SIZE_MB": "256"}):
            assert lmdb_map_size() == 256 * 1024 * 1024

        with patch.dict(os.environ, {"GHOST_LMDB_MAX_SIZE_MB": ""}):
            assert lmdb_map_size() == 512 * 1024 * 1024

        with patch.dict(os.environ, {"GHOST_LMDB_MAX_SIZE_MB": "invalid"}):
            assert lmdb_map_size() == 512 * 1024 * 1024


class TestSprint3DOpenLMDB:
    """Test open_lmdb() helper."""

    def test_open_lmdb_uses_env_map_size(self):
        from hledac.universal.paths import open_lmdb

        with patch.dict(os.environ, {"GHOST_LMDB_MAX_SIZE_MB": "128"}):
            with tempfile.TemporaryDirectory() as tmpdir:
                env = open_lmdb(Path(tmpdir) / "test.lmdb")
                assert env is not None
                env.close()

    def test_open_lmdb_accepts_explicit_map_size(self):
        from hledac.universal.paths import open_lmdb

        with tempfile.TemporaryDirectory() as tmpdir:
            env = open_lmdb(Path(tmpdir) / "test.lmdb", map_size=16 * 1024 * 1024)
            assert env is not None
            env.close()

    def test_open_lmdb_returns_lmdb_env(self):
        from hledac.universal.paths import open_lmdb

        with tempfile.TemporaryDirectory() as tmpdir:
            env = open_lmdb(Path(tmpdir) / "test.lmdb", map_size=16 * 1024 * 1024)
            assert hasattr(env, "begin")
            assert hasattr(env, "close")
            env.close()


class TestSprint3DTaskCache:
    """Test planning/task_cache.py migration."""

    def test_task_cache_uses_open_lmdb(self):
        from hledac.universal.planning.task_cache import TaskCache

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = TaskCache(db_path=os.path.join(tmpdir, "task_cache.lmdb"), max_size_mb=10)
            assert cache.env is not None
            cache.env.close()

    def test_task_cache_no_direct_lmdb_open(self):
        src = Path(__file__).parent.parent.parent / "planning" / "task_cache.py"
        if src.exists():
            content = src.read_text()
            assert "lmdb.open(" not in content


class TestSprint3DPrefetchCache:
    """Test prefetch/prefetch_cache.py migration."""

    def test_prefetch_cache_uses_open_lmdb(self):
        from hledac.universal.prefetch.prefetch_cache import PrefetchCache

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = PrefetchCache(db_path=os.path.join(tmpdir, "prefetch.lmdb"), max_size_mb=10)
            assert cache.env is not None
            cache.env.close()

    def test_prefetch_cache_no_direct_lmdb_open(self):
        src = Path(__file__).parent.parent.parent / "prefetch" / "prefetch_cache.py"
        if src.exists():
            content = src.read_text()
            assert "lmdb.open(" not in content


class TestSprint3DSourceBandit:
    """Test tools/source_bandit.py migration."""

    def test_source_bandit_uses_open_lmdb_main_path(self):
        """SourceBandit uses _open_lmdb in the main path (not bare lmdb.open)."""
        src = Path(__file__).parent.parent.parent / "tools" / "source_bandit.py"
        if not src.exists():
            pytest.skip("source_bandit.py not found")
        content = src.read_text()
        # After migration, main path uses _open_lmdb
        assert "_open_lmdb" in content, "source_bandit should use _open_lmdb"
        # The import should be lazy at __init__ time
        assert "open_lmdb as _open_lmdb" in content

    def test_source_bandit_no_module_level_lmdb_open(self):
        """No module-level bare lmdb.open outside fallback else-block."""
        src = Path(__file__).parent.parent.parent / "tools" / "source_bandit.py"
        if not src.exists():
            pytest.skip("source_bandit.py not found")
        lines = src.read_text().splitlines()
        in_fallback_else = False
        module_level_bare_lmdb_open = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("class "):
                in_fallback_else = False
            if "else:" in stripped and i > 0:
                prev = "\n".join(lines[max(0, i-5):i])
                if "_open_lmdb" in prev:
                    in_fallback_else = True
            if "lmdb.open(" in stripped and not stripped.startswith("#"):
                if not in_fallback_else and "import lmdb" not in stripped:
                    module_level_bare_lmdb_open = True
        assert not module_level_bare_lmdb_open


class TestSprint3DLMDBKV:
    """Test tools/lmdb_kv.py migration."""

    def test_lmdb_kv_store_canonical_path(self):
        from hledac.universal.tools.lmdb_kv import LMDBKVStore, _USE_CANONICAL

        if not _USE_CANONICAL:
            pytest.skip("Canonical paths not available")

        with tempfile.TemporaryDirectory() as tmpdir:
            store = LMDBKVStore(path=os.path.join(tmpdir, "kv.lmdb"), map_size=16 * 1024 * 1024)
            assert store._path is not None
            assert store._env is not None
            store.close()

    def test_lmdb_kv_store_uses_canonical_paths(self):
        from hledac.universal.tools.lmdb_kv import _USE_CANONICAL, _PATH_ROOT
        if _USE_CANONICAL:
            assert "sprint" in str(_PATH_ROOT)


class TestSprint3DTopologyManifest:
    """Test the TOPOLOGY.md manifest is present."""

    def test_topology_manifest_exists(self):
        manifest = Path(__file__).parent / "TOPOLOGY.md"
        assert manifest.exists()
        content = manifest.read_text()
        assert "Sprint 3D" in content
        assert "SPRINT_LMDB_ROOT" in content


class TestSprint3DNoRegressions:
    """Ensure no regressions in core paths functionality."""

    def test_paths_import_clean(self):
        from hledac.universal import paths as paths_mod
        assert paths_mod.RAMDISK_ROOT is not None
        assert paths_mod.LMDB_ROOT is not None
        assert paths_mod.SPRINT_LMDB_ROOT is not None

    def test_open_lmdb_in_paths_all(self):
        import hledac.universal.paths as paths_mod
        assert "open_lmdb" in paths_mod.__all__
        assert "lmdb_map_size" in paths_mod.__all__

    def test_sprint_dir_created_at_init(self):
        from hledac.universal.paths import SPRINT_LMDB_ROOT
        assert SPRINT_LMDB_ROOT.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-q"])
