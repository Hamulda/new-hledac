"""
Circuit Breaker — transport resilience pattern.

Prevents cascading failures by opening the circuit after repeated
consecutive failures/timeouts for a given domain.

Sprint 8VB — Transport Resilience + Self-Hosted Search
Sprint 8VE C — Transport fallback chain
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class CBState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    domain: str
    failure_threshold: int = 3
    recovery_timeout: float = 60.0
    _state: CBState = field(default=CBState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)
    _consecutive_timeouts: int = field(default=0, init=False)

    def is_open(self) -> bool:
        if self._state == CBState.OPEN:
            if time.monotonic() - self._last_failure_time > self.recovery_timeout:
                self._state = CBState.HALF_OPEN
                return False
            return True
        return False

    def record_success(self):
        self._failure_count = 0
        self._consecutive_timeouts = 0
        self._state = CBState.CLOSED

    def record_failure(self, is_timeout: bool = False):
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if is_timeout:
            self._consecutive_timeouts += 1
            if self._consecutive_timeouts >= 3:
                self.recovery_timeout = min(
                    self.recovery_timeout * 2, 3600.0
                )
                self._consecutive_timeouts = 0
        else:
            self._consecutive_timeouts = 0
        if self._failure_count >= self.failure_threshold:
            self._state = CBState.OPEN

    def get_state(self) -> str:
        return self._state.value


_BREAKERS: dict[str, CircuitBreaker] = {}


def get_breaker(domain: str) -> CircuitBreaker:
    if domain not in _BREAKERS:
        _BREAKERS[domain] = CircuitBreaker(domain=domain)
    return _BREAKERS[domain]


def get_all_breaker_states() -> dict[str, str]:
    return {d: b.get_state() for d, b in _BREAKERS.items()}


# =============================================================================
# Sprint 8VE C.2: Transport fallback chain
# AUTHORITY NOTE (audit/8SF):
#   This module is a TEST-SEAM only. resilient_fetch() and get_transport_for_domain()
#   are exercised by probe_8ve tests but are NOT called from production code.
#
#   Production path:
#     FetchCoordinator._fetch_url() handles .onion/.i2p directly via
#     _fetch_with_tor() / _fetch_with_lightpanda() / _fetch_with_curl().
#
#   Donor/Compat:
#     circuit_breaker.py CircuitBreaker class IS used by other code (shared state).
#     get_breaker() is the canonical domain circuit breaker accessor.
#
#   Migration precondition:
#     Remove this module's fallback-chain functions only AFTER
#     TransportResolver.resolve() is wired into FetchCoordinator._fetch_url()
#     and probe_8ve tests are redirected to the wired path.
# =============================================================================

async def get_transport_for_domain(domain: str) -> str:
    """
    Fallback chain: clearnet → Tor → Nym.
    Nym má 2-10s latenci — používej POUZE pro anonymity_required tasky.
    Rozhoduje podle Circuit Breaker stavů.
    """
    cb_clearnet = get_breaker(domain)
    if not cb_clearnet.is_open():
        return "clearnet"
    cb_tor = get_breaker(f"tor:{domain}")
    if not cb_tor.is_open():
        return "tor"
    return "nym"


async def resilient_fetch(
    url: str,
    anonymity_required: bool = False,
    **kwargs
) -> str | None:
    """
    Fetch s automatickým transport fallback.
    anonymity_required=True → preskočí clearnet, jde rovnou na Tor/Nym.
    Nym NIKDY v automatickém fallback pro normální tasky — 2-10s latence
    by zablokovala semaphore slot a snížila throughput sprintu.
    """
    from urllib.parse import urlparse
    domain = urlparse(url).netloc

    if anonymity_required:
        transport = "tor"
    else:
        transport = await get_transport_for_domain(domain)
        if transport == "nym":
            # Nym pouze pro explicitní anonymity_required=True
            logger.debug(f"[TRANSPORT] Nym skipped for {domain} (use anonymity_required=True)")
            return None

    if transport == "clearnet":
        # Direct fetch pres aiohttp
        try:
            import aiohttp
            timeout = kwargs.get("timeout", 15.0)
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        return await resp.text()
                    return None
        except Exception:
            return None

    elif transport == "tor":
        cb = get_breaker(f"tor:{domain}")
        try:
            # Tor fetch pres SOCKS5 proxy (Tor daemon musí běžet na 9050)
            import aiohttp
            from aiohttp_socks import ProxyConnector
            timeout = kwargs.get("timeout", 15.0)
            connector = ProxyConnector.from_url("socks5://127.0.0.1:9050", rdns=True)
            async with aiohttp.ClientSession(connector=connector,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as session:
                async with session.get(url) as resp:
                    cb.record_success()
                    if resp.status == 200:
                        return await resp.text()
                    return None
        except Exception:
            cb.record_failure()
            if anonymity_required:
                # Tor selhal + anonymity required → zkus Nym
                try:
                    from hledac.universal.transport.nym_transport import NymTransport
                    nym = NymTransport()
                    await nym.start()
                    try:
                        result = await nym.send_message(url, "fetch", {}, "", "")
                        return result
                    finally:
                        await nym.stop()
                except Exception:
                    pass
            return None

    return None
