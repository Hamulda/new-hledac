"""
Sprint 8RC — Test C.8: source_hit_log insert + get_source_leaderboard.
"""
import pytest
import time


class TestSprint8RCSourceHitLog:
    """Test source_hit_log insert and leaderboard query."""

    def test_log_source_hit_and_leaderboard(self):
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

            import duckdb
            now = time.time()
            conn = duckdb.connect(str(db_path))
            # Insert source_hit_log records
            conn.execute(
                "INSERT INTO source_hit_log VALUES (?,?,?,?,?,?)",
                ["s1", now - 100, "clearnet", 10, 5, 0.5]
            )
            conn.execute(
                "INSERT INTO source_hit_log VALUES (?,?,?,?,?,?)",
                ["s1", now - 50, "dark", 20, 10, 0.67]
            )
            conn.execute(
                "INSERT INTO source_hit_log VALUES (?,?,?,?,?,?)",
                ["s2", now, "clearnet", 15, 8, 0.6]
            )
            conn.close()

            leaderboard = store.get_source_leaderboard(days=7)
            assert len(leaderboard) >= 1
            # clearnet should appear
            clearnet_row = next(
                (r for r in leaderboard if r["source_type"] == "clearnet"),
                None
            )
            assert clearnet_row is not None
            assert clearnet_row["total_findings"] == 25  # 10 + 15
            store.aclose()

    def test_source_hit_log_top_source(self):
        from hledac.universal.knowledge.duckdb_store import DuckDBShadowStore
        import duckdb

        store = DuckDBShadowStore()
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = pathlib.Path(tmpdir) / "test.duckdb"
            store._db_path = db_path
            store._temp_dir = pathlib.Path(tmpdir) / "tmp"
            store._initialized = False
            store._closed = False
            store.initialize()

            now = time.time()
            conn = duckdb.connect(str(db_path))
            conn.execute(
                "INSERT INTO source_hit_log VALUES (?,?,?,?,?,?)",
                ["s1", now, "dark", 100, 20, 0.9]
            )
            conn.execute(
                "INSERT INTO source_hit_log VALUES (?,?,?,?,?,?)",
                ["s1", now, "clearnet", 5, 1, 0.1]
            )
            conn.close()

            leaderboard = store.get_source_leaderboard(days=1)
            assert leaderboard[0]["source_type"] == "dark"
            assert leaderboard[0]["total_findings"] == 100
            store.aclose()

    def test_leaderboard_empty_source_hit_log(self):
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

            # No data inserted — should return empty
            leaderboard = store.get_source_leaderboard(days=1)
            assert leaderboard == []
            store.aclose()
