from transport.circuit_breaker import get_breaker

def test_cb_singleton_per_domain():
    assert get_breaker("a.com") is get_breaker("a.com")
