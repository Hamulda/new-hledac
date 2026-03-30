"""
Advanced Research Coordinator - DEPRECATED
==========================================

This module is a compatibility wrapper around UniversalResearchCoordinator.
All functionality has been merged into research_coordinator.py.

For new code, use:
    from .research_coordinator import UniversalResearchCoordinator, ResearchDepth

Migration:
    Old: UniversalAdvancedResearchCoordinator
    New: UniversalResearchCoordinator(research_depth=ResearchDepth.DEEP)

Backward compatibility aliases are provided below.
"""

import warnings
from typing import Any, Dict, List, Optional

# Import from consolidated research coordinator
from .research_coordinator import (
    UniversalResearchCoordinator,
    ResearchDepth,
    ExcavationStrategy,
    ExcavationConfig,
    ResearchPaper,
    ResearchThread,
    MetaPattern,
    ResearchTheory,
    HierarchicalPlan,
)

# Issue deprecation warning
warnings.warn(
    "advanced_research_coordinator is deprecated. "
    "Use research_coordinator.UniversalResearchCoordinator with ResearchDepth.DEEP instead.",
    DeprecationWarning,
    stacklevel=2
)


class UniversalAdvancedResearchCoordinator(UniversalResearchCoordinator):
    """
    Backward compatibility wrapper for UniversalResearchCoordinator.

    Automatically sets research_depth to DEEP mode.

    DEPRECATED: Use UniversalResearchCoordinator(research_depth=ResearchDepth.DEEP) instead.
    """

    def __init__(self, max_concurrent: int = 3):
        """Initialize with DEEP research mode for backward compatibility."""
        super().__init__(
            max_concurrent=max_concurrent,
            research_depth=ResearchDepth.DEEP
        )

        warnings.warn(
            "UniversalAdvancedResearchCoordinator is deprecated. "
            "Use UniversalResearchCoordinator(research_depth=ResearchDepth.DEEP) instead.",
            DeprecationWarning,
            stacklevel=2
        )

    # All methods inherited from UniversalResearchCoordinator
    # Deep research methods: excavate(), meta_synthesize(), create_hierarchical_plan()


# Convenience function for backward compatibility
async def scan_deep_web(target_url: str, options: Optional[Dict[str, Any]] = None) -> List[Any]:
    """
    Backward compatibility wrapper for deep web scanning.

    DEPRECATED: Use DeepProbeScanner directly from research module.
    """
    warnings.warn(
        "scan_deep_web is deprecated. Use DeepProbeScanner directly.",
        DeprecationWarning,
        stacklevel=2
    )

    options = options or {}
    # Return empty list as placeholder - DeepProbeScanner moved to deep_research module
    return []


# Export all symbols for backward compatibility
__all__ = [
    # Deprecated class
    "UniversalAdvancedResearchCoordinator",
    # Enums and dataclasses (forwarded from research_coordinator)
    "ResearchDepth",
    "ExcavationStrategy",
    "ExcavationConfig",
    "ResearchPaper",
    "ResearchThread",
    "MetaPattern",
    "ResearchTheory",
    "HierarchicalPlan",
    # Deprecated function
    "scan_deep_web",
]
