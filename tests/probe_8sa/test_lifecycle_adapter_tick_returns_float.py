"""
D.3: _LifecycleAdapter.tick() vrací SprintPhase (ne float).
runtime: tick() returns SprintPhase enum.
"""
import sys
sys.path.insert(0, ".")


def test_lifecycle_adapter_tick_returns_sprint_phase():
    from hledac.universal.runtime.sprint_scheduler import _LifecycleAdapter
    from hledac.universal.runtime.sprint_lifecycle import SprintLifecycleManager, SprintPhase

    lc = SprintLifecycleManager(sprint_duration_s=30.0)
    adapter = _LifecycleAdapter(lc)
    adapter.start()

    result = adapter.tick()
    # runtime tick() returns SprintPhase enum
    assert isinstance(result, SprintPhase), f"tick() returned {type(result)}, expected SprintPhase"
    assert result in (SprintPhase.WARMUP, SprintPhase.ACTIVE)
    print(f"PASS: adapter.tick() → {result} (SprintPhase)")


if __name__ == "__main__":
    test_lifecycle_adapter_tick_returns_sprint_phase()

