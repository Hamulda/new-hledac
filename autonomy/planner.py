"""
ResearchPlanner - Tree of Thoughts plánování pro UniversalResearchOrchestrator

Implementuje MCTS-based (Monte Carlo Tree Search) plánování pro komplexní výzkum.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, List, Optional

from ..types import ResearchMode

logger = logging.getLogger(__name__)


class ResearchPlanner:
    """
    Plánovač výzkumu s Tree of Thoughts.
    
    Používá MCTS pro nalezení optimální cesty výzkumu.
    """
    
    def __init__(self):
        self._tree_planner = None
    
    async def initialize(self) -> None:
        """Inicializovat plánovač"""
        logger.info("Initializing ResearchPlanner...")
        
        try:
            # Use local SerializedTreePlanner instead of importing from supreme
            self._tree_planner = SerializedTreePlanner(
                max_depth=5,
                max_branches=3,
                max_evaluations=15,
            )
            logger.info("✓ ResearchPlanner initialized (ToT with DFS)")
        except Exception as e:
            logger.warning(f"Tree planner initialization failed: {e}")
    
    async def create_plan(self, query: str, mode: ResearchMode) -> Dict[str, Any]:
        """
        Vytvořit výzkumný plán.
        
        Args:
            query: Výzkumný dotaz
            mode: Režim výzkumu
            
        Returns:
            Plán výzkumu
        """
        # Základní plány podle režimu
        plans = {
            ResearchMode.QUICK: self._quick_plan(query),
            ResearchMode.STANDARD: self._standard_plan(query),
            ResearchMode.DEEP: self._deep_plan(query),
            ResearchMode.EXTREME: self._extreme_plan(query),
            ResearchMode.AUTONOMOUS: self._autonomous_plan(query),
        }
        
        return plans.get(mode, self._standard_plan(query))
    
    def _quick_plan(self, query: str) -> Dict[str, Any]:
        """Rychlý plán (5-10 min)"""
        return {
            "mode": "quick",
            "steps": [
                {"action": "search", "params": {"query": query}},
                {"action": "deep_read", "params": {"url": "{top_result}"}},
                {"action": "synthesize", "params": {}},
            ],
            "max_steps": 5,
        }
    
    def _standard_plan(self, query: str) -> Dict[str, Any]:
        """Standardní plán (20-30 min)"""
        return {
            "mode": "standard",
            "steps": [
                {"action": "search", "params": {"query": query}},
                {"action": "osint_discovery", "params": {"query": query}},
                {"action": "deep_read", "params": {"url": "{source1}"}},
                {"action": "deep_read", "params": {"url": "{source2}"}},
                {"action": "research_paper", "params": {"query": query}},
                {"action": "fact_check", "params": {"claims": "{extracted_claims}"}},
                {"action": "synthesize", "params": {}},
            ],
            "max_steps": 15,
        }
    
    def _deep_plan(self, query: str) -> Dict[str, Any]:
        """Hluboký plán (1-2 hod)"""
        return {
            "mode": "deep",
            "steps": [
                {"action": "search", "params": {"query": query}},
                {"action": "osint_discovery", "params": {"query": query}},
                {"action": "research_paper", "params": {"query": query}},
                {"action": "deep_research", "params": {"query": query, "depth": 3}},
                {"action": "fact_check", "params": {"claims": "{extracted_claims}"}},
                {"action": "archive_fallback", "params": {"url": "{failed_urls}"}},
                {"action": "synthesize", "params": {}},
            ],
            "max_steps": 30,
        }
    
    def _extreme_plan(self, query: str) -> Dict[str, Any]:
        """Extrémní plán (3+ hod) - 'tajné rohy internetu'"""
        return {
            "mode": "extreme",
            "steps": [
                {"action": "search", "params": {"query": query}},
                {"action": "osint_discovery", "params": {"query": query}},
                {"action": "stealth_harvest", "params": {"url": "{protected_source}"}},
                {"action": "research_paper", "params": {"query": query}},
                {"action": "deep_research", "params": {"query": query, "depth": 5}},
                {"action": "fact_check", "params": {"claims": "{all_claims}"}},
                {"action": "archive_fallback", "params": {"url": "{all_urls}"}},
                {"action": "probe", "params": {"target": "{related_domains}"}},
                {"action": "synthesize", "params": {}},
            ],
            "max_steps": 50,
        }
    
    def _autonomous_plan(self, query: str) -> Dict[str, Any]:
        """Autonomní plán - nechá rozhodnout orchestrátor"""
        return {
            "mode": "autonomous",
            "steps": [],  # Dynamicky generováno
            "max_steps": 30,
            "autonomous": True,
        }


# =============================================================================
# SERIALIZED TREE PLANNER (from Supreme) - FIXED to use Hermes-3
# =============================================================================

"""
SerializedTreePlanner - Tree of Thoughts (ToT) with Serialized DFS
===================================================================
Memory-efficient planning system using Depth-First Search with state serialization.

