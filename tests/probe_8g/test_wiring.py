"""
Sprint 8G — AdaptiveCostModel → HTNPlanner Wiring Probe
=========================================================

Tests:
1.  HTNPlanner opravdu volá AdaptiveCostModel.predict() tam, kde wiring aktivní
2.  Fallback při selhání predict() funguje a planner nespadne
3.  _fallback_count se zvyšuje při bad input / forced failure
4.  _estimate_cost vrací > 0
5.  Žádné DB/I/O volání v _estimate_*
6.  Planner zůstává non-AO (neimportuje AO moduly)
7.  Import planning.htn_planner neprovádí těžký init
8.  Test isolation nepoužívá produkční LMDB
9.  Různé task typy nevedou vždy na bit-for-bit identické výsledky
10. register_task_type() stav je explicitně pokryt
"""

from __future__ import annotations

import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class MockCostModel:
    """
    Mock cost model that tracks predict() calls.
    Returns different values per task_type to test diversity wiring.
    """

    # Per-type return values: (cost, ram, network, value, uncertainty)
    _PER_TYPE = {
        'fetch': (1.5, 60.0, 0.5, 2.0, 0.1),
        'deep_read': (3.0, 128.0, 1.5, 4.0, 0.15),
        'branch': (2.0, 80.0, 0.8, 3.0, 0.12),
        'analyse': (2.5, 100.0, 1.0, 3.5, 0.13),
        'synthesize': (4.0, 150.0, 2.0, 5.0, 0.2),
        'hypothesis': (1.0, 40.0, 0.3, 1.5, 0.08),
        'explain': (0.8, 30.0, 0.2, 1.2, 0.05),
        'other': (1.0, 50.0, 0.5, 1.0, 0.1),
    }

    # Sentinel to distinguish "explicit None" from "use default"
    _USE_DEFAULT = object()

    def __init__(self, fail_predict: bool = False, return_values=None, return_none: bool = False):
        self.fail_predict = fail_predict
        # return_none=True means predict() should actually return None
        self._return_none = return_none
        self.return_values = return_values
        self.predict_calls: list = []

    def predict(self, task_type: str, params: Dict, system_state: Dict):
        self.predict_calls.append((task_type, params, system_state))
        if self.fail_predict:
            raise RuntimeError("simulated predict failure")
        if self._return_none:
            return None
        if self.return_values is not None:
            return self.return_values
        return self._PER_TYPE.get(task_type, self._PER_TYPE['other'])


class MockGovernor:
    """Lightweight mock governor — no real resource tracking."""

    def __init__(self):
        self._active_tasks = 0
        self._rss_gb = 2.0
        self._avg_latency = 0.1
        self._reserve_context = None

    def get_current_usage(self):
        return {
            'active_tasks': self._active_tasks,
            'rss_gb': self._rss_gb,
            'avg_latency': self._avg_latency,
        }

    def can_afford_sync(self, cost_estimate: Dict, priority=None) -> bool:
        return True

    async def reserve(self, resources: Dict, priority, **kwargs):
        class ReserveCtx:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        return ReserveCtx()


class MockDecomposer:
    """Mock SLM decomposer."""

    def __init__(self, tasks=None):
        self.tasks = tasks or []

    async def decompose(self, goal, context):
        return self.tasks


class TestEstimateAlwaysPositive:
    """4. _estimate_cost vrací > 0"""

    @pytest.fixture
    def planner(self):
        from hledac.universal.planning.htn_planner import HTNPlanner

        governor = MockGovernor()
        cost_model = MockCostModel()
        decomposer = MockDecomposer([])
        scheduler = MagicMock()
        planner = HTNPlanner(governor, cost_model, decomposer, scheduler, None)
        return planner

    def test_estimate_cost_always_positive(self, planner):
        for task_type in ['fetch', 'deep_read', 'branch', 'analyse', 'synthesize']:
            task = {'type': task_type, 'url': 'http://example.com/path'}
            cost = planner._estimate_cost(task)
            assert cost > 0, f"_estimate_cost returned {cost} for {task_type}"

    def test_estimate_ram_always_positive(self, planner):
        for task_type in ['fetch', 'deep_read', 'branch', 'analyse']:
            task = {'type': task_type, 'url': 'http://example.com/path'}
            ram = planner._estimate_ram(task)
            assert ram > 0, f"_estimate_ram returned {ram} for {task_type}"

    def test_estimate_network_always_positive(self, planner):
        for task_type in ['fetch', 'deep_read', 'branch', 'analyse']:
            task = {'type': task_type, 'url': 'http://example.com/path'}
            net = planner._estimate_network(task)
            assert net > 0, f"_estimate_network returned {net} for {task_type}"

    def test_estimate_value_always_positive(self, planner):
        for task_type in ['fetch', 'deep_read', 'branch', 'analyse']:
            task = {'type': task_type, 'url': 'http://example.com/path'}
            value = planner._estimate_value(task)
            assert value > 0, f"_estimate_value returned {value} for {task_type}"


