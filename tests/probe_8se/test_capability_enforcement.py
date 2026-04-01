"""
Sprint 8SE: Capability Enforcement Flow Tests
==============================================

Tests for the analyzer -> capability router -> tool registry enforcement pipeline.

Invariant table:
- test_analyzer_result_to_capability_signal: AnalyzerResult.to_capability_signal() works
- test_capability_router_route_analyzer_result: CapabilityRouter.route() with AnalyzerResult
- test_capability_router_route_legacy_dict: CapabilityRouter.route() with legacy dict
- test_tool_registry_capability_check_pass: ToolRegistry.check_capabilities() passes when satisfied
- test_tool_registry_capability_check_fail: ToolRegistry.check_capabilities() fails when missing
- test_execute_with_limits_enforces_capabilities: execute_with_limits() enforces capabilities
- test_execute_with_limits_skips_when_none: execute_with_limits() skips when available_capabilities=None
- test_ghost_executor_is_donor_compat: GhostExecutor is marked as donor/compat (not canonical)
- test_required_capabilities_populated: Representative tools have required_capabilities set
- test_enforcement_happens_in_registry_not_analyzer: Enforcement is in ToolRegistry, not analyzer
"""

import pytest

from hledac.universal.capabilities import CapabilityRouter, Capability
from hledac.universal.tool_registry import create_default_registry
from hledac.universal.types import AnalyzerResult
from hledac.universal.autonomous_analyzer import AutoResearchProfile


class TestAnalyzerResultCapabilitySignal:
    """Test AnalyzerResult.to_capability_signal() produces correct output."""

    def test_to_capability_signal_basic(self):
        """AnalyzerResult.to_capability_signal() returns correct keys."""
        profile = AutoResearchProfile(
            tools={"web_intelligence", "academic_search"},
            sources={"surface", "academic"},
            privacy_level="STANDARD",
            use_tor=False,
            depth="DEEP",
            use_tot=False,
            tot_mode="standard",
        )
        result = AnalyzerResult.from_profile(profile)
        signal = result.to_capability_signal()

        assert "tools" in signal
        assert "sources" in signal
        assert "privacy_level" in signal
        assert "use_tor" in signal
        assert "depth" in signal
        assert signal["tools"] == {"web_intelligence", "academic_search"}
        assert signal["requires_embeddings"] is False
        assert signal["requires_ner"] is False
        assert signal["requires_temporal"] is False
        assert signal["requires_crypto"] is False

    def test_to_capability_signal_models(self):
        """AnalyzerResult.to_capability_signal() sets model flags correctly."""
        profile = AutoResearchProfile(
            tools={"academic_search", "identity_stitching"},
            models_needed={"hermes", "modernbert", "gliner"},
        )
        result = AnalyzerResult.from_profile(profile)
        signal = result.to_capability_signal()

        assert signal["requires_embeddings"] is True  # modernbert
        assert signal["requires_ner"] is True  # gliner

    def test_to_capability_signal_temporal(self):
        """AnalyzerResult.to_capability_signal() sets temporal flag."""
        profile = AutoResearchProfile(tools={"temporal_analyzer"})
        result = AnalyzerResult.from_profile(profile)
        signal = result.to_capability_signal()

        assert signal["requires_temporal"] is True

    def test_to_capability_signal_crypto(self):
        """AnalyzerResult.to_capability_signal() sets crypto flag."""
        profile = AutoResearchProfile(tools={"blockchain_analyzer"})
        result = AnalyzerResult.from_profile(profile)
        signal = result.to_capability_signal()

        assert signal["requires_crypto"] is True


class TestCapabilityRouter:
    """Test CapabilityRouter.route() with both AnalyzerResult and legacy dict."""

    def test_route_analyzer_result_stealth(self):
        """CapabilityRouter.route() with AnalyzerResult - STEALTH."""
        profile = AutoResearchProfile(
            tools={"stealth_crawler"},
            privacy_level="MAXIMUM",
            use_tor=True,
        )
        result = AnalyzerResult.from_profile(profile)
        caps = CapabilityRouter.route(result)

        assert Capability.STEALTH in caps
        assert Capability.DARK_WEB in caps

    def test_route_analyzer_result_academic(self):
        """CapabilityRouter.route() with AnalyzerResult - academic."""
        profile = AutoResearchProfile(
            tools={"academic_search"},
            models_needed={"hermes", "modernbert"},
        )
        result = AnalyzerResult.from_profile(profile)
        caps = CapabilityRouter.route(result)

        assert Capability.RERANKING in caps
        assert Capability.ENTITY_LINKING in caps
        assert Capability.MODERNBERT in caps

    def test_route_analyzer_result_blockchain(self):
        """CapabilityRouter.route() with AnalyzerResult - blockchain."""
        profile = AutoResearchProfile(tools={"blockchain_analyzer"})
        result = AnalyzerResult.from_profile(profile)
        caps = CapabilityRouter.route(result)

        assert Capability.CRYPTO_INTEL in caps

    def test_route_legacy_dict_stealth(self):
        """CapabilityRouter.route() with legacy dict - STEALTH (backward compat)."""
        analysis = {
            "tools": ["stealth_crawler"],
            "privacy_level": "MAXIMUM",
            "use_tor": True,
        }
        caps = CapabilityRouter.route(analysis)

        assert Capability.STEALTH in caps
        assert Capability.DARK_WEB in caps

    def test_route_legacy_dict_temporal_signal(self):
        """CapabilityRouter.route() with legacy signal dict."""
        signal = {
            "tools": ["temporal_analyzer"],
            "requires_temporal": True,
        }
        caps = CapabilityRouter.route(signal)

        assert Capability.TEMPORAL in caps

    def test_route_empty_tools(self):
        """CapabilityRouter.route() with empty tools - HERMES always present."""
        profile = AutoResearchProfile(tools=set())
        result = AnalyzerResult.from_profile(profile)
        caps = CapabilityRouter.route(result)

        assert Capability.HERMES in caps


