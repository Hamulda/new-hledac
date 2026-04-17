"""
Universal Package — COMPAT_EXPORT Surface (Sprint F181A)
=======================================================

.. role::
    COMPAT_EXPORT: This package is a compatibility export surface, NOT a
    production entrypoint. It aggregates symbols from multiple layers for
    backward compatibility.

.. canonical_owner::
    - Production sprint: core.__main__:run_sprint() — SOLE canonical sprint owner
    - Production orchestrator: runtime.sprint_scheduler:SprintScheduler
    - Legacy implementation: legacy/autonomous_orchestrator.py (~31k lines)

.. what_this_is::
    Compatibility export aggregator. Re-exports symbols from:
    - legacy/autonomous_orchestrator.py (via autonomous_orchestrator facade)
    - config, types, research_context, evidence_log, capabilities
    - layers, coordinators, utils, enhanced_research, orchestrator_integration
    - budget_manager

.. what_this_is_not::
    - NOT production entrypoint — use python -m hledac.universal.core --sprint
    - NOT canonical sprint owner — use core.__main__.run_sprint()
    - NOT canonical orchestrator — use runtime.sprint_scheduler
    - NOT recommended import path for new code

.. authority_chain::
    This package
        → autonomous_orchestrator.py (NON_CANONICAL_FACADE)
            → legacy/autonomous_orchestrator.py (IMPLEMENTATION TRUTH)
    vs.
    Production path (canonical):
    core/__main__.py::run_sprint()
        → runtime/sprint_scheduler.py::SprintScheduler.run()

.. migration_guidance::
    For new code:
    - Sprint entry: python -m hledac.universal.core --sprint
    - Direct imports: from hledac.universal.runtime.sprint_scheduler import SprintScheduler
    - Legacy facade: from hledac.universal.legacy.autonomous_orchestrator import FullyAutonomousOrchestrator

.. deprecated_example::
    OLD (still works but deprecated):
        from hledac.universal import create_autonomous_orchestrator
    NEW (canonical path):
        from hledac.universal.core.__main__ import run_sprint

Universal Package v5.0 — COMPATIBILITY EXPORT SURFACE
=====================================================

.. note::
    This is NOT a production entrypoint. This package re-exports symbols
    from legacy/autonomous_orchestrator.py (via autonomous_orchestrator facade)
    and other subpackages for backward compatibility.

    **Production entrypoint:** ``python -m hledac.universal.core --sprint``
    **Canonical sprint owner:** ``core.__main__:run_sprint()``
    **Canonical orchestrator:** ``runtime.sprint_scheduler:SprintScheduler``

Compatibility exports (do not imply production readiness):
- AutonomousOrchestrator: Fully autonomous orchestrator (v5.0)
- create_autonomous_orchestrator: Factory function
- UniversalConfig: Configuration class
- ResearchMode, OrchestratorState: Enums
- DiscoveryDepth, ResearchPhase: Autonomous enums

Legacy (for backward compatibility):
- UniversalResearchOrchestrator -> AutonomousOrchestrator
- create_universal_orchestrator -> create_autonomous_orchestrator

Layers (internal use):
- GhostLayer: GhostDirector integration
- MemoryLayer: M1 memory management
- CoordinationLayer: Coordinator delegation
- SecurityLayer: Obfuscation, secure destruction
- StealthLayer: Browser, evasion, CAPTCHA
- ResearchLayer: Deep research, citations
- PrivacyLayer: VPN/Tor, PGP, audit

Autonomous Tools:
- AgentCoordinationEngine: Multi-agent orchestration
- ResearchOptimizer: Caching, deduplication
- PrivacyEnhancedResearch: Anonymization
- QueryExpander: Query variations
- ReciprocalRankFusion: Result fusion
- IntelligentCache: LRU/LFU/ADAPTIVE

Example:
    from hledac.universal import create_autonomous_orchestrator, DiscoveryDepth

    orchestrator = await create_autonomous_orchestrator(
        mode=ResearchMode.AUTONOMOUS,
        m1_optimized=True
    )

    result = await orchestrator.research(
        "quantum computing",
        depth=DiscoveryDepth.EXTREME
    )
    print(result.synthesized_answer)
"""

from .config import UniversalConfig, create_config, load_config_from_file

