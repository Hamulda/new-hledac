"""
Resource Allocator with Predictive Modeling
==========================================

ROLE: Canonical REQUEST-LEVEL BUDGETING / CONCURRENCY PRIMITIVE (not a sampler or governor).

This module provides:
- Request-level RAM budgeting with MLX linear regression prediction
- Adaptive concurrency semaphore based on memory pressure
- Emergency brake (cancel lowest priority task)
- Concurrency limits that adapt to system memory pressure

AUTHORITY BOUNDARY:
- SAMPLER (utils/uma_budget.py): raw memory sampling, no policy
- GOVERNOR (core/resource_governor.py): policy/hysteresis/runtime governance
- ALLOCATOR (resource_allocator.py): request-level budgeting/concurrency

Note: get_memory_pressure_level() in this module uses percent-based thresholds
(pct > 85 → warn, pct > 93 → critical) which are independent from
uma_budget.py absolute-MB thresholds. These serve different purposes:
- uma_budget.py: absolute system+MLX used (Calibrated for M1 8GB UMA)
- resource_allocator.py: percent-based system pressure (for AdaptiveSemaphore decisions)
"""

import time
import psutil
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Try to import MLX for predictive modeling
try:
    import mlx.core as mx
    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False

# Named fallback constant for non-MLX RAM estimation.
# Conservative 500MB default when MLX linear regression is unavailable.
# Chosen because: (a) fits within M1 8GB UMA budget, (b) covers typical
# lightweight research requests, (c) is well above the 100MB minimum floor.
_FALLBACK_RAM_ESTIMATE_MB: float = 500.0
_FALLBACK_RAM_ESTIMATE_GB: float = 0.5


@dataclass
class ResourceBudget:
    """Resource budget for a request."""
    ram_mb: int
    time_sec: float
    priority: int
    request_id: str


class ResourceExhausted(Exception):
    """Raised when resources cannot be allocated."""
    pass


