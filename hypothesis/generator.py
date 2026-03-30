"""
Hypothesis generator – generuje hypotézy z kontextu pomocí SLM.
"""

import asyncio
import logging
from typing import List, Dict, Any

from hledac.universal.planning.slm_decomposer import SLMDecomposer
from hledac.universal.evidence_log import EvidenceLog

logger = logging.getLogger(__name__)


class HypothesisGenerator:
    """Generator hypotéz z výzkumného kontextu."""
    def __init__(self, decomposer: SLMDecomposer, evidence_log: EvidenceLog):
        self.decomposer = decomposer
        self.evidence_log = evidence_log

    async def generate(self, context: Dict) -> List[Dict]:
        """Generuje hypotézy z kontextu."""
        hypotheses = []

        # Generování pomocí SLM
        slm_hypotheses = await self._generate_from_slm(context)
        hypotheses.extend(slm_hypotheses)

        # Null hypotéza (všechno je náhoda)
        hypotheses.append({
            'id': 'null',
            'description': 'Všechna pozorování jsou náhodná.',
            'type': 'null',
            'priority': 1
        })

        # Opak hlavní hypotézy
        main_hyp = slm_hypotheses[0] if slm_hypotheses else {}
        opposite_desc = f"Opak hypotézy: {main_hyp.get('description', '')}"
        hypotheses.append({
            'id': 'opposite',
            'description': opposite_desc,
            'type': 'opposite',
            'priority': 1
        })

        return hypotheses

    async def _generate_from_slm(self, context: Dict) -> List[Dict]:
        """Generuje hypotézy pomocí SLM decomposeru."""
        try:
            # Použijeme decompose jako generátor hypotéz
            result = await self.decomposer.decompose(str(context), context)
            if result:
                return [{
                    'id': f"slm_{i}",
                    'description': r.get('description', str(r)),
                    'type': 'slm',
                    'priority': r.get('priority', 5)
                } for i, r in enumerate(result)]
        except Exception as e:
            logger.warning(f"SLM generování hypotéz selhalo: {e}")
        return []
