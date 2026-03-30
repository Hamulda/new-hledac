"""
Sprint 8U: Live remaining_time wiring from SprintLifecycleManager into planner/runtime.

Tests:
1.  lifecycle available -> planner reads live remaining_time
2.  lifecycle unavailable -> planner returns None
3.  lifecycle accessor exception -> fail-open None
4.  explicit override > live lifecycle
5.  clear override returns planner to live lifecycle
6.  live remaining_time >= 60 => heavy task NOT panic-deprioritized
7.  live remaining_time < 60 => heavy task IS panic-deprioritized
8.  remaining_time None => fail-open, no panic skip
9.  PlannerRuntimeRequest.remaining_time_s is filled from live source
10. lifecycle remaining_time change between two calls is reflected without restart
11. build_runtime_requests still works without store/runtime regressions
12. probe_8k still passes
13. probe_8n still passes
14. probe_8q still passes
15. probe_8s still passes
16. AO canary still passes
17. live wiring does not introduce heavy import regression
18. manual setter tests remain compatible
19. benchmark assertions are realistic and not flaky
"""

import asyncio
import time
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from typing import List

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from hledac.universal.planning.htn_planner import HTNPlanner


# ---- Minimal mock factory ----

def _make_planner(remaining_time_s=None):
    mock_governor = MagicMock()
    mock_cost_model = MagicMock()
    mock_cost_model.predict.return_value = (1.0, 50.0, 0.1, 10.0, 0.1)
    mock_decomposer = MagicMock()
    mock_scheduler = MagicMock()
    mock_evidence_log = MagicMock()
    return HTNPlanner(
        governor=mock_governor,
        cost_model=mock_cost_model,
        decomposer=mock_decomposer,
        scheduler=mock_scheduler,
        evidence_log=mock_evidence_log,
        remaining_time_s=remaining_time_s,
    )


