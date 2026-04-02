"""Sprint 8TH: STIX degradation is no longer silent.

Probe test — NOT a unit test.
Locks invariants:
  1. DuckPGQGraph lacks export_stix_bundle → _stix_status="unavailable", _stix_reason mentions backend name
  2. IOCGraph has export_stix_bundle → _stix_status="available" when nodes exist
  3. synthesis_runner._build_stix_context() NEVER returns empty with unknown state
  4. Sprint 8VQ: Priority 1 (_stix_graph) before Priority 2 (_ioc_graph)
"""

import tempfile

import pytest

from hledac.universal.brain.synthesis_runner import SynthesisRunner
from hledac.universal.graph.quantum_pathfinder import DuckPGQGraph
from hledac.universal.knowledge.ioc_graph import IOCGraph


class _SynthesisRunnerProbe(SynthesisRunner):
    """Probe subclass exposing _build_stix_context structured state."""

    @property
    def stix_status(self) -> str:
        return self._stix_status

    @property
    def stix_reason(self) -> str:
        return self._stix_reason

    @property
    def stix_backend(self) -> str:
        return self._stix_backend


@pytest.mark.asyncio
async def test_duckpgq_graph_lacks_export_stix_bundle():
    """
    PROBE: DuckPGQGraph lacks export_stix_bundle (Priority 2 path).

    When DuckPGQGraph is injected (no _stix_graph set) and
    _build_stix_context is called, status MUST be 'unavailable'
    with a reason that names the backend.
    """
    with tempfile.TemporaryDirectory() as tmp:
        graph = DuckPGQGraph(db_path=f"{tmp}/probe.duckdb")
        graph.add_ioc("1.2.3.4", "ip")

        runner = _SynthesisRunnerProbe.__new__(_SynthesisRunnerProbe)
        runner._stix_graph = None  # Sprint 8VQ: Priority 1 is None
        runner._ioc_graph = graph   # Priority 2 fallback
        runner._stix_status = "unknown"
        runner._stix_reason = ""
        runner._stix_backend = ""

        result = await runner._build_stix_context()

        assert result == "", f"Expected empty string, got: {result!r}"
        assert runner.stix_status == "unavailable", (
            f"Expected status='unavailable', got: {runner.stix_status!r}"
        )
        assert "DuckPGQGraph" in runner.stix_reason, (
            f"Reason must name the backend. Got: {runner.stix_reason!r}"
        )
        assert runner.stix_backend == "DuckPGQGraph", (
            f"Expected stix_backend='DuckPGQGraph', got: {runner.stix_backend!r}"
        )


@pytest.mark.asyncio
async def test_ioc_graph_has_export_stix_bundle():
    """
    PROBE: IOCGraph (truth store) via Priority 1 (_stix_graph).

    When IOCGraph is injected via _stix_graph (not _ioc_graph) and has IOCs,
    status MUST be 'available' via Priority 1 path.
    """
    with tempfile.TemporaryDirectory() as tmp:
        graph = IOCGraph(db_path=f"{tmp}/probe_kuzu")
        await graph.initialize()
        await graph.upsert_ioc("ip", "5.6.7.8")
        await graph.upsert_ioc("domain", "truth-store.test")

        runner = _SynthesisRunnerProbe.__new__(_SynthesisRunnerProbe)
        runner._stix_graph = graph  # Sprint 8VQ: Priority 1
        runner._ioc_graph = None     # Not used in Priority 1
        runner._stix_status = "unknown"
        runner._stix_reason = ""
        runner._stix_backend = ""

        result = await runner._build_stix_context()

        assert result != "", "Expected non-empty STIX context with real IOCs"
        assert runner.stix_status == "available", (
            f"Expected status='available', got: {runner.stix_status!r}. Reason: {runner.stix_reason!r}"
        )
        assert runner.stix_backend == "IOCGraph", (
            f"Expected stix_backend='IOCGraph', got: {runner.stix_backend!r}"
        )
        assert "stix_graph" in runner.stix_reason.lower(), (
            f"Priority 1 path reason should mention stix_graph. Got: {runner.stix_reason!r}"
        )
        await graph.close()


@pytest.mark.asyncio
async def test_none_graph_sets_unavailable():
    """PROBE: When both _stix_graph and _ioc_graph are None, status must be 'unavailable' with reason."""
    runner = _SynthesisRunnerProbe.__new__(_SynthesisRunnerProbe)
    runner._stix_graph = None
    runner._ioc_graph = None
    runner._stix_status = "unknown"
    runner._stix_reason = ""
    runner._stix_backend = ""

    result = await runner._build_stix_context()

    assert result == ""
    assert runner.stix_status == "unavailable", runner.stix_status
    assert runner.stix_reason != "", "Reason must be set — no silent degradation"
    assert "None" in runner.stix_reason or "none" in runner.stix_reason.lower(), (
        f"Reason should mention that both graphs are None. Got: {runner.stix_reason!r}"
    )


@pytest.mark.asyncio
async def test_ioc_graph_no_nodes_available_empty():
    """
    PROBE: IOCGraph via Priority 1 with 0 nodes.
    Status should be 'available' with empty-friendly reason.
    """
    with tempfile.TemporaryDirectory() as tmp:
        graph = IOCGraph(db_path=f"{tmp}/probe_empty")
        await graph.initialize()
        # graph is empty — no upserts

        runner = _SynthesisRunnerProbe.__new__(_SynthesisRunnerProbe)
        runner._stix_graph = graph  # Sprint 8VQ: Priority 1
        runner._ioc_graph = None
        runner._stix_status = "unknown"
        runner._stix_reason = ""
        runner._stix_backend = ""

        result = await runner._build_stix_context()

        assert result == ""
        assert runner.stix_status == "available", runner.stix_status
        assert "empty" in runner.stix_reason.lower(), (
            f"Expected 'empty' in reason, got: {runner.stix_reason!r}"
        )
        await graph.close()
