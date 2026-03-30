# hledac/universal/utils/action_result.py
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class ActionResult:
    """Unified result from any research action."""
    success: bool = False
    findings: List[Any] = field(default_factory=list)   # ResearchFinding objekty
    sources: List[Any] = field(default_factory=list)    # ResearchSource objekty
    hypotheses: List[Any] = field(default_factory=list) # Hypothesis objekty
    contradictions: List[Any] = field(default_factory=list) # Contradiction objekty
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
