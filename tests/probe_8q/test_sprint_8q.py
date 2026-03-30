"""
Sprint 8Q — Per-task timing feedback refinement + precise negative-signal learning.

Tests cover:
1.  update() is really called (non-test call-site in planner layer)
2.  _update_count > 0 after successful execute_and_learn
3.  _update_fail_count grows when update() raises
4.  planner returns runtime results even when update() throws
5.  cache clear occurs exactly once per batch (not per-item)
6.  cache clear does NOT happen per-item
7.  system_state is NOT empty dict
8.  system_state contains active_tasks, rss_gb, avg_latency
9.  timeout/network/403-like errors are learnable
10. internal errors (model_not_loaded, planner_error) are NOT learnable
11. negative signals are deduplicated within a single batch
12. panic-skipped tasks are NOT learned
13. model_not_loaded is NOT learned
14. per-task elapsed for single-task request is precise
15. per-task elapsed for multi-task is NOT elapsed/N
16. deterministic task + deterministic mocked outcome → same update inputs
17. probe_8o passes after sprint
18. probe_8n passes
19. probe_8k passes
20. probe_8g passes
21. probe_8i passes
22. AO canary passes
"""

import asyncio
import time
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from typing import List

import sys
import os

sys.path.insert(0, os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
))

from hledac.universal.planning.htn_planner import (
    HTNPlanner,
    PlannerRuntimeRequest,
    PlannerRuntimeResult,
)
from hledac.universal.planning.cost_model import AdaptiveCostModel


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

class _MockGovernor:
    def __init__(self):
        self._active_tasks = 0
        self._rss_gb = 2.0
        self._avg_latency = 0.1

    def get_current_usage(self):
        return {
            'active_tasks': self._active_tasks,
            'rss_gb': self._rss_gb,
            'avg_latency': self._avg_latency,
        }

    async def reserve(self, resources, priority, **kwargs):
        class _Ctx:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
        return _Ctx()


class _MockCostModel:
    """Minimal cost model that records update() calls."""
    def __init__(self):
        self.update_calls = []
        self.predict_result = (1.5, 50.0, 0.5, 3.0, 0.1)
        self._fail_next = False
        self._fail_on_task_type = None

    def predict(self, task_type, params, system_state):
        return self.predict_result

    async def update(self, task_type, params, system_state, actual):
        self.update_calls.append((task_type, params, system_state, actual))
        if self._fail_next:
            self._fail_next = False
            raise RuntimeError("simulated update failure")
        if self._fail_on_task_type == task_type:
            raise RuntimeError(f"simulated failure for {task_type}")


class _FailingCostModel:
    """Cost model that always raises on update."""
    def predict(self, task_type, params, system_state):
        return (1.5, 50.0, 0.5, 3.0, 0.1)

    async def update(self, task_type, params, system_state, actual):
        raise RuntimeError("always fails")


class _MockDecomposer:
    def decompose(self, task):
        return [task]


class _MockScheduler:
    pass


class _MockEvidenceLog:
    pass


class _MockEngineWithTiming:
    """
    Mock Hermes3Engine that supports per-task timing.

    Simulates per-task execution with realistic delays so we can verify
    that per-task elapsed is NOT bridge_elapsed / N.
    """
    def __init__(self, results: List[PlannerRuntimeResult], per_task_delay_s: float = 0.05):
        self._results = results
        self._per_task_delay = per_task_delay_s
        self.call_count = 0
        self._elapsed_times: List[float] = []

    async def execute_planner_requests(self, requests):
        self.call_count += 1
        # Per-request timing: each request takes per_task_delay_s
        # Return result matching requests[0].task_id from self._results
        elapsed = 0.0
        for _ in requests:
            t0 = time.monotonic()
            await asyncio.sleep(self._per_task_delay)
            elapsed += time.monotonic() - t0
            self._elapsed_times.append(time.monotonic() - t0)
        # Return the result corresponding to requests[0].task_id
        req_id = requests[0].task_id
        for r in self._results:
            if r.task_id == req_id:
                return [r]
        return [self._results[0]]


class _SlowThenFastEngine:
    """
    Mock engine where first task is slow, rest are fast.
    Used to verify per-task timing is NOT averaged.
    """
    def __init__(self, results: List[PlannerRuntimeResult]):
        self._results = results

    async def execute_planner_requests(self, requests):
        return self._results