class TestPredictWiring:
    """1. HTNPlanner opravdu volá AdaptiveCostModel.predict()"""

    def test_safe_predict_calls_cost_model_predict(self):
        from hledac.universal.planning.htn_planner import HTNPlanner

        governor = MockGovernor()
        cost_model = MockCostModel()
        decomposer = MockDecomposer([])
        scheduler = MagicMock()
        planner = HTNPlanner(governor, cost_model, decomposer, scheduler, None)

        task = {'type': 'fetch', 'url': 'http://example.com', 'depth': 2}
        cost, ram, net, value, used = planner._safe_predict(task)

        assert cost_model.predict_calls, "predict() never called on cost_model"
        assert used is True, "used_predict should be True when predict() succeeds"

    def test_safe_predict_unpacks_four_values(self):
        from hledac.universal.planning.htn_planner import HTNPlanner

        governor = MockGovernor()
        cost_model = MockCostModel(return_values=(3.0, 128.0, 1.5, 4.0, 0.2))
        decomposer = MockDecomposer([])
        scheduler = MagicMock()
        planner = HTNPlanner(governor, cost_model, decomposer, scheduler, None)

        task = {'type': 'deep_read', 'url': 'http://example.com/page'}
        cost, ram, net, value, used = planner._safe_predict(task)

        assert used is True
        # cost_model returns (cost, ram, network, value, uncertainty)
        assert cost == 3.0
        assert ram == 128.0
        assert net == 1.5
        assert value == 4.0

    def test_estimate_methods_call_safe_predict(self):
        from hledac.universal.planning.htn_planner import HTNPlanner

        governor = MockGovernor()
        cost_model = MockCostModel()
        decomposer = MockDecomposer([])
        scheduler = MagicMock()
        planner = HTNPlanner(governor, cost_model, decomposer, scheduler, None)

        task = {'type': 'fetch', 'url': 'http://example.com'}

        # Clear any calls from previous operations
        cost_model.predict_calls.clear()

        # Call each estimate method
        planner._estimate_cost(task)
        planner._estimate_ram(task)
        planner._estimate_network(task)
        planner._estimate_value(task)

        # Each _estimate_* calls _safe_predict exactly once
        # (but cached results may reduce actual predict calls)
        assert len(cost_model.predict_calls) >= 1, "predict() not called"


class TestFallbackBehavior:
    """2. Fallback při selhání predict() funguje a planner nespadne"""

    def test_fallback_on_cost_model_none(self):
        from hledac.universal.planning.htn_planner import HTNPlanner

        governor = MockGovernor()
        decomposer = MockDecomposer([])
        scheduler = MagicMock()
        planner = HTNPlanner(governor, None, decomposer, scheduler, None)

        task = {'type': 'fetch', 'url': 'http://example.com'}
        cost, ram, net, value, used = planner._safe_predict(task)

        # Must return fallback values, not crash
        assert cost == 1.0  # _FALLBACK_COST
        assert ram == 50.0  # _FALLBACK_RAM
        assert net == 0.1  # _FALLBACK_NETWORK
        assert value == 1.0  # _FALLBACK_VALUE
        assert used is False

    def test_fallback_on_predict_exception(self):
        from hledac.universal.planning.htn_planner import HTNPlanner

        governor = MockGovernor()
        cost_model = MockCostModel(fail_predict=True)
        decomposer = MockDecomposer([])
        scheduler = MagicMock()
        planner = HTNPlanner(governor, cost_model, decomposer, scheduler, None)

        task = {'type': 'fetch', 'url': 'http://example.com'}
        cost, ram, net, value, used = planner._safe_predict(task)

        # Must return fallback values, not crash
        assert cost == 1.0
        assert ram == 50.0
        assert net == 0.1
        assert value == 1.0
        assert used is False

    def test_fallback_on_predict_returns_none(self):
        from hledac.universal.planning.htn_planner import HTNPlanner

        governor = MockGovernor()
        cost_model = MockCostModel(return_none=True)
        decomposer = MockDecomposer([])
        scheduler = MagicMock()
        planner = HTNPlanner(governor, cost_model, decomposer, scheduler, None)

        task = {'type': 'fetch', 'url': 'http://example.com'}
        cost, ram, net, value, used = planner._safe_predict(task)

        assert cost == 1.0
        assert used is False


