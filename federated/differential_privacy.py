"""
Differential privacy pro federated learning.
"""

import numpy as np
from typing import Dict
import logging

logger = logging.getLogger(__name__)


class DPNoise:
    """Differential noise pro federated learning."""

    def __init__(self, epsilon: float = 1.0, delta: float = 1e-5, sensitivity: float = 1.0):
        self.epsilon = epsilon
        self.delta = delta
        self.sensitivity = sensitivity
        # Gaussian noise scale: sigma >= sensitivity * sqrt(2*ln(1.25/delta)) / epsilon
        self.noise_scale = sensitivity * np.sqrt(2 * np.log(1.25 / delta)) / epsilon
        logger.info(f"DPNoise initialized: epsilon={epsilon}, delta={delta}, noise_scale={self.noise_scale:.4f}")

    def clip_update(self, weights: Dict[str, np.ndarray], max_norm: float = 1.0) -> Dict[str, np.ndarray]:
        """Ořízne update (gradient clipping)."""
        clipped = {}
        for k, v in weights.items():
            norm = np.linalg.norm(v)
            if norm > max_norm:
                clipped[k] = v * (max_norm / norm)
            else:
                clipped[k] = v
        return clipped

    def add_noise(self, weights: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        """Přidá Gaussovský šum."""
        noisy = {}
        for k, v in weights.items():
            noise = np.random.normal(0, self.noise_scale, v.shape).astype(np.float32)
            noisy[k] = v + noise
        return noisy


class RDPCalculator:
    """Rényi Differential Privacy kalkulačka."""

    def __init__(self, noise_scale: float, delta: float = 1e-5):
        self.noise_scale = noise_scale
        self.delta = delta

    def get_epsilon(self, q: float, steps: int, alpha: float = 10.0) -> float:
        """
        Vypočítá epsilon z Rényi DP.

        Args:
            q: sampling ratio
            steps: počet kroků
            alpha: Rényi parameter (order)
        """
        # Zjednodušená RDP -> DP konverze
        # Pro Gaussian mechanism: RDP(delta) = alpha / (2 * sigma^2) * q^2
        rdp = (alpha * q * q) / (2 * self.noise_scale * self.noise_scale)

        # Konverze RDP -> (epsilon, delta)-DP
        # epsilon = RDP + log(1/delta) / (alpha - 1)
        epsilon = rdp + np.log(1 / self.delta) / (alpha - 1)

        return epsilon * steps  # Multi-step composition
