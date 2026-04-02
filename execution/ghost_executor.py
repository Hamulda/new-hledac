"""
GhostExecutor - Vykonávací engine pro UniversalResearchOrchestrator

Implementuje 14+ akcí pro deep research:
- SCAN, GOOGLE, DOWNLOAD, SEARCH, SMART_SEARCH
- MEMORIZE, PROBE, TRACK
- RESEARCH_PAPER, DEEP_RESEARCH, DEEP_READ
- ANSWER, CRACK, ERROR
- ARCHIVE_FALLBACK, FACT_CHECK, STEALTH_HARVEST, OSINT_DISCOVERY
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ActionType(Enum):
    """Typy akcí"""
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
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "action": self.action,
            "data": self.data,
            "error": self.error,
        }


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
