"""
Transport layer for federated learning.
Provides autonomous transport selection via TransportResolver.
"""

from .base import Transport
from .inmemory_transport import InMemoryTransport
from .transport_resolver import TransportResolver, TransportContext

__all__ = [
    'Transport',
    'InMemoryTransport',
    'TransportResolver',
    'TransportContext',
]