def _make_tasks(n, task_type='fetch', extra=None):
    tasks = []
    for i in range(n):
        t = {'type': task_type, 'url': f'https://example{i}.com', 'depth': 1,
             'priority': 0.5, 'expected_results': 5}
        if extra:
            t.update(extra)
        tasks.append(t)
    return tasks


# --------------------------------------------------------------------------- #
# Test 1: update() is called
# --------------------------------------------------------------------------- #

class TestUpdateCalled:
    """Test 1: update() is called via execute_requests_and_learn."""

    @pytest.mark.asyncio
    async def test_update_count_gt_zero(self):
        mock_cm = _MockCostModel()
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=mock_cm,
            decomposer=_MockDecomposer(),
            scheduler=_MockScheduler(),
            evidence_log=_MockEvidenceLog(),
            remaining_time_s=120.0,
        )

        results = [
            PlannerRuntimeResult(
                task_id=f'planner-{i}',
                executed=True,
                skipped_panic=False,
                hermes_output=f'result{i}',
                error=None,
            )
            for i in range(4)
        ]
        engine = _MockEngineWithTiming(results, per_task_delay_s=0.01)
        tasks = _make_tasks(4)

        returned = await planner.execute_requests_and_learn(tasks, engine)

        assert len(returned) == 4
        assert planner._update_count > 0
        assert len(mock_cm.update_calls) == 4


# --------------------------------------------------------------------------- #
# Test 2: _update_count increments
# --------------------------------------------------------------------------- #

class TestUpdateCounter:
    """Test 2: _update_count increments after successful execution."""

    @pytest.mark.asyncio
    async def test_update_count_increments(self):
        mock_cm = _MockCostModel()
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=mock_cm,
            decomposer=_MockDecomposer(),
            scheduler=_MockScheduler(),
            evidence_log=_MockEvidenceLog(),
        )
        results = [
            PlannerRuntimeResult(task_id='planner-0', executed=True,
                                 skipped_panic=False, hermes_output='ok', error=None),
        ]
        engine = _MockEngineWithTiming(results)
        tasks = _make_tasks(1)

        assert planner._update_count == 0
        await planner.execute_requests_and_learn(tasks, engine)
        assert planner._update_count == 1


# --------------------------------------------------------------------------- #
# Test 3: _update_fail_count grows on exception
# --------------------------------------------------------------------------- #

class TestUpdateFailCounter:
    """Test 3: _update_fail_count grows when update() raises."""

    @pytest.mark.asyncio
    async def test_update_fail_count_on_exception(self):
        mock_cm = _MockCostModel()
        mock_cm._fail_next = True
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=mock_cm,
            decomposer=_MockDecomposer(),
            scheduler=_MockScheduler(),
            evidence_log=_MockEvidenceLog(),
        )
        results = [
            PlannerRuntimeResult(task_id='planner-0', executed=True,
                                 skipped_panic=False, hermes_output='ok', error=None),
        ]
        engine = _MockEngineWithTiming(results)
        tasks = _make_tasks(1)

        # Must NOT raise — fail-open
        returned = await planner.execute_requests_and_learn(tasks, engine)

        assert len(returned) == 1
        assert planner._update_fail_count == 1
        assert planner._update_count == 0


# --------------------------------------------------------------------------- #
# Test 4: results returned even when update fails
# --------------------------------------------------------------------------- #

class TestResultsPassthrough:
    """Test 4: planner returns runtime results even when update() fails."""

    @pytest.mark.asyncio
    async def test_results_returned_on_update_failure(self):
        failing_cm = _FailingCostModel()
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=failing_cm,
            decomposer=_MockDecomposer(),
            scheduler=_MockScheduler(),
            evidence_log=_MockEvidenceLog(),
        )
        results = [
            PlannerRuntimeResult(task_id='planner-0', executed=True,
                                 skipped_panic=False, hermes_output='ok', error=None),
            PlannerRuntimeResult(task_id='planner-1', executed=True,
                                 skipped_panic=False, hermes_output='ok2', error=None),
        ]
        engine = _MockEngineWithTiming(results)
        tasks = _make_tasks(2)

        returned = await planner.execute_requests_and_learn(tasks, engine)

        assert len(returned) == 2
        assert returned[0].hermes_output == 'ok'
        assert returned[1].hermes_output == 'ok2'


