"""
Autonomy komponenty pro UniversalResearchOrchestrator.

Obsahuje:
- AutonomousResearchEngine: Plně autonomní výzkum
- ResearchPlanner: Tree of Thoughts plánování
- AgentMetaOptimizer: Performance monitoring and parameter tuning
"""

from .research_engine import AutonomousResearchEngine
from .planner import ResearchPlanner

# Lazy loading for optional components
AGENT_META_OPTIMIZER_AVAILABLE = False
try:
    from .agent_meta_optimizer import (
        AgentMetaOptimizer,
        AgentPerformance,
        create_agent_meta_optimizer,
    )
    AGENT_META_OPTIMIZER_AVAILABLE = True
except ImportError:
    AgentMetaOptimizer = None  # type: ignore
    AgentPerformance = None  # type: ignore
    create_agent_meta_optimizer = None  # type: ignore

__all__ = [
    "AutonomousResearchEngine",
    "ResearchPlanner",
    "AGENT_META_OPTIMIZER_AVAILABLE",
]

if AGENT_META_OPTIMIZER_AVAILABLE:
    __all__.extend([
        "AgentMetaOptimizer",
        "AgentPerformance",
        "create_agent_meta_optimizer",
    ])
