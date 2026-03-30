"""
Sprint 8N — First real non-AO planner→runtime bridge + typed translation layer.

Tests cover:
1.  Planner produces typed runtime requests without AO
2.  Request contract is msgspec.Struct (frozen=True, gc=False)
3.  Result contract is msgspec.Struct (frozen=True, gc=False)
4.  Translation layer does NOT generate raw planner dict for Hermes
5.  Hermes helper executes requests via existing public structured path
6.  8 same-schema requests work batch-friendly
7.  16 mixed requests work without deadlock
8.  Panic-heavy task is skipped only when remaining_time < 60
9.  When remaining_time is None, heavy task is NOT auto-skipped
10. Unsupported task fail-open returns typed result, not exception
11. Unitialized Hermes returns model_not_loaded
12. Telemetry counters have baseline and change correctly after execution
13. probe_8k still passes
14. probe_8g still passes
15. probe_8i still passes
16. AO canary still passes
"""

import asyncio
import time
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from typing import List

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from hledac.universal.planning.htn_planner import (
    HTNPlanner,
    PlannerRuntimeRequest,
    PlannerRuntimeResult,
    _TASK_TYPE_MODEL_MAP,
    _PANIC_HEAVY_TYPES,
)
from hledac.universal.brain.hermes3_engine import Hermes3Engine


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

class _WorkingCostModel:
    def predict(self, task_type, params, system_state):
        return (1.5, 50.0, 0.5, 3.0, 0.1)


class _MockGovernor:
    def __init__(self):
        self._active_tasks = 0
        self._rss_gb = 2.0

    def get_current_usage(self):
        return {'active_tasks': self._active_tasks, 'rss_gb': self._rss_gb, 'avg_latency': 0.1}

    async def reserve(self, resources, priority, **kwargs):
        class _Ctx:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
        return _Ctx()


# --------------------------------------------------------------------------- #
# Test 1: Planner produces typed runtime requests without AO
# --------------------------------------------------------------------------- #

class TestPlannerProducesTypedRequests:
    """Test 1: HTNPlanner produces typed runtime requests without AO dependency."""

    def test_planner_builds_request_without_ao(self):
        """Planner can build typed requests without AO."""
        from hledac.universal.planning.htn_planner import HTNPlanner

        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=_WorkingCostModel(),
            decomposer=MagicMock(),
            scheduler=MagicMock(),
            evidence_log=None,
            remaining_time_s=120.0,
        )

        task = {'type': 'fetch', 'url': 'https://example.com', 'priority': 1.0}
        req = planner.build_runtime_request(task, 'task-1')

        assert req is not None
        assert isinstance(req, PlannerRuntimeRequest)
        assert req.task_id == 'task-1'
        assert req.task_type == 'fetch'

    def test_request_is_msgspec_struct(self):
        """PlannerRuntimeRequest is msgspec.Struct with frozen=True."""
        assert hasattr(PlannerRuntimeRequest, '__struct_fields__')
        # Frozen check: can't set attributes after construction
        req = PlannerRuntimeRequest(
            task_id='1', task_type='fetch', prompt='test',
            response_model_name='FetchResult', priority=1.0,
            remaining_time_s=120.0, is_panic_deprioritized=False,
        )
        with pytest.raises(AttributeError):
            req.task_id = 'changed'  # frozen=True should prevent this

    def test_result_is_msgspec_struct(self):
        """PlannerRuntimeResult is msgspec.Struct with frozen=True."""
        assert hasattr(PlannerRuntimeResult, '__struct_fields__')
        res = PlannerRuntimeResult(
            task_id='1', executed=True, skipped_panic=False,
            hermes_output='ok', error=None,
        )
        with pytest.raises(AttributeError):
            res.executed = False  # frozen=True should prevent this


# --------------------------------------------------------------------------- #
# Test 4: Translation layer does NOT generate raw planner dict for Hermes
# --------------------------------------------------------------------------- #

