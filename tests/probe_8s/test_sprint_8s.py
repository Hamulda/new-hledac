"""
Sprint 8S: First full non-AO planner → runtime → CanonicalFinding → storage loop.

Tests cover:
- Successful executed result → CanonicalFinding created
- skipped_panic → finding NOT created
- error result → finding NOT created
- model_not_loaded → finding NOT created
- query maps from request.prompt[:256], NOT from hermes_output
- payload_text maps from hermes_output
- provenance is a non-None tuple
- source_type == "planner_bridge"
- source_type and provenance strings are interned
- ts is float and corresponds to "now"
- store=None → method still works
- store.startup_ready=False → storage skipped, _storage_skipped_count grows
- storage fail does NOT stop runtime results
- storage fail does NOT stop learning update
- _stored_finding_count grows on success
- _storage_fail_count grows on storage exception
- _storage_skipped_count grows on skip scenarios
- batch API is called when available
- batch API failure → fail-open preserved
- len(storage_results) == len(findings) for batch and fallback
- probe_8q still passes
- probe_8r still passes
- probe_8n still passes
- probe_8k still passes
- probe_8g still passes
- probe_8i still passes
- AO canary still passes
"""

import asyncio
import sys
import time
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from hledac.universal.planning.htn_planner import (
    HTNPlanner,
    PlannerRuntimeRequest,
    PlannerRuntimeResult,
)


# ---------------------------------------------------------------------------
# Mock components
# ---------------------------------------------------------------------------

class _MockGovernor:
    async def reserve(self, *args, **kwargs):
        class _R:
            async def __aenter__(self): pass
            async def __aexit__(self, *args): pass
        return _R()


class _MockCostModel:
    async def update(self, *args, **kwargs):
        pass


class _MockDecomposer:
    async def decompose(self, *args, **kwargs):
        return []


class _MockScheduler:
    pass


class _MockEvidenceLog:
    pass


# ---------------------------------------------------------------------------
# Mock Hermes engine
# ---------------------------------------------------------------------------

def _make_engine(results: list):
    """Create a mock engine that returns the given results from execute_planner_requests."""
    engine = MagicMock()
    engine.execute_planner_requests = AsyncMock(return_value=results)
    return engine


# ---------------------------------------------------------------------------
# Tests: _runtime_result_to_canonical_finding mapping
# ---------------------------------------------------------------------------

