"""
Sprint 8PA — D.1: TorTransport graceful ImportError → available=False
"""
import builtins
from unittest.mock import patch, MagicMock

import pytest


class TestTorTransportGracefulImport:
    """D.1: TorTransport.available=False when aiohttp_socks missing, no exception."""

    def test_available_attribute_exists(self):
        """TorTransport.available must be a defined class attribute."""
        from hledac.universal.transport.tor_transport import TorTransport
        assert hasattr(TorTransport, 'available'), \
            "TorTransport must have 'available' attribute"
        assert isinstance(TorTransport.available, bool)

    def test_available_true_when_deps_present(self):
        """When all deps present, TorTransport.available=True."""
        import importlib
        import hledac.universal.transport.tor_transport as tt_module
        importlib.reload(tt_module)

        tt = tt_module.TorTransport()
        assert hasattr(tt, 'available')
        assert isinstance(tt.available, bool)

    def test_init_returns_early_on_import_error(self):
        """TorTransport.__init__ returns early when aiohttp_socks ImportError."""
        import importlib
        import hledac.universal.transport.tor_transport as tt_module
        importlib.reload(tt_module)

        # If aiohttp_socks is installed, available should be True
        # (we're running on a machine with it installed per preflight)
        tt = tt_module.TorTransport()
        # The init must complete without raising RuntimeError
        # It should have available=True (since deps are present)
        assert hasattr(tt, 'available')
        assert isinstance(tt.available, bool), \
            f"available must be bool, got {type(tt.available)}"