Algorithm:
1. Generate 3 possible actions for a given goal
2. Serialize decision state to disk or memory
3. Evaluate the best action
4. If leads to goal -> continue
5. If leads to dead end -> load previous state and try different branch
"""

import asyncio
import json
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime


class TreeNodeStatus(Enum):
    """Status of a tree node"""
    PENDING = "pending"
    EVALUATING = "evaluating"
    SUCCESS = "success"
    FAILED = "failed"
    DEAD_END = "dead_end"


@dataclass
class Thought:
    """Represents a single thought/action in the ToT tree"""
    content: str
    reasoning: str
    score: float
    status: TreeNodeStatus = TreeNodeStatus.PENDING
    depth: int = 0
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Thought':
        return cls(**data)


@dataclass
class TreeNode:
    """Represents a node in the search tree"""
    thought: Thought
    children: List['TreeNode'] = None
    parent: Optional['TreeNode'] = None
    
    def __post_init__(self):
        if self.children is None:
            self.children = []
    
    def add_child(self, child: 'TreeNode') -> None:
        child.parent = self
        self.children.append(child)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'thought': self.thought.to_dict(),
            'children': [c.to_dict() for c in self.children],
            'parent_id': id(self.parent) if self.parent else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TreeNode':
        thought = Thought.from_dict(data['thought'])
        return cls(thought=thought)


@dataclass
class PlannerState:
    """Serializable state of the planner for DFS backtracking"""
    goal: str
    current_node: Optional[TreeNode] = None
    visited_states: List[str] = None
    max_depth: int = 5
    max_branches: int = 3
    max_evaluations: int = 15
    
    def __post_init__(self):
        if self.visited_states is None:
            self.visited_states = []
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PlannerState':
        return cls(**data)


class SerializedTreePlanner:
    """
    Tree of Thoughts planner with serialized DFS for memory efficiency.
    
    Key features:
    - Generates 3 alternative actions per node (ToT principle)
    - Serializes state to enable backtracking without memory bloat
    - Uses Hermes-3 LLM for evaluation (M1-optimized)
    - Depth-First Search with intelligent pruning
    """
    
    def __init__(
        self,
        max_depth: int = 5,
        max_branches: int = 3,
        max_evaluations: int = 15,
        use_disk_serialization: bool = False,
        cache_dir: Optional[str] = None,
        hermes_engine: Optional[Any] = None
    ):
        self.max_depth = max_depth
        self.max_branches = max_branches
        self.max_evaluations = max_evaluations
        self.use_disk_serialization = use_disk_serialization
        
        self._hermes_engine: Any = hermes_engine
        self._knowledge_layer: Any = None
        
        self._state_stack: List[PlannerState] = []
        self._evaluation_count = 0
        self._current_plan: List[Thought] = []
        
        if cache_dir is None:
            cache_dir = Path(tempfile.gettempdir()) / "hledac" / "planner"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("✓ SerializedTreePlanner initialized")
        logger.info(f"  Max depth: {max_depth}, Max branches: {max_branches}")
        logger.info(f"  Cache dir: {self.cache_dir}")
        if hermes_engine:
            logger.info("  ✓ Hermes-3 engine connected")
    
    def set_brain(self, hermes_engine: Any) -> None:
        """Set the Hermes-3 engine for evaluation."""
        self._hermes_engine = hermes_engine
        logger.info("✓ Hermes-3 connected to planner")
    
    async def generate_robust_plan(
        self,
        goal: str,
        knowledge_layer: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """Generate a robust action plan using ToT with DFS."""
        if self._hermes_engine is None:
            # Try to initialize Hermes if not set
            try:
                from ..brain.hermes3_engine import Hermes3Engine
                self._hermes_engine = Hermes3Engine()
                await self._hermes_engine.initialize()
                logger.info("✓ Auto-initialized Hermes-3 for planner")
            except Exception as e:
                logger.error(f"Failed to auto-initialize Hermes-3: {e}")
                raise RuntimeError("Hermes-3 engine not set and auto-initialization failed. Call set_brain() first.")
        
        if knowledge_layer:
            self._knowledge_layer = knowledge_layer
        
        logger.info(f"🌳 Starting ToT planning for: {goal}")
        logger.info(f"  Max depth: {self.max_depth}, Max evaluations: {self.max_evaluations}")
        
        self._evaluation_count = 0
        self._current_plan = []
        self._state_stack = []
        
        try:
            initial_state = PlannerState(goal=goal)
            self._state_stack.append(initial_state)
            
            best_actions = await self._dfs_search(goal, depth=0)
            
            if best_actions:
                logger.info(f"✓ ToT planning complete: {len(best_actions)} actions")
                return self._thoughts_to_actions(best_actions)
            else:
                logger.warning("No viable plan found, using fallback")
                return await self._fallback_plan(goal)
        
        except Exception as e:
            logger.error(f"ToT planning failed: {e}")
            import traceback
            traceback.print_exc()
            return await self._fallback_plan(goal)
    
    async def _dfs_search(self, goal: str, depth: int) -> List[Thought]:
        """Depth-First Search with state serialization."""
        if self._evaluation_count >= self.max_evaluations:
            logger.info("Max evaluations reached, returning best path so far")
            return self._current_plan
        
        if depth >= self.max_depth:
            logger.debug(f"Max depth ({self.max_depth}) reached")
            return self._current_plan
        
        logger.debug(f"DFS at depth {depth}, evaluations: {self._evaluation_count}")
        
        thoughts = await self._generate_alternatives(goal, depth)
        
        for thought in thoughts:
            self._evaluation_count += 1
            
            thought.status = TreeNodeStatus.EVALUATING
            logger.debug(f"  Evaluating: {thought.content[:50]}... (score: {thought.score:.2f})")
            
            if self._evaluation_count >= self.max_evaluations:
                break
            
            self._current_plan.append(thought)
            
            evaluation = await self._evaluate_thought(thought, goal, depth)
            
            if evaluation.get('promising', False):
                thought.status = TreeNodeStatus.SUCCESS
                
                if evaluation.get('complete', False):
                    logger.info(f"✓ Goal achieved at depth {depth}")
                    return self._current_plan
                
                deeper_path = await self._dfs_search(goal, depth + 1)
                
                if deeper_path and len(deeper_path) > len(self._current_plan) - 1:
                    return deeper_path
            else:
                thought.status = TreeNodeStatus.FAILED
                logger.debug(f"  Branch failed, backtracking...")
            
            self._current_plan.pop()
            
            if self.use_disk_serialization:
                await self._serialize_state(goal, depth)
        
        return self._current_plan if self._current_plan else []
    
    async def _generate_alternatives(self, goal: str, depth: int) -> List[Thought]:
        """Generate 3 alternative thoughts/actions using Hermes-3."""
        context = self._build_context(goal, depth)
        
        system_msg = """You are a Tree of Thoughts planner for autonomous research.
