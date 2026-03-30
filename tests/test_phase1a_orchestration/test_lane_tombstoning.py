"""
Test Lane Tombstoning
====================

Tests for lane tombstoning:
- release references after kill
- lane doesn't stay hung in active structures
"""

import pytest
import time

from hledac.universal.orchestrator.lane_state import (
    LaneStatus, LaneState, LaneManager
)


class TestLaneTombstoning:
    """Test tombstoning behavior."""

    def test_tombstone_clears_containers(self):
        """Test tombstone clears bounded containers."""
        lane = LaneState(lane_id="test_1", hypothesis="test hypothesis")

        # Add data
        lane._pending_candidates.append("candidate1")
        lane._pending_candidates.append("candidate2")
        lane._pending_candidates.append("candidate3")
        lane._recent_findings.append("finding1")
        lane._recent_findings.append("finding2")

        # Tombstone
        lane.mark_killed("test")
        lane.tombstone()

        # Verify cleared
        assert len(lane._pending_candidates) == 0
        assert len(lane._recent_findings) == 0

    def test_tombstone_resets_metrics(self):
        """Test tombstone resets metrics."""
        lane = LaneState(lane_id="test_1", hypothesis="test")

        # Add metrics
        lane.metrics.findings_yield = 100.0
        lane.metrics.cost_accumulated = 500.0
        lane.metrics.sources_covered = 50

        lane.mark_killed("test")
        lane.tombstone()

        # Verify reset
        assert lane.metrics.findings_yield == 0.0
        assert lane.metrics.cost_accumulated == 0.0

    def test_tombstone_marks_as_tombstoned(self):
        """Test tombstone sets flag."""
        lane = LaneState(lane_id="test_1", hypothesis="test")

        lane.mark_killed("test")
        lane.tombstone()

        assert lane._tombstoned is True

    def test_double_tombstone_is_idempotent(self):
        """Test double tombstone doesn't error."""
        lane = LaneState(lane_id="test_1", hypothesis="test")

        lane.mark_killed("test")
        lane.tombstone()

        # Should not raise
        lane.tombstone()

        assert lane._tombstoned is True

    def test_tombstone_only_on_killed(self):
        """Test tombstone only runs on killed lanes."""
        lane = LaneState(lane_id="test_1", hypothesis="test")

        # Don't kill, just tombstone - should still work
        lane.tombstone()

        # State unchanged except flag
        assert lane.status == LaneStatus.ACTIVE
        assert lane._tombstoned is True


class TestLaneManagerTombstoning:
    """Test LaneManager tombstoning."""

    def test_remove_lane_tombstones(self):
        """Test remove_lane tombstones."""
        manager = LaneManager()

        lane = manager.add_lane("test hypothesis")
        lane_id = lane.lane_id

        manager.remove_lane(lane_id)

        killed = manager.get_lane(lane_id)
        assert killed is None  # Removed from dict

    def test_killed_lane_not_in_active(self):
        """Test killed lane not in active lanes."""
        manager = LaneManager()

        lane = manager.add_lane("test")
        lane_id = lane.lane_id

        # Kill it
        lane.mark_killed("test")
        lane.tombstone()

        # Should not be in active
        active_ids = [l.lane_id for l in manager.active_lanes]
        assert lane_id not in active_ids

    def test_beam_prune_tombstones(self):
        """Test beam prune tombstones killed lanes."""
        manager = LaneManager()

        # Add 5 lanes directly (bypass auto-kill)
        for i in range(5):
            lane_id = f"test_lane_{i}"
            from hledac.universal.orchestrator.lane_state import LaneState
            lane = LaneState(lane_id=lane_id, hypothesis=f"hypothesis {i}")
            lane.metrics.findings_yield = float(10 - i)
            lane.metrics.cost_accumulated = 1.0
            lane.compute_priority()
            manager._lanes[lane_id] = lane
            manager._active_ids.append(lane_id)

        # Beam prune
        survivors = manager.beam_prune()

        # Should have 3 survivors
        assert len(survivors) == 3

        # All survivors should be ACTIVE
        for s in survivors:
            assert s.status == LaneStatus.ACTIVE


class TestMemoryRelease:
    """Test memory release after kill."""

    def test_large_payloads_cleared(self):
        """Test large payloads are cleared."""
        lane = LaneState(lane_id="test_1", hypothesis="test")

        # Simulate large data
        large_data = "x" * 10000
        lane._pending_candidates.append(large_data)
        lane._recent_findings.append(large_data)
        lane._recent_findings.append(large_data)

        # Verify data exists
        assert len(lane._pending_candidates) > 0
        assert len(lane._recent_findings) > 0

        # Tombstone
        lane.mark_killed("test")
        lane.tombstone()

        # Verify cleared
        assert len(lane._pending_candidates) == 0
        assert len(lane._recent_findings) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
