"""Sprint 8VF: IOC extraction — regex patterns."""
from hledac.universal.brain.ane_embedder import extract_iocs_from_text


def test_extract_ipv4():
    iocs = extract_iocs_from_text("Malware C2 at 185.220.101.47 port 4444")
    assert any(
        i["ioc_type"] == "ipv4" and "185.220.101.47" in i["value"]
        for i in iocs
    )


def test_extract_cve():
    iocs = extract_iocs_from_text("Exploiting CVE-2024-3400 via buffer overflow")
    assert any("CVE-2024-3400" in i["value"] for i in iocs)


def test_extract_sha256():
    sha = "a" * 64
    iocs = extract_iocs_from_text(f"Hash: {sha}")
    assert any(i["ioc_type"] == "sha256" for i in iocs)


def test_extract_md5():
    md5 = "d41d8cd98f00b204e9800998ecf8427e"
    iocs = extract_iocs_from_text(f"MD5: {md5}")
    assert any(i["ioc_type"] == "md5" for i in iocs)


def test_extract_sha1():
    sha1 = "da39a3ee5e6b4b0d3255bfef95601890afd80709"
    iocs = extract_iocs_from_text(f"SHA1: {sha1}")
    assert any(i["ioc_type"] == "sha1" for i in iocs)


def test_extract_url():
    iocs = extract_iocs_from_text("Found at https://evil.com/payload.exe")
    assert any(i["ioc_type"] == "url" and "evil.com" in i["value"] for i in iocs)


def test_extract_domain():
    iocs = extract_iocs_from_text("Contact malware at C2.badactor.net")
    assert any(i["ioc_type"] == "domain" and "badactor" in i["value"].lower() for i in iocs)


def test_extract_email():
    iocs = extract_iocs_from_text("Contact attacker@evil.ru for details")
    assert any(i["ioc_type"] == "email" and "evil.ru" in i["value"] for i in iocs)


def test_extract_iocs_never_throws():
    assert extract_iocs_from_text("") == []
    assert isinstance(extract_iocs_from_text("x" * 50_000), list)
    assert isinstance(extract_iocs_from_text(None), list)  # type: ignore


def test_regex_before_spacy():
    """Regex must be primary — verify IP found even without spaCy."""
    from unittest.mock import patch

    def _fake_spacy():
        raise RuntimeError("spaCy unavailable")

    with patch("hledac.universal.brain.ane_embedder._get_spacy", return_value=None):
        iocs = extract_iocs_from_text("C2: 10.0.0.1")
        assert any(i["ioc_type"] == "ipv4" for i in iocs), \
            "regex must find IP even without spaCy"
