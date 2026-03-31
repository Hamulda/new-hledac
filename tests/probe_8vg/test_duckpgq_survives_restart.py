import tempfile, pathlib
from graph.quantum_pathfinder import DuckPGQGraph

def test_duckpgq_survives_restart():
    with tempfile.TemporaryDirectory() as tmp:
        db = str(pathlib.Path(tmp) / "test_ioc.duckdb")
        g1 = DuckPGQGraph(db_path=db)
        g1.add_relation("185.1.1.1", "evil.com", "resolves_to")
        g1.checkpoint()
        del g1
        g2 = DuckPGQGraph(db_path=db)
        stats = g2.stats()
        assert stats["nodes"] >= 2, "Data nez prezila restart"
        assert stats["edges"] >= 1
