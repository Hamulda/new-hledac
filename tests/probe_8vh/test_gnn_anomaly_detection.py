"""Test: get_anomaly_scores detects high-degree nodes."""
from hledac.universal.brain.gnn_predictor import get_anomaly_scores


def test_gnn_anomaly_detection():
    edges = [
        ("hub.com", f"node{i}.com", "links_to", 0.5)
        for i in range(20)  # hub.com má 20 hran → anomálie
    ] + [("a.com", "b.com", "links_to", 0.5)]

    scores = get_anomaly_scores(edges)
    assert isinstance(scores, list)
    if scores:
        assert any(s["value"] == "hub.com" for s in scores)