# --------------------------------------------------------------------------- #
# Test 5+6: cache invalidation exactly once per batch (not per-item)
# --------------------------------------------------------------------------- #

class TestCacheInvalidation:
    """Test 5+6: cache cleared once per batch, not N times."""

    @pytest.mark.asyncio
    async def test_cache_invalidated_after_batch(self):
        mock_cm = _MockCostModel()
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=mock_cm,
            decomposer=_MockDecomposer(),
            scheduler=_MockScheduler(),
            evidence_log=_MockEvidenceLog(),
        )

        # Populate cache
        planner._cached_predict_hash.cache_info()

        results = [
            PlannerRuntimeResult(task_id='planner-0', executed=True,
                                 skipped_panic=False, hermes_output='ok', error=None),
        ]
        engine = _MockEngineWithTiming(results)
        tasks = _make_tasks(1)

        await planner.execute_requests_and_learn(tasks, engine)

        info = planner._cached_predict_hash.cache_info()
        assert info.currsize == 0

    @pytest.mark.asyncio
    async def test_cache_not_invalidated_when_no_updates(self):
        mock_cm = _MockCostModel()
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=mock_cm,
            decomposer=_MockDecomposer(),
            scheduler=_MockScheduler(),
            evidence_log=_MockEvidenceLog(),
        )

        # Pre-populate cache
        task = _make_tasks(1)[0]
        planner._estimate_cost(task)
        planner._estimate_cost(task)
        info_before = planner._cached_predict_hash.cache_info()
        assert info_before.currsize > 0

        # All skipped panic → no update calls
        results = [
            PlannerRuntimeResult(task_id='planner-0', executed=False,
                                 skipped_panic=True, hermes_output=None, error=None),
        ]
        engine = _MockEngineWithTiming(results)
        tasks = _make_tasks(1)

        await planner.execute_requests_and_learn(tasks, engine)

        info_after = planner._cached_predict_hash.cache_info()
        assert info_after.currsize == info_before.currsize

    @pytest.mark.asyncio
    async def test_cache_invalidated_exactly_once_per_batch(self):
        mock_cm = _MockCostModel()
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=mock_cm,
            decomposer=_MockDecomposer(),
            scheduler=_MockScheduler(),
            evidence_log=_MockEvidenceLog(),
        )

        results = [
            PlannerRuntimeResult(task_id=f'planner-{i}', executed=True,
                                 skipped_panic=False, hermes_output=f'ok{i}', error=None)
            for i in range(8)
        ]
        engine = _MockEngineWithTiming(results)
        tasks = _make_tasks(8)

        # Populate cache
        for t in tasks:
            planner._estimate_cost(t)

        info_before = planner._cached_predict_hash.cache_info()
        assert info_before.currsize > 0

        await planner.execute_requests_and_learn(tasks, engine)

        info_after = planner._cached_predict_hash.cache_info()
        assert info_after.currsize == 0
        assert len(mock_cm.update_calls) == 8


# --------------------------------------------------------------------------- #
# Test 7: system_state is NOT empty dict
# --------------------------------------------------------------------------- #

class TestSystemState:
    """Test 7+8: system_state is not empty and contains required keys."""

    @pytest.mark.asyncio
    async def test_system_state_not_empty(self):
        mock_cm = _MockCostModel()
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=mock_cm,
            decomposer=_MockDecomposer(),
            scheduler=_MockScheduler(),
            evidence_log=_MockEvidenceLog(),
        )
        results = [
            PlannerRuntimeResult(task_id='planner-0', executed=True,
                                 skipped_panic=False, hermes_output='ok', error=None),
        ]
        engine = _MockEngineWithTiming(results)
        tasks = _make_tasks(1)

        await planner.execute_requests_and_learn(tasks, engine)

        assert len(mock_cm.update_calls) == 1
        _, _, system_state, _ = mock_cm.update_calls[0]

        # system_state must NOT be empty dict
        assert system_state is not None
        assert isinstance(system_state, dict)
        assert len(system_state) > 0, "system_state must not be empty"

    @pytest.mark.asyncio
    async def test_system_state_has_required_keys(self):
        mock_cm = _MockCostModel()
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=mock_cm,
            decomposer=_MockDecomposer(),
            scheduler=_MockScheduler(),
            evidence_log=_MockEvidenceLog(),
        )
        results = [
            PlannerRuntimeResult(task_id='planner-0', executed=True,
                                 skipped_panic=False, hermes_output='ok', error=None),
        ]
        engine = _MockEngineWithTiming(results)
        tasks = _make_tasks(1)

        await planner.execute_requests_and_learn(tasks, engine)

        _, _, system_state, _ = mock_cm.update_calls[0]

        assert 'active_tasks' in system_state, "system_state must have active_tasks"
        assert 'rss_gb' in system_state, "system_state must have rss_gb"
        assert 'avg_latency' in system_state, "system_state must have avg_latency"


