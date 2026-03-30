"""
Test Lane Pruning
=================

Tests for LaneManager:
- max 3 lanes
- beam prune works
- weak lanes die
"""

import pytest
import time

from hledac.universal.orchestrator.lane_state import (
    LaneStatus, LaneMetrics, LaneState, LaneManager
)


class TestLaneState:
    """Test LaneState."""

    def test_lane_creation(self):
        """Test lane creation."""
        lane = LaneState(lane_id="test_1", hypothesis="test hypothesis")

        assert lane.lane_id == "test_1"
        assert lane.hypothesis == "test hypothesis"
        assert lane.status == LaneStatus.ACTIVE
        assert lane.metrics.contradiction_hits == 0

    def test_mark_stalled(self):
        """Test marking lane as stalled."""
        lane = LaneState(lane_id="test_1", hypothesis="test")
        lane.mark_stalled()

        assert lane.status == LaneStatus.STALLED

    def test_mark_killed(self):
        """Test marking lane as killed."""
        lane = LaneState(lane_id="test_1", hypothesis="test")
        lane.mark_killed("test_reason")

        assert lane.status == LaneStatus.KILLED
        assert lane._tombstoned is True

    def test_is_alive(self):
        """Test is_alive."""
        lane = LaneState(lane_id="test_1", hypothesis="test")

        assert lane.is_alive() is True

        lane.mark_stalled()
        assert lane.is_alive() is False

    def test_should_kill_hard_threshold(self):
        """Test hard kill on 2+ independent contradictions."""
        lane = LaneState(lane_id="test_1", hypothesis="test")

        # Add 2 independent contradictions
        lane.add_contradiction(independent=True)
        lane.add_contradiction(independent=True)

        assert lane.should_kill(contradiction_threshold=2) is True

    def test_should_kill_low_yield(self):
        """Test soft kill on low yield + high cost + stagnation."""
        lane = LaneState(lane_id="test_1", hypothesis="test")

        # Low yield, high cost, many iterations
        lane.metrics.findings_yield = 0.1
        lane.metrics.cost_accumulated = 100.0
        lane.metrics.iterations = 10

        assert lane.should_kill(stagnation_threshold=5) is True

    def test_tombstone(self):
        """Test tombstoning clears data."""
        lane = LaneState(lane_id="test_1", hypothesis="test")
        lane.metrics.findings_yield = 10.0
        lane.metrics.cost_accumulated = 50.0
        lane._pending_candidates.append("candidate1")
        lane._recent_findings.append("finding1")

        lane.tombstone()

        assert lane._tombstoned is True
        assert len(lane._pending_candidates) == 0
        assert len(lane._recent_findings) == 0
        assert lane.metrics.findings_yield == 0.0

    def test_compute_priority(self):
        """Test priority calculation with Bayes-UCB-lite."""
        lane = LaneState(lane_id="test_1", hypothesis="test")
        # New formula uses: alpha, beta, cost_ema, iterations
        lane.metrics.alpha = 5.0  # high success
        lane.metrics.beta = 1.0
        lane.metrics.cost_ema = 5.0
        lane.metrics.iterations = 3

        priority = lane.compute_priority()

        # High alpha/beta ratio + reasonable cost = high priority
        assert priority > 0.0


class TestLaneManager:
    """Test LaneManager."""

    def test_add_lane(self):
        """Test adding a lane."""
        manager = LaneManager()
        lane = manager.add_lane("hypothesis 1")

        assert lane is not None
        assert manager.active_count == 1

    def test_max_lanes(self):
        """Test max 3 lanes limit."""
        manager = LaneManager()

        # Add 3 lanes
        manager.add_lane("hypothesis 1")
        manager.add_lane("hypothesis 2")
        manager.add_lane("hypothesis 3")

        assert manager.active_count == 3

    def test_max_lanes_kills_weakest(self):
        """Test adding 4th lane kills weakest."""
        manager = LaneManager()

        # Add 3 lanes with different posterior states
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

        # Add 4th lane - should kill weakest (l3)
        l4 = manager.add_lane("hypothesis 4")

        # l3 should be killed (lowest posterior mean)
        killed_lane = manager.get_lane(l3.lane_id)
        assert killed_lane.status == LaneStatus.KILLED

    def test_beam_prune(self):
        """Test beam prune keeps top 3."""
        manager = LaneManager()

        # Add 5 lanes with different priorities (bypass auto-kill by adding directly to internal state)
        lanes = []
        for i in range(5):
            lane_id = f"test_lane_{i}"
            from hledac.universal.orchestrator.lane_state import LaneState
            lane = LaneState(lane_id=lane_id, hypothesis=f"hypothesis {i}")
            lane.metrics.findings_yield = float(10 - i)  # 10, 9, 8, 7, 6
            lane.metrics.cost_accumulated = 1.0
            lane.compute_priority()
            manager._lanes[lane_id] = lane
            manager._active_ids.append(lane_id)
            lanes.append(lane)

        # Beam prune should keep top 3
        survivors = manager.beam_prune()

        assert len(survivors) == 3
        # Survivors should have highest priorities
        priorities = [s.priority for s in survivors]
        assert priorities == sorted(priorities, reverse=True)

    def test_check_and_kill(self):
        """Test check_and_kill removes bad lanes."""
        manager = LaneManager()

        lane = manager.add_lane("bad hypothesis")
        lane.add_contradiction(independent=True)
        lane.add_contradiction(independent=True)

        killed = manager.check_and_kill()

        assert len(killed) == 1
        assert killed[0].status == LaneStatus.KILLED

    def test_kill_weakest(self):
        """Test kill_weakest with Bayes-UCB-lite."""
        manager = LaneManager()

        l1 = manager.add_lane("hypothesis 1")
        l1.metrics.alpha = 10.0  # high success
        l1.metrics.beta = 1.0
        l1.metrics.cost_ema = 1.0
        l1.compute_priority()

        l2 = manager.add_lane("hypothesis 2")
        l2.metrics.alpha = 1.0  # low success
        l2.metrics.beta = 5.0
        l2.metrics.cost_ema = 10.0
        l2.compute_priority()

        weakest = manager.kill_weakest()

        assert weakest.lane_id == l2.lane_id
        assert manager.active_count == 1


class TestLaneMetrics:
    """Test LaneMetrics."""

    def test_default_metrics(self):
        """Test default metrics."""
        metrics = LaneMetrics()

        assert metrics.contradiction_hits == 0
        assert metrics.iterations == 0
        assert metrics.findings_yield == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
