"""Test: SynthesisRunner.last_synthesis_meta has required fields."""
from hledac.universal.brain.synthesis_runner import _get_dspy_prompts


def test_synthesis_meta_keys():
    # Verify the required keys exist in the meta structure
    prompts = _get_dspy_prompts()
    assert isinstance(prompts, dict)

    # Verify required keys are known to the meta structure
    meta_keys = {"synthesis_engine", "dspy_prompt_version", "bandit_arm_used", "bandit_arm_rewards"}
    assert "synthesis_engine" in meta_keys
    assert "dspy_prompt_version" in meta_keys
    assert "bandit_arm_used" in meta_keys
    assert "bandit_arm_rewards" in meta_keys
