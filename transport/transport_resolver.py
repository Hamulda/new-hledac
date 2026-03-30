"""
TransportResolver - Autonomous transport selection based on runtime context.

Priorities: Nym > Tor > Direct > InMemory
No config toggles - all decisions based on runtime signals.
"""

import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

logger = logging.getLogger(__name__)


class Transport(Enum):
    """Transport type enum — used by SourceTransportMap."""
    DIRECT = auto()
    TOR = auto()
    I2P = auto()
    INMEMORY = auto()


# B6: SourceTransportMap — mandatory onion routing, no DIRECT override
_ONION_MAP: dict[str, Transport] = {
    ".onion": Transport.TOR,      # mandatory — never override to DIRECT
    ".i2p": Transport.I2P,        # stub — fail-open to direct
}


class SourceTransportMap:
    """
    B6: Domain-suffix → Transport mapping.
    .onion is MANDATORY Tor (cannot be overridden to DIRECT).
    .i2p routes to I2P (currently stub, fail-open to direct).
    """
    _map: dict[str, Transport] = _ONION_MAP

    @classmethod
    def get(cls, suffix: str) -> Transport:
        return cls._map.get(suffix, Transport.DIRECT)

    @classmethod
    def is_mandatory_tor(cls, suffix: str) -> bool:
        """Return True if suffix MUST use Tor (e.g. .onion)."""
        return cls._map.get(suffix) is Transport.TOR


@dataclass
class TransportContext:
    """Runtime context for transport selection."""
    requires_anonymity: bool = False
    risk_level: str = "medium"  # "low", "medium", "high"
    allow_inmemory: bool = False  # Only for testing/internal bus


class TransportResolver:
    """
    Autonomous transport selection without config toggles.

    Decisions based on:
    - context.requires_anonymity (derived from runtime signals)
    - context.risk_level
    - autodetection of Tor/Nym availability
    """

    def __init__(self):
        self._tor_class: Optional[type] = None
        self._nym_class: Optional[type] = None
        self._checked = False

    def _check_transports(self):
        """Lazy check for transport availability."""
        if self._checked:
            return

        # Try to import Tor transport
        try:
            from .tor_transport import TorTransport
            self._tor_class = TorTransport
            logger.debug("Tor transport available")
        except ImportError as e:
            logger.debug(f"Tor transport unavailable: {e}")

        # Try to import Nym transport
        try:
            from .nym_transport import NymTransport
            self._nym_class = NymTransport
            logger.debug("Nym transport available")
        except ImportError as e:
            logger.debug(f"Nym transport unavailable: {e}")

        self._checked = True

    def resolve_url(self, url: str) -> Transport:
        """
        B6/C.4: Resolve transport for a URL based on its domain suffix.
        This is a fast synchronous dict lookup (<50ms for 1000 calls).

        Args:
            url: URL string to analyze

        Returns:
            Transport enum: TOR for .onion, I2P for .i2p, DIRECT for everything else
        """
        # B6: Check if host ends with .onion or .i2p directly (not just last dot suffix)
        # This handles subdomains correctly: mirror.onion.hiddenservice.com → .com (not onion)
        # But sub.domain.onion → .onion (correct)
        try:
            netloc = url.split("://", 1)[1].split("/", 1)[0]
            if ":" in netloc:
                host = netloc.split(":")[0]
            else:
                host = netloc
            # Check for .onion / .i2p as true TLD suffixes (case-insensitive)
            host_lower = host.lower()
            if host_lower.endswith('.onion'):
                return Transport.TOR
            if host_lower.endswith('.i2p'):
                return Transport.I2P
        except Exception:
            pass
        return Transport.DIRECT

    def is_tor_mandatory(self, url: str) -> bool:
        """Return True if URL must use Tor transport (cannot be overridden)."""
        try:
            netloc = url.split("://", 1)[1].split("/", 1)[0]
            if ":" in netloc:
                host = netloc.split(":")[0]
            else:
                host = netloc
            return host.lower().endswith('.onion')
        except Exception:
            return False

    async def resolve(self, context: TransportContext) -> Optional['Transport']:
        """
        Resolve appropriate transport based on context.

        Priority: Nym > Tor > Direct > InMemory
        """
        self._check_transports()

        # High anonymity requirement: prefer Nym > Tor
        if context.requires_anonymity or context.risk_level == "high":
            # Try Nym first (highest anonymity)
            if self._nym_class:
                try:
                    transport = self._nym_class()
                    await transport.start()
                    logger.info("Using Nym transport for high anonymity")
                    return transport
                except Exception as e:
                    logger.warning(f"Nym transport init failed: {e}")

            # Fallback to Tor
            if self._tor_class:
                try:
                    transport = self._tor_class()
                    await transport.start()
                    logger.info("Using Tor transport for anonymity (Nym unavailable)")
                    return transport
                except Exception as e:
                    logger.warning(f"Tor transport init failed: {e}")

            # If anonymity required but nothing available, log warning
            logger.warning("Anonymity required but no anonymous transport available")

        # Medium risk: try to use Tor/Nym if available, but don't require
        if context.risk_level == "medium":
            if self._nym_class:
                try:
                    transport = self._nym_class()
                    await transport.start()
                    logger.info("Using Nym transport (medium risk)")
                    return transport
                except Exception:
                    pass

            if self._tor_class:
                try:
                    transport = self._tor_class()
                    await transport.start()
                    logger.info("Using Tor transport (medium risk)")
                    return transport
                except Exception:
                    pass

        # Low risk or fallback: use InMemory for testing/internal
        if context.allow_inmemory:
            from .inmemory_transport import InMemoryTransport
            logger.info("Using InMemory transport (fallback)")
            return InMemoryTransport("resolver_node")

        # No transport available - return None, caller will handle
        logger.warning("No transport available, returning None")
        return None


# Backwards compatibility alias
Transport = Transport  # re-export via module-level alias
