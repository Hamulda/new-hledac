"""Sprint 8TA B.3: sprint_scorecard table exists in schema."""
import pytest


def test_scorecard_table_exists():
    """DuckDBShadowStore.initialize() -> sprint_scorecard tabulka existuje."""
    # Read _SCHEMA_SQL from duckdb_store module
    import sys
    sys.path.insert(0, "/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal")
    from knowledge.duckdb_store import _SCHEMA_SQL

    assert "sprint_scorecard" in _SCHEMA_SQL
    assert "findings_per_minute" in _SCHEMA_SQL
    assert "ioc_density" in _SCHEMA_SQL
    assert "semantic_novelty" in _SCHEMA_SQL
    assert "source_yield_json" in _SCHEMA_SQL
    assert "phase_timings_json" in _SCHEMA_SQL
    assert "outlines_used" in _SCHEMA_SQL
    assert "accepted_findings" in _SCHEMA_SQL
    assert "ioc_nodes" in _SCHEMA_SQL
