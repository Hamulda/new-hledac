"""Shared fixtures for probe_8az."""
import pytest


@pytest.fixture
def sample_rss_canonical_finding():
    """CanonicalFinding representing a short RSS security headline."""
    from hledac.universal.knowledge.duckdb_store import CanonicalFinding

    return CanonicalFinding(
        finding_id="rss-test-001",
        query="CVE-2024-1234",
        source_type="rss_atom_pipeline",
        confidence=0.8,
        ts=1700000000.0,
        provenance=("rss_atom", "http://example.com/feed", "urn:entry:1", "feed_entry"),
        payload_text="critical vulnerability exploited in the wild",
    )


@pytest.fixture
def sample_rss_short_finding():
    """CanonicalFinding representing an extremely short RSS finding."""
    from hledac.universal.knowledge.duckdb_store import CanonicalFinding

    return CanonicalFinding(
        finding_id="rss-test-002",
        query="zero-day",
        source_type="rss_atom_pipeline",
        confidence=0.8,
        ts=1700000000.0,
        provenance=("rss_atom", "http://example.com/feed", "urn:entry:2", "feed_entry"),
        payload_text="zero-day",
    )


@pytest.fixture
def sample_web_canonical_finding():
    """CanonicalFinding representing a web/general security finding."""
    from hledac.universal.knowledge.duckdb_store import CanonicalFinding

    return CanonicalFinding(
        finding_id="web-test-001",
        query="APT41 scanning for Citrix Bleed",
        source_type="live_public_pipeline",
        confidence=0.9,
        ts=1700000000.0,
        provenance=("web", "http://example.com/article"),
        payload_text="APT41 threat actors are actively scanning for Citrix Bleed vulnerability",
    )


@pytest.fixture
def sample_junk_finding():
    """CanonicalFinding representing obvious junk — should always be rejected."""
    from hledac.universal.knowledge.duckdb_store import CanonicalFinding

    return CanonicalFinding(
        finding_id="junk-test-001",
        query="xxx",
        source_type="rss_atom_pipeline",
        confidence=0.3,
        ts=1700000000.0,
        provenance=(),
        payload_text="xxx",
    )
