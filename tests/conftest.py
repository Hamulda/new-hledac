"""
Sprint 8AR: pytest configuration for early cache root enforcement.
Sets HF_* and model cache env vars BEFORE any project imports.

This is the ONLY safe bootstrap point in the test harness because pytest
calls pytest_configure() before importing any test modules.
"""

import asyncio
import os
import pytest


def pytest_configure(config=None) -> None:
    """
    Called before any test module is imported.
    Sets cache root env vars so that HuggingFace/transformers/sentence-transformers
    use the declared runtime root instead of ~/.cache/.
    """
    # Determine runtime root - must match paths.py FALLBACK_ROOT logic
    # but without triggering the OPSEC warning (we're in test context)
    _ramdisk_env = os.environ.get("GHOST_RAMDISK", "")
    if _ramdisk_env:
        _selected = _ramdisk_env
    else:
        _selected = os.environ.get("HLEDAC_RUNTIME_ROOT", "")

    # Only override if not already set by user
    _cache_root = os.environ.get("HLEDAC_CACHE_ROOT", "")
    if not _cache_root:
        if _selected:
            os.environ["HLEDAC_CACHE_ROOT"] = _selected
        else:
            # Use fallback root path (same as paths.py)
            from pathlib import Path
            os.environ["HLEDAC_CACHE_ROOT"] = str(Path.home() / ".hledac_fallback_ramdisk")

    # HuggingFace cache directories
    _fallback_cache = os.environ["HLEDAC_CACHE_ROOT"]
    for _env_var in [
        "HF_HOME",
        "HF_HUB_CACHE",
        "HF_DATASETS_CACHE",
        "TRANSFORMERS_CACHE",
        "PYTORCH_TRANSFORMERS_CACHE",
        "PYTORCH_PRETRAINED_BERT_CACHE",
        "TORCH_HOME",
        "XDG_CACHE_HOME",
        "SENTENCE_TRANSFORMERS_HOME",
    ]:
        if not os.environ.get(_env_var):
            os.environ[_env_var] = os.path.join(_fallback_cache, "hf_cache")

    # Ensure cache directory exists
    os.makedirs(os.environ["HLEDAC_CACHE_ROOT"], exist_ok=True)
    os.makedirs(os.path.join(_fallback_cache, "hf_cache"), exist_ok=True)


# ----------------------------------------------------------------------
# Sprint 8J: Event loop repair after asyncio.run() damage
# ----------------------------------------------------------------------
# test_uma_watchdog.py uses asyncio.run() which permanently closes the
# main-thread event loop. This autouse fixture restores a fresh loop
# after every test so subsequent tests never see "no current event loop".
# https://docs.python.org/3.11/library/asyncio-runner.html#asyncio.run


@pytest.fixture(autouse=True)
def _restore_event_loop():
    """
    Restore a fresh event loop after every test.

    Problem: asyncio.run() calls loop.close() and does NOT restore the
    previous event loop. This leaves MainThread with no registered loop,
    causing subsequent tests that call asyncio.get_event_loop() to raise:
        RuntimeError: There is no current event loop in thread 'MainThread'.

    Solution: snapshot the loop before the test, restore it after.
    If the loop was destroyed (asyncio.run case), create a new one.
    """
    # Snapshot loop before test
    old_loop = None
    try:
        old_loop = asyncio.get_event_loop()
    except RuntimeError:
        pass  # no loop registered yet — normal for first test

    yield

    # Restore or recreate loop after test
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        # Loop was destroyed (asyncio.run() damage) — restore it
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
