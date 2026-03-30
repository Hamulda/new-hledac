"""D.2 — process_html_payload offloads to CPU executor."""
import asyncio
import sys

sys.path.insert(0, ".")


async def test_process_html_offload():
    """HTML is processed and patterns are matched in CPU executor."""
    from hledac.universal.fetching.public_fetcher import process_html_payload

    html = "<h1>CVE-2026-1234 cobalt strike</h1>"
    text, matches = await process_html_payload(html, "https://t.com")

    assert "CVE-2026-1234" in text, f"Expected CVE in text, got: {text[:100]}"
    assert len(matches) > 0, "Expected non-empty matches"