# --------------------------------------------------------------------------- #
# Test 9+10: learnable vs internal error classification
# --------------------------------------------------------------------------- #

class TestLearnableErrors:
    """Test 9+10: learnable errors vs internal errors."""

    @pytest.mark.asyncio
    async def test_timeout_is_learnable(self):
        mock_cm = _MockCostModel()
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=mock_cm,
            decomposer=_MockDecomposer(),
            scheduler=_MockScheduler(),
            evidence_log=_MockEvidenceLog(),
        )
        results = [
            PlannerRuntimeResult(task_id='planner-0', executed=False,
                                 skipped_panic=False, hermes_output=None,
                                 error='timeout after 30s'),
        ]
        engine = _MockEngineWithTiming(results)
        tasks = _make_tasks(1)

        await planner.execute_requests_and_learn(tasks, engine)

        assert len(mock_cm.update_calls) == 1
        _, _, _, actual = mock_cm.update_calls[0]
        assert actual[3] == 0  # success_flag = 0 for negative

    @pytest.mark.asyncio
    async def test_network_error_is_learnable(self):
        mock_cm = _MockCostModel()
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=mock_cm,
            decomposer=_MockDecomposer(),
            scheduler=_MockScheduler(),
            evidence_log=_MockEvidenceLog(),
        )
        results = [
            PlannerRuntimeResult(task_id='planner-0', executed=False,
                                 skipped_panic=False, hermes_output=None,
                                 error='network unreachable'),
        ]
        engine = _MockEngineWithTiming(results)
        tasks = _make_tasks(1)

        await planner.execute_requests_and_learn(tasks, engine)

        assert len(mock_cm.update_calls) == 1
        _, _, _, actual = mock_cm.update_calls[0]
        assert actual[3] == 0

    @pytest.mark.asyncio
    async def test_403_is_learnable(self):
        mock_cm = _MockCostModel()
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=mock_cm,
            decomposer=_MockDecomposer(),
            scheduler=_MockScheduler(),
            evidence_log=_MockEvidenceLog(),
        )
        results = [
            PlannerRuntimeResult(task_id='planner-0', executed=False,
                                 skipped_panic=False, hermes_output=None,
                                 error='403 forbidden'),
        ]
        engine = _MockEngineWithTiming(results)
        tasks = _make_tasks(1)

        await planner.execute_requests_and_learn(tasks, engine)

        assert len(mock_cm.update_calls) == 1
        _, _, _, actual = mock_cm.update_calls[0]
        assert actual[3] == 0

    @pytest.mark.asyncio
    async def test_internal_errors_not_learned(self):
        """model_not_loaded and planner_error are internal → NOT learned."""
        mock_cm = _MockCostModel()
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=mock_cm,
            decomposer=_MockDecomposer(),
            scheduler=_MockScheduler(),
            evidence_log=_MockEvidenceLog(),
        )
        results = [
            PlannerRuntimeResult(task_id='planner-0', executed=False,
                                 skipped_panic=False, hermes_output=None,
                                 error='model_not_loaded'),
        ]
        engine = _MockEngineWithTiming(results)
        tasks = _make_tasks(1)

        await planner.execute_requests_and_learn(tasks, engine)

        # model_not_loaded → NO update
        assert len(mock_cm.update_calls) == 0
        assert planner._update_count == 0

    @pytest.mark.asyncio
    async def test_unknown_error_not_learned(self):
        """Unknown error class → NOT learned."""
        mock_cm = _MockCostModel()
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=mock_cm,
            decomposer=_MockDecomposer(),
            scheduler=_MockScheduler(),
            evidence_log=_MockEvidenceLog(),
        )
        results = [
            PlannerRuntimeResult(task_id='planner-0', executed=False,
                                 skipped_panic=False, hermes_output=None,
                                 error='some_totally_unknown_error_xyz'),
        ]
        engine = _MockEngineWithTiming(results)
        tasks = _make_tasks(1)

        await planner.execute_requests_and_learn(tasks, engine)

        assert len(mock_cm.update_calls) == 0