class ResourceAllocator:
    """
    Predictive resource allocator with:
    - MAX_CONCURRENT: Maximum concurrent requests (default 3)
    - MAX_RAM_GB: Maximum RAM usage before rejecting new requests (default 5.5 GB)
    - EMERGENCY_RAM_GB: Threshold for emergency brake (default 6.2 GB)
    - Warm-up: First 5 queries use fixed allocation
    - MLX-based linear regression for prediction after warm-up
    """

    MAX_CONCURRENT: int = 3
    MAX_RAM_GB: float = 5.5
    EMERGENCY_RAM_GB: float = 6.2
    WARMUP_QUERIES: int = 5

    def __init__(self):
        self.active_requests: Dict[str, ResourceBudget] = {}
        self.total_ram_mb: float = 0.0

        # History for MLX linear regression: (features, actual_ram_mb)
        self.history: List[tuple[List[float], float]] = []
        self.coeffs: Optional[mx.array] = None
        self.warmup_counter: int = 0

    def _extract_features(self, ctx: Any) -> List[float]:
        """Extract feature vector for RAM prediction."""
        return [
            float(len(ctx.query)) if hasattr(ctx, 'query') else 100.0,
            float(ctx.depth) if hasattr(ctx, 'depth') else 1.0,
            float(len(getattr(ctx, 'selected_sources', []))),
            float(getattr(ctx, 'complexity_score', 0.5)),
        ]

    def _update_model(self):
        """Update MLX linear regression model from history."""
        if len(self.history) < self.WARMUP_QUERIES:
            self.warmup_counter += 1
            return

        if self.warmup_counter < self.WARMUP_QUERIES:
            self.warmup_counter += 1
            return

        try:
            # Build feature matrix and target vector
            X = mx.array([f for f, _ in self.history])
            y = mx.array([a for _, a in self.history])

            # Add bias term (column of ones)
            ones = mx.ones((X.shape[0], 1))
            X = mx.concatenate([X, ones], axis=1)

            # Solve least squares: X @ coeffs = y
            self.coeffs, _, _, _ = mx.linalg.lstsq(X, y, rcond=None)
            logger.debug(f"Updated MLX prediction model with {len(self.history)} samples")
        except Exception as e:
            logger.warning(f"Failed to update MLX model: {e}")
            self.coeffs = None

    def predict_ram(self, ctx: Any) -> float:
        """Predict RAM usage for a context using MLX linear regression."""
        if self.coeffs is None:
            # Default prediction during warm-up or if MLX model unavailable
            return _FALLBACK_RAM_ESTIMATE_MB

        try:
            features = mx.array(self._extract_features(ctx) + [1.0])  # +1 for bias
            prediction = float(mx.sum(features * self.coeffs))
            return max(100.0, prediction)  # Minimum 100 MB
        except Exception as e:
            logger.warning(f"RAM prediction failed: {e}")
            return _FALLBACK_RAM_ESTIMATE_MB

    def can_accept(self, ctx: Any) -> bool:
        """Check if a new request can be accepted."""
        if len(self.active_requests) >= self.MAX_CONCURRENT:
            return False

        predicted = self.predict_ram(ctx)
        if self.total_ram_mb + predicted > self.MAX_RAM_GB * 1024:
            return False

        return True

    def acquire(self, request_id: str, ctx: Any, priority: int) -> ResourceBudget:
        """Acquire resources for a new request."""
        if not self.can_accept(ctx):
            raise ResourceExhausted(f"Cannot accept request {request_id}: resources exhausted")

        predicted = self.predict_ram(ctx)

        budget = ResourceBudget(
            ram_mb=int(predicted),
            time_sec=300.0,
            priority=priority,
            request_id=request_id
        )

        self.active_requests[request_id] = budget
        self.total_ram_mb += predicted

        logger.debug(f"Allocated {predicted:.0f} MB for request {request_id} (priority {priority})")

        return budget

    def release(self, request_id: str, actual_ram_mb: float):
        """Release resources and record actual usage for learning."""
        if request_id in self.active_requests:
            budget = self.active_requests.pop(request_id)
            self.total_ram_mb -= budget.ram_mb

            # Record actual usage for MLX learning
            ctx = getattr(budget, 'context', None)
            if ctx is not None:
                features = self._extract_features(ctx)
                self.history.append((features, actual_ram_mb))

                # Keep history bounded
                if len(self.history) > 100:
                    self.history = self.history[-50:]

            self._update_model()
            logger.debug(f"Released request {request_id}, actual RAM: {actual_ram_mb:.0f} MB")

    def emergency_brake(self) -> Optional[str]:
        """
        Emergency brake: cancel lowest priority task if RSS > EMERGENCY_RAM_GB.
        Returns cancelled request_id or None.
        """
        try:
            mem = psutil.virtual_memory()
            if mem.used < self.EMERGENCY_RAM_GB * (1024 ** 3):
                return None

            if not self.active_requests:
                return None

            # Find task with lowest priority (highest priority number = least important)
            lowest = max(
                self.active_requests.values(),
                key=lambda b: b.priority
            )

            self.cancel(lowest.request_id)
            logger.warning(f"Emergency brake: cancelled {lowest.request_id} (RSS: {mem.used / (1024**3):.2f} GB)")
            return lowest.request_id

        except Exception as e:
            logger.error(f"Emergency brake failed: {e}")
            return None

    def cancel(self, request_id: str):
        """Cancel a specific request."""
        if request_id in self.active_requests:
            budget = self.active_requests.pop(request_id)
            self.total_ram_mb -= budget.ram_mb
            logger.info(f"Cancelled request {request_id}")

    def get_stats(self) -> Dict[str, Any]:
        """Get current allocator statistics."""
        return {
            "active_requests": len(self.active_requests),
            "total_ram_mb": self.total_ram_mb,
            "warmup_counter": self.warmup_counter,
            "history_size": len(self.history),
            "model_ready": self.coeffs is not None,
        }


# Sprint 8VD §C: Memory Pressure Governor
# psutil is already imported at the top of this module

def get_memory_pressure_level() -> str:
    """
    Read memory pressure via psutil (ARM64 native, no subprocess overhead).

    Thresholds calibrated for M1 8GB UMA:
      > 85% used  → warn      (~6.8 GB)
      > 93% used  → critical  (~7.4 GB)
    Swap is used as a secondary signal.
    """
    try:
        vm = psutil.virtual_memory()
        pct = vm.percent
        sw = psutil.swap_memory()
        if pct > 93 or sw.percent > 50:
            return "critical"
        if pct > 85 or sw.percent > 25:
            return "warn"
    except Exception:
        pass
    return "normal"


