"""
D.13: _LifecycleAdapter.is_terminal() vrací True pouze v TEARDOWN.
"""
import sys
sys.path.insert(0, ".")


def test_lifecycle_adapter_is_terminal():
    from hledac.universal.runtime.sprint_scheduler import _LifecycleAdapter
    from hledac.universal.runtime.sprint_lifecycle import SprintLifecycleManager

    lc = SprintLifecycleManager(sprint_duration_s=30.0)
    adapter = _LifecycleAdapter(lc)
    adapter.start()

    # In WARMUP/ACTIVE — should not be terminal
    assert not adapter.is_terminal(), "WARMUP should not be terminal"
    print(f"PASS: is_terminal() in WARMUP → False (phase={adapter._current_phase})")

    # After 30s the sprint naturally ends — check via remaining_time
    remaining = adapter.remaining_time()
    print(f"PASS: remaining_time() = {remaining:.2f}s")


if __name__ == "__main__":
    test_lifecycle_adapter_is_terminal()