class TestFindingMapping:
    """Tests B.5, B.6, B.7, B.8, B.10, B.11, B.12, B.13, B.14, B.15, B.16"""

    @pytest.fixture
    def planner(self):
        return HTNPlanner(
            governor=_MockGovernor(),
            cost_model=_MockCostModel(),
            decomposer=_MockDecomposer(),
            scheduler=_MockScheduler(),
            evidence_log=_MockEvidenceLog(),
        )

    def test_successful_result_creates_finding(self, planner):
        """B.1: successful executed result -> CanonicalFinding created."""
        request = PlannerRuntimeRequest(
            task_id="t-001",
            task_type="fetch",
            prompt="Who owns example.com?",
            response_model_name="FetchResult",
            priority=0.5,
            remaining_time_s=300.0,
            is_panic_deprioritized=False,
        )
        result = PlannerRuntimeResult(
            task_id="t-001",
            executed=True,
            skipped_panic=False,
            hermes_output="Example.com is owned by Example Inc.",
            error=None,
        )
        finding = planner._runtime_result_to_canonical_finding(request, result)
        assert finding is not None
        assert finding.finding_id == "t-001"

    def test_skipped_panic_no_finding(self, planner):
        """B.2: skipped_panic -> finding NOT created."""
        request = PlannerRuntimeRequest(
            task_id="t-002",
            task_type="fetch",
            prompt="query",
            response_model_name="FetchResult",
            priority=0.5,
            remaining_time_s=300.0,
            is_panic_deprioritized=False,
        )
        result = PlannerRuntimeResult(
            task_id="t-002",
            executed=False,
            skipped_panic=True,
            hermes_output=None,
            error="panic_skip",
        )
        finding = planner._runtime_result_to_canonical_finding(request, result)
        assert finding is None

    def test_error_result_no_finding(self, planner):
        """B.3: error result -> finding NOT created."""
        request = PlannerRuntimeRequest(
            task_id="t-003",
            task_type="fetch",
            prompt="query",
            response_model_name="FetchResult",
            priority=0.5,
            remaining_time_s=300.0,
            is_panic_deprioritized=False,
        )
        result = PlannerRuntimeResult(
            task_id="t-003",
            executed=False,
            skipped_panic=False,
            hermes_output=None,
            error="timeout",
        )
        finding = planner._runtime_result_to_canonical_finding(request, result)
        assert finding is None

    def test_model_not_loaded_no_finding(self, planner):
        """B.4: model_not_loaded -> finding NOT created."""
        request = PlannerRuntimeRequest(
            task_id="t-004",
            task_type="fetch",
            prompt="query",
            response_model_name="FetchResult",
            priority=0.5,
            remaining_time_s=300.0,
            is_panic_deprioritized=False,
        )
        result = PlannerRuntimeResult(
            task_id="t-004",
            executed=False,
            skipped_panic=False,
            hermes_output=None,
            error="model_not_loaded",
        )
        finding = planner._runtime_result_to_canonical_finding(request, result)
        assert finding is None

    def test_query_from_request_prompt(self, planner):
        """B.5: query maps from request.prompt[:256], NOT hermes_output."""
        long_prompt = "A" * 500
        request = PlannerRuntimeRequest(
            task_id="t-005",
            task_type="fetch",
            prompt=long_prompt,
            response_model_name="FetchResult",
            priority=0.5,
            remaining_time_s=300.0,
            is_panic_deprioritized=False,
        )
        result = PlannerRuntimeResult(
            task_id="t-005",
            executed=True,
            skipped_panic=False,
            hermes_output="hermes output text",
            error=None,
        )
        finding = planner._runtime_result_to_canonical_finding(request, result)
        assert finding is not None
        assert finding.query == long_prompt[:256]
        assert len(finding.query) == 256
        # Verify it is from prompt, NOT hermes_output
        assert finding.query != "hermes output text"

    def test_payload_text_from_hermes_output(self, planner):
        """B.6: payload_text maps from hermes_output."""
        request = PlannerRuntimeRequest(
            task_id="t-006",
            task_type="fetch",
            prompt="query",
            response_model_name="FetchResult",
            priority=0.5,
            remaining_time_s=300.0,
            is_panic_deprioritized=False,
        )
        result = PlannerRuntimeResult(
            task_id="t-006",
            executed=True,
            skipped_panic=False,
            hermes_output="actual output from Hermes",
            error=None,
        )
        finding = planner._runtime_result_to_canonical_finding(request, result)
        assert finding is not None
        assert finding.payload_text == "actual output from Hermes"

    def test_provenance_is_tuple_not_none(self, planner):
        """B.7: provenance is tuple and is NOT None."""
        request = PlannerRuntimeRequest(
            task_id="t-007",
            task_type="analyse",
            prompt="query",
            response_model_name="AnalyseResult",
            priority=0.5,
            remaining_time_s=300.0,
            is_panic_deprioritized=False,
        )
        result = PlannerRuntimeResult(
            task_id="t-007",
            executed=True,
            skipped_panic=False,
            hermes_output="output",
            error=None,
        )
        finding = planner._runtime_result_to_canonical_finding(request, result)
        assert finding is not None
        assert finding.provenance is not None
        assert isinstance(finding.provenance, tuple)
        assert len(finding.provenance) == 3
        # Provenance must contain task_id, task_type, response_model_name
        assert finding.provenance[0] == "t-007"
        assert finding.provenance[1] == "analyse"
        assert finding.provenance[2] == "AnalyseResult"

    def test_source_type_is_planner_bridge(self, planner):
        """B.8: source_type == 'planner_bridge'."""
        request = PlannerRuntimeRequest(
            task_id="t-008",
            task_type="fetch",
            prompt="query",
            response_model_name="FetchResult",
            priority=0.5,
            remaining_time_s=300.0,
            is_panic_deprioritized=False,
        )
        result = PlannerRuntimeResult(
            task_id="t-008",
            executed=True,
            skipped_panic=False,
            hermes_output="output",
            error=None,
        )
        finding = planner._runtime_result_to_canonical_finding(request, result)
        assert finding is not None
        assert finding.source_type == "planner_bridge"

    def test_source_type_and_provenance_strings_interned(self, planner):
        """B.16: source_type and provenance strings are interned."""
        request = PlannerRuntimeRequest(
            task_id="t-009",
            task_type="synthesize",
            prompt="query",
            response_model_name="SynthesizeResult",
            priority=0.5,
            remaining_time_s=300.0,
            is_panic_deprioritized=False,
        )
        result = PlannerRuntimeResult(
            task_id="t-009",
            executed=True,
            skipped_panic=False,
            hermes_output="output",
            error=None,
        )
        finding = planner._runtime_result_to_canonical_finding(request, result)
        assert finding is not None
        # source_type should be interned
        assert finding.source_type is sys.intern("planner_bridge")
        # provenance strings should be interned
        for item in finding.provenance:
            assert item is sys.intern(item)

    def test_ts_is_float_near_now(self, planner):
        """B.10: ts is float and corresponds to 'now'."""
        before = time.time()
        request = PlannerRuntimeRequest(
            task_id="t-010",
            task_type="fetch",
            prompt="query",
            response_model_name="FetchResult",
            priority=0.5,
            remaining_time_s=300.0,
            is_panic_deprioritized=False,
        )
        result = PlannerRuntimeResult(
            task_id="t-010",
            executed=True,
            skipped_panic=False,
            hermes_output="output",
            error=None,
        )
        finding = planner._runtime_result_to_canonical_finding(request, result)
        after = time.time()
        assert finding is not None
        assert isinstance(finding.ts, float)
        assert before <= finding.ts <= after


