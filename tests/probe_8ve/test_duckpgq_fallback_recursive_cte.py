from hledac.universal.graph import quantum_pathfinder as qp


def test_duckpgq_fallback_recursive_cte():
    original = qp._DUCKPGQ_AVAILABLE
    qp._DUCKPGQ_AVAILABLE = False
    try:
        g = qp.DuckPGQGraph()
        g.add_relation("a.com", "b.com", rel_type="links_to")
        result = g.find_connected("a.com", max_hops=1)
        assert isinstance(result, list)
    finally:
        qp._DUCKPGQ_AVAILABLE = original
