"""Sprint 8QA: extract_iocs RFC1918 filtering test."""

import pytest

from hledac.universal.knowledge.ioc_graph import extract_iocs_from_text


def test_extract_iocs_rfc1918_filtered():
    """Private IPs (192.168.x, 10.x, 172.16-31.x, 127.x, 169.254.x) are filtered out."""
    iocs = extract_iocs_from_text(
        "CVE-2026-9999 cobalt_strike 192.168.1.1 1.2.3.4 10.0.0.1 172.16.0.1 127.0.0.1 169.254.0.1",
        [("CVE-2026-9999", "vulnerability_id"), ("cobalt_strike", "offensive_tool")],
    )
    values = {v for v, t in iocs}
    assert "CVE-2026-9999" in values
    assert "1.2.3.4" in values
    assert "cobalt_strike" in values
    assert "192.168.1.1" not in values
    assert "10.0.0.1" not in values
    assert "172.16.0.1" not in values
    assert "127.0.0.1" not in values
    assert "169.254.0.1" not in values
