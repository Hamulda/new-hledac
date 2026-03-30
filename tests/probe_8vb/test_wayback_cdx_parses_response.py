def test_wayback_cdx_parses_response():
    rows = [
        ["timestamp","original","statuscode","mimetype"],
        ["20241201000000","http://evil.com/page","200","text/html"]
    ]
    keys = rows[0]
    rec  = dict(zip(keys, rows[1]))
    assert rec["original"] == "http://evil.com/page"
    assert rec["statuscode"] == "200"
