"""
Sprint 8VI §E: _generate_next_sprint_seeds creates valid seed JSON.
"""
import json
import pathlib
import tempfile
import pytest
from export.sprint_exporter import _generate_next_sprint_seeds
from unittest.mock import MagicMock

def test_seeds_json_generated():
    """_generate_next_sprint_seeds must create a JSON file with seed tasks."""
    scheduler = MagicMock()
    scheduler._ioc_graph = MagicMock()
    scheduler._ioc_graph.get_top_nodes_by_degree.return_value = [
        {"value": "evil.com", "ioc_type": "domain", "confidence": 0.9, "degree": 10},
    ]

    with tempfile.TemporaryDirectory() as tmp:
        path = _generate_next_sprint_seeds(scheduler, "test_s", pathlib.Path(tmp))
        assert path.exists(), "Seed file should be created"
        seeds = json.loads(path.read_text())
        assert len(seeds) >= 1, "At least 1 seed task expected"
        assert any(s["task_type"] == "rdap_lookup" for s in seeds), "rdap_lookup expected"
        assert all(s["value"] == "evil.com" for s in seeds), "All values should be 'evil.com'"
