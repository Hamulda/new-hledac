"""
Sprint 8RC — Test C.6: sprint_delta schema creation.

Invariant: initialize() creates sprint_delta with 13 required columns.
"""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch


class TestSprint8RCSprintDeltaSchema:
    """Test sprint_delta table creation in initialize()."""

    def test_sprint_delta_schema_created(self):
        """DuckDBShadowStore.initialize() creates sprint_delta with all 13 columns."""
        from hledac.universal.knowledge.duckdb_store import DuckDBShadowStore

        store = DuckDBShadowStore()
        # Initialize synchrously (file-based temp)
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = pathlib.Path(tmpdir) / "test.duckdb"
            store._db_path = db_path
            store._temp_dir = pathlib.Path(tmpdir) / "tmp"
            store._initialized = False
            store._closed = False
            store.initialize()

            # Query the schema
            duckdb = __import__("duckdb")
            conn = duckdb.connect(str(db_path))
            cols = conn.execute(
                "PRAGMA table_info('sprint_delta')"
            ).fetchall()
            conn.close()

            col_names = {r[1] for r in cols}
            expected = {
                "sprint_id", "ts", "query", "duration_s", "new_findings",
                "dedup_hits", "ioc_nodes", "ioc_new_this_sprint", "uma_peak_gib",
                "synthesis_success", "findings_per_min", "top_source_type",
                "synthesis_confidence",
            }
            assert expected.issubset(col_names), f"Missing: {expected - col_names}"
            store.aclose()

    def test_source_hit_log_schema_created(self):
        """source_hit_log table is created with correct schema."""
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

            duckdb = __import__("duckdb")
            conn = duckdb.connect(str(db_path))
            cols = conn.execute(
                "PRAGMA table_info('source_hit_log')"
            ).fetchall()
            conn.close()

            col_names = {r[1] for r in cols}
            expected = {
                "sprint_id", "ts", "source_type",
                "findings_count", "ioc_count", "hit_rate",
            }
            assert expected.issubset(col_names)
            store.aclose()

    def test_get_sprint_trend_empty_table(self):
        """get_sprint_trend() returns [] on empty table."""
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

            result = store.get_sprint_trend(5)
            assert result == []
            store.aclose()
