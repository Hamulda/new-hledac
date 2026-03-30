"""Sprint 8UC: research_episodes DuckDB table."""
import pytest


def test_research_episodes_table_defined_in_schema():
    """_SCHEMA_SQL must contain research_episodes CREATE TABLE."""
    from hledac.universal.knowledge.duckdb_store import _SCHEMA_SQL
    assert "research_episodes" in _SCHEMA_SQL
    assert "episode_id" in _SCHEMA_SQL
    assert "synthesis_engine" in _SCHEMA_SQL
