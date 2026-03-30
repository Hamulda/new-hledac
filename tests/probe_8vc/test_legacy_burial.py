"""Test that legacy burial was done correctly."""
import os
import sys

# Ensure the universal directory is in the path
_universal_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _universal_dir not in sys.path:
    sys.path.insert(0, _universal_dir)


def test_legacy_dir_exists():
    """legacy/ directory should exist with autonomous_orchestrator.py."""
    # Use absolute path: tests/probe_8vc/test_xxx.py -> ../../../universal/
    _test_dir = os.path.dirname(os.path.abspath(__file__))  # tests/probe_8vc
    _tests_dir = os.path.dirname(_test_dir)  # tests
    _universal_dir = os.path.dirname(_tests_dir)  # hledac/universal
    _legacy_dir = os.path.join(_universal_dir, "legacy")
    assert os.path.exists(_legacy_dir), f"legacy/ should exist at {_legacy_dir}"
    assert os.path.exists(os.path.join(_legacy_dir, "autonomous_orchestrator.py")), \
        "legacy/autonomous_orchestrator.py should exist"
    assert os.path.exists(os.path.join(_legacy_dir, "__init__.py")), \
        "legacy/__init__.py should exist"


def test_persistent_layer_gone_from_knowledge():
    """persistent_layer.py should be in legacy/, not knowledge/."""
    assert not os.path.exists("knowledge/persistent_layer.py"), \
        "knowledge/persistent_layer.py should be in legacy/"


def test_atomic_storage_gone_from_knowledge():
    """atomic_storage.py should be in legacy/, not knowledge/."""
    assert not os.path.exists("knowledge/atomic_storage.py"), \
        "knowledge/atomic_storage.py should be in legacy/"


def test_duckdb_store_importable():
    """duckdb_store should be importable via hledac.universal."""
    from hledac.universal.knowledge.duckdb_store import DuckDBShadowStore
    assert DuckDBShadowStore is not None


def test_brain_lazy_importable():
    """brain._lazy should be importable via hledac.universal."""
    from hledac.universal.brain._lazy import get, get_attr, _cache
    assert callable(get)
    assert callable(get_attr)
    assert isinstance(_cache, dict)
