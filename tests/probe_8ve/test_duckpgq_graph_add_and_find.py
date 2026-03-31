from hledac.universal.graph.quantum_pathfinder import DuckPGQGraph


def test_duckpgq_graph_add_and_find():
    g = DuckPGQGraph()
    g.add_relation("185.220.101.47", "evil.com",
                   rel_type="resolves_to", evidence="test")
    connected = g.find_connected("185.220.101.47", max_hops=1)
    assert len(connected) >= 1
    assert any(r["value"] == "evil.com" for r in connected)
