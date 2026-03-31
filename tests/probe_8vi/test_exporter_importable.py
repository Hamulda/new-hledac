"""
Sprint 8VI §E: export_sprint() + _generate_next_sprint_seeds() import test.
"""
import pytest

def test_exporter_importable():
    """export/sprint_exporter must have export_sprint and _generate_next_sprint_seeds."""
    from export.sprint_exporter import export_sprint, _generate_next_sprint_seeds
    assert callable(export_sprint)
    assert callable(_generate_next_sprint_seeds)
