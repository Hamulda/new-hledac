"""
Sprint 8UD B.8: AsyncSessionFactory returns aiohttp.ClientSession

Verifies get_session() returns ClientSession not AbstractEventLoop.
"""
import asyncio
import unittest
from unittest.mock import patch, MagicMock, AsyncMock


class TestAsyncSessionFactory(unittest.TestCase):
    """Test AsyncSessionFactory returns aiohttp.ClientSession."""

    def test_factory_returns_client_session_type(self):
        """get_session returns aiohttp.ClientSession instance."""
        import aiohttp

        factory = None  # Will be created by importing

        # Reset singleton for test isolation
        from hledac.universal.__main__ import AsyncSessionFactory
        AsyncSessionFactory._instance = None
        AsyncSessionFactory._session = None
        AsyncSessionFactory._lock = None

        factory = AsyncSessionFactory()

        async def run_test():
            session = await factory.get_session()
            self.assertIsInstance(session, aiohttp.ClientSession)
            self.assertFalse(session.closed)
            await factory.close_session()

        asyncio.run(run_test())

    def test_factory_no_new_event_loop_created(self):
        """get_session does NOT create a new event loop."""
        from hledac.universal.__main__ import AsyncSessionFactory

        # Reset singleton
        AsyncSessionFactory._instance = None
        AsyncSessionFactory._session = None
        AsyncSessionFactory._lock = None

        factory = AsyncSessionFactory()

        new_event_loop_calls = []

        original_new_event_loop = asyncio.new_event_loop

        def track_new_event_loop(*args, **kwargs):
            new_event_loop_calls.append(True)
            return original_new_event_loop(*args, **kwargs)

        async def run_test():
            with patch('asyncio.new_event_loop', side_effect=track_new_event_loop):
                await factory.get_session()

        asyncio.run(run_test())

        # Should NOT have called new_event_loop (should use existing loop)
        self.assertEqual(len(new_event_loop_calls), 0,
                        "get_session should not create new event loop")

    def test_factory_close_session(self):
        """close_session properly closes the ClientSession."""
        from hledac.universal.__main__ import AsyncSessionFactory

        # Reset singleton
        AsyncSessionFactory._instance = None
        AsyncSessionFactory._session = None
        AsyncSessionFactory._lock = None

        factory = AsyncSessionFactory()

        async def run_test():
            session = await factory.get_session()
            await factory.close_session()
            self.assertTrue(session.closed or AsyncSessionFactory._session is None)

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
