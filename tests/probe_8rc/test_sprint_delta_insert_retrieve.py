"""
Sprint 8RC — Test C.7: sprint_delta insert + get_sprint_trend retrieval.
"""
import pytest
import time


class TestSprint8RCSprintDeltaInsertRetrieve:
    """Test insert → retrieve cycle for sprint_delta."""

    def test_insert_and_retrieve_sprint_delta(self):
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

            # Insert a sprint_delta record
            row = {
                "sprint_id": "sprint_test_001",
                "ts": time.time(),
                "query": "test query",
                "duration_s": 1800.0,
                "new_findings": 42,
                "dedup_hits": 7,
                "ioc_nodes": 10,
                "ioc_new_this_sprint": 3,
                "uma_peak_gib": 0.5,
                "synthesis_success": True,
                "findings_per_min": 1.4,
                "top_source_type": "dark",
                "synthesis_confidence": 0.85,
            }
            result = store.get_sprint_trend(10)
            # Table exists but may be empty — insert via the raw duckdb
            import duckdb
            conn = duckdb.connect(str(db_path))
            conn.execute("""
                INSERT INTO sprint_delta VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, [
                row["sprint_id"], row["ts"], row["query"],
                row["duration_s"], row["new_findings"], row["dedup_hits"],
                row["ioc_nodes"], row["ioc_new_this_sprint"], row["uma_peak_gib"],
                row["synthesis_success"], row["findings_per_min"],
                row["top_source_type"], row["synthesis_confidence"],
            ])
            conn.close()

            # Retrieve via helper
            trend = store.get_sprint_trend(5)
            assert len(trend) >= 1
            latest = trend[0]
            assert latest["sprint_id"] == "sprint_test_001"
            assert latest["new_findings"] == 42
            assert latest["findings_per_min"] == pytest.approx(1.4)
            store.aclose()

    def test_get_sprint_trend_ordered_by_ts_desc(self):
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

            # Insert two sprints with different timestamps
            now = time.time()
            conn = duckdb.connect(str(db_path))
            conn.execute(
                "INSERT INTO sprint_delta VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ["s1", now - 100, "q1", 0, 10, 0, 0, 0, 0, False, 1.0, "a", 0]
            )
            conn.execute(
                "INSERT INTO sprint_delta VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ["s2", now, "q2", 0, 20, 0, 0, 0, 0, False, 2.0, "b", 0]
            )
            conn.close()

            trend = store.get_sprint_trend(5)
            # Most recent first
            assert trend[0]["sprint_id"] == "s2"
            assert trend[1]["sprint_id"] == "s1"
            store.aclose()