# NEW: Fully Autonomous Orchestrator (v6.0 Unified)
from .autonomous_orchestrator import (
    FullyAutonomousOrchestrator,
    autonomous_research,
    DiscoveryDepth,
    ResearchPhase,
    SourceType,
    AutonomousStrategy,
    ResearchSource,
    ResearchFinding,
    ComprehensiveResearchResult,
    ResilientExecutionManager,
    # NEW: Unified Tool Registry & Autonomous Workflow
    UnifiedToolRegistry,
    ToolCategory,
    ToolCapability,
    AutonomousWorkflowEngine,
    WorkflowState,
    # deep_research — REMOVED F187A: does not exist in legacy/autonomous_orchestrator.py
    # Use enhanced_research.deep_research() or deep_research_provider_seam() instead
)

# Legacy compatibility aliases
AutonomousOrchestrator = FullyAutonomousOrchestrator
UniversalResearchOrchestrator = FullyAutonomousOrchestrator
create_universal_orchestrator = autonomous_research
create_autonomous_orchestrator = autonomous_research

from .types import (
    ActionType,
    AgentState,
    BrowserType,
    CaptchaType,
    DecisionRequest,
    DecisionResponse,
    ExecutionContext,
    ExplorationStrategy,
    ObfuscationLevel,
    OperationType,
    OrchestratorState,
    ResearchMode,
    ResearchResult,
    RiskLevel,
    SubAgentResult,
    SubAgentType,
    SystemState,
    WipeStandard,
)

# NEW: Research Context and Evidence Log
from .research_context import (
    ResearchContext,
    BudgetState,
    Entity,
    EntityType,
    Hypothesis,
    HypothesisStatus,
    ErrorRecord,
    ErrorSeverity,
)
from .evidence_log import (
    EvidenceLog,
    EvidenceEvent,
)

# NEW: Capability System (M1 8GB Optimization)
from .capabilities import (
    Capability,
    CapabilityRegistry,
    CapabilityRouter,
    ModelLifecycleManager,
    create_default_registry,
)

# Import Layers with Capabilities Manager
from .layers import (
    LayerManager,
    get_layer_manager,
    UnifiedCapabilitiesManager,
    get_capabilities_manager,
)

# Import coordinators
from .coordinators import (
    UniversalCoordinator,
    UniversalResearchCoordinator,
    UniversalExecutionCoordinator,
    UniversalSecurityCoordinator,
    UniversalMonitoringCoordinator,
    CoordinatorRegistry,
    OperationType as CoordinatorOperationType,
    DecisionResponse as CoordinatorDecisionResponse,
    OperationResult as CoordinatorOperationResult,
    # Autonomous coordinators
    AgentCoordinationEngine,
    AgentType,
    TaskPriority,
    AgentCapability,
    TaskRequest,
    TaskResult,
    CoordinationStrategy,
    coordinated_search,
    PrivacyEnhancedResearch,
    PrivacyConfig,
    PrivacyLevel,
    DataRetention,
    private_research,
    ResearchOptimizer,
    OptimizationConfig,
    OptimizationStrategy,
    CachePolicy,
    QueryMetrics,
    OptimizedResult,
    optimized_research,
    create_optimized_pipeline,
)

# Import autonomous utilities
from .utils import (
    QueryExpander,
    ExpansionConfig,
    expand_query,
    ReciprocalRankFusion,
    RRFConfig,
    RankedResult,
    ScoreAggregator,
    fuse_results,
    IntelligentCache,
    CacheConfig,
    CacheEntry,
    CacheStats,
    EvictionStrategy,
    get_global_cache,
    # Rate Limiter (from stealth_toolkit integration)
    RateLimiter,
    RateLimitConfig,
    RateLimitExceeded,
    with_rate_limit,
)

# Unified Research Engine - Complete integration of all research tools
try:
    from .enhanced_research import (
        UnifiedResearchEngine,
        UnifiedResearchConfig,
        ResearchDepth,
        QueryType,
        ResearchFinding,
        UnifiedResearchResult,
        deep_research,
        create_unified_research_engine,
    )
    UNIFIED_RESEARCH_AVAILABLE = True
except ImportError as e:
    UNIFIED_RESEARCH_AVAILABLE = False
    import logging
    logging.getLogger(__name__).debug(
        f"Unified research engine not available: {e}"
    )