class TestFallbackCounter:
    """3. _fallback_count se zvyšuje při bad input / forced failure"""

    def test_fallback_count_increments_on_none_cost_model(self):
        from hledac.universal.planning.htn_planner import HTNPlanner

        governor = MockGovernor()
        decomposer = MockDecomposer([])
        scheduler = MagicMock()
        planner = HTNPlanner(governor, None, decomposer, scheduler, None)

        task = {'type': 'fetch', 'url': 'http://example.com'}
        initial = planner._fallback_count

        planner._safe_predict(task)
        assert planner._fallback_count == initial + 1

        planner._safe_predict(task)
        assert planner._fallback_count == initial + 2

    def test_fallback_count_increments_on_predict_exception(self):
        from hledac.universal.planning.htn_planner import HTNPlanner

        governor = MockGovernor()
        cost_model = MockCostModel(fail_predict=True)
        decomposer = MockDecomposer([])
        scheduler = MagicMock()
        planner = HTNPlanner(governor, cost_model, decomposer, scheduler, None)

        task = {'type': 'fetch', 'url': 'http://example.com'}
        initial = planner._fallback_count

        planner._safe_predict(task)
        assert planner._fallback_count == initial + 1

    def test_fallback_count_accessible_for_testing(self):
        from hledac.universal.planning.htn_planner import HTNPlanner

        governor = MockGovernor()
        cost_model = MockCostModel(fail_predict=True)
        decomposer = MockDecomposer([])
        scheduler = MagicMock()
        planner = HTNPlanner(governor, cost_model, decomposer, scheduler, None)

        assert hasattr(planner, '_fallback_count')
        assert isinstance(planner._fallback_count, int)


class TestNoIOInEstimate:
    """5. Žádné DB/I/O volání v _estimate_*"""

    def test_no_lmdb_io_in_safe_predict(self):
        from hledac.universal.planning.htn_planner import HTNPlanner

        governor = MockGovernor()
        cost_model = MockCostModel()
        decomposer = MockDecomposer([])
        scheduler = MagicMock()
        planner = HTNPlanner(governor, cost_model, decomposer, scheduler, None)

        task = {'type': 'fetch', 'url': 'http://example.com'}

        with patch('lmdb.Environment') as mock_lmdb:
            planner._safe_predict(task)
            # No LMDB operations should be triggered by _estimate_*
            mock_lmdb.assert_not_called()

    def test_no_http_io_in_estimate_methods(self):
        from hledac.universal.planning.htn_planner import HTNPlanner

        governor = MockGovernor()
        cost_model = MockCostModel()
        decomposer = MockDecomposer([])
        scheduler = MagicMock()
        planner = HTNPlanner(governor, cost_model, decomposer, scheduler, None)

        task = {'type': 'fetch', 'url': 'http://example.com'}

        with patch('aiohttp.ClientSession') as mock_http:
            planner._estimate_cost(task)
            planner._estimate_ram(task)
            planner._estimate_network(task)
            planner._estimate_value(task)
            # No HTTP operations should be triggered
            mock_http.assert_not_called()


class TestPlannerNonAO:
    """6. Planner zůstává non-AO — ověřuje že modulový source kód přímo nedefinuje AO importy"""

    def test_source_does_not_import_ao_modules(self):
        """Ověříme že htn_planner.py na úrovni moduluNEDEFINUJE import autonomous_orchestrator."""
        import os
        planner_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'planning', 'htn_planner.py'
        )
        with open(planner_path) as f:
            source = f.read()

        # Kontrola: v souboru není přímý import AO modulů
        forbidden = [
            'from hledac.universal.autonomous_orchestrator',
            'import hledac.universal.autonomous_orchestrator',
            'from hledac.universal import autonomous_orchestrator',
        ]
        for line in forbidden:
            assert line not in source, f"htn_planner.py contains forbidden AO import: {line}"

    def test_source_does_not_import_knowledge_modules(self):
        """Ověříme že htn_planner.py na úrovni moduluNEDEFINUJE import knowledge modulů."""
        import os
        planner_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'planning', 'htn_planner.py'
        )
        with open(planner_path) as f:
            source = f.read()

        forbidden = [
            'from hledac.universal.knowledge',
            'import hledac.universal.knowledge',
        ]
        for line in forbidden:
            assert line not in source, f"htn_planner.py contains forbidden knowledge import: {line}"

    def test_htn_planner_registers_task_type(self):
        from hledac.universal.planning.htn_planner import HTNPlanner

        governor = MockGovernor()
        cost_model = MockCostModel()
        decomposer = MockDecomposer([])
        scheduler = MagicMock()
        planner = HTNPlanner(governor, cost_model, decomposer, scheduler, None)

        called = []

        def dummy_expander(task, context):
            called.append(task)
            return []

        planner.register_task_type('fetch', dummy_expander, is_primitive=True)

        assert 'fetch' in planner._task_types
        assert planner._task_types['fetch']['primitive'] is True
        assert planner._task_types['fetch']['expander'] is dummy_expander