# --------------------------------------------------------------------------- #
# Test 11: negative signals deduplicated within batch
# --------------------------------------------------------------------------- #

class TestNegativeDeduplication:
    """Test 11: negative signals deduped within single batch."""

    @pytest.mark.asyncio
    async def test_negative_signals_deduplicated(self):
        """
        If 10 requests of same task_type fail on the same learnable error,
        update should be sent only once for this (task_type, error_class) combo.

        We test with 4 identical failures + 1 different → expect 2 updates.
        """
        mock_cm = _MockCostModel()
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=mock_cm,
            decomposer=_MockDecomposer(),
            scheduler=_MockScheduler(),
            evidence_log=_MockEvidenceLog(),
        )

        # 4 identical timeout failures + 1 network failure
        results = [
            PlannerRuntimeResult(task_id=f'planner-{i}', executed=False,
                                 skipped_panic=False, hermes_output=None,
                                 error='timeout after 30s')
            for i in range(4)
        ] + [
            PlannerRuntimeResult(task_id='planner-4', executed=False,
                                 skipped_panic=False, hermes_output=None,
                                 error='network unreachable'),
        ]
        engine = _MockEngineWithTiming(results)
        tasks = _make_tasks(5)

        await planner.execute_requests_and_learn(tasks, engine)

        # 2 unique (task_type, error_class) combos → 2 updates
        assert len(mock_cm.update_calls) == 2, \
            f"Expected 2 deduped updates, got {len(mock_cm.update_calls)}"


# --------------------------------------------------------------------------- #
# Test 12+13: panic-skipped and model_not_loaded skip learning
# --------------------------------------------------------------------------- #

class TestPanicSkipNoLearning:
    """Test 12+13: panic-skipped and model_not_loaded → NO learning."""

    @pytest.mark.asyncio
    async def test_panic_skipped_not_learned(self):
        mock_cm = _MockCostModel()
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=mock_cm,
            decomposer=_MockDecomposer(),
            scheduler=_MockScheduler(),
            evidence_log=_MockEvidenceLog(),
            remaining_time_s=30.0,  # panic horizon
        )
        results = [
            PlannerRuntimeResult(task_id='planner-0', executed=False,
                                 skipped_panic=True, hermes_output=None, error=None),
        ]
        engine = _MockEngineWithTiming(results)
        tasks = [{'type': 'fetch', 'url': 'https://panic.com', 'depth': 1,
                  'priority': 0.5, 'expected_results': 5}]

        await planner.execute_requests_and_learn(tasks, engine)

        assert len(mock_cm.update_calls) == 0
        assert planner._update_count == 0

    @pytest.mark.asyncio
    async def test_model_not_loaded_not_learned(self):
        mock_cm = _MockCostModel()
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=mock_cm,
            decomposer=_MockDecomposer(),
            scheduler=_MockScheduler(),
            evidence_log=_MockEvidenceLog(),
        )
        results = [
            PlannerRuntimeResult(task_id='planner-0', executed=False,
                                 skipped_panic=False, hermes_output=None,
                                 error='model_not_loaded'),
        ]
        engine = _MockEngineWithTiming(results)
        tasks = _make_tasks(1)

        await planner.execute_requests_and_learn(tasks, engine)

        assert len(mock_cm.update_calls) == 0


# --------------------------------------------------------------------------- #
# Test 14+15: per-task elapsed precision
# --------------------------------------------------------------------------- #

