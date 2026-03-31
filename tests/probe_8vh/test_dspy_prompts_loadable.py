"""Test: DSPy prompts are loadable via lazy loader."""
from hledac.universal.brain.synthesis_runner import _get_dspy_prompts


def test_dspy_prompts_loadable():
    prompts = _get_dspy_prompts()
    assert isinstance(prompts, dict)
    # Může být prázdný dict (pokud optimalizace ještě neproběhla) — to je OK
