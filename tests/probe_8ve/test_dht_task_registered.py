import pathlib


def test_dht_task_registered():
    src = pathlib.Path("hledac/universal/runtime/sprint_scheduler.py").read_text()
    assert "dht_keyword_crawl"    in src
    assert "dht_infohash_lookup"  in src
