def test_dispatch_types_registered():
    src = open("runtime/sprint_scheduler.py").read()
    required = [
        "domain_to_pdns", "domain_to_ct", "ct_live_monitor",
        "paste_keyword_search", "github_dork", "ahmia_search",
        "multi_engine_search", "commoncrawl_search",
        "wayback_search", "shodan_enrich", "rdap_lookup"
    ]
    for t in required:
        assert t in src, f"dispatch '{t}' chybí v sprint_scheduler.py"
