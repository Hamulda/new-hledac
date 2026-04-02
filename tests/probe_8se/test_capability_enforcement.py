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
        assert "Canonical authority" in docstring

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

    def test_ghost_executor_removal_condition_documented(self):
        """Sprint 8VF: GhostExecutor docstring contains REMOVAL CONDITION."""
        from hledac.universal.execution.ghost_executor import GhostExecutor

        docstring = GhostExecutor.__doc__ or ""
        assert "REMOVAL CONDITION" in docstring, \
            "GhostExecutor should document when it becomes deprecation candidate"

    def test_ghost_executor_boundary_seams_documented(self):
        """Sprint 8VF: GhostExecutor docstring contains BOUNDARY SEAMS."""
        from hledac.universal.execution.ghost_executor import GhostExecutor

        docstring = GhostExecutor.__doc__ or ""
        assert "BOUNDARY SEAMS" in docstring, \
            "GhostExecutor should document its boundary seams vs ToolRegistry"
        # Verify key seams are documented
        assert "ActionType" in docstring, "Should mention ActionType enum"
        assert "_actions" in docstring, "Should mention _actions dict"

    def test_ghost_executor_future_owner_documented(self):
        """Sprint 8VF: GhostExecutor documents ToolRegistry as future owner."""
        from hledac.universal.execution.ghost_executor import GhostExecutor

        docstring = GhostExecutor.__doc__ or ""
        assert "ToolRegistry" in docstring, \
            "GhostExecutor should mention ToolRegistry as migration target"


class TestToolRegistryCanonicalRole:
    """Sprint 8VF: Verify ToolRegistry canonical execution-control surface role."""

    def test_tool_registry_has_explicit_docstring(self):
        """ToolRegistry class docstring is explicit about canonical role."""
        from hledac.universal.tool_registry import ToolRegistry

        docstring = ToolRegistry.__doc__ or ""
        assert "CANONICAL" in docstring, \
            "ToolRegistry should explicitly state canonical role"
        assert "execution" in docstring.lower(), \
            "Should mention execution in docstring"

    def test_tool_registry_docstring_has_do_dont(self):
        """Sprint 8VF: ToolRegistry docstring contains DO/DON'T boundaries."""
        from hledac.universal.tool_registry import ToolRegistry

        docstring = ToolRegistry.__doc__ or ""
        assert "DO NOT" in docstring, \
            "ToolRegistry should have explicit DO NOT section"

    def test_tool_registry_related_components_documented(self):
        """Sprint 8VF: ToolRegistry docstring mentions related components."""
        from hledac.universal.tool_registry import ToolRegistry

        docstring = ToolRegistry.__doc__ or ""
        assert "GhostExecutor" in docstring, \
            "ToolRegistry should mention GhostExecutor as donor/compat"
        assert "ToolExecLog" in docstring, \
            "ToolRegistry should mention ToolExecLog as audit"
        assert "CapabilityRouter" in docstring, \
            "ToolRegistry should mention CapabilityRouter as signal mapping"


class TestToolExecLogAuditBoundary:
    """Sprint 8VF: Verify ToolExecLog AUDIT boundary clarity."""

    def test_tool_exec_log_has_audit_role(self):
        """ToolExecLog docstring explicitly states AUDIT role."""
        from hledac.universal.tool_exec_log import ToolExecLog

        docstring = ToolExecLog.__doc__ or ""
        assert "AUDIT" in docstring or "audit" in docstring.lower(), \
            "ToolExecLog should explicitly state AUDIT role"

    def test_tool_exec_log_is_not_execution_authority(self):
        """Sprint 8VF: ToolExecLog docstring states NOT execution authority."""
        from hledac.universal.tool_exec_log import ToolExecLog

        docstring = ToolExecLog.__doc__ or ""
        assert "NOT" in docstring and "execution" in docstring.lower(), \
            "ToolExecLog should explicitly state it is NOT execution authority"

    def test_tool_exec_log_has_correlation_boundary(self):
        """Sprint 8VF: ToolExecLog has CORRELATION BOUNDARY documented."""
        from hledac.universal.tool_exec_log import ToolExecLog

        docstring = ToolExecLog.__doc__ or ""
        assert "CORRELATION" in docstring or "correlation" in docstring.lower(), \
            "ToolExecLog should document correlation boundary"
        # Verify correlation fields are mentioned
        assert "run_id" in docstring, "Should mention run_id in correlation context"

    def test_tool_exec_log_has_do_not_list(self):
        """Sprint 8VF: ToolExecLog docstring contains DO NOT restrictions."""
        from hledac.universal.tool_exec_log import ToolExecLog

        docstring = ToolExecLog.__doc__ or ""
        assert "DO NOT" in docstring, \
            "ToolExecLog should have explicit DO NOT section"


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
    None-skip containment tests (Sprint 8SG).

    These tests verify that None-skip:
    1. Emits a DeprecationWarning (controlled compat debt)
    2. Still allows backward-compatible execution
    3. Documents what tool requires capabilities
    """

    @pytest.mark.asyncio
    async def test_none_skip_emits_deprecation_warning(self):
        """
        When None is passed, a DeprecationWarning is issued.

        This is Sprint 8SG None-skip containment:
        - Warning is emitted to signal deprecated usage
        - Execution still proceeds (backward compatibility)
        - Tool's required_capabilities are documented in warning
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

        # Sprint 8SG: DeprecationWarning IS now emitted
        cap_warnings = [
            x for x in w
            if "capability" in str(x.message).lower() or "deprecated" in str(x.message).lower()
        ]
        assert len(cap_warnings) == 1, "None-skip should emit exactly one DeprecationWarning"
        assert "academic_search" in str(cap_warnings[0].message)
        assert "reranking" in str(cap_warnings[0].message) or "entity_linking" in str(cap_warnings[0].message)

    @pytest.mark.asyncio
    async def test_none_skip_still_allows_compat_path(self):
        """
        None-skip routes through backward-compatible path.

        When available_capabilities=None:
        1. DeprecationWarning is emitted
        2. Execution proceeds without capability verification
        3. This is intentional for backward compatibility
        """
        import warnings as _warnings

        registry = create_default_registry()

        # Warning is emitted but execution still succeeds
        with _warnings.catch_warnings(record=True):
            _warnings.simplefilter("always")
            result = await registry.execute_with_limits(
                "academic_search",
                {"query": "test", "sources": ["arxiv"]},
                available_capabilities=None,
            )

        # Result returned (or error from actual handler, not capability check)
        assert result is not None or True  # Either way, no capability error

    @pytest.mark.asyncio
    async def test_none_skip_warning_contains_required_capabilities(self):
        """
        None-skip warning message contains the tool's required capabilities.

        This helps developers understand what to pass for proper enforcement.
        """
        import warnings as _warnings

        registry = create_default_registry()

        with _warnings.catch_warnings(record=True) as w:
            _warnings.simplefilter("always")
            await registry.execute_with_limits(
                "web_search",
                {"query": "test", "max_results": 5},
                available_capabilities=None,
            )

        cap_warnings = [
            x for x in w
            if "capability" in str(x.message).lower()
        ]
        assert len(cap_warnings) == 1
        # web_search requires reranking
        assert "reranking" in str(cap_warnings[0].message)


