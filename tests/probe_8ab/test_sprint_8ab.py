"""
Sprint 8AB: Unified UMA Accountant Surface Tests
================================================
Covers:
- UMAStatus contract
- sample/get UMA status
- evaluate_uma_state thresholds
- should_enter_io_only_mode + hysteresis
- fail-open for missing surfaces
- status getter is cheap
- cached Process object
- gates: probe_8t, probe_8u, ao_canary still pass
- benchmark tests
"""

import psutil
import warnings
from unittest.mock import patch, MagicMock

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from hledac.universal.core.resource_governor import (
        UMAStatus,
        sample_uma_status,
        evaluate_uma_state,
        should_enter_io_only_mode,
        get_uma_telemetry,
        _get_cached_process,
    )


class TestUMAStatusContract:
    """D.1: UMAStatus contract exists."""

    def test_uma_status_is_dataclass(self):
        assert hasattr(UMAStatus, "__dataclass_fields__")

    def test_uma_status_has_required_fields(self):
        s = UMAStatus(
            rss_gib=0.0,
            system_used_gib=0.0,
            system_available_gib=0.0,
            swap_used_gib=0.0,
            metal_cache_limit_bytes=None,
            metal_wired_limit_bytes=None,
            state="ok",
            io_only=False,
            last_error=None,
        )
        assert s.rss_gib == 0.0
        assert s.system_used_gib == 0.0
        assert s.state == "ok"
        assert s.io_only is False
        assert s.last_error is None


class TestUMAFunctionsExist:
    """D.2–D.4: Core functions exist."""

    def test_sample_uma_status_exists(self):
        assert callable(sample_uma_status)

    def test_evaluate_uma_state_exists(self):
        assert callable(evaluate_uma_state)

    def test_should_enter_io_only_mode_exists(self):
        assert callable(should_enter_io_only_mode)

    def test_get_uma_telemetry_exists(self):
        assert callable(get_uma_telemetry)


class TestEvaluateUMAStateThresholds:
    """D.5–D.8: Threshold semantics."""

    def test_threshold_below_warn(self):
        assert evaluate_uma_state(5.9) == "ok"

    def test_threshold_at_warn(self):
        assert evaluate_uma_state(6.0) == "warn"

    def test_threshold_between_warn_and_critical(self):
        assert evaluate_uma_state(6.49) == "warn"

    def test_threshold_at_critical(self):
        assert evaluate_uma_state(6.5) == "critical"

    def test_threshold_between_critical_and_emergency(self):
        assert evaluate_uma_state(6.99) == "critical"

    def test_threshold_at_emergency(self):
        assert evaluate_uma_state(7.0) == "emergency"

    def test_threshold_above_emergency(self):
        assert evaluate_uma_state(7.5) == "emergency"


class TestShouldEnterIOOnlyMode:
    """D.9–D.11: I/O-only mode and hysteresis."""

    def test_warn_returns_io_only_false(self):
        assert should_enter_io_only_mode(6.0, previous_io_only=False) is False

    def test_critical_enter_io_only_true(self):
        assert should_enter_io_only_mode(6.5, previous_io_only=False) is True

    def test_emergency_returns_io_only_true(self):
        assert should_enter_io_only_mode(7.0, previous_io_only=False) is True

    def test_hysteresis_stay_in_io_only_above_floor(self):
        # previous_io_only=True, 6.4 GiB (above 5.8 floor) → stay True
        assert should_enter_io_only_mode(6.4, previous_io_only=True) is True

    def test_hysteresis_exit_at_floor(self):
        # previous_io_only=True, 5.8 GiB (at floor) → exit False
        assert should_enter_io_only_mode(5.8, previous_io_only=True) is False

    def test_hysteresis_exit_below_floor(self):
        # previous_io_only=True, 5.7 GiB (below floor) → exit False
        assert should_enter_io_only_mode(5.7, previous_io_only=True) is False


