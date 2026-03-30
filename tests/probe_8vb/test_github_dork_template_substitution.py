def test_github_dork_template_substitution():
    from discovery.ti_feed_adapter import _GH_DORK_TEMPLATES
    q = _GH_DORK_TEMPLATES["credential"].format(v="APT28")
    assert "APT28" in q
    assert "password" in q or "token" in q
