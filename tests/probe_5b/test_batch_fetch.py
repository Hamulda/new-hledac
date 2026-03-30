"""
Sprint 5B: Batch Fetch Pipeline + Adaptive Cap Consumption + Priority Frontier Intake
======================================================================================

Tests:
- batch fetch is truly parallel/batch-aware
- batch respects timeout/concurrency matrix
- batch respects AIMD window
- gather has return_exceptions=True + logging
- lightweight priority intake is consumed
- telemetry includes batch/effective parallelism/aimd
- shutdown drain remains intact
- import/instantiation regression
"""

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from collections import deque

import sys
sys.path.insert(0, '/Users/vojtechhamada/PycharmProjects/Hledac')

from hledac.universal.coordinators.fetch_coordinator import (
    FetchCoordinator,
    FetchCoordinatorConfig,
    TIMEOUT_CLEARNET_HTML,
    TIMEOUT_CLEARNET_API,
    TIMEOUT_TOR,
    AIMD_ADDITIVE_INCREMENT,
    AIMD_DECREASE_FACTOR,
    AIMD_MIN_CONCURRENCY,
    AIMD_MAX_CONCURRENCY,
    AIMD_SUCCESS_THRESHOLD,
    CONCURRENCY_CLEARNET,
    CONCURRENCY_TOR,
    CONCURRENCY_GLOBAL_MAX,
)


class TestBatchFetchParallelism(unittest.TestCase):
    """Test that batch fetch is actually parallel."""

    def setUp(self):
        self.config = FetchCoordinatorConfig(max_urls_per_step=5)

    def test_import_instantiation(self):
        """Regression: module imports and instantiates without error."""
        coord = FetchCoordinator(config=FetchCoordinatorConfig())
        self.assertIsNotNone(coord)
        self.assertEqual(coord._aimd_concurrency, float(CONCURRENCY_CLEARNET))

    @patch('hledac.universal.coordinators.fetch_coordinator.FetchCoordinator._fetch_url')
    async def test_batch_fetches_parallel(self, mock_fetch):
        """Batch fetch must be parallel, not sequential."""
        fetch_times = []

        async def mock_fetch_with_timing(url, attempt=0):
            start = time.time()
            fetch_times.append((url, start))
            await asyncio.sleep(0.15)
            fetch_times.append((url, time.time()))
            return {'success': True, 'evidence_id': f'ev_{url}'}

        mock_fetch.side_effect = mock_fetch_with_timing

        coord = FetchCoordinator(config=self.config, max_concurrent=10)
        coord._orchestrator = MagicMock()
        coord._ctx = {'budget_manager': None}
        coord._frontier = deque(['http://a.com', 'http://b.com', 'http://c.com', 'http://d.com'])

        result = await coord.step({})

        total_time = fetch_times[-1][1] - fetch_times[0][1] if fetch_times else 0
        self.assertLess(
            total_time, 0.4,
            f"Batch fetch appears sequential: {total_time:.2f}s for 4 fetches"
        )

    @patch('hledac.universal.coordinators.fetch_coordinator.FetchCoordinator._fetch_url')
    async def test_batch_respects_aimd_window(self, mock_fetch):
        """Batch must respect AIMD concurrency window."""
        mock_fetch.return_value = {'success': True, 'evidence_id': 'ev_test'}

        coord = FetchCoordinator(config=self.config, max_concurrent=3)
        coord._orchestrator = MagicMock()
        coord._ctx = {'budget_manager': None}
        coord._aimd_concurrency = 2.0
        coord._aimd_semaphore = asyncio.Semaphore(2)
        coord._frontier = deque(['http://a.com', 'http://b.com', 'http://c.com', 'http://d.com', 'http://e.com'])

        result = await coord.step({})

        self.assertEqual(mock_fetch.call_count, 2)
        self.assertEqual(result['aimd_window'], 2.0)

    @patch('hledac.universal.coordinators.fetch_coordinator.FetchCoordinator._fetch_url')
    async def test_gather_has_return_exceptions(self, mock_fetch):
        """Gather must use return_exceptions=True and log exceptions."""
        call_count = 0

        async def mock_fetch_with_error(url, attempt=0):
            nonlocal call_count
            call_count += 1
            if 'bad' in url:
                raise ValueError(f"Simulated error for {url}")
            return {'success': True, 'evidence_id': f'ev_{url}'}

        mock_fetch.side_effect = mock_fetch_with_error

        coord = FetchCoordinator(config=self.config, max_concurrent=10)
        coord._orchestrator = MagicMock()
        coord._ctx = {'budget_manager': None}
        coord._frontier = deque(['http://good.com', 'http://bad.com'])

        result = await coord.step({})

        self.assertEqual(call_count, 2)
        self.assertGreater(len(result.get('evidence_ids', [])), 0)


