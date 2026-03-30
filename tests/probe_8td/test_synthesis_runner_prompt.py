"""Sprint 8TD: SynthesisRunner custom prompt tests."""
from unittest.mock import MagicMock


class TestSynthesisRunnerPrompt:
    """Test set_custom_prompt and set_prompt_modifier."""

    def test_set_custom_prompt(self):
        """set_custom_prompt stores the prompt."""
        from hledac.universal.brain.synthesis_runner import SynthesisRunner

        lifecycle = MagicMock()
        runner = SynthesisRunner(lifecycle)
        runner._custom_synthesis_prompt = None

        runner.set_custom_prompt("test prompt content")

        assert runner._custom_synthesis_prompt == "test prompt content"

    def test_set_prompt_modifier(self):
        """set_prompt_modifier stores the modifier."""
        from hledac.universal.brain.synthesis_runner import SynthesisRunner

        lifecycle = MagicMock()
        runner = SynthesisRunner(lifecycle)
        runner._prompt_modifier = ""

        runner.set_prompt_modifier("\nFocus on: CVEs")

        assert runner._prompt_modifier == "\nFocus on: CVEs"

    def test_init_slots_include_prompt_fields(self):
        """__slots__ includes _custom_synthesis_prompt and _prompt_modifier."""
        from hledac.universal.brain.synthesis_runner import SynthesisRunner

        assert "_custom_synthesis_prompt" in SynthesisRunner.__slots__
        assert "_prompt_modifier" in SynthesisRunner.__slots__
