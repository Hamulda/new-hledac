"""Test: predict_from_edge_list accepts edge list format."""
from hledac.universal.brain.gnn_predictor import predict_from_edge_list


def test_gnn_predict_from_edge_list():
    edges = [
        ("1.2.3.4", "evil.com", "resolves_to", 0.9),
        ("1.2.3.4", "bad.net",  "resolves_to", 0.8),
        ("evil.com", "malware.ru", "links_to", 0.7),
    ]
    result = predict_from_edge_list(edges, top_k=5)
    assert isinstance(result, list)
    for r in result:
        assert "src" in r and "dst" in r and "score" in r
        assert 0.0 <= r["score"] <= 1.0
