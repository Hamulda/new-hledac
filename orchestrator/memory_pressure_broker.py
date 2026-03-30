"""
Memory Pressure Broker - macOS Memory Pressure Monitoring
=========================================================

Phase 1A: 30min Sprint Orchestration Backbone

TRUTHFUL IMPLEMENTATION:
- Uses FALLBACK POLLING (psutil/vm_stat), NOT native GCD dispatch source
- Native GCD would require complex ctypes setup; polling is equally reliable

Požadované chování:
- WARN: throttle subsystem budgets na ~50%, zastavit low-priority enqueue
- CRITICAL: suspend low-priority admissions, kill weakest lane, release buffers

Důležité:
- callback nesmí dělat těžkou práci (STRICTLY PROHIBITED: heavy inference, MLX work, deep fetch, gc.collect)
- pouze nastaví shared state / signal
- cleanup proběhne v async orchestration vrstvě
- fallback je primární path

Admission States (Sprint 82C):
- NORMAL: Full admission, all subsystems available
- THROTTLED: Budgets reduced ~50%, stop low-priority enqueue
- SUSPEND_LOW_PRIORITY: Low-priority admissions suspended
- EMERGENCY_CLEANUP_REQUESTED: Aggressive cleanup requested
"""

from __future__ import annotations

import os
import ctypes
import ctypes.util
import logging
from enum import IntEnum
from dataclasses import dataclass
from typing import Optional, Callable, Any
from threading import Lock

logger = logging.getLogger(__name__)

# Memory pressure levels (dispatch_source_mach_port_flag)
MEMORY_PRESSURE_NORMAL = 0
MEMORY_PRESSURE_WARN = 1
MEMORY_PRESSURE_CRITICAL = 2


class MemoryPressureLevel(IntEnum):
    """Úrovně memory pressure."""
    NORMAL = 0
    WARN = 1
    CRITICAL = 2


class AdmissionState(IntEnum):
    """
    Sprint 82C: Explicit admission states.

    States:
    - NORMAL: Full admission, all subsystems available
    - THROTTLED: Budgets reduced ~50%, stop low-priority enqueue
    - SUSPEND_LOW_PRIORITY: Low-priority admissions suspended
    - EMERGENCY_CLEANUP_REQUESTED: Aggressive cleanup requested
    """
    NORMAL = 0
    THROTTLED = 1
    SUSPEND_LOW_PRIORITY = 2
    EMERGENCY_CLEANUP_REQUESTED = 3


@dataclass
class MemoryPressureState:
    """Stav memory pressure."""
    level: MemoryPressureLevel = MemoryPressureLevel.NORMAL
    last_update: float = 0.0
    consecutive_warns: int = 0
    consecutive_criticals: int = 0


