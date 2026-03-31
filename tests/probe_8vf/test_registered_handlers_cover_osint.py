"""Sprint 8VF: All OSINT handlers are registered in ti_feed_adapter."""
from hledac.universal.tool_registry import list_registered_tasks


def test_registered_handlers_cover_osint():
    """Verify required OSINT task types are registered."""
    # Trigger lazy load by calling get_task_handler which imports ti_feed_adapter
    from hledac.universal.tool_registry import get_task_handler
    get_task_handler("domain_to_pdns")  # trigger lazy load
    registered = list_registered_tasks()
    required = [
        "domain_to_pdns",
        "domain_to_ct",
        "multi_engine_search",
        "github_dork",
        "shodan_enrich",
        "rdap_lookup",
        "ahmia_search",
        "paste_keyword_search",
        "wayback_search",
        "commoncrawl_search",
    ]
    for r in required:
        assert r in registered, f"Handler '{r}' not registered"

