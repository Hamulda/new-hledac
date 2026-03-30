"""
Sprint 8AB: Test configuration.
Resets the cached psutil.Process() between tests to prevent mock leakage.
"""

import pytest
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from hledac.universal.core import resource_governor


@pytest.fixture(autouse=True)
def _reset_cached_process():
    """Reset _process_cache before each test to prevent mock object leakage."""
    resource_governor._process_cache = None
    yield
    resource_governor._process_cache = None
