"""
hypothesis/validator.py
Sprint 8VG-A: Hypothesis Validator
Valides hypotheses against action results in background.
"""
from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Hypothesis:
    """Reprezentace hypotézy."""
    statement: str
    confidence: float = 0.5
    evidence_count: int = 0
    validated: bool = False


class HypothesisValidator:
    """
    Background hypothesis validation.
    Neblokuje OODA loop — běží v asyncio.create_task.
    """

    def __init__(self):
        self._hypotheses: List[Hypothesis] = []
        self._validation_log: List[Dict[str, Any]] = []

    async def validate_against(self, evidence: Dict[str, Any]) -> List[Hypothesis]:
        """
        Validuje hypotézy proti novému důkazu.
        Vrací seznam validovaných hypotéz.
        """
        validated = []
        
        for hypothesis in self._hypotheses:
            if hypothesis.validated:
                continue
            
            # Prostá heuristická validace - M1 friendly
            evidence_text = str(evidence)
            
            # Kontrola relevance
            if hypothesis.statement.lower() in evidence_text.lower():
                hypothesis.evidence_count += 1
                hypothesis.confidence = min(1.0, hypothesis.confidence + 0.1)
                
                if hypothesis.evidence_count >= 3:
                    hypothesis.validated = True
                    validated.append(hypothesis)
            
            self._validation_log.append({
                "hypothesis": hypothesis.statement,
                "evidence_keys": list(evidence.keys()),
                "timestamp": time.monotonic(),
            })
        
        return validated

    def add_hypothesis(self, statement: str, initial_confidence: float = 0.5) -> Hypothesis:
        """Přidá novou hypotézu."""
        h = Hypothesis(
            statement=statement,
            confidence=initial_confidence,
        )
        self._hypotheses.append(h)
        return h

    def get_hypotheses(self) -> List[Hypothesis]:
        """Vrátí všechny hypotézy."""
        return self._hypotheses.copy()

    def get_validation_log(self) -> List[Dict[str, Any]]:
        """Vrátí log validací."""
        return self._validation_log.copy()
