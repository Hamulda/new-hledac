def test_threatfox_confidence_normalization():
    raw_confidence = 80
    normalized = raw_confidence / 100
    assert normalized == 0.80
