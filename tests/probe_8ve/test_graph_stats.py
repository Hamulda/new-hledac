from hledac.universal.graph.quantum_pathfinder import DuckPGQGraph


def test_graph_stats():
    g = DuckPGQGraph()
    g.add_ioc("1.2.3.4", "ip")
    g.add_ioc("evil.com", "domain")
    g.add_relation("1.2.3.4", "evil.com", "resolves_to")
    s = g.stats()
    assert s["nodes"] == 2
    assert s["edges"] == 1