Generate diverse actions to achieve research goals."""
        
        prompt = f"""Generate {self.max_branches} alternative actions for this research goal:

Goal: {goal}
Current depth: {depth}/{self.max_depth}

{context}

Available action types:
- smart_search: Semantic search across sources
- deep_research: Multi-path deep investigation
- archive_mine: Search web archives (Wayback, etc.)
- academic_search: Search academic papers
- osint_gather: OSINT from public sources
- entity_extract: Extract entities from collected data
- temporal_analysis: Analyze temporal patterns
- synthesize: Compile final report

Generate exactly {self.max_branches} diverse actions with different strategies:
1. Direct approach - search the main topic
2. Alternative angle - explore related aspects
3. Backup plan - find supporting evidence

Return ONLY this JSON format:
[
  {{
    "action": "action_type",
    "payload": "specific query or target",
    "reasoning": "why this action is relevant"
  }}
]"""

        try:
            response = await self._hermes_engine.generate(
                prompt=prompt,
                system_msg=system_msg,
                temperature=0.7,
                max_tokens=1024
            )
            
            actions = self._parse_actions_from_response_text(response)
            
            thoughts = []
            for i, action in enumerate(actions):
                score = 1.0 - (i * 0.1)
                thought = Thought(
                    content=f"{action.get('action')}: {action.get('payload', '')}",
                    reasoning=action.get('reasoning', ''),
                    score=score,
                    depth=depth
                )
                thoughts.append(thought)
            
            logger.debug(f"Generated {len(thoughts)} alternatives at depth {depth}")
            
            # Fallback if no thoughts generated
            if not thoughts:
                thoughts = self._fallback_thoughts(goal, depth)
            
            return thoughts
        
        except Exception as e:
            logger.error(f"Failed to generate alternatives: {e}")
            return self._fallback_thoughts(goal, depth)
    
    def _fallback_thoughts(self, goal: str, depth: int) -> List[Thought]:
        """Generate fallback thoughts when LLM fails."""
        return [
            Thought(
                content=f"smart_search: {goal}",
                reasoning="Direct search for the main goal",
                score=1.0,
                depth=depth
            ),
            Thought(
                content=f"academic_search: {goal}",
                reasoning="Search academic sources for credible information",
                score=0.9,
                depth=depth
            ),
            Thought(
                content=f"archive_mine: {goal}",
                reasoning="Check historical archives for context",
                score=0.8,
                depth=depth
            )
        ]
    
    async def _evaluate_thought(self, thought: Thought, goal: str, depth: int) -> Dict[str, Any]:
        """Evaluate if a thought/action is promising using Hermes-3."""
        system_msg = "You evaluate research actions. Respond ONLY in JSON."
        
        prompt = f"""Evaluate this research action:

