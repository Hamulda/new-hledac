import tempfile, pathlib
from graph.quantum_pathfinder import DuckPGQGraph

def test_top_nodes_by_degree():
    with tempfile.TemporaryDirectory() as tmp:
        g = DuckPGQGraph(db_path=str(pathlib.Path(tmp) / "t.duckdb"))
        g.add_relation("hub.com", "a.com", "links_to")
        g.add_relation("hub.com", "b.com", "links_to")
        g.add_relation("hub.com", "c.com", "links_to")
        top = g.get_top_nodes_by_degree(n=5)
        assert len(top) >= 1
        assert top[0]["value"] == "hub.com"  # nejvice hran