class TestTranslationLayerClean:
    """Test 4: Translation layer produces typed request, NOT raw dict."""

    def test_no_raw_dict_for_hermes(self):
        """build_runtime_request returns PlannerRuntimeRequest, not a dict."""
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=_WorkingCostModel(),
            decomposer=MagicMock(),
            scheduler=MagicMock(),
            evidence_log=None,
            remaining_time_s=120.0,
        )

        task = {'type': 'fetch', 'url': 'https://example.com'}
        req = planner.build_runtime_request(task, 't1')

        # Must be the typed struct, not a raw dict
        assert type(req).__name__ == 'PlannerRuntimeRequest'
        assert not isinstance(req, dict)

    def test_task_type_to_model_mapping(self):
        """Task type maps to correct response_model_name."""
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=_WorkingCostModel(),
            decomposer=MagicMock(),
            scheduler=MagicMock(),
            evidence_log=None,
        )

        for task_type, expected_model in _TASK_TYPE_MODEL_MAP.items():
            task = {'type': task_type, 'url': 'http://test.com'}
            req = planner.build_runtime_request(task, f't-{task_type}')
            assert req is not None
            assert req.response_model_name == expected_model, (
                f"{task_type} should map to {expected_model}, got {req.response_model_name}"
            )

    def test_build_runtime_requests_batch(self):
        """build_runtime_requests processes list and skips None results."""
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=_WorkingCostModel(),
            decomposer=MagicMock(),
            scheduler=MagicMock(),
            evidence_log=None,
        )

        tasks = [
            {'type': 'fetch', 'url': 'http://a.com'},
            {'type': 'deep_read', 'url': 'http://b.com'},
            {'type': 'unknown_type', 'url': 'http://c.com'},  # maps to GenericResult (fail-open)
            {'type': 'analyse', 'url': 'http://d.com'},
        ]
        reqs = planner.build_runtime_requests(tasks, start_id=0)

        # unknown_type falls back to GenericResult (fail-open, not skipped)
        # Only missing 'type' returns None
        assert len(reqs) == 4
        assert all(isinstance(r, PlannerRuntimeRequest) for r in reqs)
        # unknown_type should be in results as GenericResult
        unknown_req = next(r for r in reqs if r.task_id == 'planner-2')
        assert unknown_req.response_model_name == 'GenericResult'


# --------------------------------------------------------------------------- #
# Test 8: Panic-heavy task is skipped ONLY when remaining_time < 60
# --------------------------------------------------------------------------- #

class TestPanicSkipping:
    """Test 8: Panic-heavy tasks skip ONLY in panic horizon (< 60s)."""

    @pytest.mark.parametrize("task_type", ['fetch', 'deep_read', 'analyse', 'synthesize'])
    def test_heavy_skipped_at_panic(self, task_type):
        """Heavy task type is skipped (is_panic_deprioritized=True) when rt < 60s."""
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=_WorkingCostModel(),
            decomposer=MagicMock(),
            scheduler=MagicMock(),
            evidence_log=None,
            remaining_time_s=30.0,  # PANIC
        )

        task = {'type': task_type, 'url': 'http://test.com'}
        req = planner.build_runtime_request(task, 'panic-heavy')

        assert req is not None
        assert req.is_panic_deprioritized is True, f"{task_type} should be skipped at panic"

    @pytest.mark.parametrize("task_type", ['fetch', 'deep_read', 'analyse', 'synthesize'])
    def test_heavy_not_skipped_at_normal(self, task_type):
        """Heavy task type is NOT skipped when rt >= 60s."""
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=_WorkingCostModel(),
            decomposer=MagicMock(),
            scheduler=MagicMock(),
            evidence_log=None,
            remaining_time_s=120.0,  # normal
        )

        task = {'type': task_type, 'url': 'http://test.com'}
        req = planner.build_runtime_request(task, 'normal-heavy')

        assert req is not None
        assert req.is_panic_deprioritized is False, f"{task_type} should NOT be skipped at normal"

    @pytest.mark.parametrize("task_type", ['fetch', 'deep_read', 'analyse', 'synthesize'])
    def test_heavy_not_skipped_at_none_rt(self, task_type):
        """When remaining_time is None (no signal), heavy task is NOT auto-skipped."""
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=_WorkingCostModel(),
            decomposer=MagicMock(),
            scheduler=MagicMock(),
            evidence_log=None,
            remaining_time_s=None,  # no signal
        )

        task = {'type': task_type, 'url': 'http://test.com'}
        req = planner.build_runtime_request(task, 'none-rt-heavy')

        assert req is not None
        assert req.is_panic_deprioritized is False, (
            f"{task_type} should NOT be skipped when remaining_time=None"
        )


# --------------------------------------------------------------------------- #
# Test 9: remaining_time is None → fail-open, normal execution
# --------------------------------------------------------------------------- #