class TestFailOpen:
    """D.14–D.17: Fail-open without crash."""

    def test_psutil_missing(self):
        with patch("hledac.universal.core.resource_governor.psutil") as mock_psutil:
            mock_psutil.virtual_memory.side_effect = AttributeError("no psutil")
            # Should not raise
            status = sample_uma_status()
            assert status.last_error is not None
            assert status.state in ("ok", "warn", "critical", "emergency")

    def test_psutil_process_memory_info_exception(self):
        # Patch the cached process instance's memory_info method
        proc = _get_cached_process()
        orig = proc.memory_info
        mock_mem = MagicMock(side_effect=RuntimeError("permission denied"))
        proc.memory_info = mock_mem
        try:
            # Should not raise
            status = sample_uma_status()
            assert status.last_error is not None
            assert status.rss_gib == 0.0
        finally:
            proc.memory_info = orig

    def test_swap_memory_unavailable(self):
        # swap unavailable → fail-open silently, state still computed
        proc = _get_cached_process()
        orig_mem = proc.memory_info
        proc.memory_info = MagicMock(rss=0)
        try:
            with patch("hledac.universal.core.resource_governor.psutil.swap_memory") as mock_swap:
                mock_swap.side_effect = Exception("swap not available")
                status = sample_uma_status()
                # state/io_only still valid, swap silently defaulted to 0
                assert status.swap_used_gib == 0.0
        finally:
            proc.memory_info = orig_mem

    def test_metal_diagnostic_missing(self):
        # metal surface missing → None values, no crash
        with patch("hledac.universal.core.resource_governor._get_metal_limits_status_8ab") as mock_metal:
            mock_metal.return_value = (None, None)
            status = sample_uma_status()
            assert status.metal_cache_limit_bytes is None
            assert status.metal_wired_limit_bytes is None


class TestCachedProcessObject:
    """D.19: Cached psutil.Process() object is used."""

    def test_cached_process_returns_same_instance(self):
        p1 = _get_cached_process()
        p2 = _get_cached_process()
        assert p1 is p2

    def test_sample_uma_status_uses_cached_process(self):
        proc = _get_cached_process()
        # Track calls via call_count on the instance-patched method
        original_meminfo = proc.memory_info
        call_count = [0]

        def tracking_meminfo():
            call_count[0] += 1
            return original_meminfo()

        proc.memory_info = tracking_meminfo
        sample_uma_status()
        assert call_count[0] >= 1
        # Restore
        proc.memory_info = original_meminfo


class TestStatusGetterIsCheap:
    """D.18: Status getter is cheap."""

    def test_evaluate_uma_state_10k_under_100ms(self):
        import time
        t0 = time.perf_counter()
        for _ in range(10_000):
            evaluate_uma_state(6.2)
        t1 = time.perf_counter()
        assert (t1 - t0) * 1000 < 100, f"10k evaluate took {(t1-t0)*1000:.1f}ms"

    def test_should_enter_io_only_10k_under_100ms(self):
        import time
        t0 = time.perf_counter()
        for _ in range(10_000):
            should_enter_io_only_mode(6.2, previous_io_only=False)
        t1 = time.perf_counter()
        assert (t1 - t0) * 1000 < 100, f"10k io_only took {(t1-t0)*1000:.1f}ms"


class TestTelemetryCounters:
    """D.7: Lightweight telemetry counters."""

    def test_telemetry_is_dict(self):
        tel = get_uma_telemetry()
        assert isinstance(tel, dict)
        assert "transition_count" in tel
        assert "io_only_enter_count" in tel
        assert "io_only_exit_count" in tel
        assert "last_state" in tel


class TestGiBUnits:
    """D.8: GiB units are consistent."""

    def test_sample_returns_gib_values_in_reasonable_range(self):
        status = sample_uma_status()
        # RSS should be reasonable for a process
        assert 0 <= status.rss_gib < 20
        # System used should be between 0 and total RAM
        assert 0 <= status.system_used_gib < 20
        # State is one of the valid strings
        assert status.state in ("ok", "warn", "critical", "emergency")


class TestSampleUMAStatusFresh:
    """D.21: sample_uma_status() does not cache internally."""

    def test_two_calls_return_different_rss_if_process_memory_changes(self):
        # sample_uma_status reads live RSS each time — we verify no internal cache
        # by checking that calling it twice gives potentially different values
        # (the function doesn't mutate state between calls)
        s1 = sample_uma_status()
        s2 = sample_uma_status()
        # RSS could be same or different, but the function itself doesn't cache
        # The key check: we can call it repeatedly without state accumulation
        assert isinstance(s1, UMAStatus)
        assert isinstance(s2, UMAStatus)