class MemoryPressureBroker:
    """
    Lightweight memory pressure broker.

    TRUTHFUL: Používá polling fallback (psutil/vm_stat), ne native GCD dispatch source.
    Native GCD by vyžadovalo komplexní ctypes setup, polling je stejně spolehlivé.

    Chování:
    - WARN (80%): throttle subsystem budgets na ~50%, zastavit low-priority
    - CRITICAL (90%): suspend low-priority admissions, zrušit non-winner heavy work
    """

    def __init__(
        self,
        on_warn: Optional[Callable[[], None]] = None,
        on_critical: Optional[Callable[[], None]] = None,
        on_normal: Optional[Callable[[], None]] = None,
        poll_interval: float = 5.0  # fallback poll interval
    ):
        self._state = MemoryPressureState()
        self._lock = Lock()
        self._on_warn = on_warn
        self._on_critical = on_critical
        self._on_normal = on_normal
        self._poll_interval = poll_interval

        # Sprint 82B: Add budget throttle tracking
        self._budget_throttle_factor: float = 1.0  # 1.0 = normal, 0.5 = throttled
        self._low_priority_suspended: bool = False

        # Sprint 82C: Admission state tracking
        self._admission_state: AdmissionState = AdmissionState.NORMAL

        # Fallback polling (not native GCD)
        self._dispatch_source: Any = None
        self._native_available = False
        self._initialized = False

    @property
    def level(self) -> MemoryPressureLevel:
        """Aktuální úroveň."""
        with self._lock:
            return self._state.level

    @property
    def is_warn(self) -> bool:
        """Jsme ve warning režimu?"""
        return self.level >= MemoryPressureLevel.WARN

    @property
    def is_critical(self) -> bool:
        """Jsme v critical režimu?"""
        return self.level >= MemoryPressureLevel.CRITICAL

    def _try_init_native(self) -> bool:
        """
        Zkusí inicializovat native GCD dispatch source.

        TRUTHFUL COMMENT: Native GCD dispatch source pro memory pressure
        vyžaduje komplexní ctypes setup. Pro jednoduchost a spolehlivost
        používáme fallback polling path.

        Returns:
            True pokud native init úspěšný (vždy False - fallback path).
        """
        if self._initialized:
            return self._native_available

        self._initialized = True

        try:
            # Native GCD dispatch source by bylo idealni, ale:
            # 1. Vyžaduje presné ctypes setup
            # 2. Memory pressure na macOS lze sledovat jednoduseji pres psutil
            # 3. Fallback path je stejne spolehliva pro nase ucely

            # Aktualne: vzdy pouzivame fallback polling
            self._native_available = False
            logger.debug("[MEMORY] Using fallback polling path (not native GCD dispatch)")
            return False

        except Exception as e:
            logger.debug(f"[MEMORY] Native init failed: {e}")
            self._native_available = False
            return False

    def _get_pressure_from_system(self) -> MemoryPressureLevel:
        """
        Získá memory pressure z systému (fallback polling).

        Používá:
        - macOS: sysctl hw.memsize + vm_stat
        """
        try:
            # Try to read memory pressure from system
            # On macOS we can check various signals

            # Method 1: Check available memory via psutil if available
            try:
                import psutil
                mem = psutil.virtual_memory()
                # percent: 0-100
                if mem.percent >= 90:
                    return MemoryPressureLevel.CRITICAL
                elif mem.percent >= 80:
                    return MemoryPressureLevel.WARN
                return MemoryPressureLevel.NORMAL
            except ImportError:
                pass

            # Method 2: Try to read vm_stat on macOS
            try:
                import subprocess
                result = subprocess.run(
                    ['vm_stat'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if result.returncode == 0:
                    # Parse "Pages free:" etc.
                    lines = result.stdout.strip().split('\n')
                    free_pages = 0
                    for line in lines:
                        if 'Pages free:' in line:
                            free_pages = int(line.split(':')[1].strip().rstrip('.'))
                            break

                    # Rough threshold: < 10% free pages is critical
                    # Assume 4096 bytes per page
                    if free_pages < 50000:  # ~200MB free
                        return MemoryPressureLevel.CRITICAL
                    elif free_pages < 150000:  # ~600MB free
                        return MemoryPressureLevel.WARN
            except Exception:
                pass

            # Default: normal
            return MemoryPressureLevel.NORMAL

        except Exception as e:
            logger.debug(f"[MEMORY] Pressure check failed: {e}")
            return MemoryPressureLevel.NORMAL

    def check(self) -> MemoryPressureLevel:
        """
        Zkontroluje aktuální memory pressure.

        Updates internal state and fires callbacks if level changed.
        Also updates throttle factor for budget management.
        """
        # Get current pressure
        if self._native_available:
            # Would read from dispatch source
            current = MemoryPressureLevel.NORMAL
        else:
            current = self._get_pressure_from_system()

        with self._lock:
            old_level = self._state.level
            self._state.level = current
            self._state.last_update = 0  # Would be time.time()

            # Update counters and admission state
            if current == MemoryPressureLevel.WARN:
                self._state.consecutive_warns += 1
                self._state.consecutive_criticals = 0
                # Sprint 82B: WARN throttle
                self._budget_throttle_factor = 0.5
                self._low_priority_suspended = False
                # Sprint 82C: Update admission state
                self._admission_state = AdmissionState.THROTTLED
            elif current == MemoryPressureLevel.CRITICAL:
                self._state.consecutive_criticals += 1
                self._state.consecutive_warns = 0
                # Sprint 82B: CRITICAL suspend
                self._budget_throttle_factor = 0.25
                self._low_priority_suspended = True
                # Sprint 82C: Update admission state
                self._admission_state = AdmissionState.EMERGENCY_CLEANUP_REQUESTED
            else:
                self._state.consecutive_warns = 0
                self._state.consecutive_criticals = 0
                # Reset to normal
                self._budget_throttle_factor = 1.0
                self._low_priority_suspended = False
                # Sprint 82C: Reset admission state
                self._admission_state = AdmissionState.NORMAL

            # Fire callbacks if level changed
            if current != old_level:
                logger.info(f"[MEMORY] Pressure: {old_level.name} -> {current.name}")

                # Sprint 82B: Lightweight callbacks only - do NOT do heavy work here
                if current == MemoryPressureLevel.WARN and self._on_warn:
                    try:
                        self._on_warn()
                    except Exception as e:
                        logger.warning(f"[MEMORY] on_warn callback error: {e}")

                elif current == MemoryPressureLevel.CRITICAL and self._on_critical:
                    try:
                        self._on_critical()
                    except Exception as e:
                        logger.warning(f"[MEMORY] on_critical callback error: {e}")

                elif current == MemoryPressureLevel.NORMAL and old_level != MemoryPressureLevel.NORMAL and self._on_normal:
                    try:
                        self._on_normal()
                    except Exception as e:
                        logger.warning(f"[MEMORY] on_normal callback error: {e}")

        return current

    def get_status(self) -> dict:
        """Status pro diagnostiku."""
        with self._lock:
            return {
                "level": self._state.level.name,
                "is_warn": self.is_warn,
                "is_critical": self.is_critical,
                "consecutive_warns": self._state.consecutive_warns,
                "consecutive_criticals": self._state.consecutive_criticals,
                "native_available": self._native_available,
                "budget_throttle_factor": self._budget_throttle_factor,
                "low_priority_suspended": self._low_priority_suspended,
                "admission_state": self._admission_state.name,  # Sprint 82C
            }

    def get_budget_throttle_factor(self) -> float:
        """
        Sprint 82B: Get budget throttle factor based on memory pressure.

        Returns:
            1.0 - normal operation
            0.5 - WARN level (50% budget)
        """
        with self._lock:
            return self._budget_throttle_factor

    def is_low_priority_suspended(self) -> bool:
        """Sprint 82B: Check if low priority work is suspended."""
        with self._lock:
            return self._low_priority_suspended
