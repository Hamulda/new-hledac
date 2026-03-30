from hledac.universal.tools.search_fusion import reciprocal_rank_fusion

def test_rrf_dedupes_same_url():
    rows = [
        {"title": "A", "url": "https://example.com/a", "snippet": "x", "provider": "ddgs_text", "rank": 1},
        {"title": "A", "url": "https://www.example.com/a?x=1", "snippet": "longer", "provider": "wayback_cdx", "rank": 2},
    ]
    fused = reciprocal_rank_fusion(rows)
    assert len(fused) == 1
    assert fused[0]["provider_count"] == 2
    assert "longer" in fused[0]["snippet"]
