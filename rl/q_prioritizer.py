"""
Q-learning action prioritizer pro OSINT OODA loop.
State: (query_type, memory_pressure_bin, actions_executed, findings_count_bin)
Action: výběr next action name z dostupných akcí
Reward: +10 za accepted_finding, +3 za nový entitu v grafu, -1 za timeout, -5 za OOM

M1 safe: čistý Python numpy (ne MLX — Q-table je malá, CPU je rychlejší)
Persistent: ukládá Q-table do JSON souboru pro cross-session learning
"""
from __future__ import annotations
import json
import logging
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Q-table persistence path
Q_TABLE_PATH = Path("~/.hledac/q_table.json").expanduser()

@dataclass
class RLState:
    """Kompaktní stavový prostor pro Q-learning."""
    query_type: str          # "technical", "person", "entity", "infrastructure"
    memory_pressure: int     # 0=low(<40%), 1=medium(40-70%), 2=high(>70%)
    actions_executed: int    # binned: 0,1,2,3,5,10,20+
    findings_so_far: int     # binned: 0,1,2,5,10,20+

    def to_key(self) -> str:
        return f"{self.query_type}|{self.memory_pressure}|{self._bin_actions()}|{self._bin_findings()}"

    def _bin_actions(self) -> int:
        for threshold in [0, 1, 2, 5, 10, 20]:
            if self.actions_executed <= threshold:
                return threshold
        return 20

    def _bin_findings(self) -> int:
        for threshold in [0, 1, 2, 5, 10, 20]:
            if self.findings_so_far <= threshold:
                return threshold
        return 20


class QLearningPrioritizer:
    """
    Epsilon-greedy Q-learning pro výběr OSINT akce.
    Interface: select_action(state, available_actions, scores) -> Optional[str]
    """

    def __init__(
        self,
        epsilon: float = 0.15,      # exploration rate
        alpha: float = 0.1,         # learning rate
        gamma: float = 0.9,         # discount factor
        epsilon_decay: float = 0.995,  # epsilon decay per episode
        min_epsilon: float = 0.05,
    ):
        self._epsilon = epsilon
        self._alpha = alpha
        self._gamma = gamma
        self._epsilon_decay = epsilon_decay
        self._min_epsilon = min_epsilon
        self._q_table: dict[str, dict[str, float]] = {}
        self._last_state: Optional[str] = None
        self._last_action: Optional[str] = None
        self._episode_count: int = 0
        self._load_q_table()

    def _load_q_table(self) -> None:
        """Načti Q-table z disku (persistent learning across sessions)."""
        try:
            if Q_TABLE_PATH.exists():
                with open(Q_TABLE_PATH) as f:
                    data = json.load(f)
                    self._q_table = data.get("q_table", {})
                    self._epsilon = data.get("epsilon", self._epsilon)
                    self._episode_count = data.get("episodes", 0)
                    logger.debug(f"RL: Načtena Q-table ({len(self._q_table)} stavů, eps={self._epsilon:.3f})")
        except Exception as e:
            logger.debug(f"RL: Q-table nenalezena, začínám od nuly: {e}")

    def save_q_table(self) -> None:
        """Ulož Q-table na disk."""
        try:
            Q_TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(Q_TABLE_PATH, "w") as f:
                json.dump({
                    "q_table": self._q_table,
                    "epsilon": self._epsilon,
                    "episodes": self._episode_count,
                    "updated": time.time(),
                }, f, indent=2)
        except Exception as e:
            logger.debug(f"RL: Nelze uložit Q-table: {e}")

    def select_action(
        self,
        state: RLState,
        available_actions: list[str],
        heuristic_scores: dict[str, float],
    ) -> Optional[str]:
        """
        Epsilon-greedy action selection.
        - Epsilon% času: exploration (random z top-3 heuristic)
        - (1-Epsilon)% času: exploitation (best Q-value)
        """
        if not available_actions:
            return None

        state_key = state.to_key()

        # Inicializuj Q-values pro nové state-action páry
        if state_key not in self._q_table:
            self._q_table[state_key] = {}
        for action in available_actions:
            if action not in self._q_table[state_key]:
                # Inicializuj Q-value z heuristic score (warm start)
                self._q_table[state_key][action] = heuristic_scores.get(action, 0.0)

        # Epsilon-greedy selection
        if random.random() < self._epsilon:
            # Exploration: vyber z top-3 heuristic akcí (ne čistě random — efektivnější)
            sorted_by_heuristic = sorted(available_actions, key=lambda a: heuristic_scores.get(a, 0), reverse=True)
            selected = random.choice(sorted_by_heuristic[:3])
        else:
            # Exploitation: best Q-value — find action with highest Q
            best_action = None
            best_q = -9999.0
            for action in available_actions:
                q = self._q_table[state_key].get(action, 0.0)
                if q > best_q:
                    best_q = q
                    best_action = action
            selected = best_action

        self._last_state = state_key
        self._last_action = selected
        return selected

    def update(self, reward: float, next_state: RLState, next_available_actions: list[str]) -> None:
        """
        Q-table update po provedené akci.
        Volej po každém _execute_action() v orchestrátoru.
        reward: +10 finding, +3 new_entity, -1 timeout, -5 OOM
        """
        if self._last_state is None or self._last_action is None:
            return

        next_state_key = next_state.to_key()

        # Max Q(s', a') pro Bellman equation
        next_max_q = 0.0
        if next_state_key in self._q_table and next_available_actions:
            next_q_values_list = [self._q_table[next_state_key].get(a, 0.0) for a in next_available_actions]
            next_max_q = max(next_q_values_list) if next_q_values_list else 0.0

        # Bellman update: Q(s,a) ← Q(s,a) + α[r + γ·max Q(s',a') - Q(s,a)]
        current_q = self._q_table[self._last_state].get(self._last_action, 0.0)
        td_target = reward + self._gamma * next_max_q
        td_error = td_target - current_q
        new_q = current_q + self._alpha * td_error

        self._q_table[self._last_state][self._last_action] = new_q

        # Epsilon decay
        self._epsilon = max(self._min_epsilon, self._epsilon * self._epsilon_decay)
        self._episode_count += 1

        # Auto-save každých 100 updates
        if self._episode_count % 100 == 0:
            self.save_q_table()

    def get_stats(self) -> dict:
        """Diagnostika stavu RL agenta."""
        return {
            "epsilon": round(self._epsilon, 4),
            "episodes": self._episode_count,
            "states_explored": len(self._q_table),
            "total_state_action_pairs": sum(len(v) for v in self._q_table.values()),
        }


def classify_query_type(query: str) -> str:
    """Heuristická klasifikace query pro RL state."""
    query_lower = query.lower()
    if any(w in query_lower for w in ("ip", "asn", "bgp", "cert", "domain", "infrastructure", "c2", "malware")):
        return "infrastructure"
    elif any(w in query_lower for w in ("person", "name", "who", "profile", "social")):
        return "person"
    elif any(w in query_lower for w in ("apt", "group", "actor", "campaign", "threat")):
        return "entity"
    return "technical"