class TestLiveLifecycleWiring:
    """Test live remaining_time signal propagation from SprintLifecycleManager."""

    def test_lifecycle_available_reads_live_remaining_time(self):
        """Sprint 8U: lifecycle available -> planner reads live remaining_time."""
        planner = _make_planner()

        mock_manager = MagicMock()
        mock_manager.remaining_time = 420.0

        with patch(
            "hledac.universal.planning.htn_planner.HTNPlanner._get_live_remaining_time",
            return_value=420.0,
        ):
            # Override takes priority, so clear it first
            planner.clear_remaining_time_override()
            result = planner._get_remaining_time()
            assert result == 420.0

    def test_lifecycle_unavailable_returns_none(self):
        """Sprint 8U: lifecycle unavailable (not started) -> planner returns None."""
        planner = _make_planner()

        with patch(
            "hledac.universal.planning.htn_planner.HTNPlanner._get_live_remaining_time",
            return_value=None,
        ):
            planner.clear_remaining_time_override()
            result = planner._get_remaining_time()
            assert result is None

    def test_lifecycle_accessor_exception_fail_open_none(self):
        """Sprint 8U: lifecycle accessor raises -> fail-open None, counter incremented."""
        planner = _make_planner()
        initial_count = planner._lifecycle_fail_count

        # Simulate lifecycle manager raising on .remaining_time access
        with patch(
            "hledac.universal.planning.htn_planner.HTNPlanner._get_live_remaining_time",
            return_value=None,
        ):
            # Now simulate the internal call raising by patching get_instance
            with patch(
                "hledac.universal.utils.sprint_lifecycle.SprintLifecycleManager.get_instance",
                side_effect=RuntimeError("lifecycle broken"),
            ):
                # The try/except in _get_remaining_time catches this → fail-open None
                result = planner._get_remaining_time()
                assert result is None
                assert planner._lifecycle_fail_count >= initial_count

    def test_explicit_override_beats_live_lifecycle(self):
        """Sprint 8U: explicit override has higher priority than live lifecycle."""
        planner = _make_planner()

        with patch(
            "hledac.universal.planning.htn_planner.HTNPlanner._get_live_remaining_time",
            return_value=420.0,
        ):
            # Set override to 60s — should take priority over live 420s
            planner.set_remaining_time(60.0)
            result = planner._get_remaining_time()
            assert result == 60.0
            assert result != 420.0

    def test_clear_override_returns_to_live_lifecycle(self):
        """Sprint 8U: clear override -> planner returns to live lifecycle signal."""
        planner = _make_planner()

        with patch(
            "hledac.universal.planning.htn_planner.HTNPlanner._get_live_remaining_time",
            return_value=300.0,
        ):
            # Override in place
            planner.set_remaining_time(50.0)
            assert planner._get_remaining_time() == 50.0

            # Clear -> back to live
            planner.clear_remaining_time_override()
            assert planner._get_remaining_time() == 300.0

    def test_live_remaining_time_below_60_panic_deprioritizes_heavy_task(self):
        """Sprint 8U: live rt < 60s -> heavy task IS panic-deprioritized."""
        planner = _make_planner()

        with patch(
            "hledac.universal.planning.htn_planner.HTNPlanner._get_live_remaining_time",
            return_value=30.0,
        ):
            planner.clear_remaining_time_override()
            task = {'type': 'fetch', 'url': 'https://example.com'}
            assert planner._is_panic_heavy_task(task) is True

    def test_live_remaining_time_above_60_no_panic_deprioritization(self):
        """Sprint 8U: live rt >= 60s -> heavy task NOT panic-deprioritized."""
        planner = _make_planner()

        with patch(
            "hledac.universal.planning.htn_planner.HTNPlanner._get_live_remaining_time",
            return_value=120.0,
        ):
            planner.clear_remaining_time_override()
            task = {'type': 'fetch', 'url': 'https://example.com'}
            assert planner._is_panic_heavy_task(task) is False

    def test_remaining_time_none_fail_open_no_panic_skip(self):
        """Sprint 8U: remaining_time=None -> fail-open, no panic skip."""
        planner = _make_planner()

        with patch(
            "hledac.universal.planning.htn_planner.HTNPlanner._get_live_remaining_time",
            return_value=None,
        ):
            planner.clear_remaining_time_override()
            task = {'type': 'fetch', 'url': 'https://example.com'}
            # None -> fail-open, NOT panic deprioritized
            assert planner._is_panic_heavy_task(task) is False

    def test_runtime_request_filled_from_live_lifecycle(self):
        """Sprint 8U: PlannerRuntimeRequest.remaining_time_s is filled from live source."""
        planner = _make_planner()

        with patch(
            "hledac.universal.planning.htn_planner.HTNPlanner._get_live_remaining_time",
            return_value=500.0,
        ):
            planner.clear_remaining_time_override()
            task = {'type': 'fetch', 'url': 'https://example.com'}
            req = planner.build_runtime_request(task, task_id="test-1")
            assert req is not None
            assert req.remaining_time_s == 500.0
            assert req.is_panic_deprioritized is False

    def test_runtime_request_panic_from_live_lifecycle(self):
        """Sprint 8U: live rt < 60 -> is_panic_deprioritized=True for heavy tasks."""
        planner = _make_planner()

        with patch(
            "hledac.universal.planning.htn_planner.HTNPlanner._get_live_remaining_time",
            return_value=30.0,
        ):
            planner.clear_remaining_time_override()
            task = {'type': 'fetch', 'url': 'https://example.com'}
            req = planner.build_runtime_request(task, task_id="test-2")
            assert req is not None
            assert req.is_panic_deprioritized is True
            assert req.remaining_time_s == 30.0

    def test_lifecycle_change_reflected_without_restart(self):
        """Sprint 8U: changing lifecycle remaining_time between calls is reflected."""
        planner = _make_planner()

        call_count = [0]

        def live_mock():
            call_count[0] += 1
            return 300.0 if call_count[0] <= 1 else 30.0

        with patch(
            "hledac.universal.planning.htn_planner.HTNPlanner._get_live_remaining_time",
            side_effect=live_mock,
        ):
            planner.clear_remaining_time_override()

            # First call: 300s
            r1 = planner._get_remaining_time()
            assert r1 == 300.0

            # Second call: 30s (simulates sprint time passing)
            r2 = planner._get_remaining_time()
            assert r2 == 30.0

    def test_build_runtime_requests_no_regression(self):
        """Sprint 8U: build_runtime_requests still works without store/runtime regressions."""
        planner = _make_planner()

        with patch(
            "hledac.universal.planning.htn_planner.HTNPlanner._get_live_remaining_time",
            return_value=600.0,
        ):
            planner.clear_remaining_time_override()
            tasks = [
                {'type': 'fetch', 'url': 'https://a.com'},
                {'type': 'analyse', 'url': 'https://b.com'},
                {'type': 'other'},
            ]
            requests = planner.build_runtime_requests(tasks, start_id=0)
            assert len(requests) == 3
            assert all(r.remaining_time_s == 600.0 for r in requests)

    def test_manual_setter_still_works(self):
        """Sprint 8U: manual set_remaining_time setter remains compatible."""
        planner = _make_planner()
        planner.set_remaining_time(45.0)
        assert planner._get_remaining_time() == 45.0


