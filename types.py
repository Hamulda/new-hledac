"""
Universal Orchestrator Types - Consolidated Type Definitions
=============================================================

All enums and dataclasses used across the universal orchestrator.
Consolidated from:
- orchestrator_v2.py (ResearchMode, OrchestratorState, ActionType, etc.)
- supreme/orchestrator.py (SystemState variants)
- hermes3/types.py (DecisionRequest, DecisionResponse)
- deepseek_r1/types.py (OperationType)
- m1_master_optimizer/ (SystemState)
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import numpy as np


# =============================================================================
# RESEARCH ENUMS
# =============================================================================

class ResearchMode(Enum):
    """Research depth modes"""
    QUICK = "quick"           # Fast, shallow research
    STANDARD = "standard"     # Balanced depth
    DEEP = "deep"             # Deep investigation
    EXTREME = "extreme"       # Exhaustive research
    AUTONOMOUS = "autonomous" # Self-directed research


class ActionResultType(Enum):
    """Strict typed handler result taxonomy for truthful benchmark."""
    SUCCESS = "SUCCESS"                   # Action completed with valid results
    EMPTY = "EMPTY"                       # Action completed but no results found
    NETWORK_UNAVAILABLE = "NETWORK_UNAVAILABLE"  # Network unreachable / DNS / connection refused
    UPSTREAM_API_ERROR = "UPSTREAM_API_ERROR"   # HTTP 429/403/451/502/503/504/529
    TIMEOUT = "TIMEOUT"                   # Action timed out
    EXCEPTION = "EXCEPTION"               # Unhandled exception / code bug
    MOCK_FALLBACK_USED = "MOCK_FALLBACK_USED"   # Fixture/mock data used


class OfflineModeError(Exception):
    """Raised when network operations are attempted in offline mode."""
    pass


def is_offline_mode() -> bool:
    """Check if offline mode is enabled via HLEDAC_OFFLINE environment variable."""
    return os.getenv("HLEDAC_OFFLINE", "0") == "1"


class OrchestratorState(Enum):
    """Main orchestrator state machine states"""
    IDLE = "idle"
    PLANNING = "planning"
    BRAIN = "brain"
    EXECUTION = "execution"
    SYNTHESIS = "synthesis"
    ERROR = "error"


class SystemState(Enum):
    """System health state machine (from InfrastructureOrchestrator)"""
    HEALTHY = "healthy"
    MEMORY_PRESSURE = "memory_pressure"
    THERMAL_THROTTLING = "thermal_throttling"
    DEGRADED = "degraded"
    RECOVERY = "recovery"


class AgentState(Enum):
    """Sub-agent states"""
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    LOST = "lost"  # Agent lost direction, needs redirection


class SubAgentType(Enum):
    """Types of sub-agents"""
    STEALTH_WEB = "stealth_web"    # Web crawling with TLS fingerprinting
    OSINT = "osint"                 # Hidden sources discovery
    SECURITY = "security"           # Obfuscation, audit
    ARCHIVE = "archive"             # Wayback Machine, archives
    ACADEMIC = "academic"           # Research papers
    SYNTHESIS = "synthesis"         # Result synthesis


class Severity(Enum):
    """Severity levels for logging and alerts"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class SecurityLevel(Enum):
    """Security levels for privacy protection"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionType(Enum):
    """GhostDirector action types (18+ actions)"""
    # Core actions
    SCAN = "scan"
    GOOGLE = "google"
    DOWNLOAD = "download"
    SEARCH = "search"
    SMART_SEARCH = "smart_search"
    MEMORIZE = "memorize"
    PROBE = "probe"
    TRACK = "track"
    RESEARCH_PAPER = "research_paper"
    DEEP_RESEARCH = "deep_research"
    DEEP_READ = "deep_read"
    ANSWER = "answer"
    CRACK = "crack"
    ERROR = "error"
    
    # Extended actions
    ARCHIVE_FALLBACK = "archive_fallback"
    FACT_CHECK = "fact_check"
    STEALTH_HARVEST = "stealth_harvest"
    OSINT_DISCOVERY = "osint_discovery"
    EXTRACT_ENTITIES = "extract_entities"
    ANALYZE_SENTIMENT = "analyze_sentiment"
    SUMMARIZE = "summarize"


class OperationType(Enum):
    """Operation types for coordinator delegation"""
    RESEARCH = "research"
    SECURITY = "security"
    EXECUTION = "execution"
    MONITORING = "monitoring"
    ANALYSIS = "analysis"
    SYNTHESIS = "synthesis"


class ResearchPhase(Enum):
    """Research execution phases"""
    INITIALIZATION = "initialization"
    EXPLORATION = "exploration"
    DEEP_DIVE = "deep_dive"
    ANALYSIS = "analysis"
    SYNTHESIS = "synthesis"
    FINALIZATION = "finalization"


class QueryComplexity(Enum):
    """Query complexity levels (from MODOrchestrator)"""
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    VERY_COMPLEX = "very_complex"


class ReasoningMode(Enum):
    """Reasoning modes for autonomous orchestration"""
    STANDARD = "standard"
    CHAIN_OF_THOUGHT = "chain_of_thought"
    TREE_OF_THOUGHTS = "tree_of_thoughts"
    HYBRID_TOT_MOE = "hybrid_tot_moe"


# =============================================================================
# DATACLASSES - CONFIGURATION
# =============================================================================

@dataclass
class ModelConfig:
    """Model configuration for M1 8GB - 3 model stack only"""
    # LLM: Hermes-3 for reasoning and generation
    HERMES_MODEL: str = "mlx-community/Hermes-3-Llama-3.2-3B-4bit"
    HERMES_CONTEXT: int = 8192
    HERMES_TEMP: float = 0.3

    # Embeddings: ModernBERT for semantic search
    MODERNBERT_MODEL: str = "mlx-community/answerdotai-ModernBERT-base-6bit"
    EMBED_DIM: int = 768

    # NER: GLiNER-X for entity extraction
    GLINER_MODEL: str = "knowledgator/gliner-x-base"


@dataclass
class ResearchConfig:
    """Research execution configuration"""
    mode: ResearchMode = ResearchMode.STANDARD
    max_steps: int = 20
    max_time_minutes: int = 30
    memory_limit_mb: float = 5500.0
    
    # Models - 3 model stack only
    hermes_model: str = ModelConfig.HERMES_MODEL
    modernbert_model: str = ModelConfig.MODERNBERT_MODEL
    gliner_model: str = ModelConfig.GLINER_MODEL

    # Knowledge (optional - no Neo4j)
    enable_knowledge_graph: bool = False
    enable_rag: bool = True
    db_path: Optional[str] = None
    
    # Stealth
    enable_stealth: bool = True
    auto_stealth: bool = True
    privacy_level: str = "high"
    chaff_ratio: float = 0.3
    enable_audit: bool = True
    
    # Autonomy
    enable_autonomy: bool = True
    auto_archive_fallback: bool = True
    enable_fact_checking: bool = True
    
    # Output
    output_format: str = "markdown"
    save_intermediate: bool = True
    
    # Security
    use_ram_vault: bool = True
    vault_password: Optional[str] = None
    
    # Sub-agents
    max_concurrent_agents: int = 3
    agent_timeout: int = 300


@dataclass
class MemoryConfig:
    """Memory management configuration (from InfrastructureOrchestrator)"""
    memory_limit_mb: float = 5500.0
    thermal_threshold_c: float = 85.0
    enable_secure_enclave: bool = True
    enable_metal_acceleration: bool = True
    recovery_interval_seconds: float = 30.0
    health_check_interval_seconds: float = 5.0


@dataclass
class GhostConfig:
    """Ghost layer configuration"""
    max_steps: int = 20
    enable_vault: bool = True
    vault_size_mb: int = 256
    enable_anti_loop: bool = True
    stagnation_threshold: int = 3
    enable_loot_manager: bool = True


@dataclass
class SecurityConfig:
    """Security configuration for privacy protection"""
    # Basic
    enable_audit: bool = True
    privacy_level: str = "high"
    use_ram_vault: bool = True
    vault_password: Optional[str] = None
    pii_detection: bool = True
    auto_redact: bool = True
    # Obfuscation (required by SecurityLayer)
    obfuscation_level: str = "medium"  # none, light, medium, heavy, maximum
    generate_decoys: bool = True
    decoy_count: int = 20
    # Secure destruction
    wipe_standard: str = "nist_800_88"  # nist_800_88, dod_5220_22m, gutmann
    verification_enabled: bool = True
    rename_before_delete: bool = True
    # Research obfuscation
    enable_query_masking: bool = True
    enable_chaff_traffic: bool = True
    chaff_ratio: float = 0.3
    enable_timing_jitter: bool = True
    jitter_percent: float = 50.0


@dataclass
class StealthConfig:
    """Stealth mode configuration"""
    # Basic
    enabled: bool = True
    chaff_ratio: float = 0.3
    rotate_identity: bool = True
    use_tor: bool = False
    use_proxy: bool = False
    proxy_url: Optional[str] = None
    timing_jitter: bool = True
    user_agent_rotation: bool = True
    # Browser
    browser_type: str = "chromium"  # chromium, firefox, webkit
    headless: bool = True
    pool_size: int = 2
    # Anti-detection
    enable_stealth_scripts: bool = True
    enable_fingerprint_rotation: bool = True
    fingerprint_count: int = 50
    enable_canvas_noise: bool = True
    enable_webgl_spoofing: bool = True
    # Detection evasion
    detection_threshold: float = 0.7
    adaptive_mode: bool = True
    enable_behavior_simulation: bool = True
    # CAPTCHA
    enable_captcha_solving: bool = True
    captcha_providers: List[str] = field(default_factory=lambda: ["2captcha", "anticaptcha"])
    captcha_timeout: int = 120
    # Proxy
    enable_proxy_rotation: bool = False
    proxy_list: List[str] = field(default_factory=list)
    # Anti-detection extras
    hide_webdriver: bool = True
    hide_automation: bool = True
    spoof_plugins: bool = True
    spoof_permissions: bool = True
    disable_webrtc: bool = True
    override_canvas: bool = True
    override_webgl: bool = True
    spoof_fonts: bool = True
    emulate_human_events: bool = True
    patch_detection_libs: bool = True
    randomize_globals: bool = True
    spoof_chrome_runtime: bool = True
    add_chrome_plugins: bool = False
    # OCR
    enable_image_ocr: bool = False
    ocr_model: str = "microsoft/trocr-base-handwritten"
    max_image_size: int = 2048
    confidence_threshold: float = 0.5
    # Timezone/Fonts
    randomize_timezone: bool = True
    randomize_webgl: bool = True
    randomize_fonts: bool = True
    randomize_plugins: bool = True
    consistent_per_session: bool = True
    session_duration: int = 300
    platform: str = "macos"
    # Pattern
    pattern: str = "default"
    min_delay: float = 0.1
    max_delay: float = 0.5
    randomness: float = 0.3
    mouse_speed: float = 1.0
    scroll_min: int = 20
    scroll_max: int = 50
    scroll_pause: float = 0.2


@dataclass
class CoordinationConfig:
    """Coordination layer configuration"""
    max_context_length: int = 1024  # Minimal context for M1 optimization
    temperature: float = 0.1  # Low for consistent decisions
    max_tokens_response: int = 100
    enable_delegation: bool = True


@dataclass
class AgentManagerConfig:
    """Agent management configuration (from EnhancedUnifiedOrchestrator)"""
    max_concurrent_agents: int = 6  # M1 constraint
    memory_threshold_mb: float = 512.0
    agent_timeout_seconds: float = 25.0
    circuit_breaker_threshold: int = 3
    agent_pool_size: int = 2
    auto_optimize_interval: int = 300  # 5 minutes


# =============================================================================
# DATACLASSES - EXECUTION CONTEXT
# =============================================================================

@dataclass
class ExecutionContext:
    """Context for research execution (from v1 + v2)"""
    query: str
    current_step: int = 0
    max_steps: int = 20
    state: OrchestratorState = OrchestratorState.IDLE
    
    # History
    execution_history: List[Dict[str, Any]] = field(default_factory=list)
    action_log: List[Dict[str, Any]] = field(default_factory=list)
    
    # Knowledge
    collected_data: List[Dict[str, Any]] = field(default_factory=list)
    knowledge_graph: Dict[str, Any] = field(default_factory=dict)
    
    # Stealth
    stealth_activated: bool = False
    blocked_domains: Set[str] = field(default_factory=set)
    
    # Deduplication
    visited_urls: Set[str] = field(default_factory=set)
    content_hashes: Set[str] = field(default_factory=set)
    
    # Statistics
    start_time: float = field(default_factory=lambda: datetime.now().timestamp())
    tokens_used: int = 0
    
    def add_action(self, action_type: ActionType, details: Dict[str, Any]) -> None:
        """Add action to log"""
        self.action_log.append({
            "step": self.current_step,
            "action": action_type.value,
            "timestamp": datetime.now().isoformat(),
            "details": details,
        })


@dataclass
class DecisionContext:
    """Context for decision making (from Hermes3)"""
    research_id: str
    goal: str
    phase: ResearchPhase
    iterations: int = 0
    max_iterations: int = 20
    context_data: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# DATACLASSES - RESULTS
# =============================================================================

@dataclass
class SubAgentResult:
    """Result from sub-agent execution"""
    agent_type: SubAgentType
    success: bool
    data: Dict[str, Any]
    confidence: float
    sources: List[Dict[str, Any]]
    execution_time: float
    state: AgentState


@dataclass
class ResearchResult:
    """Final research result"""
    success: bool
    query: str
    mode: ResearchMode
    final_answer: str
    sources: List[Dict[str, Any]] = field(default_factory=list)
    knowledge_graph: Dict[str, Any] = field(default_factory=dict)
    execution_history: List[Dict[str, Any]] = field(default_factory=list)
    agent_results: List[SubAgentResult] = field(default_factory=list)
    statistics: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_markdown(self) -> str:
        """Export result as Markdown"""
        lines = [
            f"# Research Report: {self.query}",
            f"",
            f"**Mode:** {self.mode.value}",
            f"**Success:** {'✅' if self.success else '❌'}",
            f"**Sources:** {len(self.sources)}",
            f"**Agents Used:** {len([r for r in self.agent_results if r.success])}",
            f"",
            f"## Answer",
            f"",
            self.final_answer,
            f"",
            f"## Sources",
            f"",
        ]
        
        for i, source in enumerate(self.sources, 1):
            lines.append(f"{i}. [{source.get('title', 'Unknown')}]({source.get('url', '#')})")
        
        if self.statistics:
            lines.extend([
                f"",
                f"## Statistics",
                f"",
                f"```json",
                f"{self._dict_to_json(self.statistics)}",
                f"```",
            ])
        
        return "\n".join(lines)
    
    @staticmethod
    def _dict_to_json(d: Dict) -> str:
        """Simple dict to JSON string"""
        import json
        return json.dumps(d, indent=2, default=str)


@dataclass
class DecisionRequest:
    """Request for decision making (from DeepSeek R1)"""
    operation_type: OperationType
    context: Dict[str, Any]
    priority: int = 5  # 1-10
    timeout_seconds: float = 30.0
    requires_delegation: bool = True


@dataclass
class DecisionResponse:
    """Response from decision making"""
    decision_id: str
    operation_type: OperationType
    action: str
    parameters: Dict[str, Any]
    confidence: float
    coordinator_id: Optional[str] = None
    reasoning: Optional[str] = None


@dataclass
class ActionResult:
    """Result from Ghost action execution"""
    action: ActionType
    success: bool
    data: Dict[str, Any]
    execution_time: float
    stagnation_detected: bool = False
    stored_in_vault: bool = False


@dataclass
class SystemMetrics:
    """System health metrics (from InfrastructureOrchestrator)"""
    memory_used_mb: float
    memory_available_mb: float
    cpu_percent: float
    temperature_c: Optional[float]
    state: SystemState
    timestamp: float


@dataclass
class AgentMetrics:
    """Agent performance metrics"""
    agent_type: SubAgentType
    success_rate: float
    avg_execution_time: float
    circuit_breaker_open: bool
    consecutive_failures: int
    total_executions: int


@dataclass
class ComplexityAnalysis:
    """Complexity analysis result for ToT decision making"""
    score: float
    requires_multi_step: bool
    estimated_depth: int
    tot_recommended: bool
    indicators: Dict[str, float]


# =============================================================================
# TYPE ALIASES
# =============================================================================

# For backwards compatibility
AgentCapability = Dict[str, Any]
TaskDefinition = Dict[str, Any]
PlanStep = Dict[str, Any]
KnowledgeNode = Dict[str, Any]


# =============================================================================
# EXCEPTIONS
# =============================================================================

class OrchestratorError(Exception):
    """Base orchestrator error"""
    pass


class StagnationError(OrchestratorError):
    """Detected stagnation/loop in research"""
    pass


class MemoryPressureError(OrchestratorError):
    """Memory limit exceeded"""
    pass


class CircuitBreakerOpenError(OrchestratorError):
    """Circuit breaker is open for agent"""
    pass


class RateLimitExceeded(OrchestratorError):
    """Rate limit exceeded"""
    pass


# =============================================================================
# BASE ORCHESTRATOR CLASS
# =============================================================================

class UniversalResearchOrchestrator:
    """
    Base class for universal research orchestrators.

    Provides common interface and base functionality for all orchestrators
    in the Hledac universal system.

    This is an abstract base class - concrete implementations should
    override the research method.
    """

    def __init__(self, config: Optional[ResearchConfig] = None):
        """
        Initialize the orchestrator.

        Args:
            config: Research configuration
        """
        self.config = config or ResearchConfig()
        self.state = OrchestratorState.IDLE
        self._initialized = False

    async def initialize(self) -> bool:
        """
        Initialize the orchestrator and all subsystems.

        Returns:
            True if initialization successful
        """
        self._initialized = True
        return True

    async def research(
        self,
        query: str,
        search_func: Optional[Any] = None,
        domain: str = "general"
    ) -> Any:
        """
        Execute research query.

        Args:
            query: Research query
            search_func: Optional search function
            domain: Domain context

        Returns:
            Research results

        Raises:
            NotImplementedError: Must be implemented by subclasses
        """
        raise NotImplementedError("Subclasses must implement research()")

    async def cleanup(self) -> None:
        """Cleanup resources."""
        self._initialized = False
        self.state = OrchestratorState.IDLE

    def get_stats(self) -> Dict[str, Any]:
        """Get orchestrator statistics."""
        return {
            "state": self.state.value,
            "initialized": self._initialized,
        }


# =============================================================================
# SECURITY & CRYPTOGRAPHY ENUMS (NEW)
# =============================================================================

class ObfuscationLevel(Enum):
    """String/content obfuscation levels"""
    NONE = "none"
    LIGHT = "light"      # Simple encoding
    MEDIUM = "medium"    # Multi-stage encoding
    HEAVY = "heavy"      # Full obfuscation with decoys
    MAXIMUM = "maximum"  # Military-grade obfuscation


class WipeStandard(Enum):
    """Secure data destruction standards"""
    NIST_800_88 = "nist_800_88"      # 1 pass random
    DoD_5220_22M = "dod_5220_22m"    # 3 passes (0x00, 0xFF, random)
    GUTMANN = "gutmann"               # 35 passes (overkill)


class RiskLevel(Enum):
    """Detection risk levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class BrowserType(Enum):
    """Browser types for stealth"""
    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


