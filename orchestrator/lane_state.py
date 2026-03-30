"""
Lane State - Hypothesis Lane Management
========================================

Phase 1A: 30min Sprint Orchestration Backbone

Spravuje hypothesis lanes s bounded stavem:
- hypothesis id
- local budget
- contradiction count
- lane-local source coverage
- novelt / echo pressure
- estimated yield
- status (active / stalled / killed)

Implementuje:
- UCB1-like lane selection
- beam pruning na top-3 lanes
- explicit branch-kill economics
- tombstoning pro mrtvé lanes
"""

from __future__ import annotations

import time
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Any
from collections import deque

logger = logging.getLogger(__name__)


class LaneStatus(Enum):
    """Stav lane."""
    ACTIVE = "active"
    STALLED = "stalled"
    KILLED = "killed"


@dataclass
class LaneMetrics:
    """
    Metriky lane.

    Sprint 82B: Deterministic posterior-like state:
    - alpha, beta: Beta-style posterior (start: 1.0, 1.0)
    - pulls: počet "pulls" (updates)
    - cost_ema: exponential moving average nákladů
    """
    # Beta-style posterior state (Sprint 82B)
    alpha: float = 1.0   # success prior (start: neutral)
    beta: float = 1.0   # failure prior (start: neutral)
    pulls: int = 0      # number of updates

    # Legacy metrics (pro backward compatibility)
    contradiction_hits: int = 0
    independent_contradictions: int = 0  # pro hard kill threshold
    iterations: int = 0
    sources_covered: int = 0
    findings_yield: float = 0.0
    echo_pressure: float = 0.0  # 0 = nové, 1 = echo
    cost_accumulated: float = 0.0

    # Sprint 82B: EMA for cost tracking
    cost_ema: float = 0.0
    _cost_ema_alpha: float = 0.3  # EMA decay factor