__version__ = "5.0.0-autonomous"

__all__ = [
    # NEW: Autonomous Orchestrator
    "AutonomousOrchestrator",
    "create_autonomous_orchestrator",
    "DiscoveryDepth",
    "ResearchPhase",

    # NEW: Research Context & Evidence Log
    "ResearchContext",
    "BudgetState",
    "Entity",
    "EntityType",
    "Hypothesis",
    "HypothesisStatus",
    "ErrorRecord",
    "ErrorSeverity",
    "EvidenceLog",
    "EvidenceEvent",

    # NEW: Capability System (M1 8GB Optimization)
    "Capability",
    "CapabilityRegistry",
    "CapabilityRouter",
    "ModelLifecycleManager",
    "create_default_registry",

    # NEW: Unified Capabilities Manager (All Layers + Coordinators + Utils)
    "LayerManager",
    "get_layer_manager",
    "UnifiedCapabilitiesManager",
    "get_capabilities_manager",
    
    # Legacy compatibility
    "UniversalResearchOrchestrator",
    "create_universal_orchestrator",
    
    # Configuration
    "UniversalConfig",
    "create_config",
    "load_config_from_file",
    
    # Types - Core
    "ResearchMode",
    "OrchestratorState",
    "SystemState",
    "AgentState",
    "SubAgentType",
    "ActionType",
    "OperationType",
    "ResearchResult",
    "SubAgentResult",
    "ExecutionContext",
    "DecisionRequest",
    "DecisionResponse",
    "BrowserType",
    "CaptchaType",
    "ExplorationStrategy",
    "ObfuscationLevel",
    "RiskLevel",
    "WipeStandard",
    
    # Coordinators
    "UniversalCoordinator",
    "UniversalResearchCoordinator",
    "UniversalExecutionCoordinator",
    "UniversalSecurityCoordinator",
    "UniversalMonitoringCoordinator",
    "CoordinatorRegistry",
    "CoordinatorOperationType",
    "CoordinatorDecisionResponse",
    "CoordinatorOperationResult",
    
    # Autonomous Coordinators
    "AgentCoordinationEngine",
    "AgentType",
    "TaskPriority",
    "AgentCapability",
    "TaskRequest",
    "TaskResult",
    "CoordinationStrategy",
    "coordinated_search",
    "PrivacyEnhancedResearch",
    "PrivacyConfig",
    "PrivacyLevel",
    "DataRetention",
    "private_research",
    "ResearchOptimizer",
    "OptimizationConfig",
    "OptimizationStrategy",
    "CachePolicy",
    "QueryMetrics",
    "OptimizedResult",
    "optimized_research",
    "create_optimized_pipeline",
    
    # Autonomous Utilities
    "QueryExpander",
    "ExpansionConfig",
    "expand_query",
    "ReciprocalRankFusion",
    "RRFConfig",
    "RankedResult",
    "ScoreAggregator",
    "fuse_results",
    "IntelligentCache",
    "CacheConfig",
    "CacheEntry",
    "CacheStats",
    "EvictionStrategy",
    "get_global_cache",
    # Stealth Toolkit Integration
    "RateLimiter",
    "RateLimitConfig",
    "RateLimitExceeded",
    "with_rate_limit",
]

# Update __all__ for unified research engine
if UNIFIED_RESEARCH_AVAILABLE:
    __all__.extend([
        # Unified Research Engine (UnifiedResearchEngine is dormant canonical provider candidate)
        "UnifiedResearchEngine",
        "UnifiedResearchConfig",
        "ResearchDepth",
        "QueryType",
        # ResearchFinding — REMOVED F187A: COLLISION with legacy/autonomous_orchestrator.py
        # Use legacy ResearchFinding from autonomous_orchestrator facade for compatibility.
        "UnifiedResearchResult",
        "deep_research",
        "create_unified_research_engine",
        "UNIFIED_RESEARCH_AVAILABLE",
    ])

