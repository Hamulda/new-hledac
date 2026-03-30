from hledac.universal.tools.ddgs_client import search_text_sync

def test_ddgs_sync_smoke():
    rows = search_text_sync("python programming language", backends=("duckduckgo",), max_results_per_backend=3, timeout=8)
    ok = [r for r in rows if r.get("url")]
    assert len(ok) >= 1