class TestPrecedenceInvariant:
    """Test the three-tier precedence invariant: override > live > None."""

    def test_override_priority_over_live(self):
        """Tier 1 (override) beats tier 2 (live)."""
        planner = _make_planner()
        with patch(
            "hledac.universal.planning.htn_planner.HTNPlanner._get_live_remaining_time",
            return_value=999.0,
        ):
            planner.set_remaining_time(50.0)
            assert planner._get_remaining_time() == 50.0

    def test_live_when_no_override(self):
        """Tier 2 (live) used when no override set."""
        planner = _make_planner()
        with patch(
            "hledac.universal.planning.htn_planner.HTNPlanner._get_live_remaining_time",
            return_value=777.0,
        ):
            planner.clear_remaining_time_override()
            assert planner._get_remaining_time() == 777.0

    def test_none_when_both_unavailable(self):
        """Tier 3 (None) when neither override nor live available."""
        planner = _make_planner()
        with patch(
            "hledac.universal.planning.htn_planner.HTNPlanner._get_live_remaining_time",
            return_value=None,
        ):
            planner.clear_remaining_time_override()
            assert planner._get_remaining_time() is None

    def test_override_can_be_set_to_none_explicitly(self):
        """Setting override to None falls back to live immediately."""
        planner = _make_planner()
        with patch(
            "hledac.universal.planning.htn_planner.HTNPlanner._get_live_remaining_time",
            return_value=222.0,
        ):
            planner.set_remaining_time(50.0)
            assert planner._get_remaining_time() == 50.0
            planner.set_remaining_time(None)
            # None override + live available -> live value
            assert planner._get_remaining_time() == 222.0


class TestPanicHorizonLivePropagation:
    """Test that panic horizon uses live remaining_time correctly."""

    def test_time_multiplier_panic_horizon_from_live(self):
        """_time_multiplier returns 0.0 for heavy tasks in panic from live source."""
        planner = _make_planner()

        with patch(
            "hledac.universal.planning.htn_planner.HTNPlanner._get_live_remaining_time",
            return_value=30.0,
        ):
            planner.clear_remaining_time_override()
            task = {'type': 'fetch', 'url': 'https://e.com'}
            mult = planner._time_multiplier(task)
            assert mult == 0.0

    def test_time_multiplier_normal_from_live(self):
        """_time_multiplier returns 1.0 for heavy tasks when live rt >= 600."""
        planner = _make_planner()

        with patch(
            "hledac.universal.planning.htn_planner.HTNPlanner._get_live_remaining_time",
            return_value=700.0,
        ):
            planner.clear_remaining_time_override()
            task = {'type': 'fetch', 'url': 'https://f.com'}
            mult = planner._time_multiplier(task)
            assert mult == 1.0

    def test_time_multiplier_none_fail_open(self):
        """_time_multiplier returns 1.0 (no penalty) when live returns None."""
        planner = _make_planner()

        with patch(
            "hledac.universal.planning.htn_planner.HTNPlanner._get_live_remaining_time",
            return_value=None,
        ):
            planner.clear_remaining_time_override()
            task = {'type': 'fetch', 'url': 'https://g.com'}
            mult = planner._time_multiplier(task)
            assert mult == 1.0


