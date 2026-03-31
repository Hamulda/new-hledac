"""
loops/ooda_loop.py
Sprint 8VG-A: OODA Loop integration
Observe → Orient → Decide → Act
"""
from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class OODAState:
    """Stav OODA smyčky."""
    step: int = 0
    last_observation: Dict[str, Any] = field(default_factory=dict)
    last_decision: Optional[str] = None
    consecutive_failures: int = 0
    stagnation_count: int = 0
    session_start: float = field(default_factory=time.monotonic)


class OODALoop:
    """
    OODA (Observe-Orient-Decide-Act) loop pro autonomní orchestrátor.
    
    Použití:
        loop = OODALoop()
        await loop.observe(data)
        await loop.orient(context)
        decision = await loop.decide(available_actions)
        await loop.act(decision)
    """

    def __init__(self, max_steps: int = 20):
        self._state = OODAState()
        self._max_steps = max_steps
        self._execution_history: List[Dict[str, Any]] = []
        self._enabled = True

    async def observe(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Observe: Shromažďování dat z prostředí.
        """
        self._state.last_observation = data
        self._state.step += 1
        
        observation_summary = {
            "step": self._state.step,
            "data_points": len(data.get("findings", [])),
            "errors": data.get("errors", []),
            "new_entities": data.get("entities_discovered", 0),
        }
        
        logger.debug(f"OODA Observe step {self._state.step}: {observation_summary}")
        return observation_summary

    async def orient(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Orient: Zpracování a interpretace dat.
        """
        session_age = time.monotonic() - self._state.session_start
        
        orientation = {
            "session_age_s": session_age,
            "history_length": len(self._execution_history),
            "failure_rate": self._state.consecutive_failures / max(1, self._state.step),
            "context_keys": list(context.keys()),
        }
        
        logger.debug(f"OODA Orient: session_age={session_age:.1f}s, history={len(self._execution_history)}")
        return orientation

    async def decide(
        self,
        available_actions: List[str],
        scores: Optional[Dict[str, float]] = None,
        decision_engine: Optional[Any] = None,
    ) -> str:
        """
        Decide: Výběr akce.
        """
        if scores is None:
            scores = {a: 0.5 for a in available_actions}
        
        self._state.last_decision = None
        
        # Použij brain/decision_engine pokud je dostupný
        if decision_engine is not None and len(self._execution_history) >= 3:
            try:
                session_age = time.monotonic() - self._state.session_start
                use_brain = session_age > 300  # 5 minut
                
                if use_brain:
                    ctx = {
                        "step": self._state.step,
                        "query": "",
                        "actions": available_actions,
                        "scores": scores,
                        "history": self._execution_history[-10:],
                    }
                    decision = decision_engine.decide(ctx)
                    if decision and decision.action in available_actions:
                        self._state.last_decision = decision.action
                        logger.info(f"OODA Decide (brain): {decision.action} confidence={decision.confidence:.2f}")
                        return decision.action
            except Exception as e:
                logger.debug(f"Decision engine fallback: {e}")
        
        # Fallback: greedy selection
        if scores:
            best = max(scores, key=scores.get)
            self._state.last_decision = best
            logger.debug(f"OODA Decide (greedy): {best}")
            return best
        
        # Default: first action
        if available_actions:
            self._state.last_decision = available_actions[0]
            return available_actions[0]
        
        return "noop"

    async def act(self, action: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Act: Provedení akce a vyhodnocení výsledku.
        """
        act_result = {
            "action": action,
            "success": result.get("success", False),
            "findings_count": len(result.get("findings", [])),
            "step": self._state.step,
        }
        
        self._execution_history.append({
            "step": self._state.step,
            "action": action,
            "result": result,
            "timestamp": time.monotonic(),
        })
        
        # Track failures
        if not result.get("success", False):
            self._state.consecutive_failures += 1
        else:
            self._state.consecutive_failures = 0
        
        # Stagnation detection
        if len(self._execution_history) >= 5:
            recent = self._execution_history[-5:]
            if all(e["result"].get("findings_count", 0) == 0 for e in recent):
                self._state.stagnation_count += 1
        
        logger.debug(f"OODA Act: {action} success={act_result['success']}")
        return act_result

    def should_continue(self) -> bool:
        """
        Rozhodne, zda pokračovat ve smyčce.
        """
        step = self._state.step
        max_steps = self._max_steps
        
        # Hard limit
        if step >= max_steps:
            return False
        
        # Soft limit - dostatek dat
        if step >= max_steps * 0.8 and len(self._execution_history) >= 5:
            findings_total = sum(e["result"].get("findings_count", 0) for e in self._execution_history[-5:])
            if findings_total >= 5:
                return False
        
        # Stagnation detection
        if self._state.stagnation_count >= 3:
            return False
        
        return True

    @property
    def state(self) -> OODAState:
        return self._state

    @property
    def execution_history(self) -> List[Dict[str, Any]]:
        return self._execution_history

    def reset(self) -> None:
        """Reset OODA state for new session."""
        self._state = OODAState()
        self._execution_history.clear()
