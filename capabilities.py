"""
Capability System for Autonomous Orchestrator

Provides capability gating for M1 8GB optimization:
- Only load required modules based on research profile
- Track availability with reasons
- Enable on-demand initialization
"""

from __future__ import annotations

import asyncio
import gc
import logging
from enum import Enum
from typing import Any, Dict, Optional, Set, Callable, Awaitable, TYPE_CHECKING

if TYPE_CHECKING:
    from .types import AnalyzerResult
from dataclasses import dataclass

try:
    import mlx.core as mx
    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False
    mx = None

logger = logging.getLogger(__name__)


class Capability(Enum):
    """Research capabilities that can be dynamically loaded."""
    # Knowledge & RAG
    GRAPH_RAG = "graph_rag"
    ENTITY_LINKING = "entity_linking"
    RERANKING = "reranking"
    CONTEXT_GRAPH = "context_graph"

    # Document Intelligence
    METADATA_EXTRACT = "metadata_extract"
    DOC_INTEL = "doc_intel"
    LONG_CONTEXT = "long_context"

    # Network & OSINT
    STEALTH = "stealth"
    DNS_TUNNEL = "dns_tunnel"
    NETWORK_RECON = "network_recon"
    DARK_WEB = "dark_web"

    # Analysis
    TEMPORAL = "temporal"
    PATTERN_MINING = "pattern_mining"
    INSIGHT = "insight"

    # Crypto & Security
    CRYPTO_INTEL = "crypto_intel"
    STEGO = "stego"
    BLOCKCHAIN = "blockchain"

    # Advanced
    SNN = "snn"
    FEDERATED = "federated"
    QUANTUM_PATH = "quantum_path"
    META_OPTIMIZER = "meta_optimizer"

    # Tree of Thoughts
    TOT = "tot"

    # Models
    HERMES = "hermes"
    MODERNBERT = "modernbert"
    GLINER = "gliner"


@dataclass
class CapabilityStatus:
    """Status of a capability."""
    available: bool
    reason: str = ""
    module_path: str = ""
    loader: Optional[Callable[[], Awaitable[bool]]] = None


class CapabilityRegistry:
    """Registry tracking which capabilities are available and why."""

    def __init__(self):
        self._status: Dict[Capability, CapabilityStatus] = {}
        self._loaded: Set[Capability] = set()
        self._lock = asyncio.Lock()

    def register(
        self,
        capability: Capability,
        available: bool = False,
        reason: str = "",
        module_path: str = "",
        loader: Optional[Callable[[], Awaitable[bool]]] = None
    ) -> None:
        """Register a capability."""
        self._status[capability] = CapabilityStatus(
            available=available,
            reason=reason,
            module_path=module_path,
            loader=loader
        )

    def is_available(self, capability: Capability) -> bool:
        """Check if capability is available."""
        if capability in self._loaded:
            return True
        status = self._status.get(capability)
        return status.available if status else False

    def get_reason(self, capability: Capability) -> str:
        """Get reason for unavailability."""
        status = self._status.get(capability)
        return status.reason if status else "Not registered"

    async def load(self, capability: Capability) -> bool:
        """Load a capability on demand."""
        async with self._lock:
            if capability in self._loaded:
                return True

            status = self._status.get(capability)
            if not status:
                logger.warning(f"[CAPABILITY] {capability.value} not registered")
                return False

            if not status.available:
                logger.warning(
                    f"[CAPABILITY] {capability.value} unavailable: {status.reason}"
                )
                return False

            if status.loader:
                try:
                    success = await status.loader()
                    if success:
                        self._loaded.add(capability)
                        logger.info(f"[CAPABILITY] {capability.value} loaded")
                        return True
                    else:
                        logger.error(f"[CAPABILITY] {capability.value} loader failed")
                        return False
                except Exception as e:
                    logger.error(f"[CAPABILITY] {capability.value} load error: {e}")
                    return False
            else:
                # No loader needed, just mark as loaded
                self._loaded.add(capability)
                return True

    def unload(self, capability: Capability) -> None:
        """Mark capability as unloaded."""
        self._loaded.discard(capability)
        logger.info(f"[CAPABILITY] {capability.value} unloaded")

    def get_loaded(self) -> Set[Capability]:
        """Get set of currently loaded capabilities."""
        return self._loaded.copy()

    def get_all_available(self) -> Dict[Capability, str]:
        """Get all available capabilities with module paths."""
        return {
            cap: status.module_path
            for cap, status in self._status.items()
            if status.available
        }

    def get_all_unavailable(self) -> Dict[Capability, str]:
        """Get all unavailable capabilities with reasons."""
        return {
            cap: status.reason
            for cap, status in self._status.items()
            if not status.available
        }

    def log_status(self) -> None:
        """Log current capability status."""
        available = self.get_all_available()
        unavailable = self.get_all_unavailable()
        loaded = self._loaded

        logger.info(f"[CAPABILITIES] enabled={len(available)}, "
                   f"unavailable={len(unavailable)}, loaded={len(loaded)}")

        if available:
            logger.info(f"[CAPABILITIES] available: {[c.value for c in available.keys()]}")
        if unavailable:
            logger.info(f"[CAPABILITIES] unavailable: "
                       f"{[(c.value, r) for c, r in unavailable.items()]}")
        if loaded:
            logger.info(f"[CAPABILITIES] loaded: {[c.value for c in loaded]}")


