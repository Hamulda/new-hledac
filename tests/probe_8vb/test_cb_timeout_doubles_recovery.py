from transport.circuit_breaker import CircuitBreaker

def test_cb_timeout_doubles_recovery():
    cb = CircuitBreaker(
        domain="slow.onion",
        failure_threshold=10,
        recovery_timeout=60.0
    )
    for _ in range(3):
        cb.record_failure(is_timeout=True)
    assert cb.recovery_timeout == 120.0