class CaptchaType(Enum):
    """CAPTCHA types"""
    RECAPTCHA_V2 = "recaptcha_v2"
    RECAPTCHA_V3 = "recaptcha_v3"
    HCAPTCHA = "hcaptcha"
    FUNCAPTCHA = "funcaptcha"
    IMAGE = "image"
    GEETEST = "geetest"


class PrivacyLevel(Enum):
    """Privacy protection levels"""
    NONE = "none"
    BASIC = "basic"          # DNS encryption only
    STANDARD = "standard"    # VPN + DNS
    ENHANCED = "enhanced"    # VPN + Tor + DNS
    MAXIMUM = "maximum"      # Multi-hop + Tor


class ExplorationStrategy(Enum):
    """Deep research exploration strategies"""
    DEPTH_FIRST = "depth_first"           # Follow one chain deeply
    BREADTH_FIRST = "breadth_first"       # Explore all levels equally
    CITATION_FOLLOWING = "citation"       # Focus on academic citations
    TANGENT_EXPLORATION = "tangent"       # Follow related topics
    HYBRID = "hybrid"                     # Combine multiple strategies


class CommunicationPattern(Enum):
    """Protocol communication patterns"""
    REQUEST_RESPONSE = "request_response"
    STREAMING = "streaming"
    PUB_SUB = "pub_sub"


