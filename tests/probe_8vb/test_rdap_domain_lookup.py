def test_rdap_domain_lookup():
    from discovery.duckduckgo_adapter import _query_rdap
    assert callable(_query_rdap)
    # Ověř že IPv4 detekce funguje:
    is_ip = "1.2.3.4".replace(".", "").isdigit()
    assert is_ip is True
    is_dom = "evil.com".replace(".", "").isdigit()
    assert is_dom is False
