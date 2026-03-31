from hledac.universal.graph.quantum_pathfinder import _stable_node_id


def test_stable_node_id_deterministic():
    """hash() není deterministický — ověř že náš ID generátor je."""
    id1 = _stable_node_id("185.220.101.47")
    id2 = _stable_node_id("185.220.101.47")
    assert id1 == id2
    assert id1 != _stable_node_id("1.1.1.1")
    assert id1 > 0
