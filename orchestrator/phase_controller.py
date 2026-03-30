"""
Phase Controller - Sprint Phase Management
==========================================

Phase 1A: 30min Sprint Orchestration Backbone

Kontroluje fáze sprintu s signal-based promotion:
- Phase 1: discovery / cheap filtering — max T=5 min
- Phase 2: contradiction + pruning — max T=15 min
- Phase 3: deepen winners — max T=24 min
- Phase 4: synthesis — do T=30 min

Signály pro promotion:
- >= 2 silné hypotheses
- contradiction pressure vysoký
- lane beam stabilizován
- otevřené gapy kvalitní
- zbývá málo času
"""

from __future__ import annotations

import time
import logging
from enum import IntEnum
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable

logger = logging.getLogger(__name__)


class Phase(IntEnum):
    """Sprint fáze."""
    DISCOVERY = 1      # max T=5 min
    CONTRADICTION = 2  # max T=15 min
    DEEPEN = 3         # max T=24 min
    SYNTHESIS = 4      # do T=30 min


@dataclass
class PhaseConfig:
    """Konfigurace fází."""
    max_time_seconds: float = 1800.0  # 30 minut
    phase_windows: dict[Phase, float] = field(default_factory=lambda: {
        Phase.DISCOVERY: 300.0,      # 5 min
        Phase.CONTRADICTION: 900.0,  # 15 min
        Phase.DEEPEN: 1440.0,        # 24 min
        Phase.SYNTHESIS: 1800.0,     # 30 min
    })


@dataclass
class PhaseSignals:
    """
    Signály pro promotion mezi fázemi.

    Sprint 82C: Explicit evidence-driven metriky.
    """
    strong_hypotheses: int = 0           # >= 2 pro promotion
    contradiction_pressure: float = 0.0   # 0-1, vysoký = promotion
    beam_stabilized: bool = False        # beam se stabilizoval
    gaps_quality: float = 0.0            # 0-1, kvalita gapů
    time_remaining_ratio: float = 1.0    # < 0.3 = málo času
    stagnation_released: bool = False    # stagnace uvolněna
    # Sprint 82C: Explicit weights per reference
    winner_margin: float = 0.0           # 0-1, jak moc winner vede (weight: 0.25)
    novelty_slope: float = 1.0          # 0-1, novelty klesá = plateau (weight: 0.15, inverted)
    source_family_coverage: float = 0.0   # 0-1, pokrytí zdrojů (weight: 0.15)
    beam_convergence: float = 0.0        # 0-1, jak moc beam konverguje (weight: 0.20)
    contradiction_frontier: int = 0      # total independent contradictions (weight: 0.15, inverted)
    open_gap_count: int = 0            # count of open gaps (weight: 0.10, inverted)