class LeakSource(Enum):
    """Data leak sources"""
    BREACH_DATABASE = "breach_database"
    DARK_WEB = "dark_web"
    PASTE_SITE = "paste_site"
    SOCIAL_MEDIA = "social_media"
    PUBLIC_RECORDS = "public_records"


class ContentSource(Enum):
    """Archive content sources"""
    WAYBACK = "wayback"
    SEARCH_CACHE = "search_cache"
    SOCIAL_ARCHIVE = "social_archive"


# =============================================================================
# DATACLASSES - SECURITY & CRYPTO (NEW)
# =============================================================================

@dataclass
class ObfuscationResult:
    """Result of string obfuscation"""
    original_hash: str
    obfuscated_data: str
    encoding_chain: List[str]  # e.g., ["xor", "base64", "zlib"]
    decoy_count: int
    success: bool


@dataclass
class DestructionResult:
    """Result of secure data destruction"""
    file_path: str
    standard: WipeStandard
    passes_completed: int
    bytes_overwritten: int
    verification_passed: bool
    timestamp: float


@dataclass
class StealthSession:
    """Stealth browsing session"""
    session_id: str
    browser_type: BrowserType
    fingerprint: Dict[str, Any]
    proxy: Optional[str]
    risk_level: RiskLevel
    created_at: float


