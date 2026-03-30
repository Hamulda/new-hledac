"""
test_threatfox_parse.py
Sprint 8RA C.2 / D.3 — parse ThreatFox JSON response (OFFLINE fixture)
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, ".")


def test_parse_threatfox_recent():
    """parse_threatfox_recent extracts IOC values from ThreatFox bulk data."""
    from hledac.universal.intelligence.ti_feed_adapter import parse_threatfox_recent

    # Valid ThreatFox-like data
    data = [
        {"ioc": "malware-lockbit-001", "ioc_type": "md5_hash"},
        {"ioc": "8.8.8.8", "ioc_type": "ip:port"},
        {"ioc": "evil.com", "ioc_type": "domain"},
        {"ioc": "http://evil.com/payload.exe", "ioc_type": "url"},
        {"ioc": "deadbeef" * 8, "ioc_type": "sha256_hash"},
        {"ioc": "ignore-me", "ioc_type": "unknown_type"},  # filtered
        {"ioc": "", "ioc_type": "md5_hash"},  # empty — filtered
    ]

    result = parse_threatfox_recent(data)

    assert len(result) == 5, f"Expected 5 IOCs, got {len(result)}"
    assert "malware-lockbit-001" in result
    assert "8.8.8.8" in result
    assert "evil.com" in result
    assert "http://evil.com/payload.exe" in result
    assert "deadbeef" * 8 in result
    assert "ignore-me" not in result
    assert "" not in result


def test_parse_threatfox_recent_empty():
    """Empty list returns empty list."""
    from hledac.universal.intelligence.ti_feed_adapter import parse_threatfox_recent

    assert parse_threatfox_recent([]) == []
    assert parse_threatfox_recent([{"ioc": "", "ioc_type": "md5_hash"}]) == []
