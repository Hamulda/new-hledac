"""Sprint 8UC: OSINT JSON Schema field validation."""
import pytest
from hledac.universal.brain.synthesis_runner import _build_osint_json_schema


def test_schema_required_fields():
    """Required fields must include title, summary, confidence."""
    schema = _build_osint_json_schema()
    assert "required" in schema
    required = schema["required"]
    assert "title" in required
    assert "summary" in required
    assert "confidence" in required


def test_schema_no_additional_props():
    """additionalProperties must be False for strict validation."""
    schema = _build_osint_json_schema()
    assert schema.get("additionalProperties", True) == False


def test_schema_findings_is_array():
    """findings must be array with maxItems."""
    schema = _build_osint_json_schema()
    props = schema["properties"]
    assert props["findings"]["type"] == "array"
    assert props["findings"]["maxItems"] == 20