@dataclass
class CaptchaSolution:
    """CAPTCHA solving result"""
    solution: str
    solved_at: float
    cost: float
    confidence: float
    provider: str


@dataclass
class PrivacyStatus:
    """Current privacy/anonymity status"""
    vpn_connected: bool
    tor_active: bool
    dns_encrypted: bool
    fingerprint_randomized: bool
    encryption_enabled: bool
    overall_level: PrivacyLevel


@dataclass
class DeepResearchConfig:
    """Configuration for deep research"""
    max_depth: int = 10
    strategy: ExplorationStrategy = ExplorationStrategy.HYBRID
    follow_citations: bool = True
    explore_tangents: bool = True
    max_threads: int = 5
    citation_types: List[str] = field(default_factory=lambda: [
        "academic", "patent", "preprint", "dataset"
    ])


@dataclass
class ExplorationNode:
    """Node in deep research exploration graph"""
    node_id: str
    url: str
    title: str
    depth: int
    parent_id: Optional[str]
    children: List[str] = field(default_factory=list)
    citations: List[str] = field(default_factory=list)
    quality_score: float = 0.0


@dataclass
class GhostAction:
    """GhostDirector action"""
    action_type: ActionType
    parameters: Dict[str, Any]
    priority: int = 5
    requires_stealth: bool = False
    vault_storage: bool = True


