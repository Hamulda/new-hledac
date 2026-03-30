"""
Subsystem Semaphores - Apple Silicon Resource Routing
===================================================

Phase 1A: 30min Sprint Orchestration Backbone

Explicit subsystem semafory pro Apple Silicon:
- gpu_sem: max 1 (Hermes / heavy MLX / GPU-heavy rerank)
- ane_sem: max 1 (Foundation Models / CoreML / Vision / NaturalLanguage)
- cpu_heavy_sem: max 2 (SimSIMD / MMR / parsing / PRF / compression)
- io_sem: max 6 (fetch / crawl / archive / network probes)
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class Subsystem(Enum):
    """Subsystem typy pro routing."""
    GPU = "gpu"           # Hermes / heavy MLX
    ANE = "ane"           # CoreML / Vision / NaturalLanguage
    CPU_HEAVY = "cpu_heavy"  # SimSIMD / MMR / parsing
    IO = "io"             # fetch / crawl / network


class SubsystemSemaphores:
    """
    Správce semaforů pro Apple Silicon subsystemy.

    Poskytuje bounded concurrency pro každý subsystem:
    - GPU: max 1 (single heavy lane)
    - ANE: max 1 (ANE je sdílená)
    - CPU-heavy: max 2
    - I/O: max 6
    """

    def __init__(
        self,
        gpu_limit: int = 1,
        ane_limit: int = 1,
        cpu_heavy_limit: int = 2,
        io_limit: int = 6,
        deep_read_limit: int = 2
    ):
        self._limits = {
            Subsystem.GPU: gpu_limit,
            Subsystem.ANE: ane_limit,
            Subsystem.CPU_HEAVY: cpu_heavy_limit,
            Subsystem.IO: io_limit,
            "DEEP_READ": deep_read_limit,
        }

        self._semaphores: dict[Subsystem, asyncio.Semaphore] = {
            subsystem: asyncio.Semaphore(limit)
            for subsystem, limit in self._limits.items()
        }

        # Action name → subsystem mapping
        self._action_routes: dict[str, Subsystem] = {
            # GPU: Hermes / heavy MLX / GPU-heavy rerank
            "hermes_generate": Subsystem.GPU,
            "hermes_inference": Subsystem.GPU,
            "mlx_generate": Subsystem.GPU,
            "mlx_inference": Subsystem.GPU,
            "gpu_rerank": Subsystem.GPU,
            "heavy_rerank": Subsystem.GPU,

            # ANE: CoreML / Vision / NaturalLanguage
            "coreml_classify": Subsystem.ANE,
            "coreml_vision": Subsystem.ANE,
            "vision_ocr": Subsystem.ANE,
            "natural_language_ner": Subsystem.ANE,
            "ane_embed": Subsystem.ANE,

            # CPU-heavy: SimSIMD / MMR / parsing / PRF / compression
            "mmr_rerank": Subsystem.CPU_HEAVY,
            "mmr_diversity": Subsystem.CPU_HEAVY,
            "simsimd_similarity": Subsystem.CPU_HEAVY,
            "parse_html": Subsystem.CPU_HEAVY,
            "parse_pdf": Subsystem.CPU_HEAVY,
            "prf_expand": Subsystem.CPU_HEAVY,
            "compress_text": Subsystem.CPU_HEAVY,
            "extract_links": Subsystem.CPU_HEAVY,

            # I/O: fetch / crawl / archive / network probes
            "fetch_page": Subsystem.IO,
            "fetch_url": Subsystem.IO,
            "crawl_deep": Subsystem.IO,
            "crawl_surface": Subsystem.IO,
            "archive_lookup": Subsystem.IO,
            "whois_probe": Subsystem.IO,
            "dns_probe": Subsystem.IO,
        }

    def get_subsystem(self, action_name: str) -> Subsystem:
        """
        Určí subsystem pro akci.

        Default: IO (pro neznámé akce)
        """
        # Check for partial match
        action_lower = action_name.lower()
        for route_name, subsystem in self._action_routes.items():
            if route_name in action_lower or action_lower in route_name:
                return subsystem

        # Default to IO for unknown actions
        return Subsystem.IO

    async def acquire(self, subsystem: Subsystem) -> asyncio.Semaphore:
        """
        Acquire semaphore pro subsystem.

        Returns:
            Semaphore pro context manager.
        """
        sem = self._semaphores.get(subsystem, self._semaphores[Subsystem.IO])
        return sem

    def acquire_sync(self, subsystem: Subsystem) -> asyncio.Semaphore:
        """
        Synchronní verze acquire (pro použití v sync kontextech).
        """
        return self._semaphores.get(subsystem, self._semaphores[Subsystem.IO])

    async def run_in_subsystem(
        self,
        subsystem: Subsystem,
        coro
    ):
        """
        Spustí coroutine v daném subsystemu s proper routing.

        Args:
            subsystem: subsystem pro routing
            coro: coroutine k spuštění
        """
        sem = await self.acquire(subsystem)
        async with sem:
            return await coro

    def get_status(self) -> dict:
        """Status semaforů."""
        return {
            subsystem.name: {
                "limit": self._limits[subsystem],
                "available": self._semaphores[subsystem]._value,
            }
            for subsystem in Subsystem
        }

    # Sprint 82B: Fairness helpers
    def is_winner_allowed_for_expensive(self, lane_role: str) -> bool:
        """
        Sprint 82B: Check if lane role is allowed for expensive path.

        Winner lane has priority for expensive path.
        Falsification lane gets minimum cheap contradiction chance.
        """
        return lane_role == "winner_deepening"

    def get_cheap_contradiction_lanes(self) -> set:
        """
        Sprint 82B: Get lanes allowed for cheap contradiction checking.

        All lanes can run cheap work (CPU-first).
        """
        # All lanes can run cheap actions - this is the fairness rule
        return {"expansion", "falsification", "winner_deepening"}

    def apply_budget_throttle(self, throttle_factor: float) -> None:
        """
        Sprint 82B: Apply budget throttle based on memory pressure.

        Called when memory pressure is WARN or CRITICAL.
        Reduces available slots proportionally.
        """
        if throttle_factor >= 1.0:
            return  # No throttle

        # Scale down limits proportionally
        for subsystem in self._semaphores:
            if isinstance(self._limits.get(subsystem), int):
                original = self._limits[subsystem]
                self._limits[subsystem] = max(1, int(original * throttle_factor))
                # Recreate semaphore with new limit
                self._semaphores[subsystem] = asyncio.Semaphore(self._limits[subsystem])

        logger.info(f"[SUBSYSTEM] Budget throttled to {throttle_factor * 100}%")
