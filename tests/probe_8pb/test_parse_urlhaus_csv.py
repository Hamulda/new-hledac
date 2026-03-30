"""
Sprint 8PB: test_parse_urlhaus_csv
D.4: Fixture: 5 řádků URLhaus CSV formátu → parse_urlhaus_csv() → 5 dict s url a tags
"""

import csv
import tempfile
from pathlib import Path

import pytest


def test_parse_urlhaus_csv():
    """Parse URLhaus CSV with 5 rows."""
    from hledac.universal.intelligence.ti_feed_adapter import parse_urlhaus_csv

    csv_content = (
        "url,date_added,tags,threat,status\n"
        "https://evil.com/malware.exe,2024-01-01,trojan,malware_download,active\n"
        "https://bad.net/phish.html,2024-01-02,phishing,phishing,active\n"
        "https://suspicious.org/bundle.exe,2024-01-03,malware,malware_download,active\n"
        "https://dark.io/hacktool.zip,2024-01-04,hacking,exploit_kit,active\n"
        "https://c2.io/payload.exe,2024-01-05,c2,botnet,active\n"
    )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False
    ) as f:
        f.write(csv_content)
        path = Path(f.name)

    try:
        result = parse_urlhaus_csv(path)
        assert len(result) == 5
        assert result[0]["url"] == "https://evil.com/malware.exe"
        assert result[0]["tags"] == "trojan"
        assert result[1]["url"] == "https://bad.net/phish.html"
        assert result[1]["threat"] == "phishing"
        assert result[4]["status"] == "active"
    finally:
        path.unlink()


if __name__ == "__main__":
    test_parse_urlhaus_csv()
