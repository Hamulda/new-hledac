"""Sprint 8TD: PromptBandit UCB1 tests."""
from hledac.universal.brain.prompt_bandit import PromptBandit


class TestBanditUCB1:
    """Test UCB1 arm selection and reward updates."""

    def test_prompt_arms_defined(self):
        """PROMPT_ARMS list exists with 5 arms."""
        assert hasattr(PromptBandit, "PROMPT_ARMS")
        assert len(PromptBandit.PROMPT_ARMS) == 5
        assert "default" in PromptBandit.PROMPT_ARMS
        assert "adversarial" in PromptBandit.PROMPT_ARMS
        assert "technical" in PromptBandit.PROMPT_ARMS

    def test_init_arm_state(self):
        """PromptBandit.__init__ initializes arm state."""
        bandit = PromptBandit.__new__(PromptBandit)
        bandit._arm_counts = {a: 0 for a in PromptBandit.PROMPT_ARMS}
        bandit._arm_rewards = {a: 0.0 for a in PromptBandit.PROMPT_ARMS}
        bandit._total_pulls = 0
        bandit._ucb_c = 1.414

        assert bandit._arm_counts["default"] == 0
        assert bandit._arm_rewards["default"] == 0.0
        assert bandit._total_pulls == 0

    def test_select_arm_explore_phase(self):
        """First 5 pulls: each arm tried once (explore phase)."""
        bandit = PromptBandit.__new__(PromptBandit)
        bandit._arm_counts = {a: 0 for a in PromptBandit.PROMPT_ARMS}
        bandit._arm_rewards = {a: 0.0 for a in PromptBandit.PROMPT_ARMS}
        bandit._total_pulls = 0
        bandit._ucb_c = 1.414

        # Explore phase: each arm selected once
        for i in range(5):
            selected = bandit.select_arm()
            assert selected == PromptBandit.PROMPT_ARMS[i]
            bandit._arm_counts[selected] += 1
            bandit._total_pulls += 1

    def test_select_arm_ucb1_prefers_best(self):
        """After explore, UCB1 should prefer arm with highest reward."""
        bandit = PromptBandit.__new__(PromptBandit)
        bandit._arm_counts = {a: 10 for a in PromptBandit.PROMPT_ARMS}  # All tried
        bandit._arm_rewards = {
            "default": 0.0,
            "adversarial": 0.0,
            "temporal": 0.0,
            "technical": 10.0,  # technical has reward
            "contextual": 0.0,
        }
        bandit._total_pulls = 50
        bandit._ucb_c = 1.414

        selected = bandit.select_arm()
        # Technical should be selected (highest reward)
        assert selected == "technical"

    def test_update_reward(self):
        """update_reward updates arm counts and rewards."""
        bandit = PromptBandit.__new__(PromptBandit)
        bandit._arm_counts = {a: 0 for a in PromptBandit.PROMPT_ARMS}
        bandit._arm_rewards = {a: 0.0 for a in PromptBandit.PROMPT_ARMS}
        bandit._total_pulls = 0

        bandit.update_reward("technical", fpm=5.0, novelty=0.8)
        # reward = fpm * novelty = 5.0 * 0.8 = 4.0
        assert bandit._arm_counts["technical"] == 1
        assert bandit._arm_rewards["technical"] == 4.0
        assert bandit._total_pulls == 1

    def test_get_prompt_modifier(self):
        """get_prompt_modifier returns correct modifier for each arm."""
        bandit = PromptBandit.__new__(PromptBandit)

        assert "CVE" in bandit.get_prompt_modifier("technical")
        assert "IOC" in bandit.get_prompt_modifier("technical")
        assert "threat actors" in bandit.get_prompt_modifier("adversarial")
        assert "timeline" in bandit.get_prompt_modifier("temporal")
        assert "recurring entities" in bandit.get_prompt_modifier("contextual")
        assert bandit.get_prompt_modifier("default") == ""

    def test_get_stats(self):
        """get_stats returns arm statistics dict."""
        bandit = PromptBandit.__new__(PromptBandit)
        bandit._arm_counts = {"default": 5, "technical": 3}
        bandit._arm_rewards = {"default": 2.0, "technical": 6.0}
        bandit._total_pulls = 8

        stats = bandit.get_stats()
        assert "arm_counts" in stats
        assert "arm_rewards" in stats
        assert "total_pulls" in stats
        assert stats["total_pulls"] == 8
