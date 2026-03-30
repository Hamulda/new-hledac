from transport.circuit_breaker import CircuitBreaker

def test_cb_opens_after_threshold():
    cb = CircuitBreaker(domain="evil.onion", failure_threshold=3)
    for _ in range(3):
        cb.record_failure()
    assert cb.is_open() is True
