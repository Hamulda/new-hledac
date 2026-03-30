from runtime.sprint_scheduler import SprintScheduler

def test_timeout_clamped_min():
    s = SprintScheduler.__new__(SprintScheduler)
    s._fetch_latency_ema = {}
    for _ in range(5):
        s._update_latency_ema("fast.com", 0.1)
    assert s.get_adaptive_timeout("fast.com") == 5.0
