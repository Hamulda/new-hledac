import time
from transport.circuit_breaker import CircuitBreaker

def test_cb_half_open_after_recovery():
    cb = CircuitBreaker(domain="t.onion", recovery_timeout=0.01)
    for _ in range(3):
        cb.record_failure()
    time.sleep(0.02)
    assert cb.is_open() is False  # prešlo do HALF_OPEN
