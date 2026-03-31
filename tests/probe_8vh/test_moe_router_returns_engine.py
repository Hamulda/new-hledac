"""Test: MoE router returns correct engine strings."""
from hledac.universal.brain.moe_router import route_synthesis, route_embedding


def test_moe_router_returns_engine():
    assert route_synthesis(0, False, "normal", "test") == "heuristic"
    assert route_synthesis(100, True, "normal", "threat") in ("hermes3", "inference", "heuristic")
    assert route_synthesis(10, False, "critical", "test") == "heuristic"
    assert route_embedding("critical") == "hash_fallback"
    assert route_embedding("normal") == "ane_minilm"
