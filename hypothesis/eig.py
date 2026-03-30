"""
Expected Information Gain (EIG) kalkulačka pro výběr akcí.
"""

import numpy as np
from typing import List, Dict, Any

from hledac.universal.hypothesis.dempster_shafer import DempsterShafer


class EIGCalculator:
    """Expected Information Gain calculator for action selection."""
    def __init__(self, bandit_arms: Dict = None):
        self.bandit_arms = bandit_arms or {}

    def compute_eig(self, hypothesis_set: List[DempsterShafer], action: Dict[str, Any]) -> float:
        """Spočítá EIG pro danou akci a množinu hypotéz."""
        current_entropy = self._entropy(hypothesis_set)
        expected_entropy = self._expected_entropy_after_action(hypothesis_set, action)
        return current_entropy - expected_entropy

    def _entropy(self, hypothesis_set: List[DempsterShafer]) -> float:
        """Vypočítá entropii pro množinu hypotéz."""
        beliefs = [h.belief() for h in hypothesis_set]
        beliefs = np.array(beliefs)
        # Normalizace
        beliefs = beliefs / (beliefs.sum() + 1e-8)
        # Shannon entropy
        return -np.sum(beliefs * np.log(beliefs + 1e-8))

    def _expected_entropy_after_action(self, hypothesis_set: List[DempsterShafer], action: Dict) -> float:
        """Očekávaná entropie po provedení akce (zjednodušená)."""
        # Zjednodušená verze - v reálné implementaci bychom simulovali výsledky
        return self._entropy(hypothesis_set) * 0.8
