"""Sprint 8TC B.1: RRF formula k=30"""
import pytest


def test_rrf_formula_k30():
    """Ověřit: 1/(30+1) ≈ 0.03226 pro rank-1 dokument v jednom signálu"""
    k = 30
    rank_1 = 1.0 / (k + 1)
    assert abs(rank_1 - 0.032258) < 0.001
    # Pro rank-2
    rank_2 = 1.0 / (k + 2)
    assert abs(rank_2 - 0.03125) < 0.001
    # Pro rank-3
    rank_3 = 1.0 / (k + 3)
    assert abs(rank_3 - 0.030303) < 0.001
