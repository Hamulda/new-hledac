def test_crtsh_deduplicates():
    fake = [{"name_value": "sub.evil.com\nwww.evil.com",
             "issuer_name": "LE"}]
    seen: set = set()
    results = []
    for cert in fake:
        for sub in cert["name_value"].split("\n"):
            sub = sub.strip()
            if sub and sub not in seen:
                seen.add(sub)
                results.append(sub)
    assert "sub.evil.com" in results and "www.evil.com" in results
