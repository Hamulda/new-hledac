import math
from typing import Tuple


class BetaBinomial:
    def __init__(self, alpha: float = 1.0, beta: float = 1.0):
        self.alpha = alpha
        self.beta = beta

    def add_support(self, weight: float = 1.0):
        self.alpha += weight

    def add_contradict(self, weight: float = 1.0):
        self.beta += weight

    def mean(self) -> float:
        s = self.alpha + self.beta
        return self.alpha / s if s > 0 else 0.5

    def variance(self) -> float:
        s = self.alpha + self.beta
        if s <= 0:
            return 0.25
        return (self.alpha * self.beta) / (s * s * (s + 1))

    def credible_interval(self, p: float = 0.95) -> Tuple[float, float]:
        std = math.sqrt(self.variance())
        return max(0.0, self.mean() - 2 * std), min(1.0, self.mean() + 2 * std)

    def conflict(self) -> float:
        return min(1.0, self.variance() * 4)