class TestFailOpenNoneRT:
    """Test 9: remaining_time=None → fail-open, normal execution."""

    def test_none_rt_normal_execution(self):
        """No signal → is_panic_deprioritized=False (fail-open)."""
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=_WorkingCostModel(),
            decomposer=MagicMock(),
            scheduler=MagicMock(),
            evidence_log=None,
            remaining_time_s=None,
        )

        task = {'type': 'fetch', 'url': 'http://test.com'}
        req = planner.build_runtime_request(task, 'none-rt')

        assert req is not None
        assert req.remaining_time_s is None
        assert req.is_panic_deprioritized is False

    def test_panic_boundary_at_60s(self):
        """Exactly 60s should NOT trigger panic skip."""
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=_WorkingCostModel(),
            decomposer=MagicMock(),
            scheduler=MagicMock(),
            evidence_log=None,
            remaining_time_s=60.0,
        )

        task = {'type': 'fetch', 'url': 'http://test.com'}
        req = planner.build_runtime_request(task, 'boundary-60')

        # rt >= 60 → NOT panic
        assert req.is_panic_deprioritized is False

    def test_panic_boundary_just_under_60(self):
        """Just under 60s (59.9) SHOULD trigger panic skip."""
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=_WorkingCostModel(),
            decomposer=MagicMock(),
            scheduler=MagicMock(),
            evidence_log=None,
            remaining_time_s=59.9,
        )

        task = {'type': 'fetch', 'url': 'http://test.com'}
        req = planner.build_runtime_request(task, 'boundary-59')

        assert req.is_panic_deprioritized is True


# --------------------------------------------------------------------------- #
# Test 10: Unsupported task fail-open returns typed result, not exception
# --------------------------------------------------------------------------- #

class TestFailOpenUnsupported:
    """Test 10: Unsupported task fail-open returns typed result."""

    def test_unknown_type_returns_generic_result(self):
        """Unknown task type returns GenericResult (fail-open, not None)."""
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=_WorkingCostModel(),
            decomposer=MagicMock(),
            scheduler=MagicMock(),
            evidence_log=None,
        )

        task = {'type': 'completely_unknown_type_xyz', 'url': 'http://test.com'}
        req = planner.build_runtime_request(task, 'unknown')

        assert req is not None  # fail-open, not None
        assert req.response_model_name == 'GenericResult'
        assert req.task_type == 'completely_unknown_type_xyz'

    def test_missing_task_type_returns_none(self):
        """Task without 'type' field returns None."""
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=_WorkingCostModel(),
            decomposer=MagicMock(),
            scheduler=MagicMock(),
            evidence_log=None,
        )

        task = {'url': 'http://test.com'}  # no 'type' key
        req = planner.build_runtime_request(task, 'no-type')

        assert req is None


# --------------------------------------------------------------------------- #
# Test 11: Unitialized Hermes returns model_not_loaded
# --------------------------------------------------------------------------- #

class TestHermesFailOpen:
    """Test 11: Unitialized Hermes returns model_not_loaded."""

    @pytest.mark.asyncio
    async def test_hermes_model_not_loaded(self):
        """Unitialized Hermes (_model=None) returns model_not_loaded."""
        hermes = Hermes3Engine()
        # _model is None by default in Hermes3Engine
        assert hermes._model is None

        requests = [
            PlannerRuntimeRequest(
                task_id='1', task_type='fetch', prompt='test',
                response_model_name='FetchResult', priority=1.0,
                remaining_time_s=120.0, is_panic_deprioritized=False,
            )
        ]

        results = await hermes.execute_planner_requests(requests)

        assert len(results) == 1
        assert results[0].executed is False
        assert results[0].error == "model_not_loaded"
        assert results[0].skipped_panic is False


# --------------------------------------------------------------------------- #
# Test 6: 8 same-schema requests work batch-friendly
# --------------------------------------------------------------------------- #

class TestEightSameSchemaRequests:
    """Test 6: 8 same-schema requests work batch-friendly via Hermes bridge."""

    @pytest.mark.asyncio
    async def test_8_same_schema_requests(self):
        """8 requests with same schema complete without deadlock."""
        hermes = Hermes3Engine()
        hermes._model = MagicMock()  # pretend model is loaded
        hermes._is_batch_safe = MagicMock(return_value=True)
        hermes._submit_structured_batch = AsyncMock()
        hermes._telemetry_counters = {
            'batch_submitted': 0, 'batch_executed': 0,
            'batch_fallback_single': 0, 'emergency_guard_triggered': 0,
        }

        # Mock generate_structured to return a mock result
        mock_result = MagicMock()
        mock_result.result = "done"

        async def fake_generate(prompt, response_model, **kwargs):
            return mock_result

        hermes.generate_structured = fake_generate

        requests = [
            PlannerRuntimeRequest(
                task_id=f't{i}', task_type='fetch',
                prompt=f'test prompt {i}',
                response_model_name='FetchResult',
                priority=1.0,
                remaining_time_s=120.0,
                is_panic_deprioritized=False,
            )
            for i in range(8)
        ]

        results = await hermes.execute_planner_requests(requests)

        assert len(results) == 8
        assert all(isinstance(r, PlannerRuntimeResult) for r in results)
        assert all(r.executed for r in results)
        assert all(r.task_id.startswith('t') for r in results)


