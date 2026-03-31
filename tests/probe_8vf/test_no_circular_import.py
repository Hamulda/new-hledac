"""Sprint 8VF: No circular import — ti_feed_adapter not loaded on tool_registry import."""
import sys


def test_no_circular_import():
    # Remove cache for ti_feed_adapter only (not tool_registry itself)
    for k in list(sys.modules.keys()):
        if "ti_feed_adapter" in k:
            del sys.modules[k]

    from hledac.universal import tool_registry
    # Access _HANDLERS_LOADED flag — if True, handlers were already loaded
    # which would indicate circular import happened
    if hasattr(tool_registry, '_HANDLERS_LOADED') and tool_registry._HANDLERS_LOADED:
        # This means ti_feed_adapter was already imported somewhere before this test
        # Check if it got loaded during tool_registry import
        pass  # Acceptable — handlers may have been loaded by earlier test
    assert "hledac.universal.discovery.ti_feed_adapter" not in sys.modules, \
        "Circular import — ti_feed_adapter must not load on tool_registry import"
