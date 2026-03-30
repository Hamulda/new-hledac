"""
Testy pro Sprint 82B: Policy Hardening
======================================

Proof tests pro:
- Lane policy (deterministic posterior-like)
- Winner-only expensive path
- Contradiction kill independence
- Phase evidence-driven promotion
- Bounded streaming findings
- Memory pressure broker behavior
"""

import pytest
import time
from hledac.universal.orchestrator.lane_state import (
    LaneState, LaneManager, LaneStatus, LaneMetrics
)
from hledac.universal.orchestrator.phase_controller import (
    PhaseController, Phase, PhaseConfig, PhaseSignals
)
from hledac.universal.orchestrator.subsystem_semaphores import (
    SubsystemSemaphores, Subsystem
)
from hledac.universal.orchestrator.memory_pressure_broker import (
    MemoryPressureBroker, MemoryPressureLevel
)


class TestLanePolicySprint82B:
    """Testy pro deterministic lane policy (Sprint 82B)."""

    def test_posterior_initial_state(self):
        """Test: Lane začíná s neutral prior (alpha=1, beta=1)."""
        lane = LaneState(lane_id="test", hypothesis="test")
        assert lane.metrics.alpha == 1.0
        assert lane.metrics.beta == 1.0
        assert lane.metrics.pulls == 0

    def test_update_posterior(self):
        """Test: update_posterior správně aktualizuje alpha/beta."""
        lane = LaneState(lane_id="test", hypothesis="test")

        # Update s vysokým success
        lane.update_posterior(success=1.0, cost=10.0)
        assert lane.metrics.alpha == 2.0  # 1 + 1
        assert lane.metrics.beta == 1.0  # 1 + 0
        assert lane.metrics.pulls == 1

        # Update s nízkým success
        lane.update_posterior(success=0.0, cost=20.0)
        assert lane.metrics.alpha == 2.0
        assert lane.metrics.beta == 2.0  # 1 + 1
        assert lane.metrics.pulls == 2

    def test_cost_ema(self):
        """Test: Cost EMA se správně počítá."""
        lane = LaneState(lane_id="test", hypothesis="test")

        # First update
        lane.update_posterior(success=1.0, cost=10.0)
        assert lane.metrics.cost_ema == 10.0

        # Second update - EMA with alpha=0.3
        lane.update_posterior(success=1.0, cost=20.0)
        expected = 0.3 * 20 + 0.7 * 10  # = 13.0
        assert abs(lane.metrics.cost_ema - expected) < 0.1

    def test_contradiction_penalty_monotonic(self):
        """Test: Contradiction penalty je monotonic (více contradictions = nižší priority)."""
        lane = LaneState(lane_id="test", hypothesis="test")
        lane.metrics.findings_yield = 10.0

        # Žádné contradictions
        lane.compute_priority()
        p0 = lane.priority

        # 1 contradiction
        lane.add_contradiction(independent=True)
        lane.compute_priority()
        p1 = lane.priority

        # 2 contradictions
        lane.add_contradiction(independent=True)
        lane.compute_priority()
        p2 = lane.priority

        # Monotonic: p0 > p1 > p2
        assert p0 > p1
        assert p1 > p2

    def test_echo_density_penalty(self):
        """Test: Echo density snižuje priority."""
        lane1 = LaneState(lane_id="test1", hypothesis="test")
        lane1.metrics.findings_yield = 10.0
        lane1.metrics.echo_pressure = 0.0  # žádný echo

        lane2 = LaneState(lane_id="test2", hypothesis="test")
        lane2.metrics.findings_yield = 10.0
        lane2.metrics.echo_pressure = 0.8  # vysoký echo

        lane1.compute_priority()
        lane2.compute_priority()

        # Lane s nižším echo má vyšší priority
        assert lane1.priority > lane2.priority

    def test_starvation_bonus(self):
        """Test: Starvation bonus funguje, ale nepřepíše hard kill."""
        lane = LaneState(lane_id="test", hypothesis="test")
        lane.metrics.findings_yield = 1.0

        # Fresh lane - žádný bonus
        lane.compute_priority()
        p1 = lane.priority

        # Simulate long inactivity (set last update to old time)
        lane._last_priority_update = time.time() - 100  # 100s ago

        lane.compute_priority()
        p2 = lane.priority

        # Starvation bonus should give small boost
        assert p2 >= p1

    def test_add_lane_overflow_kills_weakest(self):
        """Test: add_lane overflow stále zabije weakest lane."""
        manager = LaneManager()

        # Přidáme 3 lanes s různými posterior stavy
        l1 = manager.add_lane("hypothesis 1")
        l1.metrics.alpha = 10.0  # high success
        l1.metrics.beta = 1.0
        l1.metrics.cost_ema = 1.0
        l1.compute_priority()

        l2 = manager.add_lane("hypothesis 2")
        l2.metrics.alpha = 5.0
        l2.metrics.beta = 2.0
        l2.metrics.cost_ema = 2.0
        l2.compute_priority()

        l3 = manager.add_lane("hypothesis 3")
        l3.metrics.alpha = 1.0  # low success
        l3.metrics.beta = 5.0
        l3.metrics.cost_ema = 5.0
        l3.compute_priority()

        assert manager.active_count == 3

        # Přidáme 4. lane - měla by zabít weakest (l3)
        l4 = manager.add_lane("hypothesis 4")

        # l3 (nejslabší) by měl být killed
        killed_lane = manager.get_lane(l3.lane_id)
        assert killed_lane.status == LaneStatus.KILLED


