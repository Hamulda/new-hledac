"""
Sprint 8PB: test_parse_cisa_kev
D.3: Fixture: minimální CISA KEV JSON (3 záznamy) → parse_cisa_kev() → 3 dict s cveID
"""

import json
import tempfile
from pathlib import Path

import pytest


def test_parse_cisa_kev():
    """Parse CISA KEV JSON with 3 vulnerabilities."""
    from hledac.universal.intelligence.ti_feed_adapter import parse_cisa_kev

    data = {
        "vulnerabilities": [
            {
                "cveID": "CVE-2024-1234",
                "vendorProject": "TestVendor",
                "product": "TestProduct",
                "dateAdded": "2024-01-01",
                "shortDescription": "Test vuln 1",
                "knownRansomwareCampaignUse": "Known",
                "notes": "",
            },
            {
                "cveID": "CVE-2024-5678",
                "vendorProject": "AnotherVendor",
                "product": "AnotherProduct",
                "dateAdded": "2024-01-02",
                "shortDescription": "Test vuln 2",
                "knownRansomwareCampaignUse": "Unknown",
                "notes": "",
            },
            {
                "cveID": "CVE-2024-9999",
                "vendorProject": "ThirdVendor",
                "product": "ThirdProduct",
                "dateAdded": "2024-01-03",
                "shortDescription": "Test vuln 3",
                "knownRansomwareCampaignUse": "Unknown",
                "notes": "note3",
            },
        ]
    }

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        json.dump(data, f)
        path = Path(f.name)

    try:
        result = parse_cisa_kev(path)
        assert len(result) == 3
        assert result[0]["cve_id"] == "CVE-2024-1234"
        assert result[1]["cve_id"] == "CVE-2024-5678"
        assert result[2]["cve_id"] == "CVE-2024-9999"
        assert result[0]["vendor_project"] == "TestVendor"
        assert result[2]["notes"] == "note3"
    finally:
        path.unlink()


if __name__ == "__main__":
    test_parse_cisa_kev()
