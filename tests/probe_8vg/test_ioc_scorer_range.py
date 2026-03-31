from hledac.universal.brain.ner_engine import IOCScorer

def test_ioc_scorer_range():
    for source in ["abuse_ch", "dht_crawl", "unknown_xyz"]:
        entry = {"source": source, "confidence": 0.7, "hit_count": 5}
        score = IOCScorer.final_score(entry)
        assert 0.0 <= score <= 1.0, f"Score out of range for {source}: {score}"
