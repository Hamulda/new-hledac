import tempfile, pathlib
from graph.quantum_pathfinder import DuckPGQGraph

def test_duckpgq_export_edge_list():
    with tempfile.TemporaryDirectory() as tmp:
        g = DuckPGQGraph(db_path=str(pathlib.Path(tmp) / "t.duckdb"))
        g.add_relation("1.2.3.4", "evil.com", "resolves_to", weight=0.9)
        edges = g.export_edge_list()
        assert len(edges) >= 1
        src, dst, rel, w = edges[0]
        assert isinstance(src, str) and isinstance(dst, str)
        assert w > 0
