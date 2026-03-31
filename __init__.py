"""
Universal Orchestrator Package v5.0 - Autonomous
===============================================

Consolidated autonomous orchestrator combining all capabilities:

Main exports:
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
    deep_research,
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
    "HermesCommander",
    "DiscoveryDepth",
    "ResearchPhase",
    "ToolSelection",
    "ResearchContext",
    "AutonomousResearchResult",

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
        # Unified Research Engine
        "UnifiedResearchEngine",
        "UnifiedResearchConfig",
        "ResearchDepth",
        "QueryType",
        "ResearchFinding",
        "UnifiedResearchResult",
        "deep_research",
        "create_unified_research_engine",
        "UNIFIED_RESEARCH_AVAILABLE",
    ])

# =============================================================================
# ENHANCED FULLY AUTONOMOUS ORCHESTRATOR v6.0 - COMPLETE INTEGRATION
# =============================================================================
# Nový plně autonomní orchestrátor integrující ABSOLUTNĚ VŠE:
# - Deep Research (archives, dark web, steganography)
# - Temporal Analysis
# - OSINT Intelligence
# - Self-Healing & Recovery
# - AI-Powered Synthesis

try:
    from .autonomous_orchestrator_enhanced import (
        FullyAutonomousOrchestrator,
        SourceType,
        AutonomousStrategy,
        ResearchFinding,
        ResearchSource,
        ComprehensiveResearchResult,
        autonomous_research,
        ResilientExecutionManager,
    )
    
    # Alias pro jednodušší použití
    UltimateOrchestrator = FullyAutonomousOrchestrator
    
    ENHANCED_ORCHESTRATOR_AVAILABLE = True
    
except ImportError as e:
    ENHANCED_ORCHESTRATOR_AVAILABLE = False
    import logging
    logging.getLogger(__name__).debug(
        f"Enhanced orchestrator not available (some dependencies missing): {e}"
    )

# Update __all__ pro enhanced orchestrator
if ENHANCED_ORCHESTRATOR_AVAILABLE:
    __all__.extend([
        # Enhanced Orchestrator
        "FullyAutonomousOrchestrator",
        "UltimateOrchestrator",
        "ENHANCED_ORCHESTRATOR_AVAILABLE",
        
        # Enhanced Types
        "SourceType",
        "AutonomousStrategy",
        "ResearchFinding",
        "ResearchSource",
        "ComprehensiveResearchResult",
        
        # Convenience Functions
        "autonomous_research",
        "ResilientExecutionManager",
    ])


# =============================================================================
# SUPREME INTEGRATION EXPORTS
# =============================================================================

# Knowledge Components (from Supreme)
# Sprint 8VC: persistent_layer moved to legacy/, use knowledge.__init__ proxy
from .knowledge import (
    PersistentKnowledgeLayer,
    KnowledgeNode,
    KnowledgeEdge,
    NodeType,
    EdgeType,
    KuzuDBBackend,
    JSONBackend,
)
from .knowledge.graph_rag import GraphRAGOrchestrator
from .knowledge.graph_builder import KnowledgeGraphBuilder

# Tools (from Supreme)
from .tools import (
    LightweightReranker,
    RerankResult,
    RerankRequest,
    RerankerConfig,
    RerankerFactory,
    create_reranker,
    RustMiner,
    MiningResult,
    create_rust_miner,
)

# Security (from Supreme)
from .security import (
    SecurityGate,
    PIICategory,
    PIIMatch,
    SanitizationResult,
    create_security_gate,
    quick_sanitize,
    LootManager,
    RamDiskVault,
)

SUPREME_INTEGRATION_AVAILABLE = False

# =============================================================================
# PEP 562 LAZY EXPORTS - Defer heavy subpackage imports
# Root cause: knowledge/tools/security/autonomy pull intelligence/* modules
# which have eager torch/sklearn/networkx/scipy imports at module level.
# Lazy __getattr__ defers loading until first attribute access.
# =============================================================================

_LAZY_SUBPACKAGES = {
    # Knowledge Components (from Supreme) - pulls torch via graph_rag
    "PersistentKnowledgeLayer": (".knowledge.persistent_layer", "PersistentKnowledgeLayer"),
    "KnowledgeNode": (".knowledge.persistent_layer", "KnowledgeNode"),
    "KnowledgeEdge": (".knowledge.persistent_layer", "KnowledgeEdge"),
    "NodeType": (".knowledge.persistent_layer", "NodeType"),
    "EdgeType": (".knowledge.persistent_layer", "EdgeType"),
    "KuzuDBBackend": (".knowledge.persistent_layer", "KuzuDBBackend"),
    "JSONBackend": (".knowledge.persistent_layer", "JSONBackend"),
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
    # Supreme Brain
    "SerializedTreePlanner": (".autonomy.planner", "SerializedTreePlanner"),
    "TreeNodeStatus": (".autonomy.planner", "TreeNodeStatus"),
    "Thought": (".autonomy.planner", "Thought"),
    "TreeNode": (".autonomy.planner", "TreeNode"),
    "PlannerState": (".autonomy.planner", "PlannerState"),
    "create_tree_planner": (".autonomy.planner", "create_tree_planner"),
}

# Also lazily export non-existent symbols that were previously in __all__ but not defined
_FALLBACK_ATTRS = {
    "ENHANCED_ORCHESTRATOR_AVAILABLE": False,
    "SUPREME_INTEGRATION_AVAILABLE": True,
    "INTEGRATED_ORCHESTRATOR_AVAILABLE": False,
    "BUDGET_MANAGER_AVAILABLE": False,
    "UNIFIED_RESEARCH_AVAILABLE": False,
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
# PHASE C INTEGRATION - Full Autonomy with Connected Coordinators
# =============================================================================

try:
    from .orchestrator_integration import (
        IntegratedOrchestrator,
        integrated_research,
    )
    INTEGRATED_ORCHESTRATOR_AVAILABLE = True
    
    # Make IntegratedOrchestrator the default for advanced usage
    AdvancedOrchestrator = IntegratedOrchestrator
    
except ImportError as e:
    INTEGRATED_ORCHESTRATOR_AVAILABLE = False
    import logging
    logging.getLogger(__name__).debug(
        f"Integrated orchestrator not available (optional dependencies): {e}"
    )

# Update __all__ for integrated orchestrator
if INTEGRATED_ORCHESTRATOR_AVAILABLE:
    __all__.extend([
        # Phase C Integration
        "IntegratedOrchestrator",
        "AdvancedOrchestrator",
        "integrated_research",
        "INTEGRATED_ORCHESTRATOR_AVAILABLE",
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