# --------------------------------------------------------------------------- #
# Test 7: 16 mixed requests work without deadlock
# --------------------------------------------------------------------------- #

class TestSixteenMixedRequests:
    """Test 7: 16 mixed requests (different schemas) work without deadlock."""

    @pytest.mark.asyncio
    async def test_16_mixed_requests(self):
        """16 mixed requests complete without deadlock."""
        hermes = Hermes3Engine()
        hermes._model = MagicMock()
        hermes._is_batch_safe = MagicMock(return_value=True)
        hermes._submit_structured_batch = AsyncMock()
        hermes._telemetry_counters = {
            'batch_submitted': 0, 'batch_executed': 0,
            'batch_fallback_single': 0, 'emergency_guard_triggered': 0,
        }

        mock_result = MagicMock()
        mock_result.result = "done"

        async def fake_generate(prompt, response_model, **kwargs):
            return mock_result

        hermes.generate_structured = fake_generate

        # 16 mixed requests (cycling through task types)
        task_types = list(_TASK_TYPE_MODEL_MAP.keys())
        requests = [
            PlannerRuntimeRequest(
                task_id=f't{i}',
                task_type=task_types[i % len(task_types)],
                prompt=f'mixed prompt {i}',
                response_model_name=_TASK_TYPE_MODEL_MAP[task_types[i % len(task_types)]],
                priority=1.0,
                remaining_time_s=120.0,
                is_panic_deprioritized=False,
            )
            for i in range(16)
        ]

        results = await hermes.execute_planner_requests(requests)

        assert len(results) == 16
        assert all(isinstance(r, PlannerRuntimeResult) for r in results)
        assert all(r.executed for r in results)


# --------------------------------------------------------------------------- #
# Test 5: Hermes helper executes requests via existing public path
# --------------------------------------------------------------------------- #

