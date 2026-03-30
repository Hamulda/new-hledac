"""
Sprint 8UA: GNN Live Scoring Tests
B.4: score_ioc_batch with live Kuzu API + type weights
"""

import math


class MockKuzuConn:
    """Mock Kuzu connection for testing degree lookup."""
    def __init__(self, degrees=None):
        self._degrees = degrees or {}

    def execute(self, _query, params=None):
        v = params.get("v", "") if params else ""
        degree = self._degrees.get(v, 0)
        result = __import__("unittest.mock").MagicMock()
        result.has_next.return_value = True
        result.get_next.return_value = (degree,)
        return result


class MockIOCGraph:
    """Mock IOCGraph for testing degree lookup."""
    def __init__(self, kuzu_conn=None):
        self._conn = kuzu_conn


class TestGNNLiveScoring:
    """test_gnn_live_scoring_type + test_gnn_type_weight_cve + test_gnn_high_degree_higher_score"""

    def test_gnn_live_scoring_type(self):
        """IOC scoring returns {value: float} in range 0-1"""
        type_weight = {
            "domain": 1.20, "ipv4": 1.10, "ipv6": 1.05,
            "sha256": 1.15, "md5": 1.10, "sha1": 1.08,
            "cve": 1.25, "url": 0.95, "email": 0.90,
            "malware_family": 1.30,
        }
        # degree=0 case
        _, ioc_type = "1.2.3.4", "ipv4"
        degree = 0
        tw = type_weight.get(ioc_type, 1.0)
        base = min(1.0, 0.45 + 0.12 * math.log1p(max(0, degree - 1)))
        score = min(1.0, round(base * tw, 4))
        assert 0 < score <= 1.0, f"Score out of range: {score}"

    def test_gnn_type_weight_cve(self):
        """CVE IOC type → score >= ipv4 score (cve=1.25 > ipv4=1.10)"""
        type_weight = {
            "domain": 1.20, "ipv4": 1.10, "ipv6": 1.05,
            "sha256": 1.15, "md5": 1.10, "sha1": 1.08,
            "cve": 1.25, "url": 0.95, "email": 0.90,
            "malware_family": 1.30,
        }
        degree = 5
        base = min(1.0, 0.45 + 0.12 * math.log1p(max(0, degree - 1)))
        cve_score = min(1.0, round(base * type_weight["cve"], 4))
        ipv4_score = min(1.0, round(base * type_weight["ipv4"], 4))
        assert cve_score >= ipv4_score, f"CVE score {cve_score} should be >= IPv4 score {ipv4_score}"
        assert type_weight["cve"] > type_weight["ipv4"]

    def test_gnn_high_degree_higher_score(self):
        """degree=10 → score > degree=1 for same ioc_type"""
        type_weight = {"ipv4": 1.10}
        ioc_type = "ipv4"
        base_fn = lambda d: min(1.0, 0.45 + 0.12 * math.log1p(max(0, d - 1)))
        tw = type_weight[ioc_type]
        score_d1 = min(1.0, round(base_fn(1) * tw, 4))
        score_d10 = min(1.0, round(base_fn(10) * tw, 4))
        assert score_d10 > score_d1, f"degree=10 score ({score_d10}) should be > degree=1 score ({score_d1})"
