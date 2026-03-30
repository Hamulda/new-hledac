"""Sprint 8TC B.1: RRF four signals SQL query structure"""
import pytest
import re


def test_rrf_four_signals_union():
    """SQL query v rrf_rank_findings obsahuje 4× ROW_NUMBER (4 signály)"""
    # Načteme actual source code rrf_rank_findings
    import hledac.universal.knowledge.duckdb_store as store_module
    import inspect
    source = inspect.getsource(store_module.DuckDBShadowStore.rrf_rank_findings)

    # Počet ROW_NUMBER volání
    row_number_count = source.count("ROW_NUMBER()")
    assert row_number_count >= 4, f"Expected at least 4 ROW_NUMBER calls, got {row_number_count}"

    # 4 signály = 4 CTEs (s1, s2, s3, s4)
    cte_count = len(re.findall(r'\bs[1-4]\s+AS\s*\(', source))
    assert cte_count == 4, f"Expected 4 signal CTEs, got {cte_count}"

    # UNION ALL mezi signály
    assert "UNION ALL" in source, "Missing UNION ALL between signal CTEs"