@dataclass
class LaneState:
    """
    Bounded state pro jednu hypothesis lane.

    Každá lane má:
    - hypothesis id
    - local budget
    - metriky
    - status
    - Beta-style posterior state (Sprint 82B)

    Sprint 82B Priority Components:
    - posterior expectation: alpha / (alpha + beta)
    - expected VoI / cost: yield / cost_ema
    - contradiction penalty: multiplicative reduction
    - echo-density penalty: multiplicative reduction
    - starvation bonus: small additive boost for inactive lanes
    """
    lane_id: str
    hypothesis: str
    local_budget: float = 100.0  # default budget per lane
    metrics: LaneMetrics = field(default_factory=LaneMetrics)
    status: LaneStatus = LaneStatus.ACTIVE
    created_at: float = field(default_factory=time.time)
    last_update: float = field(default_factory=time.time)
    priority: float = 1.0  # Deterministic score (Sprint 82B)
    _tombstoned: bool = False

    # Sprint 82B: Source family tracking for independence
    _source_families: set = field(default_factory=set)  # tracked source families

    # Sprint 82B: Starvation tracking
    _last_priority_update: float = field(default_factory=time.time)

    # Bounded containers
    _pending_candidates: deque = field(default_factory=lambda: deque(maxlen=50))
    _recent_findings: deque = field(default_factory=lambda: deque(maxlen=20))

    def mark_stalled(self) -> None:
        """Označí lane jako stalled."""
        if self.status == LaneStatus.ACTIVE:
            self.status = LaneStatus.STALLED
            logger.debug(f"[LANE] {self.lane_id} -> STALLED")

    def mark_killed(self, reason: str = "") -> None:
        """Označí lane jako killed a spustí tombstoning."""
        if self.status != LaneStatus.KILLED:
            self.status = LaneStatus.KILLED
            self._tombstoned = True
            logger.info(f"[LANE] {self.lane_id} -> KILLED ({reason})")

    def is_alive(self) -> bool:
        """Je lane ještě aktivní?"""
        return self.status == LaneStatus.ACTIVE

    def should_kill(self, contradiction_threshold: int = 2, stagnation_threshold: int = 5) -> bool:
        """
        Rozhodne, zda by měla být lane zabita.

        Rules:
        - 2+ nezávislé contradiction hits → hard kill
        - nízký yield + vysoký cost + stagnace → kill
        """
        # Hard kill: 2+ independent contradictions
        if self.metrics.independent_contradictions >= contradiction_threshold:
            return True

        # Soft kill: nízký yield + vysoký cost + stagnace
        if self.metrics.iterations > stagnation_threshold:
            avg_cost = self.metrics.cost_accumulated / max(self.metrics.iterations, 1)
            yield_per_cost = self.metrics.findings_yield / max(avg_cost, 1e-6)
            if yield_per_cost < 0.1:  # velmi nízká efektivita
                return True

        return False

    def tombstone(self) -> None:
        """
        Uvolní resources po kill.

        Tombstoning:
        - odstraní velké textové buffery
        - uvolní graph refs
        - uvolní pending candidate refs
        """
        # Always clear, even if already marked for tombstone
        # Clear bounded containers
        self._pending_candidates.clear()
        self._recent_findings.clear()

        # Clear metrics that hold data
        self.metrics = LaneMetrics()

        self._tombstoned = True
        logger.debug(f"[LANE] {self.lane_id} tombstoned")

    def add_contradiction(self, independent: bool = False) -> None:
        """Přidá contradiction hit."""
        self.metrics.contradiction_hits += 1
        if independent:
            self.metrics.independent_contradictions += 1

    def add_finding(self, yield_value: float = 1.0) -> None:
        """Přidá finding."""
        self.metrics.findings_yield += yield_value
        self.last_update = time.time()

    def iteration(self) -> None:
        """Inkrementuje iteraci."""
        self.metrics.iterations += 1
        self.last_update = time.time()

    def update_posterior(self, success: float, cost: float) -> None:
        """
        Sprint 82B: Update Beta-style posterior.

        Args:
            success: 0-1 reward (finding quality)
            cost: positive cost value
        """
        # Update Beta posterior
        self.metrics.alpha += success
        self.metrics.beta += (1.0 - success)
        self.metrics.pulls += 1

        # Update cost EMA
        if self.metrics.cost_ema <= 0:
            self.metrics.cost_ema = cost
        else:
            self.metrics.cost_ema = (
                self.metrics._cost_ema_alpha * cost +
                (1.0 - self.metrics._cost_ema_alpha) * self.metrics.cost_ema
            )

        self._last_priority_update = time.time()

    def add_source_family(self, family: str) -> None:
        """Sprint 82B: Track source family for independence."""
        self._source_families.add(family)

    def get_source_families(self) -> set:
        """Get tracked source families."""
        return self._source_families.copy()

    def compute_priority(self, global_cost: float = 0.0) -> float:  # noqa: ARG001
        """
        Sprint 82C: Deterministic Bayes-UCB-lite priority score.

        Reference formula (Sprint 82C):
        - posterior_mean = alpha / (alpha + beta)
        - posterior_var = (posterior_mean * (1 - posterior_mean)) / max(alpha + beta + 1, 1)
        - uncertainty_bonus = min(posterior_var ** 0.5, 0.25)
        - voi_per_cost = posterior_mean / max(cost_ema, 1e-3)
        - contra_factor = 1 / (1 + 0.5 * contradiction_count)
        - echo_factor = 1 - min(echo_density, 0.9)
        - starve_bonus = min(cycles_since_action * 0.05, 0.30)

        Returns: max(0, (voi_per_cost + uncertainty_bonus) * contra_factor * echo_factor * (1 + starve_bonus))

        All components are deterministic (no RNG).
        """
        # 1. Posterior mean: alpha / (alpha + beta)
        total = self.metrics.alpha + self.metrics.beta
        if total > 0:
            posterior_mean = self.metrics.alpha / total
        else:
            # Cold start: neutral prior
            posterior_mean = 0.5

        # 2. Posterior variance for uncertainty bonus
        if total > 0:
            posterior_var = (posterior_mean * (1.0 - posterior_mean)) / max(total + 1.0, 1.0)
        else:
            posterior_var = 0.25  # Max uncertainty

        # 3. Uncertainty bonus (Bayes-UCB-lite, deterministic)
        uncertainty_bonus = min(posterior_var ** 0.5, 0.25)

        # 4. VoI per cost
        voi_per_cost = posterior_mean / max(self.metrics.cost_ema, 1e-3)

        # 5. Contradiction factor (multiplicative, monotonic)
        contra_factor = 1.0 / (1.0 + 0.5 * self.metrics.independent_contradictions)

        # 6. Echo density factor (multiplicative)
        echo_factor = 1.0 - min(self.metrics.echo_pressure, 0.9)

        # 7. Starvation bonus (additive, capped)
        # Track cycles since action via iterations
        starve_bonus = min(self.metrics.iterations * 0.05, 0.30)

        # Combine all components
        self.priority = max(
            0.0,
            (voi_per_cost + uncertainty_bonus) * contra_factor * echo_factor * (1.0 + starve_bonus)
        )

        return self.priority

    def get_status(self) -> dict:
        """Status pro diagnostiku."""
        return {
            "lane_id": self.lane_id,
            "hypothesis": self.hypothesis[:50] + "..." if len(self.hypothesis) > 50 else self.hypothesis,
            "status": self.status.value,
            "priority": self.priority,
            # Sprint 82B: Posterior state
            "alpha": self.metrics.alpha,
            "beta": self.metrics.beta,
            "pulls": self.metrics.pulls,
            "cost_ema": self.metrics.cost_ema,
            # Legacy metrics
            "contradictions": self.metrics.contradiction_hits,
            "independent_contradictions": self.metrics.independent_contradictions,
            "iterations": self.metrics.iterations,
            "findings_yield": self.metrics.findings_yield,
            "echo_pressure": self.metrics.echo_pressure,
            "cost": self.metrics.cost_accumulated,
            # Sprint 82B: Source families
            "source_families": list(self._source_families),
            "tombstoned": self._tombstoned,
        }


