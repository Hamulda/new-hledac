"""
SprintLifecycleManager — canonical sprint state machine.

Phases: BOOT → WARMUP → ACTIVE → WINDUP → EXPORT → TEARDOWN

Hard invariant: T-3min wind-down.
All timing uses time.monotonic().
No async. No threads. No I/O.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


# ── Phase enum ───────────────────────────────────────────────────────────────

class SprintPhase(Enum):
    BOOT = auto()
    WARMUP = auto()
    ACTIVE = auto()
    WINDUP = auto()
    EXPORT = auto()
    TEARDOWN = auto()


# ── Exceptions ────────────────────────────────────────────────────────────────

class SprintLifecycleError(Exception):
    """Base exception for sprint lifecycle errors."""


class InvalidPhaseTransitionError(SprintLifecycleError):
    """Raised when a non-monotonic phase transition is attempted."""


# ── Phase ordering ────────────────────────────────────────────────────────────

_PHASE_ORDER = [
    SprintPhase.BOOT,
    SprintPhase.WARMUP,
    SprintPhase.ACTIVE,
    SprintPhase.WINDUP,
    SprintPhase.EXPORT,
    SprintPhase.TEARDOWN,
]


# ── Manager ──────────────────────────────────────────────────────────────────

@dataclass
class SprintLifecycleManager:
    """
    Lightweight sprint lifecycle state machine.

    All methods accept an optional ``now_monotonic`` parameter to allow
    deterministic testing with a fake clock. When omitted the call uses
    ``time.monotonic()`` at runtime.
    """

    sprint_duration_s: float = 1800.0          # 30 minutes
    windup_lead_s: float = 180.0               # T-3min before trigger
    checkpoint_interval_s: float = 60.0          # lightweight checkpoint hint
    checkpoint_path: str = ""                    # metadata only — no I/O here

    # Mutable state
    _started_at: Optional[float] = field(default=None, repr=False)
    _current_phase: SprintPhase = field(default=SprintPhase.BOOT, repr=False)
    _entered_phase_at: Optional[float] = field(default=None, repr=False)
    _export_started: bool = field(default=False, repr=False)
    _teardown_started: bool = field(default=False, repr=False)
    _abort_requested: bool = field(default=False, repr=False)
    _abort_reason: str = field(default="", repr=False)
    _last_checkpoint_at: Optional[float] = field(default=None, repr=False)

    # ── start ────────────────────────────────────────────────────────────────

    def start(self, now_monotonic: Optional[float] = None) -> None:
        """Transition from BOOT → WARMUP and record start time."""
        if self._started_at is not None:
            raise SprintLifecycleError("Sprint has already been started.")
        now = _now(now_monotonic)
        self._started_at = now
        self._transition_to_unlocked(SprintPhase.WARMUP)

    # ── transition_to ────────────────────────────────────────────────────────

    def transition_to(self, phase: SprintPhase, now_monotonic: Optional[float] = None) -> None:
        """Transition to the given phase if it respects monotonic ordering."""
        now = _now(now_monotonic)
        if self._started_at is None:
            raise SprintLifecycleError("Sprint has not been started. Call start() first.")
        if phase == SprintPhase.TEARDOWN and self._abort_requested:
            # Abort shortcut: TEARDOWN is always reachable from any phase when abort requested
            self._transition_to_unlocked(phase, now)
            return
        if not self._is_valid_transition(self._current_phase, phase):
            raise InvalidPhaseTransitionError(
                f"Cannot transition from {self._current_phase.name} to {phase.name}. "
                f"Phases must advance monotonically."
            )
        self._transition_to_unlocked(phase, now)

    # ── tick ─────────────────────────────────────────────────────────────────

    def tick(self, now_monotonic: Optional[float] = None) -> SprintPhase:
        """
        Advance the state machine.

        Automatically enters WINDUP when remaining_time <= windup_lead_s.
        Returns the current phase after ticking.
        """
        now = _now(now_monotonic)

        # Auto WINDUP guard — only if we are in ACTIVE and time has run down
        if self._current_phase == SprintPhase.ACTIVE:
            remaining = self._remaining_time_unlocked(now)
            if remaining <= self.windup_lead_s:
                self._transition_to_unlocked(SprintPhase.WINDUP, now)

        return self._current_phase

    # ── remaining_time ───────────────────────────────────────────────────────

    def remaining_time(self, now_monotonic: Optional[float] = None) -> float:
        """Seconds remaining in the sprint (0 if elapsed)."""
        now = _now(now_monotonic)
        return self._remaining_time_unlocked(now)

    def _remaining_time_unlocked(self, now: float) -> float:
        if self._started_at is None:
            return self.sprint_duration_s
        return max(0.0, self._started_at + self.sprint_duration_s - now)

    # ── should_enter_windup ───────────────────────────────────────────────────

    def should_enter_windup(self, now_monotonic: Optional[float] = None) -> bool:
        """True when remaining time is at or below the windup lead threshold."""
        now = _now(now_monotonic)
        remaining = self._remaining_time_unlocked(now)
        return remaining <= self.windup_lead_s

    # ── request_abort ───────────────────────────────────────────────────────

    def request_abort(self, reason: str = "") -> None:
        """
        Signal that the sprint should abort.

        Does NOT add a new phase — abort flags are tracked separately.
        The manager can transition directly to TEARDOWN via transition_to.
        """
        self._abort_requested = True
        self._abort_reason = reason

    # ── mark_export_started / mark_teardown_started ─────────────────────────

    def mark_export_started(self, now_monotonic: Optional[float] = None) -> None:
        now = _now(now_monotonic)
        if self._current_phase != SprintPhase.WINDUP:
            raise InvalidPhaseTransitionError(
                f"EXPORT may only follow WINDUP, not {self._current_phase.name}."
            )
        self._export_started = True
        self._transition_to_unlocked(SprintPhase.EXPORT, now)

    def mark_teardown_started(self, now_monotonic: Optional[float] = None) -> None:
        now = _now(now_monotonic)
        if self._current_phase not in (SprintPhase.EXPORT, SprintPhase.WINDUP):
            raise InvalidPhaseTransitionError(
                f"TEARDOWN may only follow EXPORT or WINDUP (abort), "
                f"not {self._current_phase.name}."
            )
        self._teardown_started = True
        self._transition_to_unlocked(SprintPhase.TEARDOWN, now)

    # ── snapshot ────────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """
        Return a JSON-serializable dict representing the current state.

        No Path objects, no open handles — recovery-safe.
        """
        return {
            "sprint_duration_s": self.sprint_duration_s,
            "windup_lead_s": self.windup_lead_s,
            "checkpoint_interval_s": self.checkpoint_interval_s,
            "checkpoint_path": self.checkpoint_path,
            "started_at_monotonic": self._started_at,
            "current_phase": self._current_phase.name,
            "entered_phase_at": self._entered_phase_at,
            "export_started": self._export_started,
            "teardown_started": self._teardown_started,
            "abort_requested": self._abort_requested,
            "abort_reason": self._abort_reason,
            "last_checkpoint_at": self._last_checkpoint_at,
        }

    # ── recommended_tool_mode ────────────────────────────────────────────────

    def recommended_tool_mode(
        self,
        now_monotonic: Optional[float] = None,
        thermal_state: str = "nominal",
    ) -> str:
        """
        Returns one of: 'normal' | 'prune' | 'panic'.

        Decision tree:
        - panic : abort requested OR remaining <= 30s OR thermal == 'critical'
        - prune : remaining <= windup_lead_s OR thermal in ('throttled', 'fair')
        - normal: everything else
        """
        now = _now(now_monotonic)
        remaining = self._remaining_time_unlocked(now)

        if self._abort_requested or remaining <= 30.0 or thermal_state == "critical":
            return "panic"
        if remaining <= self.windup_lead_s or thermal_state in ("throttled", "fair"):
            return "prune"
        return "normal"

    # ── is_terminal ──────────────────────────────────────────────────────────

    def is_terminal(self) -> bool:
        """True when the manager has reached TEARDOWN or has aborted and completed."""
        if self._current_phase == SprintPhase.TEARDOWN:
            return True
        if self._abort_requested and self._teardown_started:
            return True
        return False

    # =============================================================================
    # Sprint 8VX §C: COMPAT ALIASES — bridge to utils/sprint_lifecycle call-sites
    # These forward to the canonical API. Labeled as COMPAT so they are clearly
    # NOT co-equal public API — they exist to make __main__.py cutover safe.
    # =============================================================================

    # ── COMPAT: begin_sprint ─────────────────────────────────────────────────

    def begin_sprint(self) -> None:
        """
        COMPAT ALIAS — forwards to start().

        Canonical: use start() directly. This alias exists to support
        __main__.py cutover without rewriting call-sites in this pass.
        """
        self.start()

    # ── COMPAT: mark_warmup_done ────────────────────────────────────────────

    def mark_warmup_done(self) -> None:
        """
        COMPAT ALIAS — transitions WARMUP→ACTIVE.

        Canonical: the WARMUP→ACTIVE transition happens via start() + tick()
        or directly via transition_to(ACTIVE). This alias exists for
        __main__.py call-site compatibility.
        """
        self.transition_to(SprintPhase.ACTIVE)

    # ── COMPAT: request_windup ──────────────────────────────────────────────

    def request_windup(self) -> None:
        """
        COMPAT ALIAS — forwards to transition_to(WINDUP).

        Canonical: use transition_to(SprintPhase.WINDUP).
        Idempotent: skips if already in WINDUP or beyond (matching utils behavior).
        """
        # Idempotent: don't re-trigger if already winding down
        if self._current_phase in (
            SprintPhase.WINDUP,
            SprintPhase.EXPORT,
            SprintPhase.TEARDOWN,
        ):
            return
        self.transition_to(SprintPhase.WINDUP)

    # ── COMPAT: request_export ───────────────────────────────────────────────

    def request_export(self) -> None:
        """
        COMPAT ALIAS — forwards to mark_export_started().

        Canonical: use mark_export_started() directly.
        Idempotent: skips if already in EXPORT or TEARDOWN (matching utils behavior).
        """
        if self._current_phase in (SprintPhase.EXPORT, SprintPhase.TEARDOWN):
            return
        self.mark_export_started()

    # ── COMPAT: request_teardown ─────────────────────────────────────────────

    def request_teardown(self) -> None:
        """
        COMPAT ALIAS — forwards to mark_teardown_started().

        Canonical: use mark_teardown_started() directly.
        """
        self.mark_teardown_started()

    # ── COMPAT: is_windup_phase ─────────────────────────────────────────────

    def is_windup_phase(self) -> bool:
        """
        COMPAT ALIAS — forwards to should_enter_windup().

        Canonical: use should_enter_windup() directly.
        """
        return self.should_enter_windup()

    # ── COMPAT: is_active property ───────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        """
        COMPAT PROPERTY — True when in ACTIVE phase.

        Canonical: use _current_phase == SprintPhase.ACTIVE.
        """
        return self._current_phase == SprintPhase.ACTIVE

    # ── COMPAT: is_winding_down property ─────────────────────────────────────

    @property
    def is_winding_down(self) -> bool:
        """
        COMPAT PROPERTY — True when in WINDUP, EXPORT, or TEARDOWN.

        Canonical: use _current_phase in (SprintPhase.WINDUP, SprintPhase.EXPORT, SprintPhase.TEARDOWN).
        """
        return self._current_phase in (
            SprintPhase.WINDUP,
            SprintPhase.EXPORT,
            SprintPhase.TEARDOWN,
        )

    # ── Public read-only surface ─────────────────────────────────────────────

    @property
    def current_phase(self) -> SprintPhase:
        """
        Public read-only access to current phase.

        Canonical alternative to direct _current_phase field access.
        """
        return self._current_phase

    def in_phase(self, phase: SprintPhase) -> bool:
        """
        True when manager is in the given phase.

        Convenience helper — equivalent to current_phase == phase.
        """
        return self._current_phase == phase

    # ── Private helpers ─────────────────────────────────────────────────────

    def _transition_to_unlocked(self, phase: SprintPhase, now: Optional[float] = None) -> None:
        if now is None:
            now = _now(None)
        self._current_phase = phase
        self._entered_phase_at = now

    def _is_valid_transition(self, from_phase: SprintPhase, to_phase: SprintPhase) -> bool:
        """Allow TEARDOWN from any phase (abort path)."""
        if to_phase == SprintPhase.TEARDOWN:
            return True
        from_idx = _PHASE_ORDER.index(from_phase)
        to_idx = _PHASE_ORDER.index(to_phase)
        return to_idx == from_idx + 1


# ── Clock helper ─────────────────────────────────────────────────────────────

def _now(m: Optional[float]) -> float:
    if m is not None:
        return m
    return time.monotonic()