class TestAIMDCapConsumption(unittest.TestCase):
    """Test that AIMD adaptive cap is properly consumed."""

    def setUp(self):
        self.config = FetchCoordinatorConfig(max_urls_per_step=5)

    @patch('hledac.universal.coordinators.fetch_coordinator.FetchCoordinator._fetch_url')
    async def test_aimd_increase_on_success(self, mock_fetch):
        """AIMD window grows after successes."""
        mock_fetch.return_value = {'success': True, 'evidence_id': 'ev'}

        coord = FetchCoordinator(config=self.config, max_concurrent=3)
        coord._orchestrator = MagicMock()
        coord._ctx = {'budget_manager': None}
        coord._frontier = deque(['http://a.com'])

        for _ in range(AIMD_SUCCESS_THRESHOLD + 1):
            await coord.step({})

        self.assertEqual(coord._telemetry['total_successes'], AIMD_SUCCESS_THRESHOLD + 1)

    async def test_aimd_decrease_on_failure(self):
        """AIMD window shrinks on failure."""
        coord = FetchCoordinator(config=self.config, max_concurrent=3)
        coord._aimd_concurrency = 10.0

        new_window = coord._aimd_release_failure()

        self.assertLess(new_window, 10.0)
        self.assertEqual(new_window, max(10.0 * AIMD_DECREASE_FACTOR, AIMD_MIN_CONCURRENCY))

    async def test_aimd_max_cap(self):
        """AIMD window respects maximum."""
        coord = FetchCoordinator(config=self.config, max_concurrent=3)
        coord._aimd_concurrency = AIMD_MAX_CONCURRENCY

        new_window = coord._aimd_release_success()

        self.assertLessEqual(new_window, AIMD_MAX_CONCURRENCY)

    async def test_aimd_min_cap(self):
        """AIMD window respects minimum."""
        coord = FetchCoordinator(config=self.config, max_concurrent=3)
        coord._aimd_concurrency = 1.5

        new_window = coord._aimd_release_failure()

        self.assertGreaterEqual(new_window, AIMD_MIN_CONCURRENCY)


class TestLightweightPriorityIntake(unittest.TestCase):
    """Test priority frontier intake without new framework."""

    def setUp(self):
        self.config = FetchCoordinatorConfig(max_urls_per_step=5)

    @patch('hledac.universal.coordinators.fetch_coordinator.FetchCoordinator._fetch_url')
    async def test_frontier_priority_api_before_tor(self, mock_fetch):
        """Priority intake: API should be fetched before Tor."""
        mock_fetch.return_value = {'success': True, 'evidence_id': 'ev'}

        coord = FetchCoordinator(config=self.config, max_concurrent=10)
        coord._orchestrator = MagicMock()
        coord._ctx = {'budget_manager': None}
        coord._frontier = deque([
            'http://tor.onion/page',
            'http://api.example.com/json',
            'http://html.example.com',
        ])

        await coord.step({})

        calls = mock_fetch.call_args_list
        fetched_urls = [call[0][0] for call in calls]

        api_idx = fetched_urls.index('http://api.example.com/json') if 'http://api.example.com/json' in fetched_urls else -1
        tor_idx = fetched_urls.index('http://tor.onion/page') if 'http://tor.onion/page' in fetched_urls else -1

        if api_idx >= 0 and tor_idx >= 0:
            self.assertLess(api_idx, tor_idx, "API should have higher priority than Tor")


