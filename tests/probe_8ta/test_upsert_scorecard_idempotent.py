"""Sprint 8TA B.3: upsert_scorecard uses INSERT OR REPLACE (idempotent)."""
import pytest
import asyncio
import tempfile
import os
import sqlite3


def test_upsert_scorecard_idempotent():
    """upsert_scorecard with same sprint_id twice -> second upsert replaces first."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_scorecard.db")

        # Create table
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sprint_scorecard (
                sprint_id TEXT PRIMARY KEY,
                ts DOUBLE NOT NULL,
                findings_per_minute REAL,
                ioc_density REAL,
                semantic_novelty REAL,
                source_yield_json TEXT,
                phase_timings_json TEXT,
                outlines_used BOOL,
                accepted_findings INT,
                ioc_nodes INT
            )
            """
        )

        data = {
            "sprint_id": "test_sprint_1",
            "ts": 1710000000.0,
            "findings_per_minute": 5.0,
            "ioc_density": 4.0,
            "semantic_novelty": 1.0,
            "source_yield_json": "{}",
            "phase_timings_json": "{}",
            "outlines_used": True,
            "accepted_findings": 10,
            "ioc_nodes": 20,
        }

        # 10 values matching DuckDB schema
        # First insert
        conn.execute(
            """
            INSERT OR REPLACE INTO sprint_scorecard
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            [
                data["sprint_id"], data["ts"], data["findings_per_minute"],
                data["ioc_density"], data["semantic_novelty"], data["source_yield_json"],
                data["phase_timings_json"], data["outlines_used"], data["accepted_findings"],
                data["ioc_nodes"],
            ]
        )
        conn.commit()

        # Second insert with different accepted_findings
        data2 = dict(data)
        data2["accepted_findings"] = 99
        data2["findings_per_minute"] = 99.0

        conn.execute(
            """
            INSERT OR REPLACE INTO sprint_scorecard
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            [
                data2["sprint_id"], data2["ts"], data2["findings_per_minute"],
                data2["ioc_density"], data2["semantic_novelty"], data2["source_yield_json"],
                data2["phase_timings_json"], data2["outlines_used"], data2["accepted_findings"],
                data2["ioc_nodes"],
            ]
        )
        conn.commit()
        conn.close()

        # Verify - should have only 1 row and new values
        conn2 = sqlite3.connect(db_path)
        rows = conn2.execute("SELECT sprint_id, accepted_findings FROM sprint_scorecard").fetchall()
        conn2.close()

        assert len(rows) == 1  # Only one row (replaced)
        assert rows[0][0] == "test_sprint_1"
        assert rows[0][1] == 99  # Updated value
