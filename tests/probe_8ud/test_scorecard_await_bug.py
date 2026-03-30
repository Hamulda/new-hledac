"""
Sprint 8UD B.1: P0 await bug fix for _print_scorecard_report()

Verifies that _print_scorecard_report() is awaited in sprint_mode.
"""
import asyncio
import inspect
import unittest
from unittest.mock import MagicMock


class TestScorecardAwaitBug(unittest.TestCase):
    """Test that _print_scorecard_report is awaited (P0 fix)."""

    def test_print_scorecard_report_is_async_def(self):
        """Verify _print_scorecard_report is declared as async def."""
        from hledac.universal.__main__ import _print_scorecard_report

        self.assertTrue(
            inspect.iscoroutinefunction(_print_scorecard_report),
            "_print_scorecard_report must be async def"
        )

    def test_print_scorecard_is_awaitable(self):
        """Verify _print_scorecard_report returns a coroutine."""
        from hledac.universal.__main__ import _print_scorecard_report

        mock_target = MagicMock()
        mock_target.sprint_id = "TEST-8UD-001"

        coro = _print_scorecard_report(mock_target, None, sprint_report={})
        self.assertTrue(asyncio.iscoroutine(coro))

        # Run and close without awaiting (store is None, just tests type)
        coro.close()

    def test_await_in_sprint_mode_code(self):
        """Verify sprint_mode calls _print_scorecard_report with await."""
        with open("/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/__main__.py") as f:
            source = f.read()

        lines = source.split('\n')
        found_await = False
        for i, line in enumerate(lines):
            if '_print_scorecard_report' in line and 'DONE' not in line and 'def ' not in line:
                stripped = line.strip()
                if stripped.startswith('await _print_scorecard_report'):
                    found_await = True
                    break

        self.assertTrue(found_await, "Found 'await _print_scorecard_report' call in __main__.py")


if __name__ == "__main__":
    unittest.main()