class CapabilityRouter:
    """
    Routes research requirements to required capabilities.

    This is the SECOND stage in the analyzer -> router -> registry pipeline.

    Supports two input modes:
    1. Legacy: Dict[str, Any] analysis + strategy + depth (backward compatible)
    2. Canonical: AnalyzerResult (from types.py)

    The AnalyzerResult path is the preferred canonical route.

    Canonical output: Set[Capability] - passed to ToolRegistry for enforcement.
    """

    # Canonical capability signal keys (from AnalyzerResult.to_capability_signal())
    SIGNAL_KEYS = frozenset([
        "tools", "sources", "privacy_level", "use_tor", "depth",
        "use_tot", "tot_mode", "requires_embeddings", "requires_ner",
        "requires_temporal", "requires_crypto",
    ])

    # Mapping: source type -> required capabilities
    SOURCE_CAPABILITIES: Dict[str, Set[Capability]] = {
        "surface_web": {Capability.RERANKING},
        "academic": {Capability.RERANKING, Capability.ENTITY_LINKING},
        "archive": {Capability.TEMPORAL, Capability.METADATA_EXTRACT},
        "dark_web": {Capability.STEALTH, Capability.DARK_WEB},
        "osint": {Capability.NETWORK_RECON, Capability.ENTITY_LINKING},
        "crypto": {Capability.CRYPTO_INTEL},
    }

    # Mapping: discovery depth -> additional capabilities
    DEPTH_CAPABILITIES: Dict[str, Set[Capability]] = {
        "surface": set(),
        "deep": {Capability.PATTERN_MINING, Capability.INSIGHT},
        "extreme": {Capability.GRAPH_RAG, Capability.TEMPORAL, Capability.SNN},
        "exhaustive": {
            Capability.GRAPH_RAG, Capability.TEMPORAL, Capability.SNN,
            Capability.QUANTUM_PATH, Capability.BLOCKCHAIN
        },
    }

    # Tool-to-capability mapping (scaffold for required_capabilities)
    TOOL_CAPABILITIES: Dict[str, Set[Capability]] = {
        "stealth_crawler": {Capability.STEALTH, Capability.DARK_WEB},
        "archive_discovery": {Capability.TEMPORAL, Capability.METADATA_EXTRACT},
        "leak_hunter": {Capability.STEALTH},
        "blockchain_analyzer": {Capability.CRYPTO_INTEL},
        "academic_search": {Capability.RERANKING, Capability.ENTITY_LINKING},
        "identity_stitching": {Capability.ENTITY_LINKING},
        "relationship_discovery": {Capability.ENTITY_LINKING},
        "pattern_mining": {Capability.PATTERN_MINING, Capability.INSIGHT},
        "temporal_analyzer": {Capability.TEMPORAL},
        "document_analyzer": {Capability.DOC_INTEL},
        "web_intelligence": {Capability.RERANKING},
        "news_analyzer": {Capability.INSIGHT},
        "threat_assessor": {Capability.STEALTH},
        "vulnerability_scanner": {Capability.NETWORK_RECON},
        "reputation_analyzer": {Capability.INSIGHT},
        "cross_reference_engine": {Capability.ENTITY_LINKING, Capability.RERANKING},
    }

    @classmethod
    def route(
        cls,
        analysis: Dict[str, Any] | "AnalyzerResult",
        strategy: Any = None,
        depth: Any = None,
        profile: str = "default"
    ) -> Set[Capability]:
        """
        Determine required capabilities from research context.

        Args:
            analysis: Either AnalyzerResult (canonical) or Dict with analysis fields
            strategy: Research strategy (legacy, optional for AnalyzerResult)
            depth: Discovery depth (legacy, optional for AnalyzerResult)
            profile: Research profile (stealth, speed, thorough)

        Returns:
            Set of required capabilities
        """
        required: Set[Capability] = set()

        # Base capabilities
        required.add(Capability.HERMES)

        # Build capability signal dict (canonical form)
        signal: Dict[str, Any] = {}

        # Canonical path: AnalyzerResult
        if hasattr(analysis, "to_capability_signal"):
            # AnalyzerResult instance -> canonical signal dict
            signal = analysis.to_capability_signal()
        elif isinstance(analysis, dict):
            if "tools" in analysis:
                # Already a capability signal dict from AnalyzerResult.to_capability_signal()
                signal = analysis
            else:
                # Legacy path: raw analysis dict
                signal = dict(analysis)
                if strategy is not None and hasattr(strategy, 'selected_sources'):
                    for source in strategy.selected_sources:
                        source_key = str(source).lower() if hasattr(source, 'value') else str(source).lower()
                        for key, caps in cls.SOURCE_CAPABILITIES.items():
                            if key in source_key:
                                required.update(caps)
                if depth is not None:
                    depth_key = str(depth).lower() if hasattr(depth, 'value') else str(depth).lower()
                    for key, caps in cls.DEPTH_CAPABILITIES.items():
                        if key in depth_key:
                            required.update(caps)

        # From signal fields
        if signal.get('requires_embeddings'):
            required.add(Capability.MODERNBERT)
        if signal.get('requires_ner'):
            required.add(Capability.GLINER)
        if signal.get('requires_temporal'):
            required.add(Capability.TEMPORAL)
        if signal.get('requires_crypto'):
            required.add(Capability.CRYPTO_INTEL)

        # From tools in signal (canonical path)
        for tool in signal.get('tools', []):
            if tool in cls.TOOL_CAPABILITIES:
                required.update(cls.TOOL_CAPABILITIES[tool])

        # From privacy level
        if signal.get('privacy_level') == "MAXIMUM" or signal.get('use_tor'):
            required.add(Capability.STEALTH)

        # Profile-specific
        if profile == "stealth":
            required.add(Capability.STEALTH)
        elif profile == "thorough":
            required.update({Capability.GRAPH_RAG, Capability.ENTITY_LINKING, Capability.TOT})

        logger.debug(f"[CAPABILITY ROUTER] required={[c.value for c in required]}")
        return required


