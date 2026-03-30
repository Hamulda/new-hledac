"""D.3 — Malformed HTML never raises; plaintext fallback returns valid tuple."""
import asyncio
import sys

sys.path.insert(0, ".")


async def test_malformed_html_no_raise():
    """Malformed/malicious HTML returns (text, matches) without raising."""
    from hledac.universal.fetching.public_fetcher import process_html_payload

    html = "<p>CVE-2026-1234<br broken" + "x" * 10000
    # Must NOT raise
    text, matches = await process_html_payload(html, "https://t.com")

    assert isinstance(text, str), f"Expected str, got {type(text)}"
    assert isinstance(matches, list), f"Expected list, got {type(matches)}"
    assert "CVE-2026-1234" in text, "Expected CVE in fallback text"