def get_recommended_concurrency() -> Dict[str, int]:
    """Return concurrency limits based on memory pressure level."""
    level = get_memory_pressure_level()
    if level == "critical":
        # Sprint 8VF §C.2: Unload ANE embedder at CRITICAL to free ~22MB
        try:
            from hledac.universal.brain.ane_embedder import unload_ane_embedder
            unload_ane_embedder()
        except Exception:
            pass
        import gc; gc.collect()
    return {
        "normal":   {"fetch": 20, "parse_workers": 4, "ml_jobs": 1, "browser": 1},
        "warn":     {"fetch": 8,  "parse_workers": 2, "ml_jobs": 0, "browser": 0},
        "critical": {"fetch": 2,  "parse_workers": 1, "ml_jobs": 0, "browser": 0},
    }[level]


# ── Sprint 8VG-C: Adaptive Concurrency ─────────────────────────────────────────

import asyncio
import platform
import time

_CONCURRENCY_FLOOR = 1
_CONCURRENCY_CEILING = 3  # M1 8GB hard limit


def get_adaptive_concurrency() -> int:
    """
    Dynamicky vypočítej optimální concurrency based on memory pressure.
    M1 8GB: max 3, min 1.
    """
    pressure_str = get_memory_pressure_level()
    # Map string level to numeric 0-1 range
    pressure_map = {"normal": 0.0, "warn": 0.6, "critical": 0.9}
    pressure = pressure_map.get(pressure_str, 0.0)

    if pressure < 0.4:
        return _CONCURRENCY_CEILING      # 3 paralelní tasks
    elif pressure < 0.6:
        return 2                          # 2 tasks
    elif pressure < 0.75:
        return 1                          # 1 task — opatrně
    else:
        return _CONCURRENCY_FLOOR         # memory critical — force sequential


class AdaptiveSemaphore:
    """
    Semaphore jehož limit se adaptivně mění podle memory pressure.
    Drop-in replacement pro asyncio.Semaphore v orchestrátoru.
    """

    def __init__(self, initial_limit: int = _CONCURRENCY_CEILING):
        self._limit = initial_limit
        self._semaphore = asyncio.Semaphore(initial_limit)
        self._last_check = time.monotonic()
        self._check_interval = 5.0  # přehodnoť každých 5s

    async def _maybe_update_limit(self) -> None:
        """Aktualizuj limit pokud uplynulo dost času od posledního checku."""
        now = time.monotonic()
        if now - self._last_check < self._check_interval:
            return
        self._last_check = now

        new_limit = get_adaptive_concurrency()
        if new_limit != self._limit:
            self._limit = new_limit
            # Vytvoř nový semaphore s novým limitem
            # POZOR: existující holders zůstanou — nový limit se projeví až po release
            self._semaphore = asyncio.Semaphore(new_limit)

    async def __aenter__(self):
        await self._maybe_update_limit()
        await self._semaphore.acquire()
        return self

    async def __aexit__(self, *args):
        self._semaphore.release()

    @property
    def current_limit(self) -> int:
        return self._limit


def get_mlx_memory_mb() -> float:
    """
    Vrátí aktuální MLX cache usage v MB.
    Funguje pouze na macOS/Darwin s MLX.
    """
    if platform.system() != "Darwin":
        return 0.0
    try:
        import mlx.core as mx
        if hasattr(mx.metal, "get_cache_memory"):
            return mx.metal.get_cache_memory() / (1024 * 1024)
        elif hasattr(mx.metal, "get_active_memory"):
            return mx.metal.get_active_memory() / (1024 * 1024)
    except Exception:
        pass
    return 0.0


def clear_mlx_cache_if_needed(threshold_mb: float = 500.0) -> bool:
    """
    Uvolni MLX cache pokud přesahuje threshold.
    Vrací True pokud byl cache vyčištěn.
    M1: cache > 500MB = čas uklidit.
    """
    if platform.system() != "Darwin":
        return False
    try:
        import mlx.core as mx
        cache_mb = get_mlx_memory_mb()
        if cache_mb > threshold_mb:
            if hasattr(mx.metal, "clear_cache"):
                mx.metal.clear_cache()
                return True
    except Exception:
        pass
    return False

