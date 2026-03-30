from hledac.universal.tools.content_miner import extract_source_map_url


def test_extract_source_map_url():
    """Test source map URL extraction."""
    html = "<html>\n//# sourceMappingURL=https://example.com/map.js\n</html>"
    url = extract_source_map_url(html)
    assert url == "https://example.com/map.js"


def test_extract_source_map_url_long():
    """Test source map URL truncation for long URLs."""
    long_url = "https://example.com/" + "a" * 600
    html = f"<html>\n//# sourceMappingURL={long_url}\n</html>"
    url = extract_source_map_url(html)
    assert len(url) == 500  # truncated without "..."


def test_extract_source_map_url_none():
    """Test source map URL extraction when not present."""
    html = "<html><body>No source map here</body></html>"
    url = extract_source_map_url(html)
    assert url is None


def test_extract_source_map_url_empty():
    """Test source map URL extraction with empty input."""
    url = extract_source_map_url("")
    assert url is None