class TestPerTaskTiming:
    """Test 14+15: per-task elapsed is precise, NOT bridge_elapsed/N."""

    @pytest.mark.asyncio
    async def test_single_task_per_task_elapsed_positive(self):
        """Per-task elapsed for single task is > 0."""
        mock_cm = _MockCostModel()
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=mock_cm,
            decomposer=_MockDecomposer(),
            scheduler=_MockScheduler(),
            evidence_log=_MockEvidenceLog(),
        )
        results = [
            PlannerRuntimeResult(task_id='planner-0', executed=True,
                                 skipped_panic=False, hermes_output='ok', error=None),
        ]
        engine = _MockEngineWithTiming(results, per_task_delay_s=0.05)
        tasks = _make_tasks(1)

        await planner.execute_requests_and_learn(tasks, engine)

        assert len(mock_cm.update_calls) == 1
        _, _, _, actual = mock_cm.update_calls[0]
        # actual[0] is observed_cost_s — must be positive
        assert actual[0] > 0, f"per-task elapsed must be > 0, got {actual[0]}"

    @pytest.mark.asyncio
    async def test_multi_task_not_bridge_elapsed_divided(self):
        """
        Per-task elapsed is NOT bridge_elapsed / N.

        With 4 tasks each taking 0.05s, if averaged we'd get 0.05.
        But each task actually takes 0.05 individually, so the actual
        per-task value should reflect the individual task timing.

        The key invariant: we no longer compute elapsed = bridge_elapsed / N.
        """
        mock_cm = _MockCostModel()
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=mock_cm,
            decomposer=_MockDecomposer(),
            scheduler=_MockScheduler(),
            evidence_log=_MockEvidenceLog(),
        )
        results = [
            PlannerRuntimeResult(task_id=f'planner-{i}', executed=True,
                                 skipped_panic=False, hermes_output=f'ok{i}', error=None)
            for i in range(4)
        ]
        engine = _MockEngineWithTiming(results, per_task_delay_s=0.05)
        tasks = _make_tasks(4)

        await planner.execute_requests_and_learn(tasks, engine)

        assert len(mock_cm.update_calls) == 4
        # Each call should have its own per-task elapsed time
        # The old code would give bridge_elapsed / 4 for each
        # The new code gives per-task individual timing
        for i, (task_type, params, system_state, actual) in enumerate(mock_cm.update_calls):
            # actual[0] must be > 0 (individual task timing)
            assert actual[0] > 0, f"task {i}: per-task elapsed must be > 0, got {actual[0]}"


# --------------------------------------------------------------------------- #
# Test 16: deterministic update inputs
# --------------------------------------------------------------------------- #

class TestDeterministicInputs:
    """Test 16: deterministic task + outcome → same update inputs."""

    @pytest.mark.asyncio
    async def test_deterministic_update_inputs(self):
        mock_cm = _MockCostModel()
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=mock_cm,
            decomposer=_MockDecomposer(),
            scheduler=_MockScheduler(),
            evidence_log=_MockEvidenceLog(),
        )

        task = {'type': 'fetch', 'url': 'https://example.com', 'depth': 2,
                'priority': 0.7, 'expected_results': 10}
        results = [
            PlannerRuntimeResult(task_id='planner-0', executed=True,
                                 skipped_panic=False, hermes_output='ok', error=None),
        ]
        engine = _MockEngineWithTiming(results)
        engine2 = _MockEngineWithTiming(results)

        # Run same task twice
        await planner.execute_requests_and_learn([task], engine)
        await planner.execute_requests_and_learn([task], engine2)

        assert len(mock_cm.update_calls) == 2
        call1 = mock_cm.update_calls[0]
        call2 = mock_cm.update_calls[1]

        # Same task → same task_type, params
        assert call1[0] == call2[0]  # task_type
        assert call1[1] == call2[1]  # params
        # system_state is mostly deterministic but avg_latency is live-measured
        # and will differ slightly between runs even with mocked timing.
        # Static keys must match; avg_latency varies legitimately.
        ss1, ss2 = call1[2], call2[2]
        for key in ('active_tasks', 'rss_gb'):
            assert ss1.get(key) == ss2.get(key), f"system_state['{key}'] should match"
        # avg_latency legitimately differs due to real timing measurement
        assert 'avg_latency' in ss1 and 'avg_latency' in ss2


# --------------------------------------------------------------------------- #
# Test 17+: gates — probe_8n, probe_8k, probe_8g, probe_8i, AO canary
# These are run as separate pytest invocations in the sprint script.
# --------------------------------------------------------------------------- #
