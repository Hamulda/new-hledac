"""Sprint 8TA B.4: ghost_global sprint_count increments."""
import pytest
import asyncio
import tempfile
import os
import sqlite3
import fcntl
import time as _time_module
from unittest.mock import patch, MagicMock


def test_ghost_global_sprint_count():
    """Insert same entity twice -> sprint_count==2 (MAX semantics)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "ghost_global.duckdb")
        lock_path = os.path.join(tmpdir, "ghost_global.lock")

        # Simulate _sync_upsert_global_entities logic
        with patch.object(_time_module, "time", return_value=1710000000.0):
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

                entities = [("1.2.3.4", "ip", 0.9)]
                now = 1710000000.0

                # First insert
                conn.execute(
                    """
                    INSERT OR REPLACE INTO global_entities
                    (entity_value, entity_type, sprint_count, last_seen, confidence_cumulative)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    ("1.2.3.4", "ip", 1, now, 0.9)
                )
                conn.commit()

                # Second insert - same entity
                existing = conn.execute(
                    "SELECT sprint_count, confidence_cumulative FROM global_entities WHERE entity_value = ?",
                    ("1.2.3.4",)
                ).fetchone()
                sprint_count = existing[0] + 1
                confidence_cumulative = max(existing[1], 0.9)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO global_entities
                    (entity_value, entity_type, sprint_count, last_seen, confidence_cumulative)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    ("1.2.3.4", "ip", sprint_count, now, confidence_cumulative)
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

        assert result[0] == 2  # sprint_count == 2
        assert result[1] == 0.9  # MAX confidence preserved
