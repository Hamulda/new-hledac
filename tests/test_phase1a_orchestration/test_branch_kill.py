"""
Test Branch Kill
===============

Tests for branch-kill economics:
- contradiction threshold kill works
- stagnating weak lane dies
"""

import pytest
import time

from hledac.universal.orchestrator.lane_state import (
    LaneStatus, LaneState, LaneManager
)


class TestBranchKill:
    """Test branch-kill economics."""

    def test_single_contradiction_penalizes(self):
        """Test 1 contradiction hit adds penalty."""
        lane = LaneState(lane_id="test_1", hypothesis="test")

        lane.add_contradiction(independent=False)

        assert lane.metrics.contradiction_hits == 1
        assert lane.metrics.independent_contradictions == 0

    def test_independent_contradiction_counts(self):
        """Test independent contradictions counted separately."""
        lane = LaneState(lane_id="test_1", hypothesis="test")

        lane.add_contradiction(independent=True)
        lane.add_contradiction(independent=False)
        lane.add_contradiction(independent=True)

        assert lane.metrics.contradiction_hits == 3
        assert lane.metrics.independent_contradictions == 2

    def test_hard_kill_on_two_independent_contradictions(self):
        """Test 2 independent contradictions triggers hard kill."""
        lane = LaneState(lane_id="test_1", hypothesis="test")

        # Add 2 independent contradictions
        lane.add_contradiction(independent=True)
        lane.add_contradiction(independent=True)

        should_kill = lane.should_kill(contradiction_threshold=2)

        assert should_kill is True

    def test_low_yield_high_cost_kill(self):
        """Test low yield + high cost + stagnation triggers kill."""
        lane = LaneState(lane_id="test_1", hypothesis="test")

        # Setup: low yield, high cost, many iterations
        lane.metrics.findings_yield = 0.05  # very low
        lane.metrics.cost_accumulated = 100.0  # high cost
        lane.metrics.iterations = 10  # stagnation

        should_kill = lane.should_kill(
            contradiction_threshold=2,
            stagnation_threshold=5
        )

        assert should_kill is True

    def test_contradiction_threshold_not_met(self):
        """Test no kill when threshold not met."""
        lane = LaneState(lane_id="test_1", hypothesis="test")

        lane.add_contradiction(independent=True)

        should_kill = lane.should_kill(contradiction_threshold=2)

        assert should_kill is False

    def test_good_lane_not_killed(self):
        """Test good lane is not killed."""
        lane = LaneState(lane_id="test_1", hypothesis="test")

        # Good metrics
        lane.metrics.findings_yield = 10.0
        lane.metrics.cost_accumulated = 5.0
        lane.metrics.iterations = 3

        should_kill = lane.should_kill(stagnation_threshold=5)

        assert should_kill is False


class TestStagnatingLane:
    """Test stagnating lane behavior."""

    def test_iteration_increments(self):
        """Test iteration counter increments."""
        lane = LaneState(lane_id="test_1", hypothesis="test")

        lane.iteration()
        lane.iteration()
        lane.iteration()

        assert lane.metrics.iterations == 3

    def test_stagnation_with_no_findings(self):
        """Test stagnation detection."""
        lane = LaneState(lane_id="test_1", hypothesis="test")

        # Many iterations with no yield
        lane.metrics.iterations = 10
        lane.metrics.findings_yield = 0.0
        lane.metrics.cost_accumulated = 50.0

        should_kill = lane.should_kill(stagnation_threshold=5)

        assert should_kill is True


class TestTombstoning:
    """Test tombstoning behavior."""

    def test_tombstone_clears_pending_candidates(self):
        """Test tombstone clears pending candidates."""
        lane = LaneState(lane_id="test_1", hypothesis="test")

        lane._pending_candidates.append("candidate1")
        lane._pending_candidates.append("candidate2")

        lane.mark_killed("tombstone_test")
        lane.tombstone()

        assert len(lane._pending_candidates) == 0

    def test_tombstone_clears_recent_findings(self):
        """Test tombstone clears recent findings."""
        lane = LaneState(lane_id="test_1", hypothesis="test")

        lane._recent_findings.append("finding1")
        lane._recent_findings.append("finding2")

        lane.mark_killed("tombstone_test")
        lane.tombstone()

        assert len(lane._recent_findings) == 0

    def test_double_tombstone_safe(self):
        """Test double tombstone is safe."""
        lane = LaneState(lane_id="test_1", hypothesis="test")

        lane.mark_killed("first")
        lane.tombstone()

        # Second tombstone should not error
        lane.tombstone()

        assert lane._tombstoned is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
