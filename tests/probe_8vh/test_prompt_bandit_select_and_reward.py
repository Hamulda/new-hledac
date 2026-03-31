"""Test: PromptBandit select and reward work without errors."""
import pytest
from hledac.universal.brain.synthesis_runner import _get_prompt_bandit


def test_prompt_bandit_select_and_reward():
    bandit = _get_prompt_bandit()
    if bandit is None:
        pytest.skip("PromptBandit nedostupný")

    arm = bandit.select_arm()
    assert arm is not None
    # update_reward(self, arm: str, fpm: float, novelty: float) — Sprint 8TD UCB1
    bandit.update_reward(arm, 0.8, novelty=0.5)  # nesmí vyhodit výjimku