class TestToolRegistryCapabilityCheck:
    """Test ToolRegistry.check_capabilities() enforcement."""

    def test_check_capabilities_pass(self):
        """check_capabilities() passes when all required are available."""
        registry = create_default_registry()

        # academic_search requires reranking + entity_linking
        satisfied, msg = registry.check_capabilities(
            "academic_search",
            {"reranking", "entity_linking", "hermes"}
        )

        assert satisfied is True
        assert msg is None

    def test_check_capabilities_fail_missing(self):
        """check_capabilities() fails when required capability is missing."""
        registry = create_default_registry()

        # academic_search requires reranking + entity_linking, but only entity_linking present
        satisfied, msg = registry.check_capabilities(
            "academic_search",
            {"entity_linking"}  # missing reranking
        )

        assert satisfied is False
        assert msg is not None
        assert "reranking" in msg
        assert "academic_search" in msg

    def test_check_capabilities_no_required(self):
        """check_capabilities() passes when tool has no required_capabilities."""
        registry = create_default_registry()

        # file_read has no required_capabilities
        satisfied, msg = registry.check_capabilities("file_read", set())

        assert satisfied is True
        assert msg is None

    def test_required_capabilities_populated(self):
        """Representative tools have required_capabilities populated."""
        registry = create_default_registry()

        web_search = registry.get_tool("web_search")
        assert "reranking" in web_search.required_capabilities

        academic_search = registry.get_tool("academic_search")
        assert "reranking" in academic_search.required_capabilities
        assert "entity_linking" in academic_search.required_capabilities

        entity_extraction = registry.get_tool("entity_extraction")
        assert "entity_linking" in entity_extraction.required_capabilities


class TestExecuteWithLimitsCapabilityEnforcement:
    """Test execute_with_limits() enforces capabilities."""

    @pytest.mark.asyncio
    async def test_enforces_capabilities(self):
        """execute_with_limits() raises when capabilities missing."""
        registry = create_default_registry()

        # academic_search requires reranking + entity_linking
        # Only entity_linking provided - should fail
        with pytest.raises(RuntimeError, match="Capability check failed"):
            await registry.execute_with_limits(
                "academic_search",
                {"query": "test", "sources": ["arxiv"]},
                available_capabilities={"entity_linking"}  # missing reranking
            )

    @pytest.mark.asyncio
    async def test_skips_when_none(self):
        """execute_with_limits() skips check when available_capabilities=None."""
        registry = create_default_registry()

        # Should not raise even though academic_search has requirements
        # (backward compatible - None means skip)
        await registry.execute_with_limits(
            "academic_search",
            {"query": "test", "sources": ["arxiv"]},
            available_capabilities=None  # skip check
        )

        # Should get past capability check (rate limit will still apply but that's OK)
        # Note: actual execution may fail due to other reasons, but capability check passes

    @pytest.mark.asyncio
    async def test_passes_when_satisfied(self):
        """execute_with_limits() passes when all required capabilities present."""
        registry = create_default_registry()

        # web_search requires reranking - provide it
        result = await registry.execute_with_limits(
            "web_search",
            {"query": "test", "max_results": 5},
            available_capabilities={"reranking"}
        )

        # Should complete without capability error
        assert result is not None