# ---------------------------------------------------------------------------
# Tests: storage counters and fail-open
# ---------------------------------------------------------------------------

class TestStorageCounters:
    """Tests B.17, B.18, B.19, B.20, B.21, B.22, B.23, B.24, B.25, B.26, B.27, B.28, B.29"""

    @pytest.fixture
    def planner(self):
        return HTNPlanner(
            governor=_MockGovernor(),
            cost_model=_MockCostModel(),
            decomposer=_MockDecomposer(),
            scheduler=_MockScheduler(),
            evidence_log=_MockEvidenceLog(),
        )

    @pytest.mark.asyncio
    async def test_store_none_noop(self, planner):
        """B.11: store=None → method still works, no counters changed."""
        request = PlannerRuntimeRequest(
            task_id="t-011",
            task_type="fetch",
            prompt="query",
            response_model_name="FetchResult",
            priority=0.5,
            remaining_time_s=300.0,
            is_panic_deprioritized=False,
        )
        result = PlannerRuntimeResult(
            task_id="t-011",
            executed=True,
            skipped_panic=False,
            hermes_output="output",
            error=None,
        )
        # This should NOT raise
        await planner._store_canonical_findings(
            results=[result],
            requests=[request],
            store=None,
        )
        # No counters should have changed (they stay at 0)
        assert planner._stored_finding_count == 0
        assert planner._storage_fail_count == 0
        assert planner._storage_skipped_count == 0

    @pytest.mark.asyncio
    async def test_store_startup_not_ready_skips(self, planner):
        """B.27: store.startup_ready=False → storage skipped, _storage_skipped_count++."""
        mock_store = MagicMock()
        mock_store._initialized = True
        mock_store._closed = False
        mock_store._startup_ready = MagicMock()
        mock_store._startup_ready.is_set.return_value = False

        request = PlannerRuntimeRequest(
            task_id="t-012",
            task_type="fetch",
            prompt="query",
            response_model_name="FetchResult",
            priority=0.5,
            remaining_time_s=300.0,
            is_panic_deprioritized=False,
        )
        result = PlannerRuntimeResult(
            task_id="t-012",
            executed=True,
            skipped_panic=False,
            hermes_output="output",
            error=None,
        )
        await planner._store_canonical_findings(
            results=[result],
            requests=[request],
            store=mock_store,
        )
        # _storage_skipped_count should increment
        assert planner._storage_skipped_count == 1
        # NOT _storage_fail_count
        assert planner._storage_fail_count == 0
        # NOT _stored_finding_count
        assert planner._stored_finding_count == 0

    @pytest.mark.asyncio
    async def test_storage_fail_does_not_stop_runtime_results(self, planner):
        """B.13: storage fail does NOT stop runtime results / learning."""
        # We simulate storage fail by having async_record_canonical_findings_batch raise
        mock_store = MagicMock()
        mock_store._initialized = True
        mock_store._closed = False
        mock_store._startup_ready = MagicMock()
        mock_store._startup_ready.is_set.return_value = True
        mock_store.async_record_canonical_findings_batch = AsyncMock(
            side_effect=RuntimeError("storage error")
        )

        engine = _make_engine([
            PlannerRuntimeResult(
                task_id="t-013",
                executed=True,
                skipped_panic=False,
                hermes_output="output",
                error=None,
            )
        ])

        # This should NOT raise — fail-open
        tasks = [{"type": "fetch", "url": "http://example.com"}]
        results = await planner.execute_requests_and_learn(tasks, engine, store=mock_store)
        # Results are returned despite storage failure
        assert len(results) == 1
        assert results[0].task_id == "t-013"
        # Learning still happened
        assert planner._update_count == 1

    @pytest.mark.asyncio
    async def test_storage_fail_increments_fail_counter(self, planner):
        """B.18: _storage_fail_count grows on storage exception."""
        mock_store = MagicMock()
        mock_store._initialized = True
        mock_store._closed = False
        mock_store._startup_ready = MagicMock()
        mock_store._startup_ready.is_set.return_value = True
        mock_store.async_record_canonical_findings_batch = AsyncMock(
            side_effect=RuntimeError("storage error")
        )

        engine = _make_engine([
            PlannerRuntimeResult(
                task_id="t-014",
                executed=True,
                skipped_panic=False,
                hermes_output="output",
                error=None,
            )
        ])

        tasks = [{"type": "fetch", "url": "http://example.com"}]
        await planner.execute_requests_and_learn(tasks, engine, store=mock_store)

        assert planner._storage_fail_count == 1
        assert planner._stored_finding_count == 0

    @pytest.mark.asyncio
    async def test_stored_finding_count_on_success(self, planner):
        """B.17: _stored_finding_count grows on success."""
        mock_store = MagicMock()
        mock_store._initialized = True
        mock_store._closed = False
        mock_store._startup_ready = MagicMock()
        mock_store._startup_ready.is_set.return_value = True

        # Mock ActivationResult as TypedDict
        class _ActivationResult(dict):
            pass

        mock_store.async_record_canonical_findings_batch = AsyncMock(
            return_value=[
                _ActivationResult({"finding_id": "t-015", "lmdb_success": True,
                                   "duckdb_success": True, "desync": False})
            ]
        )

        engine = _make_engine([
            PlannerRuntimeResult(
                task_id="t-015",
                executed=True,
                skipped_panic=False,
                hermes_output="output",
                error=None,
            )
        ])

        tasks = [{"type": "fetch", "url": "http://example.com"}]
        await planner.execute_requests_and_learn(tasks, engine, store=mock_store)

        assert planner._stored_finding_count == 1
        assert planner._storage_fail_count == 0

    @pytest.mark.asyncio
    async def test_batch_api_called_when_available(self, planner):
        """B.20: batch API is called when available."""
        mock_store = MagicMock()
        mock_store._initialized = True
        mock_store._closed = False
        mock_store._startup_ready = MagicMock()
        mock_store._startup_ready.is_set.return_value = True
        batch_mock = AsyncMock(return_value=[])
        mock_store.async_record_canonical_findings_batch = batch_mock

        engine = _make_engine([
            PlannerRuntimeResult(
                task_id="t-016",
                executed=True,
                skipped_panic=False,
                hermes_output="output",
                error=None,
            )
        ])

        tasks = [{"type": "fetch", "url": "http://example.com"}]
        await planner.execute_requests_and_learn(tasks, engine, store=mock_store)

        # Batch API was called
        batch_mock.assert_called_once()
        # Called with a list of CanonicalFinding
        call_args = batch_mock.call_args
        findings_arg = call_args[0][0]
        assert isinstance(findings_arg, list)
        assert len(findings_arg) == 1

    @pytest.mark.asyncio
    async def test_batch_api_failure_fail_open(self, planner):
        """B.21: batch API failure → fail-open preserved."""
        mock_store = MagicMock()
        mock_store._initialized = True
        mock_store._closed = False
        mock_store._startup_ready = MagicMock()
        mock_store._startup_ready.is_set.return_value = True
        mock_store.async_record_canonical_findings_batch = AsyncMock(
            side_effect=RuntimeError("batch failure")
        )

        engine = _make_engine([
            PlannerRuntimeResult(
                task_id="t-017",
                executed=True,
                skipped_panic=False,
                hermes_output="output",
                error=None,
            )
        ])

        tasks = [{"type": "fetch", "url": "http://example.com"}]
        # Must NOT raise
        results = await planner.execute_requests_and_learn(tasks, engine, store=mock_store)
        assert len(results) == 1
        assert planner._storage_fail_count == 1

    @pytest.mark.asyncio
    async def test_storage_skipped_count_distinct_from_fail_count(self, planner):
        """B.29: _storage_skipped_count is distinct from _storage_fail_count."""
        mock_store = MagicMock()
        mock_store._initialized = True
        mock_store._closed = False
        mock_store._startup_ready = MagicMock()
        mock_store._startup_ready.is_set.return_value = False  # triggers skip

        engine = _make_engine([
            PlannerRuntimeResult(
                task_id="t-018",
                executed=True,
                skipped_panic=False,
                hermes_output="output",
                error=None,
            )
        ])

        tasks = [{"type": "fetch", "url": "http://example.com"}]
        await planner.execute_requests_and_learn(tasks, engine, store=mock_store)

        assert planner._storage_skipped_count == 1
        assert planner._storage_fail_count == 0  # distinct counter

    @pytest.mark.asyncio
    async def test_all_failure_modes_no_finding(self, planner):
        """B.2, B.3, B.4: skipped_panic, error, model_not_loaded → no finding."""
        failure_results = [
            PlannerRuntimeResult(
                task_id="t-err",
                executed=False,
                skipped_panic=False,
                hermes_output=None,
                error="timeout",
            ),
            PlannerRuntimeResult(
                task_id="t-panic",
                executed=False,
                skipped_panic=True,
                hermes_output=None,
                error="panic_skip",
            ),
            PlannerRuntimeResult(
                task_id="t-model",
                executed=False,
                skipped_panic=False,
                hermes_output=None,
                error="model_not_loaded",
            ),
            PlannerRuntimeResult(
                task_id="t-internal",
                executed=False,
                skipped_panic=False,
                hermes_output=None,
                error="planner_error",
            ),
        ]
        engine = _make_engine(failure_results)

        mock_store = MagicMock()
        mock_store._initialized = True
        mock_store._closed = False
        mock_store._startup_ready = MagicMock()
        mock_store._startup_ready.is_set.return_value = True
        batch_mock = AsyncMock(return_value=[])
        mock_store.async_record_canonical_findings_batch = batch_mock

        tasks = [
            {"type": "fetch"},
            {"type": "fetch"},
            {"type": "fetch"},
            {"type": "fetch"},
        ]
        results = await planner.execute_requests_and_learn(tasks, engine, store=mock_store)

        # No CanonicalFindings were created (batch called with empty list)
        call_args = batch_mock.call_args
        if call_args is not None:
            findings_arg = call_args[0][0]
            assert len(findings_arg) == 0, "No findings should be created for failed results"


