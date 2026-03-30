"""
Sdílené executory pro celý hledac.universal.
Single source of truth — importovat odtud, nikde nevytvářet nové.
"""
from __future__ import annotations

import atexit
from concurrent.futures import ThreadPoolExecutor

__all__ = ["CPU_EXECUTOR", "IO_EXECUTOR", "shutdown_all_executors"]

# M1: 4E+4P cores — CPU-bound dostane 2 performance cores, IO dostane 4 pro síťové čekání
CPU_EXECUTOR: ThreadPoolExecutor = ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="hledac_cpu"
)
IO_EXECUTOR: ThreadPoolExecutor = ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="hledac_io"
)


def shutdown_all_executors(wait: bool = True) -> None:
    """Shutdown both shared executors. Called automatically via atexit."""
    CPU_EXECUTOR.shutdown(wait=wait)
    IO_EXECUTOR.shutdown(wait=wait)


atexit.register(shutdown_all_executors, wait=False)
