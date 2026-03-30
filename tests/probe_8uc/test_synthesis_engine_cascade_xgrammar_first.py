"""Sprint 8UC: Synthesis engine cascade — xgrammar first."""
import pytest
from unittest.mock import MagicMock, patch


def test_xgrammar_method_exists_on_runner():
    """SynthesisRunner has _run_xgrammar_generation method."""
    from hledac.universal.brain.synthesis_runner import SynthesisRunner
    runner = SynthesisRunner.__new__(SynthesisRunner)
    assert hasattr(runner, '_run_xgrammar_generation')
    assert callable(runner._run_xgrammar_generation)


def test_last_synthesis_engine_attribute_exists():
    """SynthesisRunner initializes _last_synthesis_engine."""
    from hledac.universal.brain.synthesis_runner import SynthesisRunner
    runner = SynthesisRunner.__new__(SynthesisRunner)
    # It's initialized in __init__ but __slots__ makes it a descriptor
    # Check the class has the attribute in slots
    assert "_last_synthesis_engine" in SynthesisRunner.__slots__