class TestTelemetryBatchMetrics(unittest.TestCase):
    """Test telemetry includes batch metrics."""

    def setUp(self):
        self.config = FetchCoordinatorConfig(max_urls_per_step=5)

    @patch('hledac.universal.coordinators.fetch_coordinator.FetchCoordinator._fetch_url')
    async def test_telemetry_includes_aimd_window(self, mock_fetch):
        """Telemetry response must include AIMD window."""
        mock_fetch.return_value = {'success': True, 'evidence_id': 'ev'}

        coord = FetchCoordinator(config=self.config, max_concurrent=3)
        coord._orchestrator = MagicMock()
        coord._ctx = {'budget_manager': None}
        coord._frontier = deque(['http://a.com'])

        result = await coord.step({})

        self.assertIn('aimd_window', result)
        self.assertIn('active_fetches', result)

    @patch('hledac.universal.coordinators.fetch_coordinator.FetchCoordinator._fetch_url')
    async def test_telemetry_includes_batch_size(self, mock_fetch):
        """Sprint 5B: Telemetry should track batch size."""
        mock_fetch.return_value = {'success': True, 'evidence_id': 'ev'}

        coord = FetchCoordinator(config=self.config, max_concurrent=10)
        coord._orchestrator = MagicMock()
        coord._ctx = {'budget_manager': None}
        coord._frontier = deque(['http://a.com', 'http://b.com', 'http://c.com'])

        result = await coord.step({})

        self.assertIn('batch_size', result)
        self.assertEqual(result['batch_size'], 3)

    @patch('hledac.universal.coordinators.fetch_coordinator.FetchCoordinator._fetch_url')
    async def test_telemetry_includes_effective_parallelism(self, mock_fetch):
        """Sprint 5B: Telemetry should track effective parallelism."""
        mock_fetch.return_value = {'success': True, 'evidence_id': 'ev'}

        coord = FetchCoordinator(config=self.config, max_concurrent=10)
        coord._orchestrator = MagicMock()
        coord._ctx = {'budget_manager': None}
        coord._frontier = deque(['http://a.com', 'http://b.com'])

        result = await coord.step({})

        self.assertIn('effective_parallelism', result)


class TestShutdownDrain(unittest.TestCase):
    """Test shutdown drain behavior is preserved."""

    def setUp(self):
        self.config = FetchCoordinatorConfig(max_urls_per_step=5)

    async def test_shutdown_drain_preserved(self):
        """Shutdown must still have 0.25s drain."""
        coord = FetchCoordinator(config=self.config, max_concurrent=3)
        coord._orchestrator = MagicMock()
        coord._urls_fetched_count = 10
        coord._aimd_concurrency = 8.0
        coord._telemetry = {'total_successes': 5, 'total_failures': 1, 'active_fetches': 0}

        start = time.time()
        await coord.shutdown({})
        elapsed = time.time() - start

        self.assertGreaterEqual(elapsed, 0.20)
        self.assertLessEqual(elapsed, 0.50)

    async def test_shutdown_clears_frontier(self):
        """Shutdown must clear frontier."""
        coord = FetchCoordinator(config=self.config, max_concurrent=3)
        coord._frontier = deque(['http://a.com', 'http://b.com'])

        await coord.shutdown({})

        self.assertEqual(len(coord._frontier), 0)


class TestTimeoutConcurrencyMatrix(unittest.TestCase):
    """Test that timeout/concurrency matrix is respected."""

    def test_timeout_matrix_constants(self):
        """Timeout matrix constants must be defined."""
        self.assertEqual(TIMEOUT_CLEARNET_API, 20.0)
        self.assertEqual(TIMEOUT_CLEARNET_HTML, 35.0)
        self.assertEqual(TIMEOUT_TOR, 75.0)

    def test_concurrency_matrix_constants(self):
        """Concurrency matrix constants must be defined."""
        self.assertEqual(CONCURRENCY_TOR, 4)
        self.assertEqual(CONCURRENCY_CLEARNET, 12)
        self.assertEqual(CONCURRENCY_GLOBAL_MAX, 25)

    def test_aimd_matrix_constants(self):
        """AIMD matrix constants must be defined."""
        self.assertEqual(AIMD_ADDITIVE_INCREMENT, 1)
        self.assertEqual(AIMD_DECREASE_FACTOR, 0.75)
        self.assertEqual(AIMD_MIN_CONCURRENCY, 1)
        self.assertEqual(AIMD_MAX_CONCURRENCY, 25)


if __name__ == '__main__':
    unittest.main()