# =============================================================================
# SUPREME INTEGRATION EXPORTS — NOW LAZY (F12C normalization)
# =============================================================================
# PRE-F12C: These were EAGER imports that overrode the _LAZY_SUBPACKAGES entries.
# POST-F12C: All knowledge/tools/security symbols are served exclusively via
# PEP 562 __getattr__ lazy loading from _LAZY_SUBPACKAGES (lines 452-488).
# This restores lazy-loading discipline and removes import-time side-effects.
#
# Canonical owners (verified F12C):
#   knowledge.*  → knowledge/__init__.py (graph_layer, rag_engine, entity_linker)
#   tools.*      → tools/__init__.py (reranker, content_miner, adapters)
#   security.*   → security/__init__.py (pii_gate, vault_manager, encryption)
#
# External consumers (legacy/, tests/) import directly from subpackages, not here.
# SUPREME_INTEGRATION_AVAILABLE was always False — removed as dead attribution.
#
# Heavy deps (torch, sklearn, networkx, scipy) are now truly deferred until
# first attribute access, not loaded at package import time.
#
# KNOWN COLLISION (non-blocking, pre-existing):
#   ResearchFinding: enhanced_research.py:223 (@dataclass) vs
#                   legacy/autonomous_orchestrator.py:2956 (@dataclass)
#   Neither is pydantic — both are @dataclass.
#   Resolution paths:
#     - Eager default: .autonomous_orchestrator facade → legacy/ definition
#       (facade loads legacy/autonomous_orchestrator.py at import time)
#     - Enhanced conditional: only if UNIFIED_RESEARCH_AVAILABLE=True,
#       via conditional eager import of enhanced_research.py (NOT lazy)
#   Collision is contained: neither definition overwrites the other in __all__.

SUPREME_INTEGRATION_AVAILABLE = False  # REMOVED F187A: dead attribution, keep for test compatibility only

# =============================================================================
# PEP 562 LAZY EXPORTS - Defer heavy subpackage imports
# Root cause: knowledge/tools/security/autonomy pull intelligence/* modules
# which have eager torch/sklearn/networkx/scipy imports at module level.
# Lazy __getattr__ defers loading until first attribute access.
# =============================================================================

_LAZY_SUBPACKAGES = {
    # Knowledge Components (from Supreme) - pulls torch via graph_rag
    # F1200B FIX: Corrected path from .knowledge.persistent_layer to .legacy.persistent_layer
    "PersistentKnowledgeLayer": (".legacy.persistent_layer", "PersistentKnowledgeLayer"),
    "KnowledgeNode": (".legacy.persistent_layer", "KnowledgeNode"),
    "KnowledgeEdge": (".legacy.persistent_layer", "KnowledgeEdge"),
    "NodeType": (".legacy.persistent_layer", "NodeType"),
    "EdgeType": (".legacy.persistent_layer", "EdgeType"),
    "KuzuDBBackend": (".legacy.persistent_layer", "KuzuDBBackend"),
    "JSONBackend": (".legacy.persistent_layer", "JSONBackend"),
    "GraphRAGOrchestrator": (".knowledge.graph_rag", "GraphRAGOrchestrator"),
    "KnowledgeGraphBuilder": (".knowledge.graph_builder", "KnowledgeGraphBuilder"),
    # Supreme Tools - pulls pandas via reranker
    "LightweightReranker": (".tools", "LightweightReranker"),
    "RerankResult": (".tools", "RerankResult"),
    "RerankRequest": (".tools", "RerankRequest"),
    "RerankerConfig": (".tools", "RerankerConfig"),
    "RerankerFactory": (".tools", "RerankerFactory"),
    "RustMiner": (".tools", "RustMiner"),
    "MiningResult": (".tools", "MiningResult"),
    "create_rust_miner": (".tools", "create_rust_miner"),
    # Supreme Security
    "SecurityGate": (".security", "SecurityGate"),
    "PIICategory": (".security", "PIICategory"),
    "PIIMatch": (".security", "PIIMatch"),
    "SanitizationResult": (".security", "SanitizationResult"),
    "create_security_gate": (".security", "create_security_gate"),
    "quick_sanitize": (".security", "quick_sanitize"),
    "LootManager": (".security", "LootManager"),
    "RamDiskVault": (".security", "RamDiskVault"),
}