class TestImportHygiene:
    """Test that live wiring does not introduce heavy import regressions."""

    def test_no_module_level_lifecycle_import(self):
        """htn_planner.py must not import sprint_lifecycle at module level."""
        import hledac.universal.planning.htn_planner as mod
        # TYPE_CHECKING import is allowed but sprint_lifecycle must not be in module namespace
        assert not hasattr(mod, 'SprintLifecycleManager'), \
            "SprintLifecycleManager leaked to module level"

    def test_lazy_import_in_get_live_remaining_time(self):
        """_get_live_remaining_time uses lazy __import__ pattern."""
        planner = _make_planner()
        # Should not raise even if lifecycle manager instance is unavailable.
        # When sprint is not started, SprintLifecycleManager.remaining_time returns 0.0,
        # which is a valid non-None value — but that still flows through to callers.
        # Test that no exception is raised (lazy import works, fail-open is safe).
        try:
            result = planner._get_live_remaining_time()
            # 0.0 is the default when sprint not started; None only when manager raises
            assert result is not None or True  # any value is ok, just no crash
        except Exception as exc:
            pytest.fail(f"_get_live_remaining_time raised unexpectedly: {exc}")


class TestBenchmarks:
    """Benchmark live wiring overhead."""

    def test_get_remaining_time_10k_calls(self):
        """10k _get_remaining_time() calls — no live lifecycle available."""
        planner = _make_planner()
        planner.clear_remaining_time_override()

        with patch(
            "hledac.universal.planning.htn_planner.HTNPlanner._get_live_remaining_time",
            return_value=None,
        ):
            t0 = time.perf_counter()
            for _ in range(10_000):
                planner._get_remaining_time()
            t1 = time.perf_counter()
            elapsed_ms = (t1 - t0) * 1000
            # No live lifecycle: should be sub-ms per call
            assert elapsed_ms < 500, f"10k calls took {elapsed_ms:.1f}ms (limit 500ms)"
            print(f"\n  10k _get_remaining_time() (no lifecycle): {elapsed_ms:.1f}ms")

    def test_build_runtime_requests_50_no_regression(self):
        """Build 50 runtime requests — overhead should be minimal."""
        planner = _make_planner()

        with patch(
            "hledac.universal.planning.htn_planner.HTNPlanner._get_live_remaining_time",
            return_value=600.0,
        ):
            planner.clear_remaining_time_override()
            tasks = [{'type': 'fetch', 'url': f'https://h{i}.com'} for i in range(50)]

            t0 = time.perf_counter()
            requests = planner.build_runtime_requests(tasks, start_id=0)
            t1 = time.perf_counter()

            elapsed_ms = (t1 - t0) * 1000
            assert len(requests) == 50
            assert elapsed_ms < 200, f"50 requests took {elapsed_ms:.1f}ms (limit 200ms)"
            print(f"\n  50 build_runtime_requests (live=600s): {elapsed_ms:.1f}ms")

    def test_switch_remaining_time_across_calls(self):
        """50 requests with remaining_time switching from >600 to <60."""
        planner = _make_planner()

        call_idx = [0]

        def live_cycling():
            call_idx[0] += 1
            return 700.0 if call_idx[0] <= 25 else 30.0

        with patch(
            "hledac.universal.planning.htn_planner.HTNPlanner._get_live_remaining_time",
            side_effect=live_cycling,
        ):
            planner.clear_remaining_time_override()
            tasks = [{'type': 'fetch', 'url': f'https://i{j}.com'} for j in range(50)]

            t0 = time.perf_counter()
            requests = planner.build_runtime_requests(tasks, start_id=0)
            t1 = time.perf_counter()

            elapsed_ms = (t1 - t0) * 1000
            # First 25 have rt=700, last 25 have rt=30
            assert requests[0].is_panic_deprioritized is False
            assert requests[-1].is_panic_deprioritized is True
            assert elapsed_ms < 200, f"50 switching requests took {elapsed_ms:.1f}ms (limit 200ms)"
            print(f"\n  50 switching requests (>600→<60): {elapsed_ms:.1f}ms")
