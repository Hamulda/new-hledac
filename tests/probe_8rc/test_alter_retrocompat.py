"""
Sprint 8RC — Test C.9: ALTER TABLE retrokompatibilita.

Invariant: initialize() adds missing columns to existing sprint_delta via ALTER TABLE.
"""
import pytest
import duckdb
import tempfile
import pathlib


class TestSprint8RCAlterRetrocompat:
    """Test B.2 ALTER TABLE ADD COLUMN for retrokompatibilita."""

    def test_alter_table_adds_missing_columns(self):
        """
        Simulate an old sprint_delta without new columns.
        initialize() must ADD them without error.
        """
        from hledac.universal.knowledge.duckdb_store import DuckDBShadowStore

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = pathlib.Path(tmpdir) / "old_sprint.duckdb"

            # Create OLD schema (missing: findings_per_min, synthesis_confidence, top_source_type)
            conn = duckdb.connect(str(db_path))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sprint_delta (
                    sprint_id TEXT PRIMARY KEY,
                    ts DOUBLE NOT NULL,
                    query TEXT,
                    duration_s REAL DEFAULT 0,
                    new_findings INT DEFAULT 0,
                    dedup_hits INT DEFAULT 0,
                    ioc_nodes INT DEFAULT 0,
                    ioc_new_this_sprint INT DEFAULT 0,
                    uma_peak_gib REAL DEFAULT 0,
                    synthesis_success BOOL DEFAULT false
                )
            """)
            # Also source_hit_log
            conn.execute("""
                CREATE TABLE IF NOT EXISTS source_hit_log (
                    sprint_id TEXT,
                    ts DOUBLE,
                    source_type TEXT,
                    findings_count INT,
                    ioc_count INT,
                    hit_rate REAL
                )
            """)
            conn.close()

            # Now initialize the store — should ALTER TABLE to add missing columns
            store = DuckDBShadowStore()
            store._db_path = db_path
            store._temp_dir = pathlib.Path(tmpdir) / "tmp"
            store._initialized = False
            store._closed = False
            result = store.initialize()
            assert result is True

            # Verify all columns now exist
            conn = duckdb.connect(str(db_path))
            cols = conn.execute("PRAGMA table_info('sprint_delta')").fetchall()
            conn.close()

            col_names = {r[1] for r in cols}
            assert "findings_per_min" in col_names
            assert "synthesis_confidence" in col_names
            assert "top_source_type" in col_names
            store.aclose()

    def test_no_error_on_already_present_columns(self):
        """ALTER TABLE does not fail if column already exists."""
        from hledac.universal.knowledge.duckdb_store import DuckDBShadowStore

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = pathlib.Path(tmpdir) / "full_sprint.duckdb"

            # Create full schema first
            conn = duckdb.connect(str(db_path))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sprint_delta (
                    sprint_id TEXT PRIMARY KEY,
                    ts DOUBLE NOT NULL,
                    query TEXT,
                    duration_s REAL DEFAULT 0,
                    new_findings INT DEFAULT 0,
                    dedup_hits INT DEFAULT 0,
                    ioc_nodes INT DEFAULT 0,
                    ioc_new_this_sprint INT DEFAULT 0,
                    uma_peak_gib REAL DEFAULT 0,
                    synthesis_success BOOL DEFAULT false,
                    findings_per_min REAL DEFAULT 0,
                    top_source_type TEXT,
                    synthesis_confidence REAL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS source_hit_log (
                    sprint_id TEXT,
                    ts DOUBLE,
                    source_type TEXT,
                    findings_count INT,
                    ioc_count INT,
                    hit_rate REAL
                )
            """)
            conn.close()

            # Should not raise
            store = DuckDBShadowStore()
            store._db_path = db_path
            store._temp_dir = pathlib.Path(tmpdir) / "tmp"
            store._initialized = False
            store._closed = False
            result = store.initialize()
            assert result is True
            store.aclose()
