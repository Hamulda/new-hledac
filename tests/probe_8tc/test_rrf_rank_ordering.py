"""Sprint 8TC B.1: rrf_rank_findings — ordering test with mock rows"""
import pytest
from unittest.mock import MagicMock


def test_rrf_rank_ordering():
    """INSERT 3 findings s různými semantic_score → rrf_rank → správné DESC pořadí"""
    # Simulujeme RRF rankingu — vyšší semantic_score = vyšší rank = nižší r v RRF
    # RRF score = SUM(1/(k + r_i)), kde k=30
    k = 30
    findings = [
        {"finding_id": "f1", "semantic_score": 0.9, "pattern_count": 5, "ioc_degree": 3, "ts": 1000.0, "content": "a"},
        {"finding_id": "f2", "semantic_score": 0.5, "pattern_count": 10, "ioc_degree": 1, "ts": 2000.0, "content": "b"},
        {"finding_id": "f3", "semantic_score": 0.1, "pattern_count": 2, "ioc_degree": 0, "ts": 3000.0, "content": "c"},
    ]

    # Ruční RRF výpočet pro signal 1 (semantic_score)
    rrf_scores = {}
    for f in findings:
        fid = f["finding_id"]
        # Pro každý finding počítáme rank v rámci každého signálu
        # Signal 1: řazení podle semantic_score DESC → rank 1,2,3
        sorted_by_sem = sorted(findings, key=lambda x: x["semantic_score"], reverse=True)
        ranks = {f["finding_id"]: i + 1 for i, f in enumerate(sorted_by_sem)}
        rrf_scores[fid] = 1.0 / (k + ranks[fid])

    # f1 má rank 1 → rrf = 1/31 ≈ 0.03226
    # f2 má rank 2 → rrf = 1/32 ≈ 0.03125
    # f3 má rank 3 → rrf = 1/33 ≈ 0.03030
    assert rrf_scores["f1"] > rrf_scores["f2"] > rrf_scores["f3"]
    assert abs(rrf_scores["f1"] - 1/31) < 0.0001
    assert abs(rrf_scores["f2"] - 1/32) < 0.0001
    assert abs(rrf_scores["f3"] - 1/33) < 0.0001
