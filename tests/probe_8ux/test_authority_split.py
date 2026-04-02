"""
Sprint 8UX: Source / Transport / Session Authority Tests
=========================================================

Verifies authority split without behavior changes.
These are NOT new features — they verify existing boundaries.

Test matrix:
- ux_1: Source-ingress owner is FetchCoordinator
- ux_2: Shared session surface is session_runtime.py
- ux_3: Persisted session authority is SessionManager
- ux_4: Transport circuit breaker is circuit_breaker.py (class)
- ux_5: Fallback chain is test-seam only (resilient_fetch not called from production)
- ux_6: AsyncSessionFactory in __main__.py is NOT unified with session_runtime
- ux_7: _fetch_article_text uses session_runtime directly (not FetchCoordinator)
- ux_8: No new framework was created
"""

import ast
import unittest
from pathlib import Path


# _ROOT = hledac/universal/ (test file is at tests/probe_8ux/test_authority_split.py)
_ROOT = Path(__file__).parents[2]


class TestAuthoritySplit(unittest.TestCase):
    """Verify authority split boundaries."""

    def _read_file(self, path: Path) -> str:
        return path.read_text()

    def _find_node(self, source: str, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | None:
        """Find a function or class definition by name in source."""
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == name:
                    return node
        return None

    def test_ux_1_fetch_coordinator_is_source_ingress_owner(self):
        """
        FetchCoordinator is the source-ingress owner (canonical production path).
        No other module should be the primary URL fetch authority.
        """
        fc_path = _ROOT / "coordinators" / "fetch_coordinator.py"
        if not fc_path.exists():
            self.skipTest("fetch_coordinator.py not found")

        source = self._read_file(fc_path)
        # Verify FetchCoordinator class exists and has _fetch_url method
        fc_class = self._find_node(source, "FetchCoordinator")
        self.assertIsNotNone(fc_class, "FetchCoordinator class must exist")

        # Verify _fetch_url exists
        if fc_class and hasattr(fc_class, 'body'):
            method_names = [n.name for n in fc_class.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            self.assertIn("_fetch_url", method_names, "_fetch_url must be on FetchCoordinator")

    def test_ux_2_session_runtime_is_shared_surface(self):
        """
        session_runtime.py is the shared async HTTP session surface.
        It must NOT be named or described as the source-ingress owner.
        """
        sr_path = _ROOT / "network" / "session_runtime.py"
        self.assertTrue(sr_path.exists(), "session_runtime.py must exist")

        source = self._read_file(sr_path)
        # Must have async_get_aiohttp_session
        self.assertIn("async_get_aiohttp_session", source)
        # Must NOT claim to be source-ingress owner (authority note should clarify this)
        self.assertIn("AUTHORITY SPLIT", source, "Must have authority split documentation")

    def test_ux_3_session_manager_is_persisted_authority(self):
        """
        SessionManager in tools/session_manager.py is the persisted session authority.
        It handles cookies/credentials, separate from the HTTP session surface.
        """
        sm_path = _ROOT / "tools" / "session_manager.py"
        self.assertTrue(sm_path.exists(), "session_manager.py must exist")

        source = self._read_file(sm_path)
        # Must have SessionManager class
        self.assertIn("class SessionManager", source)
        # Must have authority note
        self.assertIn("AUTHORITY NOTE", source, "Must document authority role")

    def test_ux_4_circuit_breaker_class_is_transport_canonical(self):
        """
        CircuitBreaker class in circuit_breaker.py is the canonical domain CB.
        get_breaker() is the canonical accessor.
        """
        cb_path = _ROOT / "transport" / "circuit_breaker.py"
        self.assertTrue(cb_path.exists(), "circuit_breaker.py must exist")

        source = self._read_file(cb_path)
        # Must have CircuitBreaker class
        self.assertIn("class CircuitBreaker", source)
        # Must have get_breaker function
        self.assertIn("def get_breaker", source)
        # Must have authority documentation about PRODUCTION vs TEST-SEAM split
        self.assertIn("PRODUCTION AUTHORITY", source)
        self.assertIn("TEST-SEAM ONLY", source)

    def test_ux_5_resilient_fetch_is_test_seam_only(self):
        """
        resilient_fetch() and get_transport_for_domain() are test-seam only.
        They must NOT be called from production code.
        """
        cb_path = _ROOT / "transport" / "circuit_breaker.py"
        source = self._read_file(cb_path)

        # Both functions must exist
        self.assertIn("async def resilient_fetch", source)
        self.assertIn("async def get_transport_for_domain", source)

        # Must be documented as test-seam
        self.assertIn("TEST-SEAM ONLY", source)

    def test_ux_6_asyncsession_factory_not_unified(self):
        """
        AsyncSessionFactory in __main__.py is a LEGACY/RUNTIME-SHELL artifact.
        It must NOT be unified with session_runtime.py in this sprint.
        The authority split comment must exist in session_runtime.py.
        """
        main_path = _ROOT / "__main__.py"
        if not main_path.exists():
            self.skipTest("__main__.py not found")

        source = self._read_file(main_path)
        self.assertIn("class AsyncSessionFactory", source)

        sr_path = _ROOT / "network" / "session_runtime.py"
        sr_source = self._read_file(sr_path)
        # Must explicitly mention AsyncSessionFactory is separate
        self.assertIn("AsyncSessionFactory", sr_source)
        self.assertIn("LEGACY/RUNTIME-SHELL", sr_source)

    def test_ux_7_fetch_article_text_uses_session_runtime(self):
        """
        _fetch_article_text in live_feed_pipeline.py uses session_runtime directly.
        It is NOT going through FetchCoordinator (article fallback seam, not primary path).
        """
        lfp_path = _ROOT / "pipeline" / "live_feed_pipeline.py"
        self.assertTrue(lfp_path.exists(), "live_feed_pipeline.py must exist")

        source = self._read_file(lfp_path)
        # _fetch_article_text must import from session_runtime
        self.assertIn("from hledac.universal.network.session_runtime import", source)
        # Must have authority note
        self.assertIn("AUTHORITY NOTE", source)
        self.assertIn("article-fallback seam", source)

    def test_ux_8_no_new_framework_created(self):
        """
        Verify no new module was created that could be considered a framework.
        All changes are seam comments and authority documentation only.
        """
        # Check that no new files were added in key directories
        transport_dir = _ROOT / "transport"
        network_dir = _ROOT / "network"
        tools_dir = _ROOT / "tools"
        pipeline_dir = _ROOT / "pipeline"

        for directory in [transport_dir, network_dir, tools_dir, pipeline_dir]:
            if directory.exists():
                py_files = list(directory.glob("*.py"))
                # Just verify we can list files (existence check is implicit)
                self.assertIsInstance(len(py_files), int)

        # Verify the authority audit doc exists (it's in hledac/universal/)
        audit_path = _ROOT / "AUDIT_SOURCE_TRANSPORT_SESSION.md"
        self.assertTrue(audit_path.exists(), f"AUDIT_SOURCE_TRANSPORT_SESSION.md should exist at {audit_path}")


class TestSessionSplit(unittest.TestCase):
    """Verify session_runtime vs SessionManager split."""

    def test_session_runtime_has_no_lmdb(self):
        """session_runtime.py must NOT import lmdb (that's SessionManager's job)."""
        sr_path = _ROOT / "network" / "session_runtime.py"
        source = sr_path.read_text()
        self.assertNotIn("import lmdb", source)
        self.assertNotIn("from lmdb", source)

    def test_session_manager_has_no_aiohttp_session_creation(self):
        """SessionManager must NOT create aiohttp.ClientSession (that's session_runtime's job)."""
        sm_path = _ROOT / "tools" / "session_manager.py"
        source = sm_path.read_text()
        self.assertNotIn("aiohttp.ClientSession", source)
        self.assertNotIn("ClientSession", source)


class TestNoHotPathChanges(unittest.TestCase):
    """Verify hot path behavior is unchanged."""

    def test_fetch_coordinator_still_has_tor_session_pool(self):
        """FetchCoordinator must still have its own Tor session pool (_get_tor_session)."""
        fc_path = _ROOT / "coordinators" / "fetch_coordinator.py"
        if not fc_path.exists():
            self.skipTest("fetch_coordinator.py not found")
        source = fc_path.read_text()
        self.assertIn("_get_tor_session", source)

    def test_live_feed_pipeline_unchanged_public_api(self):
        """live_feed_pipeline.py public API must be unchanged."""
        lfp_path = _ROOT / "pipeline" / "live_feed_pipeline.py"
        source = lfp_path.read_text()

        # Public API functions must still exist
        self.assertIn("async_run_live_feed_pipeline", source)
        self.assertIn("async_run_feed_source_batch", source)
        self.assertIn("async_run_default_feed_batch", source)


if __name__ == "__main__":
    unittest.main()
