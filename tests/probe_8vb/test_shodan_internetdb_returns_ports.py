def test_shodan_internetdb_returns_ports():
    from discovery.duckduckgo_adapter import _query_shodan_internetdb
    assert callable(_query_shodan_internetdb)
