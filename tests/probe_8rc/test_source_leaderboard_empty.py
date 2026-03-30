"""
Sprint 8RC — Test C.12: source_hit_log empty → get_source_leaderboard() returns [].
"""
import pytest


class TestSprint8RCSourceLeaderboardEmpty:
    """Test D.12 — empty source_hit_log returns empty list."""

    def test_leaderboard_empty_on_no_data(self):
        from hledac.universal.knowledge.duckdb_store import DuckDBShadowStore

        store = DuckDBShadowStore()
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = pathlib.Path(tmpdir) / "test.duckdb"
            store._db_path = db_path
            store._temp_dir = pathlib.Path(tmpdir) / "tmp"
            store._initialized = False
            store._closed = False
            store.initialize()

            # Empty table
            result = store.get_source_leaderboard(days=30)
            assert result == []
            store.aclose()

    def test_leaderboard_returns_list_type(self):
        """Return type is always list, never None."""
        from hledac.universal.knowledge.duckdb_store import DuckDBShadowStore

        store = DuckDBShadowStore()
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = pathlib.Path(tmpdir) / "test.duckdb"
            store._db_path = db_path
            store._temp_dir = pathlib.Path(tmpdir) / "tmp"
            store._initialized = False
            store._closed = False
            store.initialize()

            result = store.get_source_leaderboard(days=1)
            assert isinstance(result, list)
            store.aclose()