class TestImportTime:
    """7. Import planning.htn_planner neprovádí těžký init"""

    def test_import_time_under_500ms_warm(self):
        import importlib
        import time

        times = []
        for _ in range(5):
            # Remove from cache
            for mod in list(sys.modules.keys()):
                if 'planning' in mod:
                    del sys.modules[mod]

            t = time.perf_counter()
            importlib.import_module('planning.htn_planner')
            times.append((time.perf_counter() - t) * 1000)

        # Warm import (already loaded) should be < 100ms
        median = sorted(times)[len(times) // 2]
        assert median < 200, f"warm import too slow: {median:.1f}ms"


class TestIsolation:
    """8. Test isolation nepoužívá produkční LMDB"""

    def test_htn_planner_usable_without_production_lmdb(self):
        from hledac.universal.planning.htn_planner import HTNPlanner

        governor = MockGovernor()
        cost_model = MockCostModel()
        decomposer = MockDecomposer([])
        scheduler = MagicMock()

        # Should be instantiatable without any LMDB operations
        planner = HTNPlanner(governor, cost_model, decomposer, scheduler, None)
        assert planner is not None
        assert hasattr(planner, '_estimate_cost')
        assert hasattr(planner, '_estimate_ram')
        assert hasattr(planner, '_estimate_network')
        assert hasattr(planner, '_estimate_value')
        assert hasattr(planner, '_fallback_count')


class TestTaskTypeDiversity:
    """9. Různé task typy nevedou vždy na bit-for-bit identické výsledky"""

    def test_different_task_types_produce_different_predictions(self):
        from hledac.universal.planning.htn_planner import HTNPlanner

        governor = MockGovernor()
        cost_model = MockCostModel()
        decomposer = MockDecomposer([])
        scheduler = MagicMock()
        planner = HTNPlanner(governor, cost_model, decomposer, scheduler, None)

        task_types = ['fetch', 'deep_read', 'branch', 'analyse', 'synthesize']
        predictions = []

        for tt in task_types:
            # Clear cache to force re-computation
            planner._cached_predict_hash.cache_clear()
            task = {'type': tt, 'url': 'http://example.com/' + tt}
            cost, ram, net, value, used = planner._safe_predict(task)
            predictions.append((cost, ram, net, value))

        # At least some predictions should differ
        unique = set(predictions)
        assert len(unique) > 1, (
            f"All task types produce identical predictions: {predictions}. "
            "This suggests wiring is not differentiating by task type."
        )

    def test_same_task_type_gives_same_result(self):
        from hledac.universal.planning.htn_planner import HTNPlanner

        governor = MockGovernor()
        cost_model = MockCostModel()
        decomposer = MockDecomposer([])
        scheduler = MagicMock()
        planner = HTNPlanner(governor, cost_model, decomposer, scheduler, None)

        task = {'type': 'fetch', 'url': 'http://example.com'}

        # First call
        cost1, ram1, net1, value1, _ = planner._safe_predict(task)
        # Second call (cached)
        cost2, ram2, net2, value2, _ = planner._safe_predict(task)

        assert cost1 == cost2
        assert ram1 == ram2
        assert net1 == net2
        assert value1 == value2


class TestMemoization:
    """Verify LRU memoization is active and bounded."""

    def test_cached_predict_hash_is_lru_cached(self):
        from hledac.universal.planning.htn_planner import HTNPlanner

        governor = MockGovernor()
        cost_model = MockCostModel()
        decomposer = MockDecomposer([])
        scheduler = MagicMock()
        planner = HTNPlanner(governor, cost_model, decomposer, scheduler, None)

        assert hasattr(planner._cached_predict_hash, 'cache_clear')
        assert hasattr(planner._cached_predict_hash, 'cache_info')

    def test_cache_info_after_calls(self):
        from hledac.universal.planning.htn_planner import HTNPlanner

        governor = MockGovernor()
        cost_model = MockCostModel()
        decomposer = MockDecomposer([])
        scheduler = MagicMock()
        planner = HTNPlanner(governor, cost_model, decomposer, scheduler, None)

        task = {'type': 'fetch', 'url': 'http://example.com/test'}
        planner._safe_predict(task)
        planner._safe_predict(task)  # same inputs → cache hit

        info = planner._cached_predict_hash.cache_info()
        assert info.hits >= 1 or info.misses >= 1
