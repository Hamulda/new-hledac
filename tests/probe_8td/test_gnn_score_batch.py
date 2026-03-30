"""Sprint 8TD: GNN IOC batch scoring tests."""
from unittest.mock import MagicMock


class TestGNNscoreBatch:
    """Test score_ioc_batch functionality."""

    def test_score_ioc_batch_returns_dict(self):
        """score_ioc_batch returns dict with float scores."""
        from hledac.universal.brain.gnn_predictor import GNNPredictor

        predictor = GNNPredictor.__new__(GNNPredictor)
        predictor.graph = {}
        predictor.node_features = {}

        result = predictor.score_ioc_batch([("1.2.3.4", "ipv4")], None)

        assert isinstance(result, dict)
        assert "1.2.3.4" in result
        assert isinstance(result["1.2.3.4"], float)

    def test_score_ioc_batch_default_fallback(self):
        """When graph.degree raises, default 0.5 score returned."""
        from hledac.universal.brain.gnn_predictor import GNNPredictor

        predictor = GNNPredictor.__new__(GNNPredictor)
        predictor.graph = {}
        predictor.node_features = {}

        # Mock graph that raises on degree lookup
        mock_graph = MagicMock()
        mock_graph.degree.side_effect = Exception("no degree")

        result = predictor.score_ioc_batch([("test", "domain")], mock_graph)

        assert result["test"] == 0.5

    def test_score_ioc_batch_with_degree(self):
        """IOC with higher degree gets higher score."""
        from hledac.universal.brain.gnn_predictor import GNNPredictor
        import math

        predictor = GNNPredictor.__new__(GNNPredictor)
        predictor.graph = {}
        predictor.node_features = {}

        # Mock graph with degree method
        mock_graph = MagicMock()
        mock_graph.degree = MagicMock(return_value=100)

        result = predictor.score_ioc_batch([("high-degree.io", "domain")], mock_graph)

        # score = min(1.0, 0.5 + 0.1 * log1p(100))
        expected = min(1.0, 0.5 + 0.1 * math.log1p(100))
        assert abs(result["high-degree.io"] - expected) < 0.001

    def test_score_ioc_batch_multiple_iocs(self):
        """Multiple IOCs scored correctly."""
        from hledac.universal.brain.gnn_predictor import GNNPredictor

        predictor = GNNPredictor.__new__(GNNPredictor)
        predictor.graph = {}
        predictor.node_features = {}

        mock_graph = MagicMock()
        mock_graph.degree = MagicMock(return_value=0)

        iocs = [("1.2.3.4", "ipv4"), ("evil.com", "domain"), ("cve-2024-1234", "cve")]
        result = predictor.score_ioc_batch(iocs, mock_graph)

        assert len(result) == 3
        assert all(isinstance(v, float) for v in result.values())
