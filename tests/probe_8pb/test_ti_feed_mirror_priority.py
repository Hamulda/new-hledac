"""
Sprint 8PB: test_ti_feed_mirror_priority
D.7: Mirror existuje → adapter použije mirror (priority=95) před HTTP
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def test_ti_feed_mirror_priority():
    """When mirror exists, get_iocs uses local_mirror tier with priority=95."""
    from hledac.universal.intelligence.ti_feed_adapter import (
        TIFeedAdapter,
        MirrorManager,
        parse_cisa_kev,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        mirrors_root = Path(tmpdir)

        # Create fake CISA KEV mirror
        cisa_path = mirrors_root / "cisa_kev.json"
        cisa_data = {
            "vulnerabilities": [
                {
                    "cveID": "CVE-2024-0001",
                    "vendorProject": "Test",
                    "product": "TestProduct",
                    "dateAdded": "2024-01-01",
                    "shortDescription": "Test",
                    "knownRansomwareCampaignUse": "Unknown",
                    "notes": "",
                }
            ]
        }
        cisa_path.write_text(json.dumps(cisa_data))

        # Create adapter
        adapter = TIFeedAdapter(mirrors_root=mirrors_root)

        # Query CVE - should use mirror
        findings = asyncio.run(adapter.get_iocs("CVE-2024-0001"))

        # Should have mirror-based result
        assert len(findings) > 0
        mirror_result = next(
            (f for f in findings if f.get("tier") == "local_mirror"), None
        )
        assert mirror_result is not None
        assert mirror_result["priority"] == 95
        assert mirror_result["source"] == "CISA KEV"
        assert mirror_result["data"]["cve_id"] == "CVE-2024-0001"

        asyncio.run(adapter.close())


if __name__ == "__main__":
    test_ti_feed_mirror_priority()
