"""
Circuit Breaker — transport resilience pattern.

Prevents cascading failures by opening the circuit after repeated
consecutive failures/timeouts for a given domain.

Sprint 8VB — Transport Resilience + Self-Hosted Search
"""

import time
from dataclasses import dataclass, field
from enum import Enum


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