# Also lazily export non-existent symbols that were previously in __all__ but not defined
_FALLBACK_ATTRS = {
    # Availability flags — truthful state after F187A reconciliation
    # ENHANCED: autonomous_orchestrator_enhanced.py does NOT exist → False
    "ENHANCED_ORCHESTRATOR_AVAILABLE": False,
    # INTEGRATED: orchestrator_integration.py EXISTS → True (but DORMANT, not canonical)
    "INTEGRATED_ORCHESTRATOR_AVAILABLE": True,
    # DEPRECATED: IntegratedOrchestrator is dormant residue, not canonical orchestrator
    "DEPRECATED_ORCHESTRATOR_INTEGRATION": True,
    # BUDGET: budget_manager.py only at cache/ not root → False
    "BUDGET_MANAGER_AVAILABLE": False,
    # UNIFIED: enhanced_research.py exists → set by try/except below
    "UNIFIED_RESEARCH_AVAILABLE": False,
    # SUPREME: dead attribution, kept for test compatibility
    "SUPREME_INTEGRATION_AVAILABLE": False,
}


def __getattr__(name):
    """PEP 562 lazy attribute access - defer heavy subpackage imports."""
    # Check if this is a lazily-exported subpackage item
    if name in _LAZY_SUBPACKAGES:
        from importlib import import_module
        pkg_path, attr_name = _LAZY_SUBPACKAGES[name]
        module = import_module(pkg_path, package=__name__)
        value = getattr(module, attr_name)
        # Cache in globals to avoid repeated lookups
        globals()[name] = value
        return value
    # Fallback for availability flags that were set at module level
    if name in _FALLBACK_ATTRS:
        return _FALLBACK_ATTRS[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    """PEP 562 module introspection - include lazy exports."""
    # Combine module-level names with lazy exports
    return list(__all__) + list(_LAZY_SUBPACKAGES.keys()) + list(_FALLBACK_ATTRS.keys())

# =============================================================================
# ORCHESTRATOR INTEGRATION — DORMANT COMPATIBILITY STUB (F187A)
# IntegratedOrchestrator is DEPRECATED/DORMANT — NOT canonical orchestrator.
# Canonical path: core.__main__::run_sprint() → runtime.sprint_scheduler::SprintScheduler
# =============================================================================

# Pre-initialize so assignment is single in __all__ extend below
INTEGRATED_ORCHESTRATOR_AVAILABLE = False
try:
    from .orchestrator_integration import (
        IntegratedOrchestrator,
        integrated_research,
    )
    INTEGRATED_ORCHESTRATOR_AVAILABLE = True

    # DEPRECATED F187A: AdvancedOrchestrator alias REMOVED
    # IntegratedOrchestrator is DORMANT, not "advanced" canonical path.
    # Use SprintScheduler for canonical orchestrator.

except ImportError as e:
    import logging
    logging.getLogger(__name__).debug(
        f"Integrated orchestrator not available (optional dependencies): {e}"
    )

# Update __all__ for integrated orchestrator
if INTEGRATED_ORCHESTRATOR_AVAILABLE:
    __all__.extend([
        # IntegratedOrchestrator is DEPRECATED/DORMANT — not canonical orchestrator
        "IntegratedOrchestrator",
        "integrated_research",
        "INTEGRATED_ORCHESTRATOR_AVAILABLE",
        "DEPRECATED_ORCHESTRATOR_INTEGRATION",
    ])

# =============================================================================
# BUDGET MANAGER - Resource Control for Autonomous Workflows
# =============================================================================

try:
    from .budget_manager import (
        BudgetManager,
        BudgetConfig,
        BudgetState,
        BudgetStatus,
        EvidenceLog,
        StopReason,
        create_budget_manager,
        create_quick_budget,
        create_deep_budget,
    )
    BUDGET_MANAGER_AVAILABLE = True

except ImportError as e:
    BUDGET_MANAGER_AVAILABLE = False
    import logging
    logging.getLogger(__name__).debug(
        f"BudgetManager not available: {e}"
    )

# Update __all__ for BudgetManager
if BUDGET_MANAGER_AVAILABLE:
    __all__.extend([
        # Budget Management
        "BudgetManager",
        "BudgetConfig",
        "BudgetState",
        "BudgetStatus",
        "EvidenceLog",
        "StopReason",
        "create_budget_manager",
        "create_quick_budget",
        "create_deep_budget",
        "BUDGET_MANAGER_AVAILABLE",
    ])
