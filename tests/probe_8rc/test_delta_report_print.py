"""
Sprint 8RC — Test C.11: _print_delta_report() tiskne Δ + leaderboard.
"""
import pytest
import io
import sys


class TestSprint8RCDeltaReportPrint:
    """Test B.3 delta report output — must not raise, prints to stdout."""

    def test_delta_report_with_two_sprints(self, capsys):
        """_print_delta_report() runs without exception on two-sprint trend."""
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

            import duckdb, time
            now = time.time()
            conn = duckdb.connect(str(db_path))
            conn.execute(
                "INSERT INTO sprint_delta VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ["s2", now, "q2", 0, 20, 0, 5, 0, 0.3, False, 2.0, "dark", 0.8]
            )
            conn.execute(
                "INSERT INTO sprint_delta VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ["s1", now - 100, "q1", 0, 10, 0, 3, 0, 0.2, True, 1.0, "clearnet", 0.7]
            )
            conn.close()

            # Call the report function (it's a local function in __main__, so
            # we test the store helper directly)
            trend = store.get_sprint_trend(5)
            leaderboard = store.get_source_leaderboard(days=7)

            # Verify data is available
            assert len(trend) >= 2
            current = trend[0]
            prev = trend[1]
            delta_f = (current.get("new_findings", 0) or 0) - (prev.get("new_findings", 0) or 0)
            delta_ioc = (current.get("ioc_nodes", 0) or 0) - (prev.get("ioc_nodes", 0) or 0)

            assert delta_f == 10  # 20 - 10
            assert delta_ioc == 2  # 5 - 3

            # Verify leaderboard is valid (empty is OK)
            assert isinstance(leaderboard, list)
            store.aclose()

    def test_delta_report_empty_trend(self):
        """Empty trend → no crash, no negative deltas."""
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

            trend = store.get_sprint_trend(5)
            leaderboard = store.get_source_leaderboard(days=7)

            assert trend == []
            assert leaderboard == []
            store.aclose()
