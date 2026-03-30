"""D.1 — CPU_EXECUTOR is true singleton with max_workers=2."""
import sys

sys.path.insert(0, ".")

from hledac.universal.utils.executors import CPU_EXECUTOR, IO_EXECUTOR


def test_cpu_executor_singleton():
    """Import twice — must be the same object."""
    from hledac.universal.utils.executors import CPU_EXECUTOR as E1

    assert E1 is CPU_EXECUTOR, "CPU_EXECUTOR not a singleton"


def test_cpu_executor_max_workers():
    """CPU bound pool has exactly 2 workers (M1 P-cores)."""
    assert CPU_EXECUTOR._max_workers == 2, (
        f"Expected max_workers=2, got {CPU_EXECUTOR._max_workers}"
    )


def test_io_executor_max_workers():
    """IO bound pool has exactly 4 workers."""
    assert IO_EXECUTOR._max_workers == 4, (
        f"Expected max_workers=4, got {IO_EXECUTOR._max_workers}"
    )
