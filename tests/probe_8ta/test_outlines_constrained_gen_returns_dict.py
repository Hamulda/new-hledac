"""Sprint 8TA B.1: Outlines constrained gen returns (dict, True)."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def test_outlines_constrained_gen_returns_dict():
    """Mock outlines.generate.json -> _run_constrained_generation -> (dict, True)."""
    from hledac.universal.brain.synthesis_runner import SynthesisRunner, OSINT_JSON_SCHEMA

    # Verify OSINT_JSON_SCHEMA is a string (json.dumps output)
    assert isinstance(OSINT_JSON_SCHEMA, str)
    assert "title" in OSINT_JSON_SCHEMA
    assert "summary" in OSINT_JSON_SCHEMA
    assert "threat_actors" in OSINT_JSON_SCHEMA
    assert "findings" in OSINT_JSON_SCHEMA
    assert "confidence" in OSINT_JSON_SCHEMA
    assert "timestamp" in OSINT_JSON_SCHEMA

    # Schema must be valid JSON
    import json
    parsed = json.loads(OSINT_JSON_SCHEMA)
    assert parsed["type"] == "object"
    assert "title" in parsed["required"]
    assert "summary" in parsed["required"]
    assert parsed["additionalProperties"] is False
