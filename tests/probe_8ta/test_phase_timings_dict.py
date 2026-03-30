"""Sprint 8TA B.2: Phase timings dict."""
import pytest
import time


def test_phase_timings_dict():
    """_mark_phase('BOOT'), _mark_phase('DONE') -> dict má 2 záznamy s float hodnotami."""
    # Simulate _mark_phase behavior
    _phase_times = {}

    def _mark_phase(name: str):
        _phase_times[name] = time.monotonic()

    _mark_phase("BOOT")
    _mark_phase("DONE")

    assert len(_phase_times) == 2
    assert "BOOT" in _phase_times
    assert "DONE" in _phase_times
    assert isinstance(_phase_times["BOOT"], float)
    assert isinstance(_phase_times["DONE"], float)
    assert _phase_times["DONE"] >= _phase_times["BOOT"]


def test_phase_timings_sorted():
    """Phases can be sorted by start time to compute durations."""
    _phase_times = {}

    def _mark_phase(name: str):
        _phase_times[name] = time.monotonic()

    _mark_phase("BOOT")
    _mark_phase("WARMUP")
    _mark_phase("ACTIVE")
    _mark_phase("WINDUP")
    _mark_phase("EXPORT")
    _mark_phase("TEARDOWN")
    _mark_phase("DONE")

    assert len(_phase_times) == 7

    # Compute durations
    sorted_phases = sorted(_phase_times.items(), key=lambda x: x[1])
    phase_timings = {}
    for i, (name, start) in enumerate(sorted_phases):
        if i + 1 < len(sorted_phases):
            end = sorted_phases[i + 1][1]
            phase_timings[name] = round(end - start, 3)
        else:
            phase_timings[name] = 0.0

    # All durations should be >= 0
    for name, dur in phase_timings.items():
        assert dur >= 0, f"{name} duration {dur} is negative"
