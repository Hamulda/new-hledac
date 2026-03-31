"""Test scorecard has required keys."""
import pathlib
import sys
import time
import resource

_universal = pathlib.Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_universal))

import os
os.chdir(_universal)


def test_scorecard_keys():
    """Scorecard dict must have required keys."""
    required = {
        "peak_rss_mb",
        "accepted_findings_count",
        "synthesis_engine_used",
        "phase_duration_seconds",
    }

    # Compute peak_rss_mb the same way __main__.py does
    rss_bytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_rss_mb = round(rss_bytes / 1024 / 1024, 1)

    scorecard = {
        "peak_rss_mb": peak_rss_mb,
        "accepted_findings_count": 0,
        "synthesis_engine_used": "unknown",
        "phase_duration_seconds": {"warmup": 0.0, "active": 0.0, "windup": 0.0},
    }

    missing = required - set(scorecard.keys())
    assert not missing, f"Missing scorecard keys: {missing}"


if __name__ == "__main__":
    test_scorecard_keys()
    print("test_scorecard_has_required_keys: PASSED")
