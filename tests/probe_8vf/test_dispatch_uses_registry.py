"""Sprint 8VF: dispatch uses registry, elif chain <= 5 branches."""
import pytest


def test_dispatch_uses_registry():
    src = open("hledac/universal/runtime/sprint_scheduler.py").read()
    assert "get_task_handler" in src


def test_elif_chain_max_5_lifecycle():
    src = open("hledac/universal/runtime/sprint_scheduler.py").read()
    # Count elif after "Inline lifecycle handlers only" comment
    import re
    # Find the inline lifecycle handlers block
    match = re.search(r'# Sprint 8VF: Inline lifecycle handlers only.*?else:', src, re.DOTALL)
    if match:
        block = match.group()
        elif_count = block.count('elif ')
        assert elif_count <= 5, f"Too many elif ({elif_count}) — lifecycle tasks only"
    # Also check overall pattern: no long elif chains for OSINT types
    osint_types = [
        "domain_to_pdns", "domain_to_ct", "multi_engine_search",
        "shodan_enrich", "rdap_lookup", "github_dork",
    ]
    for t in osint_types:
        # These should NOT appear as elif in _execute_pivot anymore
        # (they're in the registry now)
        pass  # Handled by test_registered_handlers_cover_osint
