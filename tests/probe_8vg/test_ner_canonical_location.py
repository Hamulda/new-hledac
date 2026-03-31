from brain.ner_engine import extract_iocs_from_text

def test_ner_canonical_location():
    iocs = extract_iocs_from_text("C2 at 185.220.101.47, CVE-2024-3400")
    assert any(i["ioc_type"] == "ipv4" for i in iocs)
    assert any("CVE-2024-3400" in i["value"] for i in iocs)
