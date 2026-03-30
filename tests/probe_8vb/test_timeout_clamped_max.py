from runtime.sprint_scheduler import SprintScheduler

def test_timeout_clamped_max():
    s = SprintScheduler.__new__(SprintScheduler)
    s._fetch_latency_ema = {}
    for _ in range(5):
        s._update_latency_ema("slow.onion", 20.0)
    assert s.get_adaptive_timeout("slow.onion") == 30.0