class LaneManager:
    """
    Správce hypothesis lanes.

    Podporuje max 3 aktivní lanes.
    """
    MAX_LANES = 3
    CONTRADICTION_HARD_KILL = 2  # 2 independent contradictions = hard kill
    STAGNATION_THRESHOLD = 5

    def __init__(self):
        self._lanes: dict[str, LaneState] = {}
        self._active_ids: deque = deque(maxlen=self.MAX_LANES)

    @property
    def active_lanes(self) -> list[LaneState]:
        """Aktivní lanes (status = ACTIVE)."""
        return [lane for lane in self._lanes.values() if lane.is_alive()]

    @property
    def active_count(self) -> int:
        """Počet aktivních lanes."""
        return len(self.active_lanes)

    def add_lane(self, hypothesis: str, budget: float = 100.0) -> LaneState:
        """
        Přidá novou lane.

        Pokud přesáhneme MAX_LANES, automaticky zabijeme nejslabší existující lane.
        """
        lane_id = f"lane_{len(self._lanes)}_{int(time.time() * 1000)}"
        lane = LaneState(lane_id=lane_id, hypothesis=hypothesis, local_budget=budget)

        # Save reference to new lane before adding
        new_lane = lane

        # Auto-kill weakest when over capacity (BEFORE adding new lane)
        if len(self._active_ids) >= self.MAX_LANES:
            # Compute priorities for all active lanes EXCEPT new lane
            candidates = [l for l in self.active_lanes if l.lane_id != lane_id]
            for l in candidates:
                l.compute_priority()
            # Kill weakest from existing lanes
            if candidates:
                weakest = min(candidates, key=lambda l: l.priority)
                weakest.mark_killed("max_lanes_reached")
                weakest.tombstone()
                if weakest.lane_id in self._active_ids:
                    self._active_ids.remove(weakest.lane_id)

        # Now add the new lane
        self._lanes[lane_id] = new_lane
        self._active_ids.append(lane_id)

        logger.info(f"[LANE] Added {lane_id}, active: {self.active_count}/{self.MAX_LANES}")
        return new_lane

    def get_lane(self, lane_id: str) -> Optional[LaneState]:
        """Get lane by ID."""
        return self._lanes.get(lane_id)

    def remove_lane(self, lane_id: str) -> None:
        """Odstraní lane."""
        if lane_id in self._lanes:
            lane = self._lanes[lane_id]
            lane.mark_killed("removed")
            lane.tombstone()
            del self._lanes[lane_id]
            if lane_id in self._active_ids:
                self._active_ids.remove(lane_id)

    def kill_weakest(self) -> Optional[LaneState]:
        """
        Zabije nejslabší lane.

        Returns:
            Killed lane nebo None.
        """
        if not self.active_lanes:
            return None

        # First compute priorities for all lanes
        for lane in self.active_lanes:
            lane.compute_priority()

        # Seřadit podle priority (nejnižší první)
        sorted_lanes = sorted(
            self.active_lanes,
            key=lambda l: l.priority
        )

        weakest = sorted_lanes[0]
        weakest.mark_killed("weakest_beam")
        weakest.tombstone()

        if weakest.lane_id in self._active_ids:
            self._active_ids.remove(weakest.lane_id)

        logger.info(f"[LANE] Killed weakest: {weakest.lane_id}")
        return weakest

    def beam_prune(self) -> list[LaneState]:
        """
        Provede beam prune na top-3 lanes.

        Returns:
            Seznam přeživších lanes.
        """
        if not self._lanes:
            return []

        # Seřadit všechny lanes podle priority
        all_lanes = sorted(
            self._lanes.values(),
            key=lambda l: l.priority,
            reverse=True  # nejvyšší priority první
        )

        survivors = []
        killed = []

        for i, lane in enumerate(all_lanes):
            if i < self.MAX_LANES and lane.is_alive():
                survivors.append(lane)
            elif lane.is_alive():
                lane.mark_killed("beam_prune")
                lane.tombstone()
                killed.append(lane)

        # Update active IDs
        self._active_ids = deque([l.lane_id for l in survivors], maxlen=self.MAX_LANES)

        if killed:
            logger.info(f"[LANE] Beam pruned: killed {len(killed)} lanes")

        return survivors

    def check_and_kill(self) -> list[LaneState]:
        """
        Zkontroluje všechny lanes a zabije ty, co by měly zemřít.

        Returns:
            Seznam zabitých lanes.
        """
        killed = []

        for lane in list(self._lanes.values()):
            if not lane.is_alive():
                continue

            # Update priority
            lane.compute_priority()

            # Check kill conditions
            if lane.should_kill(self.CONTRADICTION_HARD_KILL, self.STAGNATION_THRESHOLD):
                lane.mark_killed("branch_kill")
                lane.tombstone()
                killed.append(lane)
                if lane.lane_id in self._active_ids:
                    self._active_ids.remove(lane.lane_id)

        return killed

    def get_status(self) -> dict:
        """Status všech lanes."""
        return {
            "total_lanes": len(self._lanes),
            "active_count": self.active_count,
            "max_lanes": self.MAX_LANES,
            "lanes": [l.get_status() for l in self._lanes.values()],
        }