Goal: {goal}
Proposed action: {thought.content}
Reasoning: {thought.reasoning}
Depth: {depth}/{self.max_depth}

Return ONLY this JSON:
{{
  "promising": true/false,
  "complete": true/false,
  "confidence": 0.0-1.0,
  "explanation": "brief reasoning"
}}"""

        try:
            response = await self._hermes_engine.generate(
                prompt=prompt,
                system_msg=system_msg,
                temperature=0.3,
                max_tokens=256
            )
            
            return self._parse_evaluation_text(response)
        
        except Exception as e:
            logger.warning(f"Evaluation failed: {e}")
            return {'promising': True, 'complete': False, 'confidence': 0.5}
    
    def _parse_actions_from_response_text(self, response_text: str) -> List[Dict[str, Any]]:
        """Parse actions from Hermes-3 response text"""
        actions = []
        
        try:
            text = response_text.strip()
            
            # Remove markdown code blocks
            if text.startswith('```json'):
                text = text[7:]
            elif text.startswith('```'):
                text = text[3:]
            if text.endswith('```'):
                text = text[:-3]
            
            text = text.strip()
            
            # Find JSON array
            start_idx = text.find('[')
            end_idx = text.rfind(']')
            
            if start_idx >= 0 and end_idx > start_idx:
                json_str = text[start_idx:end_idx+1]
                parsed = json.loads(json_str)
                
                if isinstance(parsed, list):
                    actions = parsed
                elif isinstance(parsed, dict):
                    actions = [parsed]
        
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse actions JSON: {e}")
        except Exception as e:
            logger.warning(f"Error parsing response: {e}")
        
        return actions[:self.max_branches]
    
    def _parse_evaluation_text(self, response_text: str) -> Dict[str, Any]:
        """Parse evaluation from Hermes-3 response text"""
        default = {'promising': True, 'complete': False, 'confidence': 0.5}
        
        try:
            text = response_text.strip()
            
            # Remove markdown code blocks
            if text.startswith('```json'):
                text = text[7:]
            elif text.startswith('```'):
                text = text[3:]
            if text.endswith('```'):
                text = text[:-3]
            
            text = text.strip()
            
            # Find JSON object
            start_idx = text.find('{')
            end_idx = text.rfind('}')
            
            if start_idx >= 0 and end_idx > start_idx:
                json_str = text[start_idx:end_idx+1]
                parsed = json.loads(json_str)
                return {**default, **parsed}
        
        except json.JSONDecodeError:
            pass
        except Exception:
            pass
        
        return default
    
    async def _fallback_plan(self, goal: str) -> List[Dict[str, Any]]:
        """Fallback plan when ToT fails"""
        logger.info("Using fallback plan")
        
        return [
            {'action': 'smart_search', 'payload': goal},
            {'action': 'deep_research', 'payload': goal}
        ]
    
    def _thoughts_to_actions(self, thoughts: List[Thought]) -> List[Dict[str, Any]]:
        """Convert thoughts to action dictionaries"""
        actions = []
        for thought in thoughts:
            parts = thought.content.split(':', 1)
            if len(parts) == 2:
                action_type = parts[0].strip()
                payload = parts[1].strip()
                actions.append({'action': action_type, 'payload': payload})
            else:
                actions.append({'action': 'smart_search', 'payload': thought.content})
        return actions
    
    def _build_context(self, goal: str, depth: int) -> str:
        """Build context for alternative generation"""
        context_parts = []
        
        if self._knowledge_layer:
            try:
                results = self._knowledge_layer.ask(f"What do we know about: {goal}")
                if results:
                    context_parts.append("Relevant knowledge available from previous steps.")
            except Exception as e:
                logger.debug(f"Could not query knowledge layer: {e}")
        
        if self._current_plan:
            recent_thoughts = [t.content for t in self._current_plan[-2:]]
            context_parts.append(f"Recent thoughts: {', '.join(recent_thoughts)}")
        
        return "\n".join(context_parts) if context_parts else ""
    
    async def _serialize_state(self, goal: str, depth: int) -> None:
        """Serialize current state to disk"""
        if not self.use_disk_serialization:
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        state_file = self.cache_dir / f"state_{hash(goal) % 100000}_{timestamp}.json"
        
        state_data = {
            'goal': goal,
            'depth': depth,
            'evaluation_count': self._evaluation_count,
            'current_plan': [t.to_dict() for t in self._current_plan]
        }
        
        try:
            with open(state_file, 'w') as f:
                json.dump(state_data, f, indent=2)
            logger.debug(f"State serialized to {state_file}")
        except Exception as e:
            logger.warning(f"Failed to serialize state: {e}")
    
    async def _load_state(self, state_file: Path) -> Optional[PlannerState]:
        """Load serialized state from disk"""
        try:
            with open(state_file, 'r') as f:
                state_data = json.load(f)
            
            state = PlannerState.from_dict(state_data)
            state.current_node = None
            
            for thought_data in state_data.get('current_plan', []):
                thought = Thought.from_dict(thought_data)
                self._current_plan.append(thought)
            
            self._evaluation_count = state_data.get('evaluation_count', 0)
            
            logger.debug(f"State loaded from {state_file}")
            return state
        
        except Exception as e:
            logger.warning(f"Failed to load state: {e}")
            return None
    
    def cleanup(self) -> None:
        """Cleanup planner resources"""
        self._state_stack.clear()
        self._current_plan.clear()
        self._hermes_engine = None
        self._knowledge_layer = None
        
        logger.info("✓ SerializedTreePlanner cleaned up")


def create_tree_planner(
    max_depth: int = 5,
    max_branches: int = 3,
    max_evaluations: int = 15,
    use_disk_serialization: bool = False,
    cache_dir: Optional[str] = None,
    hermes_engine: Optional[Any] = None
) -> SerializedTreePlanner:
    """Factory function to create a SerializedTreePlanner."""
    return SerializedTreePlanner(
        max_depth=max_depth,
        max_branches=max_branches,
        max_evaluations=max_evaluations,
        use_disk_serialization=use_disk_serialization,
        cache_dir=cache_dir,
        hermes_engine=hermes_engine
    )