class ModelLifecycleManager:
    """
    Enforces hard phase invariants for model lifecycle.

    Authority note (Sprint 8ME + 8TF):
    This class is a FACADE — it does NOT load/unload models directly.
    It orchestrates phase transitions through CapabilityRegistry.load/unload.
    The canonical runtime-wide acquire/load owner is brain.model_manager.ModelManager.
    The canonical unload owner is ModelManager._release_current_async() +
    brain.model_lifecycle.unload_model() (7K SSOT delegát).

    This facade uses COARSE-GRAINED phase strings (BRAIN/TOOLS/SYNTHESIS/CLEANUP),
    which are SEMANTICALLY DIFFERENT from ModelManager.PHASE_MODEL_MAP's workflow-level
    phase strings (PLAN/DECIDE/SYNTHESIZE/EMBED/DEDUP/ROUTING/NER/ENTITY).
    These two phase systems are NOT unified — they serve different purposes and MUST NOT
    be conflated.

    IMPORTANT — Three Phase Layers (Sprint 8TF):
      Layer 1 (Workflow-level):   ModelManager.PHASE_MODEL_MAP — PLAN/DECIDE/SYNTHESIZE/EMBED/...
      Layer 2 (Coarse-grained):  ModelLifecycleManager — BRAIN/TOOLS/SYNTHESIS/CLEANUP
      Layer 3 (Windup-local):    windup_engine.SynthesisRunner — Qwen/SmolLM isolation

    Drift risk: Implicit mapping of Layer 1 ↔ Layer 2 phase strings would create
    false equivalence (e.g., "SYNTHESIZE" ≠ "SYNTHESIS"). Use brain.model_phase_facts
    to read phase facts without implicit cross-layer confusion.

    Future: If seam extraction lands, this facade may delegate to
    ModelManager.with_phase() directly, eliminating the CapabilityRegistry round-trip.
    """

    def __init__(self, registry: CapabilityRegistry):
        self.registry = registry
        self._current_phase: str = "none"
        self._active_models: Set[Capability] = set()

    async def enforce_phase_models(self, phase_name: str) -> None:
        """
        Enforce model loading for specific phase.

        Phases:
        - BRAIN: Hermes loaded, ModernBERT+GLiNER released
        - TOOLS: Hermes released; ModernBERT/GLiNER only when needed
        - SYNTHESIS: Hermes loaded; ModernBERT/GLiNER released
        """
        logger.info(f"[PHASE START] {phase_name}")
        logger.info(f"[MODEL] Before transition: active={[m.value for m in self._active_models]}")

        self._current_phase = phase_name

        if phase_name == "BRAIN":
            await self._release_all_models()
            await self.registry.load(Capability.HERMES)
            self._active_models = {Capability.HERMES}

        elif phase_name == "TOOLS":
            # Release Hermes for tool execution
            await self._release_model(Capability.HERMES)
            # ModernBERT/GLiNER loaded on-demand by specific tools
            self._active_models = set()

        elif phase_name == "SYNTHESIS":
            await self._release_all_models()
            await self.registry.load(Capability.HERMES)
            self._active_models = {Capability.HERMES}

        elif phase_name == "CLEANUP":
            await self._release_all_models()

        logger.info(f"[MODEL] After transition: active={[m.value for m in self._active_models]}")
        logger.info(f"[PHASE END] {phase_name}")

    async def _release_model(self, capability: Capability) -> None:
        """Release a specific model."""
        if capability in self._active_models:
            self.registry.unload(capability)
            self._active_models.discard(capability)
            logger.info(f"[MODEL RELEASE] {capability.value}")

    async def _release_all_models(self) -> None:
        """Release all models and force GC."""
        for cap in list(self._active_models):
            self.registry.unload(cap)
        self._active_models.clear()

        # Force garbage collection
        gc.collect()

        # Clear MLX cache if available
        if MLX_AVAILABLE and mx:
            try:
                mx.eval([])
                mx.clear_cache()
                logger.debug("[MODEL] MLX cache cleared")
            except Exception:
                pass

        logger.info("[MODEL] All models released, GC completed")

    def get_active_models(self) -> Set[Capability]:
        """Get currently active models."""
        return self._active_models.copy()

    async def load_model_for_task(self, capability: Capability) -> bool:
        """Load a model for a specific task, ensuring single-model constraint."""
        # If already loaded, return True
        if capability in self._active_models:
            return True

        # If loading a heavy model, release others first
        if capability in {Capability.HERMES, Capability.MODERNBERT, Capability.GLINER}:
            await self._release_all_models()

        success = await self.registry.load(capability)
        if success:
            self._active_models.add(capability)
            logger.info(f"[MODEL LOAD] {capability.value}")

        return success


