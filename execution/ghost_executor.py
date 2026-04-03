"""
GhostExecutor - Vykonávací engine pro UniversalResearchOrchestrator

Implementuje 14+ akcí pro deep research:
- SCAN, GOOGLE, DOWNLOAD, SEARCH, SMART_SEARCH
- MEMORIZE, PROBE, TRACK
- RESEARCH_PAPER, DEEP_RESEARCH, DEEP_READ
- ANSWER, CRACK, ERROR
- ARCHIVE_FALLBACK, FACT_CHECK, STEALTH_HARVEST, OSINT_DISCOVERY

Sprint 8VF BRIDGE SEAM:
═══════════════════════════════════════════════════════════════
GhostExecutor je DONOR/COMPAT vrstva — není canonical authority.
Canonical authority: ToolRegistry.execute_with_limits()

Tento soubor obsahuje THIN TYPED BRIDGE SEAM pro budoucí cutover:
- _ACTION_TO_CANONICAL_TOOL: read-only mapping Ghost akce → canonical tool name
- GhostBridge.to_execution_request(): Ghost params → ExecutionRequest
- GhostBridge.to_execution_result(): Ghost ActionResult → ExecutionResult

BRIDGE je READ-SIDE ADAPTER — nemění GhostExecutor.execute() path.
BRIDGE nevolá ToolRegistry.execute_with_limits() — jen typovou konverzi.

REMOVAL CONDITION:
Až všechny Ghost akce (SCAN, GOOGLE, DEEP_READ, STEALTH_HARVEST,
OSINT_DISCOVERY, atd.) budou migrovány do ToolRegistry jako proper
Tool handlery, GhostExecutor se stane kandidátem na deprecation.
Do té doby zůstává donor/compat vrstvou s tímto bridge seamem.
═══════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from ..types import ExecutionRequest, ExecutionResult, RunCorrelation

logger = logging.getLogger(__name__)


class ActionType(Enum):
    """
    Typy akcí.

    NON-CANONICAL — DUPLICATE of types.py:119 ActionResultType.
    Sprint 8VF: This enum is a LOCAL scaffold in the Ghost layer.
    It is NOT the canonical action taxonomy.

    The canonical ActionResultType enum lives in types.py:42.
    GhostExecutor uses this local enum because its action handlers
    predate the canonical scaffold.

    BRIDGE NOTE (Sprint 8VF):
    GhostBridge._ACTION_TO_CANONICAL_TOOL provides a read-only mapping
    from this local enum to canonical tool names.

    MIGRATION: When all Ghost actions migrate to ToolRegistry, this enum
    becomes deprecated in favor of types.py ActionResultType.

    See: types.py CANONICAL SCAFFOLD header (line 1269)
    """
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
    ARCHIVE_FALLBACK = "archive_fallback"
    FACT_CHECK = "fact_check"
    STEALTH_HARVEST = "stealth_harvest"
    OSINT_DISCOVERY = "osint_discovery"


@dataclass
class ActionResult:
    """Výsledek akce"""
    success: bool
    action: str
    data: Dict[str, Any]
    error: Optional[str] = None
    execution_time: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "action": self.action,
            "data": self.data,
            "error": self.error,
            "execution_time": self.execution_time,
        }


# =============================================================================
# Sprint 8VF: Thin Typed Bridge Seam
# =============================================================================
# READ-SIDE ADAPTER — nemění GhostExecutor.execute() path
# Pouze typová konverze mezi Ghost světem a canonical ExecutionRequest/ExecutionResult
# Neprodukuje side effects, nevolá ToolRegistry.execute_with_limits()
# =============================================================================

# =============================================================================
# Sprint 8VF: Delegation Matrix — Ghost Action → Canonical Tool
# =============================================================================
# STRICT CLASSIFICATION — nepřekládat vyšší coverage než repo skutečně má
#
# 3 kategorie:
#   canonical_ready       = plná sémantická shoda, lze delegovat
#   mapped_but_lossy      = mapping exists, ale sémantika ≠ (viz blokery)
#   runtime_only_compat   = žádný canonical ekvivalent, zůstává v Ghost path
#
# Audit pravidla:
#   - canonical_ready pouze když Ghost action a Tool handler dělajÍ TOTÉŽ
#   - mapped_but_lossy když mapping existuje ale sémantika se liší
#   - runtime_only_compat když není canonical ekvivalent
# =============================================================================

# === CANONICAL-READY SLICE ===
# Kritérium: Ghost action a ToolRegistry tool DĚLAJÍ TOTÉŽ (ne jen podobně)
# Aktuální stav: ŽÁDNÁ akce nesplňuje toto kritérium.
# Důvod: Ghost akce mají vlastní implementace (byť placeholder),
#        ToolRegistry handlery jsou placeholder/univerzální.
# SPRINT 8VF: Delegation seam existuje, ale canonical-ready slice je PRÁZDNÁ.
_CANONICAL_READY_ACTIONS: Set[str] = set()  # prázdná — audit viz níže

# === MAPPED-BUT-LOSSY SLICE ===
# Kritérium: Ghost action má mapping na ToolRegistry tool,
#            ale sémantika provádění se ZÁSADNĚ liší.
#
# Blokery pro canonical-ready:
#   SEARCH/GOOGLE/SMART_SEARCH → web_search:
#     Ghost: harvestuje URL přes network driver + stealth + Bloom dedup
#     TR: placeholder handler (vrací prázdné výsledky)
#     Sémantika ≠ → MAPPED-BUT-LOSSY, ne canonical-ready
#
#   RESEARCH_PAPER → academic_search:
#     Ghost: placeholder (vrací prázdné)
#     TR: placeholder (vrací prázdné)
#     Žádný skutečný obsah → MAPPED-BUT-LOSSY
#
#   DEEP_READ → file_read:
#     Ghost: URL harvest + BloomFilter dedup + context update + 8KB chunking + 5MB limit
#     TR: local file read (žádný network, žádný Bloom, žádný context)
#     Sémantika ≠ → MAPPED-BUT-LOSSY
#
_MAPPED_BUT_LOSSY_ACTIONS: Set[str] = {
    ActionType.SEARCH.value,
    ActionType.GOOGLE.value,
    ActionType.SMART_SEARCH.value,
    ActionType.RESEARCH_PAPER.value,
    ActionType.DEEP_READ.value,
}

# === RUNTIME-ONLY-COMPAT SLICE ===
# Kritérium: žádný canonical ekvivalent v ToolRegistry
_RUNTIME_ONLY_COMPAT_ACTIONS: Set[str] = {
    ActionType.SCAN.value,
    ActionType.DOWNLOAD.value,
    ActionType.MEMORIZE.value,
    ActionType.PROBE.value,
    ActionType.TRACK.value,
    ActionType.DEEP_RESEARCH.value,
    ActionType.ANSWER.value,
    ActionType.CRACK.value,
    ActionType.ERROR.value,
    ActionType.ARCHIVE_FALLBACK.value,
    ActionType.FACT_CHECK.value,
    ActionType.STEALTH_HARVEST.value,
    ActionType.OSINT_DISCOVERY.value,
}

# === UNIFIED MAPPING pro diagnostiku a delegation seam ===
# Současný stav: pouze diagnostický — obsahuje i mapped-but-lossy položky
# Future: po F9 cutover bude obsahovat pouze canonical-ready
_ACTION_TO_CANONICAL_TOOL: Dict[str, str] = {
    # Mapped (ale lossy) akce
    ActionType.SEARCH.value: "web_search",
    ActionType.GOOGLE.value: "web_search",
    ActionType.SMART_SEARCH.value: "web_search",
    ActionType.RESEARCH_PAPER.value: "academic_search",
    ActionType.DEEP_READ.value: "file_read",
    # Runtime-only akce — žádný canonical ekvivalent
    ActionType.SCAN.value: "",
    ActionType.DOWNLOAD.value: "",
    ActionType.MEMORIZE.value: "",
    ActionType.PROBE.value: "",
    ActionType.TRACK.value: "",
    ActionType.DEEP_RESEARCH.value: "",
    ActionType.ANSWER.value: "",
    ActionType.CRACK.value: "",
    ActionType.ERROR.value: "",
    ActionType.ARCHIVE_FALLBACK.value: "",
    ActionType.FACT_CHECK.value: "",
    ActionType.STEALTH_HARVEST.value: "",
    ActionType.OSINT_DISCOVERY.value: "",
}


def _get_action_classification(action: str) -> str:
    """
    Vrátí klasifikaci Ghost akce.

    Returns:
        "canonical_ready"      — lze delegovat na ToolRegistry path
        "mapped_but_lossy"     — má mapping, ale sémantika ≠
        "runtime_only_compat" — žádný canonical ekvivalent
    """
    if action in _CANONICAL_READY_ACTIONS:
        return "canonical_ready"
    elif action in _MAPPED_BUT_LOSSY_ACTIONS:
        return "mapped_but_lossy"
    elif action in _RUNTIME_ONLY_COMPAT_ACTIONS:
        return "runtime_only_compat"
    return "unknown"


class GhostBridge:
    """
    Sprint 8VF: Thin typed bridge — READ-SIDE ADAPTER mezi Ghost a canonical světem.

    ÚČEL:
    - Konvertuje Ghost akce/params na ExecutionRequest bez volání ToolRegistry
    - Konvertuje Ghost ActionResult na ExecutionResult bez side effects
    - Poskytuje read-only metadata pro dispatch parity preview

    CO NENÍ:
    - Není nový execution framework
    - Nemění GhostExecutor.execute() path
    - Nevolá ToolRegistry.execute_with_limits()
    - Neprodukuje side effects

    INVARIANTS:
    - execute_with_limits() zůstává jediný canonical execution-control surface
    - GhostExecutor zůstává donor/compat
    - Bridge je read-side adapter, ne execution authority

    REMOVAL CONDITION:
    Až všechny Ghost akce migrují do ToolRegistry, bridge zůstává
    jako backward-compat pro existující volající kód.
    """

    @staticmethod
    def action_has_canonical_tool(action: str) -> bool:
        """
        Vrátí True pokud Ghost akce má mapping na ToolRegistry tool.

        DIAGNOSTIC ONLY — čte z _ACTION_TO_CANONICAL_TOOL.
        """
        canonical = _ACTION_TO_CANONICAL_TOOL.get(action, "")
        return bool(canonical)

    @staticmethod
    def get_canonical_tool_name(action: str) -> str:
        """
        Vrátí canonical tool name pro Ghost akci, nebo prázdný string.

        DIAGNOSTIC ONLY — read-only mapping lookup.
        """
        return _ACTION_TO_CANONICAL_TOOL.get(action, "")

    @staticmethod
    def to_execution_request(
        action: str,
        params: Dict[str, Any],
        priority: int = 5,
        correlation: Optional["RunCorrelation"] = None,
    ) -> "ExecutionRequest":
        """
        Konvertuje Ghost akci + params na canonical ExecutionRequest.

        TOTO JE TYPOVÁ KONVERZE — žádné volání ToolRegistry.execute_with_limits().
        Výsledný ExecutionRequest lze předat do ToolRegistry.execute_with_limits()
        v budoucím cutover kroku.

        Args:
            action: Ghost ActionType string (např. "google", "deep_read")
            params: Parametry akce
            priority: Execution priority (1-10, lower = higher priority)
            correlation: Optional run correlation context

        Returns:
            ExecutionRequest — canonical typed request

        NOTE: Tato funkce neověřuje, zda action má canonical tool mapping.
        Použij action_has_canonical_tool() pro diagnostiku před konverzí.
        """
        from ..types import ExecutionRequest as _ExecReq
        return _ExecReq(
            action_type=action,
            parameters=params,
            priority=priority,
            correlation=correlation,
        )

    @staticmethod
    def to_execution_result(
        ghost_result: ActionResult,
        correlation: Optional["RunCorrelation"] = None,
    ) -> "ExecutionResult":
        """
        Konvertuje Ghost ActionResult na canonical ExecutionResult.

        TOTO JE TYPOVÁ KONVERZE — žádné side effects.

        Args:
            ghost_result: Ghost ActionResult z execute()
            correlation: Optional run correlation (echoed from request)

        Returns:
            ExecutionResult — canonical typed result

        NOTE: execution_time je echo zpět z GhostResult, nemeasured
        canonical execution time (protože Ghost nevolá execute_with_limits).
        """
        from ..types import ExecutionResult as _ExecRes
        return _ExecRes(
            action_type=ghost_result.action,
            success=ghost_result.success,
            data=ghost_result.data,
            execution_time=ghost_result.execution_time,
            error=ghost_result.error,
            correlation=correlation,
        )

    @staticmethod
    def get_action_classification(action: str) -> str:
        """
        Vrátí klasifikaci Ghost akce.

        Returns:
            "canonical_ready"      — lze delegovat na ToolRegistry path
            "mapped_but_lossy"     — má mapping, ale sémantika ≠
            "runtime_only_compat"  — žádný canonical ekvivalent
        """
        return _get_action_classification(action)

    @staticmethod
    def is_delegation_allowed(action: str) -> bool:
        """
        Vrátí True pokud lze akci delegovat na ToolRegistry path.

        Delegation je povolena POUZE pro canonical-ready akce.
        mapped_but_lossy akce mají mapping, ale sémantika ≠ —
        delegace by ztratila funkčnost.

        Returns:
            True pouze pro canonical-ready akce
        """
        return _get_action_classification(action) == "canonical_ready"

    @staticmethod
    def to_delegation_request(
        action: str,
        params: Dict[str, Any],
        priority: int = 5,
        correlation: Optional["RunCorrelation"] = None,
    ) -> Optional["ExecutionRequest"]:
        """
        Konvertuje Ghost akci na canonical ExecutionRequest PRO CANONICAL-READY AKCE.

        Používá _ACTION_TO_CANONICAL_TOOL mapping a překládá Ghost action
        na canonical tool name v action_type poli.

        Args:
            action: Ghost ActionType string (např. "google", "deep_read")
            params: Parametry akce
            priority: Execution priority (1-10, lower = higher priority)
            correlation: Optional run correlation context

        Returns:
            ExecutionRequest s canonical tool name v action_type,
            NEBO None pokud akce není canonical-ready.

        Delegation rules:
            canonical_ready   → vrací ExecutionRequest s canonical tool name
            mapped_but_lossy  → vrací None (sémantika ≠, nelze beztrastně delegovat)
            runtime_only_compat → vrací None (žádný canonical ekvivalent)
        """
        if not GhostBridge.is_delegation_allowed(action):
            return None

        canonical_tool = _ACTION_TO_CANONICAL_TOOL.get(action, "")
        if not canonical_tool:
            return None

        from ..types import ExecutionRequest as _ExecReq
        return _ExecReq(
            action_type=canonical_tool,
            parameters=params,
            priority=priority,
            correlation=correlation,
        )

    @staticmethod
    def get_delegation_matrix() -> Dict[str, str]:
        """
        Vrátí kompletní klasifikační matici Ghost akcí.

        Returns:
            Dict mapping action → classification pro všechny Ghost akce.
            Použitelné pro audit a dispatch parity preview.
        """
        matrix = {}
        for action in _ACTION_TO_CANONICAL_TOOL:
            matrix[action] = _get_action_classification(action)
        return matrix

    @staticmethod
    def get_canonical_ready_actions() -> Set[str]:
        """Vrátí set canonical-ready akcí (prázdná množina v current repo)."""
        return set(_CANONICAL_READY_ACTIONS)

    @staticmethod
    def get_mapped_but_lossy_actions() -> Set[str]:
        """Vrátí set mapped-but-lossy akcí."""
        return set(_MAPPED_BUT_LOSSY_ACTIONS)

    @staticmethod
    def get_runtime_only_compat_actions() -> Set[str]:
        """Vrátí set runtime-only-compat akcí."""
        return set(_RUNTIME_ONLY_COMPAT_ACTIONS)

    @staticmethod
    def get_action_canonical_tool_mapping() -> Dict[str, str]:
        """
        Vrátí kopii read-only _ACTION_TO_CANONICAL_TOOL mappingu.

        DIAGNOSTIC ONLY — pro dispatch parity preview a audit.
        """
        return dict(_ACTION_TO_CANONICAL_TOOL)


class GhostExecutor:
    """
    Donor/compatibility backend for research actions.

    ROLE (Sprint 8VF):
    ════════════════════════════════════════════════════════
    This class is a DONOR/COMPATIBILITY backend — NOT the
    canonical execution-control surface.

    Canonical authority: ToolRegistry.execute_with_limits()
    Donor reason:          Gradual migration from ActionType-based
                           actions to Tool-based handlers

    REMOVAL CONDITION:
    When all GhostExecutor actions (SCAN, GOOGLE, DEEP_READ,
    STEALTH_HARVEST, OSINT_DISCOVERY, etc.) are migrated to
    ToolRegistry as proper Tool handlers, this class becomes
    a candidate for deprecation.

    BOUNDARY SEAMS:
    - Uses ActionType enum (NOT Tool model)
    - Has own _actions dict (NOT _tools registry)
    - execute() does NOT call ToolRegistry.execute_with_limits()
    - Action handlers live here, not in ToolRegistry

    INTEGRATION NOTE:
    - Do NOT reference GhostExecutor as "the executor" in docs
    - Use ToolRegistry as the primary execution surface
    - GhostExecutor.execute() is a SEPARATE execution path
    ════════════════════════════════════════════════════════

    Integruje:
    - GhostNetworkDriver pro web crawling
    - StealthManager pro stealth operace
    - ArchiveDiscovery pro Wayback fallback
    - Bloom Filter pro deduplikaci
    """
    
    def __init__(self, enable_stealth: bool = True):
        self.enable_stealth = enable_stealth
        
        # Lazy-loaded komponenty
        self._network_driver = None
        self._stealth_manager = None
        self._bloom_filter = None
        
        # Registr akcí
        self._actions = self._init_actions()
        
    def _init_actions(self) -> Dict[str, callable]:
        """Inicializovat mapování akcí"""
        return {
            ActionType.SCAN.value: self._action_scan,
            ActionType.GOOGLE.value: self._action_google,
            ActionType.DOWNLOAD.value: self._action_download,
            ActionType.SEARCH.value: self._action_search,
            ActionType.SMART_SEARCH.value: self._action_smart_search,
            ActionType.MEMORIZE.value: self._action_memorize,
            ActionType.PROBE.value: self._action_probe,
            ActionType.TRACK.value: self._action_track,
            ActionType.RESEARCH_PAPER.value: self._action_research_paper,
            ActionType.DEEP_RESEARCH.value: self._action_deep_research,
            ActionType.DEEP_READ.value: self._action_deep_read,
            ActionType.ANSWER.value: self._action_answer,
            ActionType.CRACK.value: self._action_crack,
            ActionType.ARCHIVE_FALLBACK.value: self._action_archive_fallback,
            ActionType.FACT_CHECK.value: self._action_fact_check,
            ActionType.STEALTH_HARVEST.value: self._action_stealth_harvest,
            ActionType.OSINT_DISCOVERY.value: self._action_osint_discovery,
        }
    
    async def initialize(self) -> None:
        """Inicializovat executor"""
        logger.info("Initializing GhostExecutor...")
        
        # Inicializovat Bloom Filter pro URL deduplikaci
        await self._init_bloom_filter()
        
        logger.info("✓ GhostExecutor initialized")
    
    async def _init_bloom_filter(self) -> None:
        """Inicializovat Bloom Filter"""
        try:
            from hledac.utils.bloom_filter import ScalableBloomFilter
            self._bloom_filter = ScalableBloomFilter(
                initial_capacity=10000,
                error_rate=0.01
            )
            logger.info("✓ Bloom Filter initialized (10K URLs capacity)")
        except Exception as e:
            logger.warning(f"Bloom Filter not available: {e}")
    
    async def _get_network_driver(self):
        """Lazy load network driver"""
        if self._network_driver is None:
            from hledac.network.ghost_network_driver import GhostNetworkDriver
            logger.info("Loading GhostNetworkDriver...")
            self._network_driver = GhostNetworkDriver(headless=True)
            await self._network_driver.initialize()
            logger.info("✓ GhostNetworkDriver loaded")
        return self._network_driver
    
    async def _get_stealth_manager(self):
        """Lazy load stealth manager"""
        if self._stealth_manager is None and self.enable_stealth:
            from hledac.stealth_toolkit.stealth_orchestrator import StealthOrchestrator
            logger.info("Loading StealthOrchestrator...")
            self._stealth_manager = StealthOrchestrator()
            logger.info("✓ StealthOrchestrator loaded")
        return self._stealth_manager
    
    async def execute(
        self,
        action: str,
        params: Dict[str, Any],
        context=None
    ) -> Dict[str, Any]:
        """
        Vykonat akci.
        
        Args:
            action: Typ akce
            params: Parametry akce
            context: Výzkumný kontext
            
        Returns:
            Výsledek akce jako slovník
        """
        logger.info(f"Executing action: {action}")
        
        # Najít handler
        handler = self._actions.get(action)
        if handler is None:
            return ActionResult(
                success=False,
                action=action,
                data={},
                error=f"Unknown action: {action}"
            ).to_dict()
        
        # Vykonat
        try:
            result = await handler(params, context)
            return result
        except Exception as e:
            logger.error(f"Action {action} failed: {e}")
            return ActionResult(
                success=False,
                action=action,
                data={},
                error=str(e)
            ).to_dict()
    
    # =====================================================================
    # AKCE
    # =====================================================================
    
    async def _action_search(self, params: Dict[str, Any], context) -> Dict[str, Any]:
        """Vyhledávání"""
        query = params.get("query", "")
        logger.info(f"Searching: {query}")
        
        # TODO: Implementovat vlastní vyhledávání nebo Google
        return ActionResult(
            success=True,
            action="search",
            data={"query": query, "results": []},
        ).to_dict()
    
    async def _action_google(self, params: Dict[str, Any], context) -> Dict[str, Any]:
        """Google vyhledávání"""
        query = params.get("query", "")
        logger.info(f"Google search: {query}")
        
        try:
            driver = await self._get_network_driver()
            
            # Použít stealth pokud je povolen
            if self.enable_stealth and self._stealth_manager:
                # TODO: Implementovat stealth google search
                pass
            
            # Prozatím placeholder
            return ActionResult(
                success=True,
                action="google",
                data={"query": query, "results": []},
            ).to_dict()
            
        except Exception as e:
            return ActionResult(
                success=False,
                action="google",
                data={},
                error=str(e)
            ).to_dict()
    
    async def _action_deep_read(self, params: Dict[str, Any], context) -> Dict[str, Any]:
        """
        Bezpečné čtení obsahu z URL (8KB chunks, 5MB limit).
        
        Bezpečně stáhne a přečte obsah z URL s ochranou před velkými soubory.
        """
        url = params.get("url", "")
        
        # Kontrola duplicity
        if self._bloom_filter and self._bloom_filter.contains(url):
            logger.info(f"Skipping duplicate URL: {url}")
            return ActionResult(
                success=True,
                action="deep_read",
                data={"url": url, "skipped": True, "reason": "duplicate"},
            ).to_dict()
        
        logger.info(f"Deep reading: {url}")
        
        try:
            driver = await self._get_network_driver()
            
            # Harvestovat stránku
            result = await driver.harvest(url)
            
            if result.success:
                # Přidat do Bloom Filter
                if self._bloom_filter:
                    self._bloom_filter.add(url)
                
                # Přidat do kontextu
                if context:
                    context.visited_urls.add(url)
                    content_hash = hashlib.md5(result.main_content.encode()).hexdigest()
                    context.content_hashes.add(content_hash)
                    context.collected_data.append({
                        "url": url,
                        "title": result.metadata.get("title", ""),
                        "content": result.main_content[:5000],  # Prvních 5000 znaků
                    })
                
                return ActionResult(
                    success=True,
                    action="deep_read",
                    data={
                        "url": url,
                        "title": result.metadata.get("title", ""),
                        "content_length": len(result.main_content),
                        "content_preview": result.main_content[:500],
                    },
                ).to_dict()
            else:
                return ActionResult(
                    success=False,
                    action="deep_read",
                    data={"url": url},
                    error=result.error or "Harvest failed"
                ).to_dict()
                
        except Exception as e:
            return ActionResult(
                success=False,
                action="deep_read",
                data={"url": url},
                error=str(e)
            ).to_dict()
    
    async def _action_research_paper(self, params: Dict[str, Any], context) -> Dict[str, Any]:
        """Vyhledávání akademických prací"""
        query = params.get("query", "")
        logger.info(f"Research paper search: {query}")
        
        try:
            # Použít Semantic Scholar nebo jiný akademický zdroj
            # TODO: Implementovat akademické vyhledávání
            
            return ActionResult(
                success=True,
                action="research_paper",
                data={"query": query, "papers": []},
            ).to_dict()
            
        except Exception as e:
            return ActionResult(
                success=False,
                action="research_paper",
                data={},
                error=str(e)
            ).to_dict()
    
    async def _action_archive_fallback(self, params: Dict[str, Any], context) -> Dict[str, Any]:
        """Wayback Machine fallback"""
        url = params.get("url", "")
        logger.info(f"Archive fallback: {url}")
        
        try:
            from hledac.universal.intelligence.archive_discovery import search_archives

            archive_result = await search_archives(url)

            if archive_result and archive_result.snapshots:
                latest = archive_result.snapshots[0]
                
                return ActionResult(
                    success=True,
                    action="archive_fallback",
                    data={
                        "original_url": url,
                        "archive_url": latest.archive_url,
                        "timestamp": latest.timestamp,
                    },
                ).to_dict()
            else:
                return ActionResult(
                    success=False,
                    action="archive_fallback",
                    data={"url": url},
                    error="No archive snapshots found"
                ).to_dict()
                
        except Exception as e:
            return ActionResult(
                success=False,
                action="archive_fallback",
                data={},
                error=str(e)
            ).to_dict()
    
    async def _action_fact_check(self, params: Dict[str, Any], context) -> Dict[str, Any]:
        """Ověření faktů"""
        claims = params.get("claims", [])
        logger.info(f"Fact checking {len(claims)} claims")
        
        try:
            from hledac.fact_checking import quick_fact_check
            
            results = []
            for claim in claims:
                result = await quick_fact_check(claim)
                results.append({
                    "claim": claim,
                    "verdict": result.verdict if hasattr(result, 'verdict') else "unknown",
                })
            
            return ActionResult(
                success=True,
                action="fact_check",
                data={"results": results},
            ).to_dict()
            
        except Exception as e:
            return ActionResult(
                success=False,
                action="fact_check",
                data={},
                error=str(e)
            ).to_dict()
    
    async def _action_stealth_harvest(self, params: Dict[str, Any], context) -> Dict[str, Any]:
        """Stealth harvestování"""
        url = params.get("url", "")
        logger.info(f"Stealth harvest: {url}")
        
        try:
            from hledac.advanced_web.detection_evader import DetectionEvader
            
            evader = DetectionEvader()
            driver = await self._get_network_driver()
            
            async with evader.evasion_session() as session:
                result = await driver.harvest(url, session=session)
                
                if result.success:
                    # Označit stealth aktivaci v kontextu
                    if context:
                        context.stealth_activated = True
                    
                    return ActionResult(
                        success=True,
                        action="stealth_harvest",
                        data={
                            "url": url,
                            "title": result.metadata.get("title", ""),
                            "content_length": len(result.main_content),
                        },
                    ).to_dict()
                else:
                    return ActionResult(
                        success=False,
                        action="stealth_harvest",
                        data={"url": url},
                        error=result.error
                    ).to_dict()
                    
        except Exception as e:
            return ActionResult(
                success=False,
                action="stealth_harvest",
                data={},
                error=str(e)
            ).to_dict()
    
    async def _action_osint_discovery(self, params: Dict[str, Any], context) -> Dict[str, Any]:
        """OSINT objevování skrytých zdrojů"""
        query = params.get("query", "")
        logger.info(f"OSINT discovery: {query}")
        
        try:
            from hledac.osint import HiddenSourcesCrawler
            
            crawler = HiddenSourcesCrawler()
            discovered = await crawler.discover_sources(query, max_sources=5)
            
            sources = [
                {
                    "url": d.url,
                    "title": d.title,
                    "source_type": d.source_type,
                }
                for d in discovered
            ]
            
            return ActionResult(
                success=True,
                action="osint_discovery",
                data={
                    "query": query,
                    "sources": sources,
                    "count": len(sources),
                },
            ).to_dict()
            
        except Exception as e:
            return ActionResult(
                success=False,
                action="osint_discovery",
                data={},
                error=str(e)
            ).to_dict()
    
    # Placeholder akce
    async def _action_scan(self, params, context):
        return ActionResult(success=True, action="scan", data={}).to_dict()
    
    async def _action_download(self, params, context):
        return ActionResult(success=True, action="download", data={}).to_dict()
    
    async def _action_smart_search(self, params, context):
        return ActionResult(success=True, action="smart_search", data={}).to_dict()
    
    async def _action_memorize(self, params, context):
        return ActionResult(success=True, action="memorize", data={}).to_dict()
    
    async def _action_probe(self, params, context):
        return ActionResult(success=True, action="probe", data={}).to_dict()
    
    async def _action_track(self, params, context):
        return ActionResult(success=True, action="track", data={}).to_dict()
    
    async def _action_deep_research(self, params, context):
        return ActionResult(success=True, action="deep_research", data={}).to_dict()
    
    async def _action_answer(self, params, context):
        return ActionResult(success=True, action="answer", data={}).to_dict()
    
    async def _action_crack(self, params, context):
        return ActionResult(success=True, action="crack", data={}).to_dict()
    
    # =====================================================================
    # CLEANUP
    # =====================================================================
    
    async def unload(self) -> None:
        """Uvolnit zdroje"""
        logger.info("Unloading GhostExecutor...")
        
        if self._network_driver:
            await self._network_driver.close()
            self._network_driver = None
        
        self._stealth_manager = None
        self._bloom_filter = None
        
        logger.info("✓ GhostExecutor unloaded")
    
    async def close(self) -> None:
        """Zavřít executor"""
        await self.unload()
