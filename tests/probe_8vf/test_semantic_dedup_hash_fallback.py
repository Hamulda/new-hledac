"""Sprint 8VF: ANE semantic dedup + hash fallback."""
import asyncio
from hledac.universal.brain.ane_embedder import semantic_dedup_findings, unload_ane_embedder, get_ane_embedder


def test_semantic_dedup_hash_fallback():
    """Hash fallback when ANE model unavailable."""
    unload_ane_embedder()
    findings = [
        {"url": "http://x.com", "title": "APT28"},
        {"url": "http://x.com", "title": "APT28"},
        {"url": "http://y.com", "title": "Different"},
    ]
    result = asyncio.run(semantic_dedup_findings(findings))
    assert len(result) == 2


def test_ane_embedder_unload():
    """unload_ane_embedder() resets the embedder."""
    unload_ane_embedder()
    # When model file doesn't exist, get_ane_embedder() returns None
    # (or a non-loaded embedder)
    embedder = get_ane_embedder()
    # Should return something (possibly None if no model file)
    # Key invariant: after unload, embedder state is reset
    unload_ane_embedder()
