"""
Sprint 8PC D.4: SprintLifecycleManager — remaining_time and is_windup_phase.
"""
import sys
import time
from unittest.mock import patch

sys.path.insert(0, "/Users/vojtechhamada/PycharmProjects/Hledac")


def _fresh_manager(duration: float = 100.0):
    """Get a fresh manager, bypassing singleton, with controlled duration."""
    from hledac.universal.utils.sprint_lifecycle import SprintLifecycleManager
    SprintLifecycleManager._instance = None
    mgr = SprintLifecycleManager()
    # Override duration directly — begin_sprint() calls _get_sprint_duration_seconds()
    # so we patch it
    mgr._sprint_duration = duration
    return mgr


def test_remaining_time_not_started():
    """remaining_time = 0.0 before begin_sprint()."""
    mgr = _fresh_manager()
    assert mgr.remaining_time == 0.0
    print("[PASS] test_remaining_time_not_started")


def test_remaining_time_decreases():
    """After begin_sprint(), remaining_time decreases over real time."""
    mgr = _fresh_manager(duration=100.0)
    with patch(
        "hledac.universal.utils.sprint_lifecycle._get_sprint_duration_seconds",
        return_value=100.0,
    ):
        mgr.begin_sprint()

    initial = mgr.remaining_time
    assert initial > 90.0, f"Expected >90s, got {initial}"
    time.sleep(0.5)
    after = mgr.remaining_time
    assert after < initial, f"Expected decrease from {initial} to {after}"
    print(f"[PASS] test_remaining_time_decreases: {initial:.2f}s -> {after:.2f}s")


def test_is_windup_phase_under_180s():
    """is_windup_phase() True when remaining < 180s."""
    mgr = _fresh_manager(duration=100.0)
    with patch(
        "hledac.universal.utils.sprint_lifecycle._get_sprint_duration_seconds",
        return_value=100.0,
    ):
        mgr.begin_sprint()

    assert mgr.remaining_time < 180.0, f"remaining={mgr.remaining_time}"
    assert mgr.is_windup_phase() is True
    print(f"[PASS] test_is_windup_phase_under_180s: remaining={mgr.remaining_time:.1f}s")


def test_is_windup_phase_over_180s():
    """is_windup_phase() False when remaining > 180s."""
    mgr = _fresh_manager(duration=600.0)
    with patch(
        "hledac.universal.utils.sprint_lifecycle._get_sprint_duration_seconds",
        return_value=600.0,
    ):
        mgr.begin_sprint()

    assert mgr.remaining_time > 180.0, f"remaining={mgr.remaining_time}"
    assert mgr.is_windup_phase() is False
    print(f"[PASS] test_is_windup_phase_over_180s: remaining={mgr.remaining_time:.1f}s")


if __name__ == "__main__":
    test_remaining_time_not_started()
    test_remaining_time_decreases()
    test_is_windup_phase_under_180s()
    test_is_windup_phase_over_180s()