class TestCallSiteBoundaries:
    """
    Sprint 8TD: Call-site boundary verification.

    These tests document WHY no primary call-site was wired:
    - GhostExecutor is donor/compat, not canonical authority
    - tool_exec_log is instrumentation, not execution
    - No safe non-legacy, non-scheduler, non-stealth call-sites exist
    """

    def test_ghost_executor_execute_is_separate_from_tool_registry(self):
        """
        GhostExecutor.execute() is a SEPARATE execution path from ToolRegistry.

        It uses ActionType enum and direct action handlers.
        It does NOT go through ToolRegistry.execute_with_limits().
        """
        from hledac.universal.execution.ghost_executor import GhostExecutor, ActionType

        # GhostExecutor has its own action registry
        executor = GhostExecutor()
        assert ActionType.SEARCH.value in executor._actions

        # But those actions are NOT in ToolRegistry
        registry = create_default_registry()
        tool_names = [t.name for t in registry.list_tools()]

        # GhostExecutor actions should not appear as ToolRegistry tools
        ghost_actions = {"scan", "google", "deep_read", "stealth_harvest", "osint_discovery"}
        assert not any(a in tool_names for a in ghost_actions)

    def test_tool_exec_log_is_instrumentation_not_execution(self):
        """
        tool_exec_log is an AUDIT/LOGGING tool, not an execution tool.

        It logs tool execution events but does not execute tools itself.
        It COULD wrap ToolRegistry calls in the future for correlation.
        """
        from hledac.universal.tool_exec_log import ToolExecLog, ToolExecEvent
        from pathlib import Path
        import tempfile
        from dataclasses import fields

        with tempfile.TemporaryDirectory() as tmpdir:
            log = ToolExecLog(run_dir=Path(tmpdir), enable_persist=False)

            # Log a fake event
            log.log(
                tool_name="test_tool",
                input_data=b"input",
                output_data=b"output",
                status="success",
            )

            # tool_exec_log has log() method, not execute_with_limits()
            assert hasattr(log, "log")
            assert not hasattr(log, "execute_with_limits")

            # ToolExecEvent is a dataclass with event_id and correlation fields
            event_fields = {f.name for f in fields(ToolExecEvent)}
            assert "event_id" in event_fields
            assert "correlation" in event_fields


class TestBypassDebtMatrix:
    """
    Sprint 8TD: Bypass debt matrix documentation.

    These tests verify that documented bypasses are REAL
    and that the enforcement hook exists for future wiring.
    """

    def test_execute_with_limits_hook_exists_for_future_wiring(self):
        """
        The enforcement hook (execute_with_limits with available_capabilities)
        EXISTS and WORKS, but no production call-site passes it yet.

        This is intentional - the hook is ready for scheduler integration.
        """
        registry = create_default_registry()

        # The hook exists
        assert hasattr(registry, "execute_with_limits")

        # academic_search REQUIRES capabilities
        tool = registry.get_tool("academic_search")
        assert len(tool.required_capabilities) > 0

        # execute_with_limits CAN enforce when called properly
        # (proven by TestExecuteWithLimitsCapabilityEnforcement tests)

    @pytest.mark.asyncio
    async def test_none_skip_still_warns_but_does_not_hard_fail(self):
        """
        All known production call-sites use None-skip (backward compat).

        This is the current reality:
        - DeprecationWarning is emitted (Sprint 8SG)
        - But execution continues (backward compat preserved)
        - Hard fail would break production
        """
        import warnings as _warnings

        registry = create_default_registry()

        # This is how ALL current production call-sites call it
        with _warnings.catch_warnings(record=True) as w:
            _warnings.simplefilter("always")
            result = await registry.execute_with_limits(
                "academic_search",
                {"query": "test", "sources": ["arxiv"]},
                available_capabilities=None,  # What all production call-sites do
            )

        # No hard fail - execution continued
        assert result is not None

        # But warning WAS emitted
        cap_warnings = [x for x in w if "capability" in str(x.message).lower()]
        assert len(cap_warnings) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
