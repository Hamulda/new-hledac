import ast

def test_certstream_uses_running_loop():
    src = open("discovery/ti_feed_adapter.py").read()
    assert "get_running_loop" in src
    assert src.count("get_running_loop") >= 1
