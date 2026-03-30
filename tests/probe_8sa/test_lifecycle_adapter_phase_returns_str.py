"""
D.4: _LifecycleAdapter.phase vrací string.
"""
import sys
sys.path.insert(0, ".")


def test_lifecycle_adapter_phase_returns_str():
    from hledac.universal.runtime.sprint_scheduler import _LifecycleAdapter
    from hledac.universal.runtime.sprint_lifecycle import SprintLifecycleManager

    lc = SprintLifecycleManager()
    adapter = _LifecycleAdapter(lc)
    adapter.start()

    phase = adapter._current_phase
    assert isinstance(phase, str), f"phase returned {type(phase)}, expected str"
    assert phase == "WARMUP"
    print(f"PASS: adapter._current_phase → '{phase}' (str)")


if __name__ == "__main__":
    test_lifecycle_adapter_phase_returns_str()
