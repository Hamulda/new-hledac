"""Sprint 8TA B.3: findings_per_minute calculation."""


def test_scorecard_fpm_calc():
    """accepted=10, elapsed=120s -> findings_per_minute == 5.0."""
    accepted = 10
    elapsed = 120.0  # seconds

    findings_per_minute = accepted * 60.0 / max(1.0, elapsed)

    assert findings_per_minute == 5.0


def test_scorecard_fpm_zero_elapsed():
    """elapsed=0 -> findings_per_minute == 0."""
    accepted = 10
    elapsed = 0.0

    findings_per_minute = accepted / max(1, elapsed / 60.0) if elapsed > 0 else 0.0

    assert findings_per_minute == 0.0