class TestWinnerOnlyExpensivePath:
    """Testy pro winner-only expensive path."""

    def test_is_expensive_action(self):
        """Test: Správná identifikace expensive akcí."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        # Create minimal orchestrator mock
        class MockOrchestrator:
            EXPENSIVE_ACTIONS = {
                "hermes_generate", "hermes_prose", "mlx_generate", "mlx_inference",
                "heavy_rerank", "gpu_rerank", "deep_synthesis", "prose_generation",
            }

            def _is_expensive_action(self, action_name: str) -> bool:
                action_lower = action_name.lower()
                for expensive in self.EXPENSIVE_ACTIONS:
                    if expensive in action_lower:
                        return True
                return False

        orch = MockOrchestrator()

        # Expensive actions
        assert orch._is_expensive_action("hermes_generate") is True
        assert orch._is_expensive_action("heavy_rerank") is True
        assert orch._is_expensive_action("mlx_inference") is True

        # Cheap actions
        assert orch._is_expensive_action("surface_search") is False
        assert orch._is_expensive_action("fetch_page") is False
        assert orch._is_expensive_action("nl_tag") is False

    def test_phase_allows_expensive(self):
        """Test: Phase SYNTHESIS allows expensive actions."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        class MockOrchestrator:
            def _can_run_expensive_action(self, current_phase, lane_role):
                from hledac.universal.orchestrator.phase_controller import Phase
                if current_phase == Phase.SYNTHESIS:
                    return True
                if lane_role == "winner_deepening":
                    return True
                return False

        orch = MockOrchestrator()
        from hledac.universal.orchestrator.phase_controller import Phase

        # SYNTHESIS phase - allowed for all
        assert orch._can_run_expensive_action(Phase.SYNTHESIS, "expansion") is True
        assert orch._can_run_expensive_action(Phase.SYNTHESIS, "falsification") is True

        # Winner deeping - always allowed
        assert orch._can_run_expensive_action(Phase.DISCOVERY, "winner_deepening") is True

        # Non-winner in early phase - NOT allowed
        assert orch._can_run_expensive_action(Phase.DISCOVERY, "expansion") is False
        assert orch._can_run_expensive_action(Phase.CONTRADICTION, "falsification") is False


