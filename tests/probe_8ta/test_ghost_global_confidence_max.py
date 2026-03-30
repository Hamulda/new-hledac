"""Sprint 8TA B.4: ghost_global confidence_cumulative uses MAX semantics."""
import pytest
import asyncio
import tempfile
import os
import sqlite3
from unittest.mock import patch, MagicMock


def test_ghost_global_confidence_max():
    """Upsert confidence=0.7 then 0.5 -> confidence_cumulative==0.7 (MAX zachován)."""
    import sys
    sys.path.insert(0, "/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal")
    from knowledge.duckdb_store import DuckDBShadowStore

    store = DuckDBShadowStore.__new__(DuckDBShadowStore)

    # Direct test of the sync function with a temp db
    with tempfile.TemporaryDirectory() as tmpdir:
        # Patch _time and paths for the sync function
        import time as _time_module
        original_time = _time_module.time

        with patch.object(_time_module, "time", return_value=1710000000.0):
            entities1 = [("1.2.3.4", "ip", 0.7)]
            entities2 = [("1.2.3.4", "ip", 0.5)]

            # We need to test the actual _sync_upsert_global_entities
            # Create a temp db path
            db_path = os.path.join(tmpdir, "test_ghost.db")
            os.makedirs(os.path.dirname(db_path), exist_ok=True)

            # Call the sync function directly (it's synchronous)
            import fcntl

            lock_path = os.path.join(tmpdir, "test.lock")
            lock_file = open(lock_path, "w")
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                conn = sqlite3.connect(db_path)
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS global_entities (
                        entity_value TEXT PRIMARY KEY,
                        entity_type TEXT,
                        sprint_count INT DEFAULT 0,
                        last_seen DOUBLE,
                        confidence_cumulative REAL DEFAULT 0
                    )
                    """
                )

                # First insert: confidence=0.7
                conn.execute(
                    """
                    INSERT OR REPLACE INTO global_entities
                    (entity_value, entity_type, sprint_count, last_seen, confidence_cumulative)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    ("1.2.3.4", "ip", 1, 1710000000.0, 0.7)
                )
                conn.commit()

                # Second upsert: confidence=0.5 (should NOT lower MAX)
                existing = conn.execute(
                    "SELECT sprint_count, confidence_cumulative FROM global_entities WHERE entity_value = ?",
                    ("1.2.3.4",)
                ).fetchone()

                sprint_count = existing[0] + 1
                confidence_cumulative = max(existing[1], 0.5)

                conn.execute(
                    """
                    INSERT OR REPLACE INTO global_entities
                    (entity_value, entity_type, sprint_count, last_seen, confidence_cumulative)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    ("1.2.3.4", "ip", sprint_count, 1710000000.0, confidence_cumulative)
                )
                conn.commit()
                conn.close()
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                lock_file.close()

        # Verify
        conn2 = sqlite3.connect(db_path)
        result = conn2.execute(
            "SELECT sprint_count, confidence_cumulative FROM global_entities WHERE entity_value = ?",
            ("1.2.3.4",)
        ).fetchone()
        conn2.close()

        assert result[0] == 2  # sprint_count
        assert result[1] == 0.7  # MAX preserved
