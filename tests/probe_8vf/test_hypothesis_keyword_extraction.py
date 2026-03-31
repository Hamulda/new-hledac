"""Sprint 8VF: hypothesis_probe uses keyword extraction, NOT split(' OR ')."""


def test_hypothesis_no_or_split():
    """Hypotheses are natural language sentences — OR split is wrong."""
    src = open("hledac/universal/runtime/sprint_scheduler.py").read()
    # Check only inside _execute_pivot body, not in comments
    import re
    match = re.search(r'async def _execute_pivot.*?else:', src, re.DOTALL)
    if match:
        dispatch_block = match.group()
        assert 'split(" OR ")' not in dispatch_block, \
            "Hypotheses are sentences — don't use OR split()"
        assert "split(' OR ')" not in dispatch_block, \
            "Hypotheses are sentences — don't use OR split()"


def test_hypothesis_probe_in_scheduler():
    """hypothesis_probe dispatch exists in scheduler."""
    src = open("hledac/universal/runtime/sprint_scheduler.py").read()
    assert "hypothesis_probe" in src
