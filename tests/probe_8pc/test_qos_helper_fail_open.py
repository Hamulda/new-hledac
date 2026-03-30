"""
Sprint 8PC D.5: set_thread_qos — fail-open on non-macOS or syscall failure.

B.7 Invariant: set_thread_qos() must never raise — it is fail-open.
"""
import sys
sys.path.insert(0, "/Users/vojtechhamada/PycharmProjects/Hledac")


def test_qos_fail_open_on_missing_libc():
    """B.7: set_thread_qos() fails-open when ctypes syscall is unavailable."""
    # Patch ctypes to raise on any call — simulating non-macOS environment
    import hledac.universal.core.resource_governor as rg

    original_cdll = None

    class FailingCDLL:
        def syscall(self, *args):
            raise OSError("syscall not available")

        def __call__(self, *args):
            raise OSError("libc not available")

    import ctypes
    original_cdll = ctypes.CDLL

    try:
        ctypes.CDLL = FailingCDLL
        # Reload to pick up the patched ctypes
        import importlib
        importlib.reload(rg)

        # This must NOT raise — fail-open
        rg.set_thread_qos(0x09)  # BACKGROUND QoS

        print("[PASS] test_qos_fail_open_on_missing_libc")
    except Exception as e:
        raise AssertionError(f"set_thread_qos() raised {e} — must be fail-open") from e
    finally:
        ctypes.CDLL = original_cdll
        import importlib
        importlib.reload(rg)


def test_qos_defined_constants():
    """QoS constants are defined and match expected Darwin values."""
    from hledac.universal.core.resource_governor import (
        _QOS_USER_INITIATED,
        _QOS_UTILITY,
        _QOS_BACKGROUND,
    )

    assert _QOS_USER_INITIATED == 0x19, f"Expected 0x19, got {_QOS_USER_INITIATED:#x}"
    assert _QOS_UTILITY == 0x11, f"Expected 0x11, got {_QOS_UTILITY:#x}"
    assert _QOS_BACKGROUND == 0x09, f"Expected 0x09, got {_QOS_BACKGROUND:#x}"

    print("[PASS] test_qos_defined_constants")


if __name__ == "__main__":
    test_qos_fail_open_on_missing_libc()
    test_qos_defined_constants()