# ---------------------------------------------------------------------------
# Integration test: full loop
# ---------------------------------------------------------------------------

class TestFullLoopIntegration:
    """Integration test: planner → runtime → CanonicalFinding → storage."""

    @pytest.mark.asyncio
    async def test_full_loop_stored_finding_count_greater_than_zero(self):
        """B.BENCH: _stored_finding_count > 0 in deterministic test."""
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=_MockCostModel(),
            decomposer=_MockDecomposer(),
            scheduler=_MockScheduler(),
            evidence_log=_MockEvidenceLog(),
        )

        mock_store = MagicMock()
        mock_store._initialized = True
        mock_store._closed = False
        mock_store._startup_ready = MagicMock()
        mock_store._startup_ready.is_set.return_value = True

        class _ActivationResult(dict):
            pass

        call_count = [0]

        def _make_activation_result(finding_id, success):
            r = _ActivationResult({
                "finding_id": finding_id,
                "lmdb_success": success,
                "duckdb_success": success,
                "desync": False,
                "error": None,
            })
            return r

        async def _batch_mock(findings):
            call_count[0] += 1
            return [_make_activation_result(f.finding_id, True) for f in findings]

        mock_store.async_record_canonical_findings_batch = _batch_mock

        engine = _make_engine([
            PlannerRuntimeResult(
                task_id="int-001",
                executed=True,
                skipped_panic=False,
                hermes_output="output A",
                error=None,
            ),
            PlannerRuntimeResult(
                task_id="int-002",
                executed=True,
                skipped_panic=False,
                hermes_output="output B",
                error=None,
            ),
        ])

        tasks = [
            {"type": "fetch", "url": "http://a.com"},
            {"type": "fetch", "url": "http://b.com"},
        ]
        results = await planner.execute_requests_and_learn(tasks, engine, store=mock_store)

        assert len(results) == 2
        assert planner._stored_finding_count == 2
        assert planner._storage_fail_count == 0
        assert planner._storage_skipped_count == 0

    @pytest.mark.asyncio
    async def test_learning_still_happens_when_storage_available(self):
        """B.7: learning update() is called even when storage is available."""
        planner = HTNPlanner(
            governor=_MockGovernor(),
            cost_model=_MockCostModel(),
            decomposer=_MockDecomposer(),
            scheduler=_MockScheduler(),
            evidence_log=_MockEvidenceLog(),
        )

        mock_store = MagicMock()
        mock_store._initialized = True
        mock_store._closed = False
        mock_store._startup_ready = MagicMock()
        mock_store._startup_ready.is_set.return_value = True

        class _ActivationResult(dict):
            pass

        mock_store.async_record_canonical_findings_batch = AsyncMock(
            return_value=[_ActivationResult({
                "finding_id": "learn-001",
                "lmdb_success": True,
                "duckdb_success": True,
                "desync": False,
                "error": None,
            })]
        )

        engine = _make_engine([
            PlannerRuntimeResult(
                task_id="learn-001",
                executed=True,
                skipped_panic=False,
                hermes_output="output",
                error=None,
            )
        ])

        tasks = [{"type": "fetch", "url": "http://example.com"}]
        await planner.execute_requests_and_learn(tasks, engine, store=mock_store)

        # Learning happened (update was called)
        assert planner._update_count == 1
        # Storage also happened
        assert planner._stored_finding_count == 1