@dataclass
class GhostMission:
    """GhostDirector mission"""
    mission_id: str
    goal: str
    actions: List[GhostAction]
    current_step: int = 0
    acquired_loot: List[Dict[str, Any]] = field(default_factory=list)
    anti_loop_counter: int = 0


@dataclass
class DataLeakAlert:
    """Data leak detection alert"""
    alert_id: str
    source: LeakSource
    severity: RiskLevel
    target: str
    leaked_data: Dict[str, Any]
    timestamp: float


@dataclass
class ArchiveSnapshot:
    """Web archive snapshot"""
    url: str
    timestamp: str
    source: ContentSource
    available: bool
    quality_score: float


# =============================================================================
# PRIVACY TYPES
# =============================================================================

class AnonymizationLevel(Enum):
    """PII anonymization levels"""
    NONE = "none"
    PARTIAL = "partial"      # Mask partial data
    FULL = "full"            # Hash replacement
    AGGREGATE = "aggregate"  # Count only


class PrivacyEventCategory(Enum):
    """Privacy audit event categories"""
    DATA_ACCESS = "data_access"
    DATA_MODIFICATION = "data_modification"
    DATA_DELETION = "data_deletion"
    DATA_EXPORT = "data_export"
    CONSENT_GRANTED = "consent_granted"
    CONSENT_REVOKED = "consent_revoked"
    ANONYMIZATION = "anonymization"
    ENCRYPTION = "encryption"


