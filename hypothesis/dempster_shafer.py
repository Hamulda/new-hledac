"""
Dempster-Shafer teorie pro práci s hypotézami.
"""

import numpy as np
from typing import Set, Dict, Optional


class DempsterShafer:
    """Dempster-Shafer theory implementation for hypothesis management."""
    def __init__(self, hypotheses: Set[str]):
        self.hypotheses = hypotheses
        self.masses = {h: 0.0 for h in hypotheses}
        self.unknown = 1.0
        self.conflict = 0.0

    def add_evidence(self, hypothesis: str, mass: float, source_weight: float = 1.0):
        """Přidá evidence pro hypotézu s váhou zdroje."""
        weighted_mass = mass * source_weight
        K = self.masses.get(hypothesis, 0) * weighted_mass
        self.conflict += K
        norm = 1 - K + 1e-8
        for h in self.hypotheses:
            if h == hypothesis:
                self.masses[h] = (self.masses[h] * (1 - weighted_mass) + weighted_mass * self.unknown) / norm
            else:
                self.masses[h] = self.masses[h] * (1 - weighted_mass) / norm
        self.unknown = self.unknown * (1 - weighted_mass) / norm

    def belief(self, hypothesis: Optional[str] = None) -> float:
        """Vrací belief pro hypotézu nebo celkový belief."""
        if hypothesis is None:
            return sum(self.masses.values())
        return self.masses.get(hypothesis, 0)

    def plausibility(self, hypothesis: str) -> float:
        """Vrací plausibility hypotézy."""
        neg_mass = sum(v for k, v in self.masses.items() if k != hypothesis)
        return 1 - neg_mass - self.conflict

    def conflict_mass(self) -> float:
        """Vrací conflict mass."""
        return self.conflict