class PhaseController:
    """
    Lightweight phase controller pro sprint orchestraci.

    Používá jednoduchý stavový automat, ne složité plánování.
    Fáze se mohou povýšit dřív než uplyne max čas.
    """

    def __init__(
        self,
        config: Optional[PhaseConfig] = None,
        on_phase_change: Optional[Callable[[Phase, Phase], Awaitable[None]]] = None
    ):
        self.config = config or PhaseConfig()
        self._current_phase = Phase.DISCOVERY
        self._start_time: Optional[float] = None
        self._phase_start_time: Optional[float] = None
        self._on_phase_change = on_phase_change
        self._promotion_count = 0

    @property
    def current_phase(self) -> Phase:
        """Aktuální fáze."""
        return self._current_phase

    @property
    def elapsed_time(self) -> float:
        """Uplynulý čas od startu sprintu."""
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time

    @property
    def phase_elapsed_time(self) -> float:
        """Uplynulý čas od startu aktuální fáze."""
        if self._phase_start_time is None:
            return 0.0
        return time.time() - self._phase_start_time

    def start(self) -> None:
        """Start sprintu."""
        self._start_time = time.time()
        self._phase_start_time = time.time()
        self._current_phase = Phase.DISCOVERY
        logger.info(f"[PHASE] Sprint started at Phase.DISCOVERY")

    def get_max_time_for_phase(self, phase: Phase) -> float:
        """Max čas pro danou fázi."""
        return self.config.phase_windows.get(phase, self.config.max_time_seconds)

    def should_promote(self, signals: PhaseSignals) -> bool:
        """
        Sprint 82B: Evidence-driven phase promotion.

        Používá weighted score místo pure AND logiky.
        Hard ceiling: time-based je vždy enforced.
        """
        # Time-based: přesáhli jsme max čas pro aktuální fázi? (HARD CEILING)
        max_time = self.get_max_time_for_phase(self._current_phase)
        if self.phase_elapsed_time >= max_time:
            return True

        # Sprint 82B: Weighted score promotion
        # Compute promotion score based on multiple signals
        score = self._compute_promotion_score(signals)

        # Threshold: promote if score >= 0.6
        if score >= 0.6:
            return True

        return False

    # Sprint 82C: Explicit weights per reference
    EARLY_SYNTHESIS_WEIGHTS = {
        "winner_margin": 0.25,
        "beam_converged": 0.20,
        "contradiction_frontier": 0.15,   # inverted
        "source_family_coverage": 0.15,
        "novelty_slope": 0.15,            # inverted
        "open_gap_count": 0.10,           # inverted
    }
    EARLY_SYNTHESIS_THRESHOLD = 0.72

    # Sprint 82C: Novelty EMA tracking
    _novelty_ema: float = 1.0  # initial high novelty

    def _compute_promotion_score(self, signals: PhaseSignals) -> float:
        """
        Sprint 82C: Explicit weighted promotion score.

        Reference weights (logged and testable):
        - winner_margin: 0.25
        - beam_converged: 0.20
        - contradiction_frontier: 0.15 (inverted)
        - source_family_coverage: 0.15
        - novelty_slope: 0.15 (inverted)
        - open_gap_count: 0.10 (inverted)

        Returns 0-1 score based on multiple signals.
        """
        score = 0.0
        score_terms = {}  # Pro logging

        # Phase 1 → 2 (DISCOVERY)
        if self._current_phase == Phase.DISCOVERY:
            # Winner margin: weight 0.25
            winner_score = signals.winner_margin * self.EARLY_SYNTHESIS_WEIGHTS["winner_margin"]
            score += winner_score
            score_terms["winner_margin"] = winner_score

            # Beam converged: weight 0.20
            beam_score = signals.beam_convergence * self.EARLY_SYNTHESIS_WEIGHTS["beam_converged"]
            score += beam_score
            score_terms["beam_converged"] = beam_score

            # Contradiction frontier (inverted): weight 0.15
            # More contradictions = lower score (need to resolve before promotion)
            contra_score = max(0, 1.0 - signals.contradiction_frontier / 5.0) * self.EARLY_SYNTHESIS_WEIGHTS["contradiction_frontier"]
            score += contra_score
            score_terms["contradiction_frontier"] = contra_score

            # Source family coverage: weight 0.15
            source_score = signals.source_family_coverage * self.EARLY_SYNTHESIS_WEIGHTS["source_family_coverage"]
            score += source_score
            score_terms["source_family_coverage"] = source_score

            # Novelty slope (inverted): weight 0.15
            # Low novelty = plateau = ready for synthesis
            novelty_score = max(0, 1.0 - signals.novelty_slope) * self.EARLY_SYNTHESIS_WEIGHTS["novelty_slope"]
            score += novelty_score
            score_terms["novelty_slope"] = novelty_score

            # Open gap count (inverted): weight 0.10
            gap_score = max(0, 1.0 - signals.open_gap_count / 10.0) * self.EARLY_SYNTHESIS_WEIGHTS["open_gap_count"]
            score += gap_score
            score_terms["open_gap_count"] = gap_score

        # Phase 2 → 3 (CONTRADICTION)
        elif self._current_phase == Phase.CONTRADICTION:
            # Same weights apply, emphasize resolution
            beam_score = signals.beam_convergence * self.EARLY_SYNTHESIS_WEIGHTS["beam_converged"]
            score += beam_score
            score_terms["beam_converged"] = beam_score

            contra_score = max(0, 1.0 - signals.contradiction_frontier / 5.0) * self.EARLY_SYNTHESIS_WEIGHTS["contradiction_frontier"]
            score += contra_score
            score_terms["contradiction_frontier"] = contra_score

            source_score = signals.source_family_coverage * self.EARLY_SYNTHESIS_WEIGHTS["source_family_coverage"]
            score += source_score
            score_terms["source_family_coverage"] = source_score

        # Phase 3 → 4 (DEEPEN → SYNTHESIS)
        elif self._current_phase == Phase.DEEPEN:
            # Gaps quality is primary driver
            gaps_score = signals.gaps_quality * 0.4
            score += gaps_score
            score_terms["gaps_quality"] = gaps_score

            if signals.stagnation_released:
                score += 0.3
                score_terms["stagnation_released"] = 0.3

            novelty_score = max(0, 1.0 - signals.novelty_slope) * 0.2
            score += novelty_score
            score_terms["novelty_slope"] = novelty_score

        # Time pressure always adds (hard ceiling is separate)
        if signals.time_remaining_ratio < 0.3:
            score += 0.3
            score_terms["time_pressure"] = 0.3
        elif signals.time_remaining_ratio < 0.5:
            score += 0.15
            score_terms["time_pressure"] = 0.15

        # Log the score breakdown for debugging
        logger.info(f"[PHASE] Promotion score: {score:.3f} (terms: {score_terms})")

        return min(1.0, score)

    def _update_novelty_ema(self, new_entity_count: int) -> float:
        """
        Sprint 82C: Update novelty EMA.

        Args:
            new_entity_count: Number of new entities discovered in this cycle

        Returns:
            Updated novelty EMA value
        """
        self._novelty_ema = 0.90 * self._novelty_ema + 0.10 * new_entity_count
        return self._novelty_ema

    def _is_plateau(self, threshold: float = 0.05) -> bool:
        """
        Sprint 82C: Check if novelty is at plateau.

        Args:
            threshold: EMA value below which is considered plateau

        Returns:
            True if novelty EMA is below threshold
        """
        return self._novelty_ema < threshold

    def _compute_beam_convergence(self, lane_entity_sets: list[set[str]], threshold: float = 0.70) -> float:
        """
        Sprint 82C: Compute beam convergence via CPU-only Jaccard overlap.

        Args:
            lane_entity_sets: List of entity sets from each lane
            threshold: Jaccard threshold for convergence

        Returns:
            Convergence score 0-1
        """
        if len(lane_entity_sets) < 2:
            return 0.0

        # Compute pairwise Jaccard similarity
        jaccard_scores = []
        for i, set_a in enumerate(lane_entity_sets):
            for set_b in lane_entity_sets[i+1:]:
                union = len(set_a | set_b)
                if union > 0:
                    jaccard = len(set_a & set_b) / union
                    jaccard_scores.append(jaccard)

        if not jaccard_scores:
            return 0.0

        avg_jaccard = sum(jaccard_scores) / len(jaccard_scores)
        return avg_jaccard

    def get_beam_width_for_thermal(self, thermal_state: str) -> int:
        """
        Sprint 82B: Get beam width based on thermal state.

        Thermal-aware narrowing:
        - nominal/fair → 3
        - warm → 3
        - hot → 2
        - critical → 1
        """
        thermal_map = {
            "nominal": 3,
            "fair": 3,
            "normal": 3,
            "warm": 3,
            "hot": 2,
            "serious": 1,
            "critical": 1,
        }
        return thermal_map.get(thermal_state.lower(), 3)

    async def maybe_promote(self, signals: PhaseSignals) -> bool:
        """
        Zkusí povýšit fázi pokud jsou signály příznivé.

        Returns:
            True pokud fáze byla povýšena.
        """
        if not self.should_promote(signals):
            return False

        old_phase = self._current_phase

        # Advance phase
        if self._current_phase < Phase.SYNTHESIS:
            self._current_phase = Phase(self._current_phase + 1)
            self._phase_start_time = time.time()
            self._promotion_count += 1

            logger.info(
                f"[PHASE] Promotion: {old_phase.name} → {self._current_phase.name} "
                f"(elapsed: {self.phase_elapsed_time:.1f}s, promotions: {self._promotion_count})"
            )

            # Callback
            if self._on_phase_change:
                try:
                    await self._on_phase_change(old_phase, self._current_phase)
                except Exception as e:
                    logger.warning(f"[PHASE] on_phase_change error: {e}")

            return True

        return False

    def get_phase_priority_modifier(self) -> float:
        """
        Vrací priority modifier podle fáze.

        Discovery: preferuj breadth (nízká specificita)
        Contradiction: preferuj contradiction detection
        Deepen: preferuj depth (vysoká specificita)
        Synthesis: preferuj synthesis-ready findings
        """
        modifiers = {
            Phase.DISCOVERY: 0.5,      # širší hledání
            Phase.CONTRADICTION: 1.0,  # vyvážené
            Phase.DEEPEN: 1.5,        # hlubší
            Phase.SYNTHESIS: 2.0,      # syntéza
        }
        return modifiers.get(self._current_phase, 1.0)

    def should_continue(self) -> bool:
        """Má sprint pokračovat?"""
        # Nepřesáhli jsme celkový max čas?
        if self.elapsed_time >= self.config.max_time_seconds:
            logger.info(f"[PHASE] Sprint complete: max time reached ({self.elapsed_time:.1f}s)")
            return False

        # Jsme v poslední fázi?
        if self._current_phase == Phase.SYNTHESIS:
            # V synthesis fázi můžeme pokračovat dokud máme čas
            remaining = self.config.max_time_seconds - self.elapsed_time
            if remaining < 60.0:  # méně než 1 minuta
                logger.info(f"[PHASE] Sprint ending: <1min remaining")
                return False

        return True

    def get_status(self) -> dict:
        """Status pro diagnostiku."""
        return {
            "phase": self._current_phase.name,
            "elapsed_time": self.elapsed_time,
            "phase_elapsed_time": self.phase_elapsed_time,
            "phase_max_time": self.get_max_time_for_phase(self._current_phase),
            "promotion_count": self._promotion_count,
            "should_continue": self.should_continue(),
        }
