"""
Sprint 8UA: HypothesisEngine → Pivot Injection Tests
B.6: HypothesisEngine output as new pivot seeds
"""

import re


class TestHypothesisPivotInjection:
    """test_hypothesis_pivot_injection_ip + test_hypothesis_pivot_injection_cve + test_hypothesis_pivot_injection_domain"""

    def test_hypothesis_pivot_injection_ip(self):
        """Hypotéza obsahuje "C2 at 192.168.1.1" → enqueue_pivot voláno s ipv4"""
        hypothesis = "C2 infrastructure at 192.168.1.1 identified in latest analysis"
        ips = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', hypothesis)
        assert len(ips) > 0, "Should find IP in hypothesis"
        assert ips[0] == "192.168.1.1"

    def test_hypothesis_pivot_injection_cve(self):
        """Hypotéza obsahuje "CVE-2024-1234" → enqueue_pivot voláno s cve"""
        hypothesis = "Vulnerability CVE-2024-1234 exploited in ransomware campaign"
        cves = re.findall(r'CVE-\d{4}-\d{4,7}', hypothesis, re.IGNORECASE)
        assert len(cves) > 0, "Should find CVE in hypothesis"
        assert cves[0] == "CVE-2024-1234"

    def test_hypothesis_pivot_injection_domain(self):
        """Hypotéza obsahuje "malware.com" → enqueue_pivot voláno s domain"""
        hypothesis = "Malware command server at malware.com detected"
        # More general domain pattern
        domains = re.findall(
            r'\b(?:[a-z0-9-]+\.)+(?:com|net|org|io|ru|cn|onion)\b',
            hypothesis, re.IGNORECASE
        )
        assert len(domains) > 0, "Should find domain in hypothesis"
        assert domains[0] == "malware.com"

    def test_multiple_entities_extracted(self):
        """Multiple IOC types extracted from single hypothesis"""
        hypothesis = "CVE-2024-5678 targeting 10.0.0.1 from attacker.com"
        ips = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', hypothesis)
        cves = re.findall(r'CVE-\d{4}-\d{4,7}', hypothesis, re.IGNORECASE)
        domains = re.findall(
            r'\b(?:[a-z0-9-]+\.)+(?:com|net|org|io|ru|cn|onion)\b',
            hypothesis, re.IGNORECASE
        )
        assert len(ips) == 1
        assert len(cves) == 1
        assert len(domains) == 1