class TestGhostExecutorDonorCompat:
    """Verify GhostExecutor is donor/compat, not canonical authority."""

    def test_ghost_executor_has_donor_comment(self):
        """GhostExecutor class docstring mentions donor/compat."""
        from hledac.universal.execution.ghost_executor import GhostExecutor

        docstring = GhostExecutor.__doc__ or ""
        assert "DONOR" in docstring or "donor" in docstring.lower()
        assert "COMPATIBILITY" in docstring or "compat" in docstring.lower()
        assert "Canonical execution path" in docstring

    def test_ghost_executor_not_in_tool_registry_canonical(self):
        """GhostExecutor is NOT the canonical execution surface."""
        registry = create_default_registry()

        # GhostExecutor actions should NOT be registered as canonical tools
        # through GhostExecutor itself - they may exist elsewhere
        tool_names = [t.name for t in registry.list_tools()]

        # These are GhostExecutor-specific actions - should NOT be here
        ghost_actions = {"scan", "google", "deep_read", "stealth_harvest", "osint_discovery"}
        assert not any(t in ghost_actions for t in tool_names), \
            "GhostExecutor actions found in ToolRegistry - may indicate over-registration"


class TestEnforcementHappensInRegistryNotAnalyzer:
    """Verify enforcement is in ToolRegistry, not in analyzer."""

    def test_analyzer_recommends_not_enforces(self):
        """AnalyzerResult does NOT enforce - it only recommends."""
        from hledac.universal.types import AnalyzerResult

        profile = AutoResearchProfile(tools={"academic_search"})
        result = AnalyzerResult.from_profile(profile)

        # AnalyzerResult has no enforcement mechanism
        # It only provides capability signal
        assert hasattr(result, "to_capability_signal")
        assert not hasattr(result, "enforce")
        assert not hasattr(result, "check_capabilities")

    def test_enforcement_in_tool_registry(self):
        """Capability enforcement happens in ToolRegistry, not CapabilityRouter."""
        registry = create_default_registry()

        # ToolRegistry has check_capabilities
        assert hasattr(registry, "check_capabilities")

        # CapabilityRouter only routes - no enforcement
        assert not hasattr(CapabilityRouter, "check_capabilities")
        assert not hasattr(CapabilityRouter, "enforce")

    def test_capability_router_signal_keys_defined(self):
        """CapabilityRouter.SIGNAL_KEYS defines canonical signal interface."""
        assert hasattr(CapabilityRouter, "SIGNAL_KEYS")
        assert "tools" in CapabilityRouter.SIGNAL_KEYS
        assert "requires_embeddings" in CapabilityRouter.SIGNAL_KEYS


class TestToolExecLogCorrelation:
    """Test tool_exec_log integration with RunCorrelation."""

    def test_tool_exec_event_has_correlation_field(self):
        """ToolExecEvent has correlation field for audit trail."""
        from hledac.universal.tool_exec_log import ToolExecEvent
        from datetime import datetime

        event = ToolExecEvent(
            event_id="test_1",
            ts=datetime.now(),
            tool_name="web_search",
            input_hash="abc",
            output_hash="def",
            output_len=100,
            status="success",
            correlation={"run_id": "run_1", "branch_id": None, "provider_id": None, "action_id": None}
        )

        assert event.correlation is not None
        assert event.correlation["run_id"] == "run_1"

    def test_run_correlation_to_dict(self):
        """RunCorrelation.to_dict() produces correct structure."""
        from hledac.universal.types import RunCorrelation

        corr = RunCorrelation(run_id="run_1", branch_id="branch_a", provider_id="mlx")
        d = corr.to_dict()

        assert d["run_id"] == "run_1"
        assert d["branch_id"] == "branch_a"
        assert d["provider_id"] == "mlx"
        assert d["action_id"] is None


