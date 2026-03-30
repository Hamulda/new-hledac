"""
Resource Allocator with Predictive Modeling
==========================================

Predictive resource allocator with:
- Online linear regression (MLX) for RAM prediction
- Warm-up phase (first 5 queries use fixed allocation)
- Emergency brake (cancel lowest priority task when RSS > 6.2 GB)
- Bounded concurrent requests (max 3)
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