class ProtocolType(Enum):
    """Protocol generation types"""
    MESSAGING = "messaging"
    HANDSHAKE = "handshake"
    ENCRYPTION = "encryption"
    SIGNATURE = "signature"
    ZK_PROOF = "zk_proof"
    MPC = "mpc"


@dataclass
class PrivacyConfig:
    """Privacy layer configuration"""
    level: PrivacyLevel = PrivacyLevel.STANDARD
    
    # Component enables
    enable_privacy_manager: bool = True
    enable_anonymous_comm: bool = True
    enable_audit_log: bool = True
    enable_protocol_gen: bool = False
    
    # VPN settings
    vpn_provider: str = "mullvad"
    vpn_protocol: str = "wireguard"
    
    # Tor settings
    use_tor: bool = False
    tor_use_bridges: bool = False
    
    # DNS settings
    dns_provider: str = "cloudflare"
    dns_protocol: str = "doh"
    
    # Audit settings
    audit_retention_days: int = 90
    audit_encryption: bool = True


# =============================================================================
# TYPE ALIASES (EXTENDED)
# =============================================================================

# Security aliases
ObfuscationPattern = Dict[str, str]
EncryptionKey = Union[str, bytes]
FingerprintConfig = Dict[str, Any]

# Research aliases
CitationGraph = Dict[str, List[str]]
ExplorationTree = Dict[str, ExplorationNode]
GhostLoot = Dict[str, Any]

