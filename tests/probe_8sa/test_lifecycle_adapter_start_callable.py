"""
D.2: _LifecycleAdapter.start() volá správnou metodu na runtime lifecycle.
"""
import sys
sys.path.insert(0, ".")


def test_lifecycle_adapter_start_callable():
    from hledac.universal.runtime.sprint_scheduler import _LifecycleAdapter
    from hledac.universal.runtime.sprint_lifecycle import SprintLifecycleManager

    lc = SprintLifecycleManager()
    adapter = _LifecycleAdapter(lc)

    # start() by mělo zavolat lc.start() a přejít do WARMUP
    assert lc._current_phase.name == "BOOT"
    adapter.start()
    assert lc._started_at is not None
    print("PASS: adapter.start() → lifecycle.start() called correctly")


if __name__ == "__main__":
    test_lifecycle_adapter_start_callable()