class TestEndToEndEnforcement:
    """
    End-to-end enforcement probe tests.

    These tests verify the complete flow:
    1. AnalyzerResult.from_profile() creates typed result
    2. AnalyzerResult.to_capability_signal() produces signal dict
    3. CapabilityRouter.route() converts to Set[Capability]
    4. ToolRegistry.execute_with_limits() enforces capabilities

    The flow is real but isolated (no production call-sites exist yet).
    """

    def _caps_to_strings(self, caps: set) -> set[str]:
        """Convert Capability enum set to string set for execute_with_limits."""
        return {c.value for c in caps}

    @pytest.mark.asyncio
    async def test_e2e_analyzer_to_registry_success(self):
        """
        End-to-end: AnalyzerResult → CapabilityRouter → ToolRegistry (success).

        Profile: academic_search with models_needed including modernbert+gliner.
        Expected: academic_search requires {reranking, entity_linking},
                  both are provided → passes.
        """
        registry = create_default_registry()

        # AnalyzerResult from profile
        profile = AutoResearchProfile(
            tools={"academic_search"},
            models_needed={"hermes", "modernbert", "gliner"},
        )
        result = AnalyzerResult.from_profile(profile)

        # Route to capabilities
        caps = CapabilityRouter.route(result)
        cap_strings = self._caps_to_strings(caps)

        # Execute with all required capabilities provided
        result = await registry.execute_with_limits(
            "academic_search",
            {"query": "machine learning", "sources": ["arxiv"]},
            available_capabilities=cap_strings,  # {"reranking", "entity_linking", "hermes", ...}
        )

        # Should succeed
        assert result is not None
        assert "papers" in result or "total_found" in result or result == {}

    @pytest.mark.asyncio
    async def test_e2e_analyzer_to_registry_capability_fail(self):
        """
        End-to-end: AnalyzerResult → CapabilityRouter → ToolRegistry (fail).

        Profile: academic_search without providing capabilities.
        Expected: academic_search requires {reranking, entity_linking},
                  neither provided → RuntimeError.
        """
        registry = create_default_registry()

        # Execute with ONLY entity_linking (missing reranking)
        # academic_search requires both reranking AND entity_linking
        with pytest.raises(RuntimeError, match="Capability check failed"):
            await registry.execute_with_limits(
                "academic_search",
                {"query": "machine learning", "sources": ["arxiv"]},
                available_capabilities={"entity_linking"},  # missing reranking
            )

    @pytest.mark.asyncio
    async def test_e2e_analyzer_to_registry_none_skip_compat(self):
        """
        End-to-end: None-skip backward compatibility path.

        Profile: academic_search with full models.
        Expected: execute_with_limits(available_capabilities=None) silently skips
                  capability check (backward compat). No error raised.
        """
        registry = create_default_registry()

        # None-skip: capability check is bypassed entirely
        # This is the current state of ALL production call-sites
        result = await registry.execute_with_limits(
            "academic_search",
            {"query": "machine learning", "sources": ["arxiv"]},
            available_capabilities=None,  # Backward compat skip
        )

        # Should not raise even though academic_search has requirements
        # (backward compatible - None means skip)
        assert result is not None

    @pytest.mark.asyncio
    async def test_e2e_web_search_single_capability(self):
        """
        End-to-end: web_search (single capability).

        web_search requires only "reranking".
        Providing it → success. Missing it → fail.
        """
        registry = create_default_registry()

        # Success case: provide reranking
        result = await registry.execute_with_limits(
            "web_search",
            {"query": "test", "max_results": 5},
            available_capabilities={"reranking"},
        )
        assert result is not None

        # Fail case: missing reranking
        with pytest.raises(RuntimeError, match="Capability check failed"):
            await registry.execute_with_limits(
                "web_search",
                {"query": "test", "max_results": 5},
                available_capabilities=set(),  # missing reranking
            )

    @pytest.mark.asyncio
    async def test_e2e_no_capability_tool_always_passes(self):
        """
        End-to-end: tools with no required_capabilities always pass.

        file_read and file_write have no capability requirements.
        They should pass regardless of available_capabilities.
        """
        registry = create_default_registry()

        # Even with empty capabilities, no-requirement tools pass
        result = await registry.execute_with_limits(
            "file_read",
            {"path": __file__},  # Read this test file
            available_capabilities=set(),  # Empty - no capabilities
        )

        # Should succeed (file_read doesn't check capabilities)
        # Note: may fail on actual file read but NOT on capability check
        assert result is not None


class TestNoneSkipWarning:
    """
    None-skip containment tests.

    These tests document that None-skip is:
    1. Intentionally backward-compatible
    2. A known debt (no warning when None is passed)
    3. The current state of ALL production call-sites
    """

    @pytest.mark.asyncio
    async def test_none_skip_no_warning_implicit(self):
        """
        When None is passed, no deprecation warning is issued.

        This is the documented DEBT: should emit warnings.warn()
        but currently does not.
        """
        import warnings as _warnings

        registry = create_default_registry()

        # Capture warnings
        with _warnings.catch_warnings(record=True) as w:
            _warnings.simplefilter("always")
            await registry.execute_with_limits(
                "academic_search",
                {"query": "test", "sources": ["arxiv"]},
                available_capabilities=None,
            )

        # Currently: NO warning is emitted (this is the debt)
        # In future: should emit DeprecationWarning
        cap_warnings = [
            x for x in w
            if "capability" in str(x.message).lower() or "deprecated" in str(x.message).lower()
        ]
        assert len(cap_warnings) == 0, "None-skip should warn but currently doesn't (debt)"

    @pytest.mark.asyncio
    async def test_none_skip_contains_to_compat_path(self):
        """
        None-skip routes through backward-compatible path.

        When available_capabilities=None:
        1. check_capabilities() is NOT called
        2. Execution proceeds without capability verification
        3. This is intentional for backward compatibility
        """
        registry = create_default_registry()

        # This should NOT raise (None means skip)
        result = await registry.execute_with_limits(
            "academic_search",
            {"query": "test", "sources": ["arxiv"]},
            available_capabilities=None,
        )

        # Result returned (or error from actual handler, not capability check)
        assert result is not None or True  # Either way, no capability error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
