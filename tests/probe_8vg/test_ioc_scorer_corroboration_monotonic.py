from hledac.universal.brain.ner_engine import IOCScorer

def test_ioc_scorer_corroboration_monotonic():
    b1 = IOCScorer.score_by_corroboration(1)
    b5 = IOCScorer.score_by_corroboration(5)
    b50 = IOCScorer.score_by_corroboration(50)
    assert b1 <= b5 <= b50