# Stealth aliases
ProxyConfig = Dict[str, str]
EvasionScript = str
DetectionSignature = Dict[str, Any]

# Privacy aliases
VPNCredentials = Dict[str, str]
PGPKeypair = Dict[str, str]
AuditEntry = Dict[str, Any]

# =============================================================================
# COMMUNICATION TYPES
# =============================================================================

class MessagePriority(Enum):
    """Message priority levels"""
    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4
    BACKGROUND = 5


@dataclass
class CommunicationConfig:
    """Communication layer configuration"""
    enable_agent_messaging: bool = True
    enable_model_bridge: bool = True
    enable_emergent_comm: bool = True
    enable_a2a_protocol: bool = True

    # Optimization settings
    enable_batching: bool = True
    enable_compression: bool = True
    batch_timeout_ms: float = 50.0
    max_batch_size: int = 10

    # Routing settings
    semantic_routing: bool = True
    load_balancing: bool = True

    # Protocol settings
    a2a_version: str = "1.0"
    agent_card_ttl: int = 3600


# =============================================================================
# NEUROMORPHIC COMPUTING TYPES
# =============================================================================

class EventType(Enum):
    """Neural event types for neuromorphic computing"""
    SPIKE = "spike"                          # Neuron spiked
    SYNAPTIC_UPDATE = "synaptic_update"      # Synaptic weight update
    LEARNING_UPDATE = "learning_update"      # STDP learning update
    MEMBRANE_UPDATE = "membrane_update"      # Membrane potential update
    NETWORK_RESET = "network_reset"          # Network state reset
    THRESHOLD_CROSS = "threshold_cross"      # Threshold crossing event


class ProcessingState(Enum):
    """Processing states for neuromorphic operations"""
    IDLE = "idle"
    ACTIVE = "active"
    PROCESSING = "processing"
    LEARNING = "learning"
    CONSOLIDATING = "consolidating"
    SLEEPING = "sleeping"


@dataclass(frozen=True)
class SpikeData:
    """Immutable spike event data"""
    neuron_id: int
    timestamp: float
    amplitude: float = 1.0


