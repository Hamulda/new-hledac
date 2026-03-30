from transport.circuit_breaker import CircuitBreaker

def test_cb_resets_on_success():
    cb = CircuitBreaker(domain="x.com")
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    assert cb._failure_count == 0 and not cb.is_open()