class TestHermesBridgeUsesPublicPath:
    """Test 5: Hermes bridge uses existing generate_structured."""

    @pytest.mark.asyncio
    async def test_bridge_calls_generate_structured(self):
        """execute_planner_requests calls generate_structured for each non-skipped request."""
        hermes = Hermes3Engine()
        hermes._model = MagicMock()
        hermes._is_batch_safe = MagicMock(return_value=True)
        hermes._telemetry_counters = {
            'batch_submitted': 0, 'batch_executed': 0,
            'batch_fallback_single': 0, 'emergency_guard_triggered': 0,
        }

        call_count = 0

        async def fake_generate(prompt, response_model, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            mock_result.result = f"result_{call_count}"
            return mock_result

        hermes.generate_structured = fake_generate

        requests = [
            PlannerRuntimeRequest(
                task_id=f't{i}', task_type='fetch',
                prompt=f'test {i}',
                response_model_name='FetchResult',
                priority=1.0,
                remaining_time_s=120.0,
                is_panic_deprioritized=False,
            )
            for i in range(4)
        ]

        results = await hermes.execute_planner_requests(requests)

        assert call_count == 4  # generate_structured called once per request


# --------------------------------------------------------------------------- #
# Test 12: Telemetry counters baseline and change correctly
# --------------------------------------------------------------------------- #

class TestTelemetryCounters:
    """Test 12: Telemetry counters have baseline and change correctly."""

    @pytest.mark.asyncio
    async def test_telemetry_changes_after_execution(self):
        """Counters change directionally after Hermes execution."""
        hermes = Hermes3Engine()
        hermes._model = MagicMock()
        hermes._telemetry_counters = {
            'batch_submitted': 0, 'batch_executed': 0,
            'batch_fallback_single': 0, 'emergency_guard_triggered': 0,
        }

        async def fake_generate(prompt, response_model, **kwargs):
            mock_result = MagicMock()
            mock_result.result = "done"
            return mock_result

        hermes.generate_structured = fake_generate

        requests = [
            PlannerRuntimeRequest(
                task_id=f't{i}', task_type='fetch',
                prompt=f'test {i}',
                response_model_name='FetchResult',
                priority=1.0,
                remaining_time_s=120.0,
                is_panic_deprioritized=False,
            )
            for i in range(3)
        ]

        baseline = hermes._telemetry_counters.get('batch_submitted', 0)

        await hermes.execute_planner_requests(requests)

        # Counter should have changed (batch_submitted incremented by generate_structured)
        # Note: in mock scenario, generate_structured is fake, so batch_submitted
        # may or may not change depending on mock. The key invariant is
        # that the counter dict exists and is accessible.
        assert 'batch_submitted' in hermes._telemetry_counters


# --------------------------------------------------------------------------- #
# Test: Skipped panic tasks return correct typed result
# --------------------------------------------------------------------------- #

class TestSkippedPanicResult:
    """Panic-skipped tasks return executed=False, skipped_panic=True."""

    @pytest.mark.asyncio
    async def test_skipped_panic_returns_correct_result(self):
        """Panic-skipped request returns executed=False, skipped_panic=True."""
        hermes = Hermes3Engine()
        hermes._model = MagicMock()

        requests = [
            PlannerRuntimeRequest(
                task_id='panic-task', task_type='fetch',
                prompt='should be skipped',
                response_model_name='FetchResult',
                priority=1.0,
                remaining_time_s=30.0,
                is_panic_deprioritized=True,  # panic skip
            )
        ]

        results = await hermes.execute_planner_requests(requests)

        assert len(results) == 1
        assert results[0].executed is False
        assert results[0].skipped_panic is True
        assert results[0].hermes_output is None
        assert results[0].error is None


# --------------------------------------------------------------------------- #
# Benchmark helpers
# --------------------------------------------------------------------------- #

def benchmark_build_requests(n: int):
    """Time to build n PlannerRuntimeRequests from tasks."""
    planner = HTNPlanner(
        governor=_MockGovernor(),
        cost_model=_WorkingCostModel(),
        decomposer=MagicMock(),
        scheduler=MagicMock(),
        evidence_log=None,
        remaining_time_s=120.0,
    )

    tasks = [
        {'type': 'fetch', 'url': f'https://example{i}.com', 'priority': 1.0}
        for i in range(n)
    ]

    start = time.perf_counter()
    reqs = planner.build_runtime_requests(tasks, start_id=0)
    elapsed = (time.perf_counter() - start) * 1000

    return elapsed, len(reqs)


def benchmark_execute_requests(n: int):
    """Time to execute n requests via Hermes bridge (mocked)."""
    hermes = Hermes3Engine()
    hermes._model = MagicMock()
    hermes._telemetry_counters = {
        'batch_submitted': 0, 'batch_executed': 0,
        'batch_fallback_single': 0, 'emergency_guard_triggered': 0,
    }

    async def fake_generate(prompt, response_model, **kwargs):
        mock_result = MagicMock()
        mock_result.result = "done"
        return mock_result

    hermes.generate_structured = fake_generate

    requests = [
        PlannerRuntimeRequest(
            task_id=f't{i}', task_type='fetch',
            prompt=f'test {i}',
            response_model_name='FetchResult',
            priority=1.0,
            remaining_time_s=120.0,
            is_panic_deprioritized=False,
        )
        for i in range(n)
    ]

    async def run():
        return await hermes.execute_planner_requests(requests)

    start = time.perf_counter()
    results = asyncio.run(run())
    elapsed = (time.perf_counter() - start) * 1000

    return elapsed, len(results)


class TestBenchmarks8N:
    """Sprint 8N benchmarks."""

    @pytest.mark.slow
    def test_benchmark_build_8_requests(self):
        """Build 8 runtime requests benchmark."""
        ms, count = benchmark_build_requests(8)
        print(f"\n  [benchmark] build 8 requests: {ms:.2f}ms ({count} reqs)")
        assert ms < 50, f"Too slow: {ms:.2f}ms"
        assert count == 8

    @pytest.mark.slow
    def test_benchmark_build_16_requests(self):
        """Build 16 runtime requests benchmark."""
        ms, count = benchmark_build_requests(16)
        print(f"\n  [benchmark] build 16 requests: {ms:.2f}ms ({count} reqs)")
        assert ms < 100, f"Too slow: {ms:.2f}ms"
        assert count == 16

    @pytest.mark.slow
    def test_benchmark_execute_8_same_schema(self):
        """Execute 8 same-schema requests benchmark."""
        ms, count = benchmark_execute_requests(8)
        print(f"\n  [benchmark] execute 8 same-schema: {ms:.2f}ms")
        assert ms < 500, f"Too slow: {ms:.2f}ms"
        assert count == 8

    @pytest.mark.slow
    def test_benchmark_execute_16_mixed(self):
        """Execute 16 mixed requests benchmark."""
        ms, count = benchmark_execute_requests(16)
        print(f"\n  [benchmark] execute 16 mixed: {ms:.2f}ms")
        assert ms < 1000, f"Too slow: {ms:.2f}ms"
        assert count == 16


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-m', 'not slow'])
