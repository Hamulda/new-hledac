"""
ClaimsCoordinator - Delegates claims pipeline to coordinator
==========================================================

Implements the stable coordinator interface (start/step/shutdown) for:
- Claim extraction from evidence
- ClaimClusterIndex updates
- Stance scoring and veracity updates

This enables the orchestrator to become a thin "spine" that delegates
claims logic to this coordinator.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from .base import UniversalCoordinator

logger = logging.getLogger(__name__)


# Maximum uncertain clusters to return per step (bounded output)
MAX_UNCERTAIN_CLUSTERS = 10

# Maximum pending evidence IDs to prevent unbounded memory growth
# 10000 chosen as reasonable upper bound for research session
# Keeps last N evidence IDs (keep-last determinism)
MAX_PENDING_EVIDENCE_IDS = 10000


@dataclass
class ClaimsCoordinatorConfig:
    """Configuration for ClaimsCoordinator."""
    max_evidence_per_step: int = 10
    max_clusters_per_step: int = 20
    enable_stance_update: bool = True
    enable_veracity_update: bool = True


class ClaimsCoordinator(UniversalCoordinator):
    """
    Coordinator for claims pipeline delegation.

    Responsibilities:
    - Extract claims from new evidence
    - Update ClaimClusterIndex
    - Update stance scores and veracity priors
    - Return bounded outputs (cluster counts, uncertain IDs)
    """

    def __init__(
        self,
        config: Optional[ClaimsCoordinatorConfig] = None,
        max_concurrent: int = 3,
    ):
        super().__init__(name="ClaimsCoordinator", max_concurrent=max_concurrent)
        self._config = config or ClaimsCoordinatorConfig()

        # State - Bounded pending evidence using deque+set for O(1) membership + keep-last determinism
        self._pending_evidence_ids: deque = deque(maxlen=MAX_PENDING_EVIDENCE_IDS)
        self._pending_evidence_set: Set[str] = set()  # O(1) membership check
        self._clusters_updated: int = 0
        self._evidence_processed: int = 0
        self._uncertain_clusters: List[str] = []
        self._stop_reason: Optional[str] = None

        # Orchestrator reference (set via start)
        self._orchestrator: Optional[Any] = None
        self._ctx: Dict[str, Any] = {}

    def get_supported_operations(self) -> List[Any]:
        """Return supported operation types."""
        from .base import OperationType
        return [OperationType.SYNTHESIS, OperationType.RESEARCH]

    async def handle_request(
        self,
        operation_ref: str,
        decision: Any
    ) -> Any:
        """
        Handle a decision request (required by UniversalCoordinator base).

        For spine pattern, we use start/step/shutdown instead.
        This is a compatibility method.
        """
        # Delegate to step with decision as context
        result = await self.step({'decision': decision})
        return result

    async def _do_initialize(self) -> bool:
        """Initialize coordinator."""
        logger.info("ClaimsCoordinator initialized")
        return True

    async def _do_start(self, ctx: Dict[str, Any]) -> None:
        """
        Start coordinator with context from orchestrator.

        Expected ctx keys:
        - pending_evidence: List[str] - evidence IDs to process
        - orchestrator: reference to orchestrator instance
        - claim_index: ClaimClusterIndex instance
        """
        self._ctx = ctx
        self._orchestrator = ctx.get('orchestrator')

        # Load pending evidence if provided
        if 'pending_evidence' in ctx:
            # Convert to deque with bounded size (keep-last)
            items = list(ctx['pending_evidence'])[-MAX_PENDING_EVIDENCE_IDS:]
            self._pending_evidence_ids = deque(items, maxlen=MAX_PENDING_EVIDENCE_IDS)
            self._pending_evidence_set = set(items)

        logger.info(f"ClaimsCoordinator started with {len(self._pending_evidence_ids)} pending evidence")

    async def _do_step(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute one claims processing step.

        Process up to max_evidence_per_step from pending evidence.
        Returns bounded output with cluster updates.
        """
        # Update context
        self._ctx.update(ctx)

        # Add new evidence from ctx (bounded, keep-last determinism)
        new_evidence = ctx.get('new_evidence_ids', [])
        for evidence_id in new_evidence:
            if evidence_id not in self._pending_evidence_set:
                self._pending_evidence_set.add(evidence_id)
                self._pending_evidence_ids.append(evidence_id)
                # deque with maxlen automatically evicts oldest when full

        if not self._pending_evidence_ids:
            self._stop_reason = "no_pending_evidence"
            return self._get_step_result()

        # Process evidence (take from front, leave rest)
        evidence_to_process = []
        for _ in range(min(self._config.max_evidence_per_step, len(self._pending_evidence_ids))):
            if self._pending_evidence_ids:
                eid = self._pending_evidence_ids.popleft()
                self._pending_evidence_set.discard(eid)
                evidence_to_process.append(eid)

        clusters_updated = 0
        uncertain_clusters = []

        for evidence_id in evidence_to_process:
            # Process claim extraction
            result = await self._process_evidence(evidence_id)
            if result:
                self._evidence_processed += 1
                clusters_updated += result.get('clusters_updated', 0)

                # Track uncertain clusters
                uncertain = result.get('uncertain_clusters', [])
                uncertain_clusters.extend(uncertain)

        self._clusters_updated += clusters_updated
        self._uncertain_clusters = (self._uncertain_clusters + uncertain_clusters)[:MAX_UNCERTAIN_CLUSTERS]

        return self._get_step_result(clusters_updated, uncertain_clusters)

    def _get_step_result(
        self,
        clusters_updated: int = 0,
        uncertain_clusters: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Get bounded step result."""
        return {
            'clusters_updated': clusters_updated,
            'evidence_processed': self._evidence_processed,
            'total_clusters_updated': self._clusters_updated,
            'uncertain_clusters': (uncertain_clusters or [])[:MAX_UNCERTAIN_CLUSTERS],
            'stop_reason': self._stop_reason,
            'pending_evidence': len(self._pending_evidence_ids),
        }

    async def _process_evidence(self, evidence_id: str) -> Optional[Dict[str, Any]]:
        """
        Process a single evidence ID for claims.

        Delegates to orchestrator's claim extraction methods.
        """
        if not self._orchestrator:
            logger.warning(f"ClaimsCoordinator: no orchestrator reference for {evidence_id}")
            return None

        try:
            # Get claim index from orchestrator
            claim_index = None
            if hasattr(self._orchestrator, '_research_mgr'):
                rm = self._orchestrator._research_mgr
                if hasattr(rm, '_claim_index'):
                    claim_index = rm._claim_index

            if not claim_index:
                logger.warning(f"ClaimsCoordinator: no claim_index available")
                return None

            # Load evidence packet from disk (not in memory)
            evidence_packet = self._load_evidence_packet(evidence_id)
            if not evidence_packet:
                return None

            # Extract claims (would use orchestrator's method)
            claims = await self._extract_claims(evidence_packet)
            if not claims:
                return None

            # Update cluster index
            uncertain = []
            for claim in claims:
                cluster_id = claim_index.add_claim(
                    evidence_id=evidence_id,
                    claim_text=claim.get('text', ''),
                    polarity=claim.get('polarity', 'neutral'),
                    domain=evidence_packet.get('domain', 'unknown')
                )
                if cluster_id:
                    # Check if cluster needs stance update
                    if self._config.enable_stance_update:
                        # Would trigger stance update
                        pass

                    # Track uncertain clusters (low evidence count)
                    cluster = claim_index.get_cluster(cluster_id)
                    if cluster and len(cluster.evidence_ids) < 3:
                        uncertain.append(cluster_id)

            return {
                'clusters_updated': len(claims),
                'uncertain_clusters': uncertain,
            }

        except Exception as e:
            logger.warning(f"ClaimsCoordinator: failed to process {evidence_id}: {e}")
            return None

    def _load_evidence_packet(self, evidence_id: str) -> Optional[Dict[str, Any]]:
        """Load evidence packet from disk (RAM-safe)."""
        if not self._orchestrator:
            return None

        try:
            # Get evidence packet storage from orchestrator
            if hasattr(self._orchestrator, '_research_mgr'):
                rm = self._orchestrator._research_mgr
                if hasattr(rm, '_evidence_packet_storage'):
                    storage = rm._evidence_packet_storage
                    return storage.load_packet(evidence_id)
            return None
        except Exception as e:
            logger.debug(f"ClaimsCoordinator: failed to load packet {evidence_id}: {e}")
            return None

    async def _extract_claims(self, evidence_packet: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract claims from evidence packet.

        This would delegate to the orchestrator's claim extraction logic.
        For now, returns empty list as placeholder.
        """
        # Thisestrator's claim would use the orch extraction
        # For now, return empty - real implementation would call
        # the orchestrator's internal claim extraction method
        return []

    async def _do_shutdown(self, ctx: Dict[str, Any]) -> None:
        """Cleanup on shutdown."""
        logger.info(f"ClaimsCoordinator shutting down: {self._evidence_processed} evidence processed")
        self._pending_evidence_ids.clear()
        self._pending_evidence_set.clear()
        self._uncertain_clusters.clear()