@dataclass
class NeuralEvent:
    """Neural event for event-driven processing"""
    event_type: EventType
    source_neuron: int
    target_neurons: List[int]
    timestamp: float
    weight_delta: float = 0.0
    priority: int = 5  # 1-10, lower is higher priority
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.timestamp == 0:
            object.__setattr__(self, 'timestamp', datetime.now().timestamp())


@dataclass
class ProcessingMetrics:
    """Metrics for neuromorphic processing"""
    energy_consumption_joules: float = 0.0
    spike_count: int = 0
    active_neurons: int = 0
    synaptic_operations: int = 0
    processing_time_ms: float = 0.0
    memory_used_bytes: int = 0


@dataclass
class ProcessingResult:
    """Result from neuromorphic processing"""
    success: bool
    state: ProcessingState
    metrics: ProcessingMetrics
    spike_history: List[SpikeData] = field(default_factory=list)
    output_pattern: Optional[np.ndarray] = None
    error_message: Optional[str] = None


@dataclass
class SNNConfig:
    """Configuration for Spiking Neural Network"""
    n_neurons: int = 1000
    connection_prob: float = 0.1
    use_metal: bool = True
    enable_stdp: bool = True
    v_rest: float = -65.0
    v_thresh: float = -50.0
    tau_m: float = 20.0
    dt: float = 1.0
    refractory_period: float = 2.0


@dataclass
class STDPParams:
    """STDP (Spike-Timing-Dependent Plasticity) parameters"""
    A_plus: float = 0.01       # LTP amplitude
    A_minus: float = -0.0105   # LTD amplitude
    tau_plus: float = 20.0     # LTP time constant (ms)
    tau_minus: float = 20.0    # LTD time constant (ms)
    w_min: float = -1.0        # Minimum weight
    w_max: float = 1.0         # Maximum weight


@dataclass
class NeuronParameters:
    """Biological parameters for LIF neurons"""
    v_rest: float = -65.0      # Resting potential (mV)
    v_reset: float = -65.0     # Reset potential after spike (mV)
    v_thresh: float = -50.0    # Spike threshold (mV)
    tau_m: float = 20.0        # Membrane time constant (ms)
    tau_ref: float = 2.0       # Refractory period (ms)
    resistance: float = 1.0    # Membrane resistance (MΩ)
    noise_std: float = 0.5     # Synaptic noise standard deviation (mV)


@dataclass
class NeuromorphicEnergyReport:
    """Energy efficiency report for neuromorphic computing"""
    total_energy_joules: float
    energy_per_spike_joules: float
    active_neuron_ratio: float
    efficiency_gain_vs_ann: float
    computational_efficiency: float
    co2_emissions_kg: float = 0.0
    trees_equivalent: float = 0.0  # CO2 absorbed by trees per year
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())


@dataclass
class ReservoirConfig:
    """Configuration for Reservoir Computing (ESN/LSM)"""
    reservoir_size: int = 1000
    input_scaling: float = 1.0
    spectral_radius: float = 0.9
    leaking_rate: float = 0.3
    sparsity: float = 0.1
    use_metal: bool = True
    reservoir_type: str = "esn"  # "esn" or "lsm"


@dataclass
class SNNEncryptedContainer:
    """Encrypted container using SNN-based cryptography"""
    ciphertext: bytes
    neural_signature: np.ndarray
    key_id: str
    timestamp: float
    entropy_used: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "ciphertext": base64.b64encode(self.ciphertext).decode(),
            "neural_signature": base64.b64encode(self.neural_signature.tobytes()).decode(),
            "key_id": self.key_id,
            "timestamp": self.timestamp,
            "entropy_used": self.entropy_used
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SNNEncryptedContainer":
        """Create from dictionary"""
        return cls(
            ciphertext=base64.b64decode(data["ciphertext"]),
            neural_signature=np.frombuffer(
                base64.b64decode(data["neural_signature"]),
                dtype=np.float32
            ),
            key_id=data["key_id"],
            timestamp=data["timestamp"],
            entropy_used=data.get("entropy_used", 0)
        )