def create_default_registry() -> CapabilityRegistry:
    """Create a registry with default capability registrations."""
    registry = CapabilityRegistry()

    # Check availability based on module imports
    def check_module(module_name: str) -> tuple[bool, str]:
        try:
            __import__(module_name)
            return True, ""
        except ImportError as e:
            return False, f"Module not available: {e}"

    # Register all capabilities
    modules_to_check = {
        Capability.GRAPH_RAG: ("hledac.universal.knowledge.rag_engine", "RAG engine"),
        Capability.ENTITY_LINKING: ("hledac.universal.knowledge.entity_linker", "Entity linker"),
        Capability.TEMPORAL: ("hledac.universal.intelligence.temporal_analysis", "Temporal analyzer"),
        Capability.DARK_WEB: ("hledac.universal.intelligence.stealth_crawler", "Dark web crawler"),
        Capability.CRYPTO_INTEL: ("hledac.universal.intelligence.cryptographic_intelligence", "Crypto intelligence"),
        Capability.DOC_INTEL: ("hledac.universal.intelligence.document_intelligence", "Document intelligence"),
        Capability.NETWORK_RECON: ("hledac.universal.intelligence.network_reconnaissance", "Network recon"),
        Capability.TOT: ("hledac.universal.tot_integration", "Tree of Thoughts"),
    }

    for cap, (module, description) in modules_to_check.items():
        available, reason = check_module(module)
        registry.register(
            capability=cap,
            available=available,
            reason=reason if not available else f"{description} available",
            module_path=module
        )

    # Always register model capabilities as available (they're core)
    for cap in [Capability.HERMES, Capability.MODERNBERT, Capability.GLINER]:
        registry.register(
            capability=cap,
            available=True,
            reason="Core model",
            module_path="hledac.universal.brain"
        )

    # Register derived capabilities
    registry.register(
        capability=Capability.RERANKING,
        available=True,
        reason="Core utility",
        module_path="hledac.universal.utils.ranking"
    )

    registry.register(
        capability=Capability.INSIGHT,
        available=check_module("hledac.universal.brain.insight_engine")[0],
        reason="",
        module_path="hledac.universal.brain.insight_engine"
    )

    registry.register(
        capability=Capability.PATTERN_MINING,
        available=check_module("hledac.universal.intelligence.pattern_mining")[0],
        reason="",
        module_path="hledac.universal.intelligence.pattern_mining"
    )

    return registry
