from runtime.sprint_scheduler import SprintScheduler

def test_timeout_ema_converges():
    s = SprintScheduler.__new__(SprintScheduler)
    s._fetch_latency_ema = {}
    for _ in range(10):
        s._update_latency_ema("x.com", 5.0)
    t = s.get_adaptive_timeout("x.com")
    assert 14.5 < t < 15.5