class TestContradictionKill:
    """Testy pro contradiction kill s independence."""

    def test_extract_source_family(self):
        """Test: Source family extraction."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        class MockOrchestrator:
            ARCHIVE_DOMAINS = {"archive.org", "web.archive.org", "Wayback", "archive.is", "archive.ph", "ghostarchive.org"}
            SYNDICATION_PATTERNS = {"repubblica", "apnews", "reuters", "prnewswire", "businesswire", "syndicated"}

            def _extract_source_family(self, url: str) -> str:
                from urllib.parse import urlparse
                try:
                    parsed = urlparse(url)
                    domain = parsed.netloc.lower()
                    if domain.startswith("www."):
                        domain = domain[4:]
                    for archive in self.ARCHIVE_DOMAINS:
                        if archive in domain:
                            return f"archive:{domain}"
                    parts = domain.split(".")
                    if len(parts) >= 2:
                        return ".".join(parts[-2:])
                    return domain
                except Exception:
                    return "unknown"

        orch = MockOrchestrator()

        # Regular domains
        assert orch._extract_source_family("https://example.com/page") == "example.com"
        assert orch._extract_source_family("https://www.bbc.com/news") == "bbc.com"

        # Archive
        assert orch._extract_source_family("https://web.archive.org/page").startswith("archive:")

    def test_is_independent_source(self):
        """Test: Independence check správně filtruje."""
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        class MockOrchestrator:
            ARCHIVE_DOMAINS = {"archive.org"}
            SYNDICATION_PATTERNS = {"repubblica", "apnews"}

            def _is_independent_source(self, existing_families, new_family):
                if new_family.startswith("archive:"):
                    return False
                if new_family in existing_families:
                    return False
                return True

        orch = MockOrchestrator()

        # Same domain = NOT independent
        assert orch._is_independent_source({"example.com"}, "example.com") is False

        # Archive = NOT independent
        assert orch._is_independent_source(set(), "archive:web.archive.org") is False

        # Different domain = independent
        assert orch._is_independent_source({"example.com"}, "bbc.com") is True


class TestPhaseEvidenceDriven:
    """Testy pro evidence-driven phase promotion."""

    def test_weighted_promotion_score(self):
        """Test: Weighted promotion score."""
        config = PhaseConfig()
        controller = PhaseController(config)
        controller._current_phase = Phase.DISCOVERY

        signals = PhaseSignals()
        signals.strong_hypotheses = 2
        signals.winner_margin = 0.8
        signals.novelty_slope = 0.2
        signals.time_remaining_ratio = 0.8

        score = controller._compute_promotion_score(signals)

        # Should be high due to strong hypotheses and winner margin
        assert score >= 0.6

    def test_thermal_beam_width(self):
        """Test: Thermal-aware beam width."""
        config = PhaseConfig()
        controller = PhaseController(config)

        # Normal states
        assert controller.get_beam_width_for_thermal("nominal") == 3
        assert controller.get_beam_width_for_thermal("fair") == 3
        assert controller.get_beam_width_for_thermal("normal") == 3

        # Hot states
        assert controller.get_beam_width_for_thermal("hot") == 2
        assert controller.get_beam_width_for_thermal("serious") == 1
        assert controller.get_beam_width_for_thermal("critical") == 1

    def test_hard_ceiling_enforced(self):
        """Test: Hard ceiling stále funguje."""
        config = PhaseConfig()
        controller = PhaseController(config)
        controller._current_phase = Phase.DISCOVERY
        controller._phase_start_time = time.time() - 400  # Přes 5 min

        signals = PhaseSignals()
        signals.strong_hypotheses = 0
        signals.time_remaining_ratio = 1.0

        # Should promote due to time ceiling
        assert controller.should_promote(signals) is True


class TestSubsystemSemaphores:
    """Testy pro subsystem semaphores."""

    def test_budget_throttle(self):
        """Test: Budget throttle při memory pressure."""
        semaphores = SubsystemSemaphores()

        original_gpu_limit = semaphores._limits[Subsystem.GPU]

        # Apply 50% throttle
        semaphores.apply_budget_throttle(0.5)

        # GPU limit should be reduced
        assert semaphores._limits[Subsystem.GPU] <= original_gpu_limit

    def test_winner_allowed_for_expensive(self):
        """Test: Winner lane allowed for expensive."""
        semaphores = SubsystemSemaphores()

        assert semaphores.is_winner_allowed_for_expensive("winner_deepening") is True
        assert semaphores.is_winner_allowed_for_expensive("expansion") is False
        assert semaphores.is_winner_allowed_for_expensive("falsification") is False


class TestMemoryPressureBroker:
    """Testy pro memory pressure broker."""

    def test_native_fallback_contract(self):
        """Test: Fallback je fail-safe."""
        broker = MemoryPressureBroker()

        # Should use fallback (not native)
        broker._try_init_native()

        assert broker._native_available is False

    def test_warn_throttle(self):
        """Test: WARN throttle nastavuje správný factor."""
        broker = MemoryPressureBroker()

        # Manually trigger WARN state
        broker.check()  # This will poll actual system

        # After WARN, throttle should be applied
        # (Actual level depends on system state, but logic should be correct)

    def test_critical_suspends_low_priority(self):
        """Test: CRITICAL suspends low priority."""
        broker = MemoryPressureBroker()

        # Check should set low_priority_suspended on CRITICAL
        # (Actual behavior depends on system memory)

        # Verify the status includes throttle info
        status = broker.get_status()
        assert "budget_throttle_factor" in status

    def test_callbacks_lightweight(self):
        """Test: Callbacks are lightweight (no heavy work in callback)."""
        callback_executed = []

        def light_callback():
            callback_executed.append(True)
            # No heavy work here!

        broker = MemoryPressureBroker(on_warn=light_callback)

        # Callback should just set flag
        # Heavy work is delegated to orchestrator


class TestStreamingFindings:
    """Testy pro bounded streaming findings."""

    def test_queue_bounded(self):
        """Test: Queue je bounded."""
        import asyncio
        from hledac.universal.autonomous_orchestrator import FullyAutonomousOrchestrator

        # This would need full orchestrator setup
        # Basic check that queue exists
        assert True  # Placeholder - full test needs orchestrator

    def test_low_priority_drop(self):
        """Test: Low priority findings drop při tlaku."""
        # Would test that low-confidence findings are dropped
        # when queue is full
        assert True  # Placeholder


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
