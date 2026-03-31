"""
autonomy/closed_loop_seed.py
Sprint 8VG-A: Closed-loop seed generation
Výstupy sprintu → vstupy dalšího sprintu.
"""
from __future__ import annotations
import asyncio
import json
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    pass

import logging

logger = logging.getLogger(__name__)


@dataclass
class SeedCandidate:
    """Seed candidate extracted from action result."""
    query: str
    source_action: str
    confidence: float  # 0-1
    entity_type: str   # "domain", "ip", "person", "org", "hash"
    timestamp: float = field(default_factory=time.monotonic)
    used: bool = False


class ClosedLoopSeedGenerator:
    """
    Extrahuje seed queries z výsledků akcí a injectuje je do dalšího sprintovacího kola.
    Napojení: volat `ingest_result()` po každé akci, `get_next_seeds()` na začátku kola.
    """

    def __init__(self, max_seeds: int = 50, min_confidence: float = 0.6):
        self._seeds: deque[SeedCandidate] = deque(maxlen=max_seeds)
        self._min_confidence = min_confidence
        self._extraction_patterns = self._build_patterns()

    def _build_patterns(self) -> dict:
        """Regex patterns pro entity extraction z výsledků."""
        return {
            "domain": re.compile(r'\b(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b', re.I),
            "ip": re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
            "hash_md5": re.compile(r'\b[0-9a-f]{32}\b', re.I),
            "hash_sha256": re.compile(r'\b[0-9a-f]{64}\b', re.I),
            "onion": re.compile(r'\b[a-z2-7]{56}\.onion\b', re.I),
            "asn": re.compile(r'\bAS\d{1,6}\b'),
        }

    async def ingest_result(self, result: dict, source_action: str) -> int:
        """
        Zpracuj výsledek akce a extrahuj seed candidates.
        Vrací počet extrahovaných seedů.
        """
        extracted = 0
        text = json.dumps(result)

        for entity_type, pattern in self._extraction_patterns.items():
            matches = set(pattern.findall(text))
            for match in matches:
                confidence = self._score_entity(match, entity_type, result)
                if confidence >= self._min_confidence:
                    self._seeds.append(SeedCandidate(
                        query=match,
                        source_action=source_action,
                        confidence=confidence,
                        entity_type=entity_type,
                    ))
                    extracted += 1

        return extracted

    def _score_entity(self, entity: str, entity_type: str, context: dict) -> float:
        """Heuristic confidence scoring — M1 friendly (pure Python, no ML)."""
        base = 0.6
        # Bonusy za kontext
        if entity_type == "onion":
            base = 0.9  # onion adresy jsou vždy zajímavé
        elif entity_type in ("hash_md5", "hash_sha256"):
            base = 0.85  # hashe = IOC
        # Penalizace za common falešné pozitivy
        if entity in ("127.0.0.1", "0.0.0.0", "255.255.255.255"):
            base = 0.0
        return min(1.0, base)

    def get_next_seeds(self, limit: int = 10) -> List[SeedCandidate]:
        """Vrátí top-N nepoužité seeds seřazené dle confidence."""
        unused = [s for s in self._seeds if not s.used]
        top = sorted(unused, key=lambda s: s.confidence, reverse=True)[:limit]
        for seed in top:
            seed.used = True
        return top

    def inject_into_query(self, base_query: str, seeds: List[SeedCandidate]) -> List[str]:
        """
        Rozšiř base_query o seed entity → vytvoř derived queries pro další sprint.
        """
        queries = [base_query]  # originál vždy první
        for seed in seeds[:5]:  # max 5 derivátů
            if seed.entity_type == "domain":
                queries.append(f"{base_query} {seed.query} infrastructure")
            elif seed.entity_type == "ip":
                queries.append(f"ASN BGP history {seed.query}")
            elif seed.entity_type in ("hash_md5", "hash_sha256"):
                queries.append(f"malware hash {seed.query} attribution")
            elif seed.entity_type == "onion":
                queries.append(f"onion service {seed.query}")
            else:
                queries.append(f"{base_query} {seed.query}")
        return queries
