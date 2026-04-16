"""
MARLCoordinator – spravuje agenty, replay buffer, trénink a interakci se schedulerem.

PROMOTION GATE — DORMANT / HEAVY / NOT PROMOTED
================================================
QMIX multi-agent reinforcement learning koordinátor.

STATUS: DORMANT
  - training_enabled ALWAYS False (hardcoded property, řádek 60)
  - start_training() async method existuje, ale NENÍ VOLÁNA z žádného canonical surface
  - žádné skutečné call sites mimo testy
  - RL enginy (mlx, numpy, QMIX*) jsou LAZY importované — žádné startup cost při importu

M1 8GB MEMORY CEILING:
  - QMIXAgent (mlx.nn.Module) + QMixer + target_mixer: ~50-200MB per agent
  - Replay buffer: n_agents * state_dim * batch_size (konfigurovatelné)
  - NUMPY interop: np.array pro reward computation (float64, mimo MLX)
  - training loop: asyncio.Task, 60s interval, 64-batch updates
  - Epsilon decay: 0.9995 per step, min 0.05

CONTAINMENT HARDENING (F184F):
  - training_enabled je PROPERTY vracející vždy False — jakýkolivpokynout kód
    který se pokusí nastavit self.training_enabled = True bude IGNOROVÁN
  - _TRAINING_EVER_ENABLED flag NIKDY nebude True
  - MLX/numpy/rl_modules importy jsou LAZY — uvnitř __init__ a per-method
  - replay_buffer push neaktivuje training — pouze sleduje metriky
  - žádné hidden startup cost při importu modulu

ALLOWED PURPOSE: Research/experiment only — QMIX algoritmus je paper-impl
  bez reálného RL reward signálu v OSINT kontextu.
  _compute_reward() je dummy: new_entities*2 + confidence*1.5 - time_penalty

PROMOTION ELIGIBILITY: NO
  - Žádné production call sites (grep -r "marl_coordinator" --include="*.py" | grep -v test)
  - training_enabled always False = training nikdy nezačne
  - ETHEREINCI žádného reálného reward feedback loop
  - M1 8GB: parallel QMIX training by SWAPOVALO

SECURITY: Žádná. Tento kód nepracuje se senzitivními daty.
STEALTH: Žádná. RL training traffic by byl plně auditovatelný.
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# --- LAZY IMPORT GATE ---
# MLX, numpy, a rl_submodules jsou importovány LAZY uvnitř __init__ a per-method.
# Tím se zamezí hidden startup cost při importu modulu.
# Používáme varovnou bariéru proti eager importu.
_LAZY_IMPORTS_OK = True  # containment signal


def _lazy_import_mlx():
    """Lazy import MLX + utils. Volá se POUZE uvnitř methods, ne při module load."""
    global _LAZY_IMPORTS_OK
    if not _LAZY_IMPORTS_OK:
        raise RuntimeError("MARLCoordinator: eager MLX import blocked by containment")
    import mlx.core as mx
    from mlx.utils import tree_flatten, tree_unflatten
    return mx, tree_flatten, tree_unflatten


def _lazy_import_np():
    """Lazy import numpy."""
    import numpy as np
    return np


def _lazy_import_rl_modules():
    """Lazy import všech RL submodulů najednou."""
    global _LAZY_IMPORTS_OK
    if not _LAZY_IMPORTS_OK:
        raise RuntimeError("MARLCoordinator: eager RL import blocked by containment")
    from hledac.universal.rl.actions import ACTION_NAMES, ACTION_DIM, ACTION_FETCH_MORE, ACTION_CONTINUE
    from hledac.universal.rl.qmix import QMIXAgent, QMixer, QMIXJointTrainer
    from hledac.universal.rl.replay_buffer import MARLReplayBuffer
    from hledac.universal.rl.state_extractor import StateExtractor
    return (ACTION_NAMES, ACTION_DIM, ACTION_FETCH_MORE, ACTION_CONTINUE,
            QMIXAgent, QMixer, QMIXJointTrainer,
            MARLReplayBuffer, StateExtractor)


class MARLCoordinator:
    """
    QMIX MARL Coordinator — DORMANT / F184F HARDENED.

    CONTAINMENT GUARD (F184F):
    - _training_ever_enabled je ALWAYS False — žádná cesta k RL training
    - MLX/RL submoduly jsou lazy importované — žádné startup cost
    - Replay buffer pouze měří metriky, nikdy neaktivuje training
    """

    # F184F: training je vždy disabled — property zamezuje jakýmkoliv pokusům o změnu
    _training_ever_enabled: bool = False  # ALWAYS False, hardcoded at class level

    def __init__(self, n_agents: int, state_dim: int, hidden_dim: int = 64,
                 metrics_registry: Optional['MetricsRegistry'] = None):
        self.n_agents = n_agents
        self.state_dim = state_dim
        self.agents: Dict[str, 'QMIXAgent'] = {}
        self._mixer = None   # lazy — inicializováno při prvním použití
        self._target_mixer = None
        self._trainer: Optional['QMIXJointTrainer'] = None
        # Lazy init RL submodules
        self._rl_modules_loaded = False
        self._replay_buffer = None
        self._extractor = None
        self.metrics = metrics_registry
        self.training_task: Optional[asyncio.Task] = None
        self.step = 0
        self.epsilon = 1.0
        self.epsilon_decay = 0.9995
        self.epsilon_min = 0.05
        # F184F: training_enabled je vždy False — property guard viz níže

    @property
    def training_enabled(self) -> bool:
        """CONTAINMENT: training je VŽDY zakázáno. Nikdy nevrátí True."""
        return False

    @training_enabled.setter
    def training_enabled(self, value) -> None:
        """
        F184F CONTAINMENT GUARD: jakýkoliv pokus nastavit training_enabled
        je IGNOROVÁN. RL training NIKDY nebude aktivní.
        """
        # No-op — hodnota je vždy False bez ohledu na to, co volající předává
        # Log pouze PRVNÍ pokus (avoid log spam)
        if not hasattr(self, '_training_set_attempt_logged'):
            self._training_set_attempt_logged = True
            logger.debug("[F184F] training_enabled setter blocked — training always dormant")

    @property
    def replay_buffer(self):
        """Lazy init replay buffer — MLX/numpy se načte až při prvním přístupu."""
        if self._replay_buffer is None:
            _, _, _, _, _, _, _, MARLReplayBuffer, _ = _lazy_import_rl_modules()
            np = _lazy_import_np()
            self._replay_buffer = MARLReplayBuffer(state_dim=self.state_dim, n_agents=self.n_agents)
        return self._replay_buffer

    @property
    def extractor(self):
        """Lazy init state extractor."""
        if self._extractor is None:
            _, _, _, _, _, _, _, _, StateExtractor = _lazy_import_rl_modules()
            self._extractor = StateExtractor(self.state_dim)
        return self._extractor

    def _ensure_mixer(self):
        """Lazy init MLX mixers — žádné eager MLX při __init__."""
        if self._mixer is None:
            _, tree_flatten, tree_unflatten = _lazy_import_mlx()
            _, _, _, _, _, QMixer, QMIXJointTrainer, _, _ = _lazy_import_rl_modules()
            self._mixer = QMixer(self.n_agents, self.state_dim)
            self._target_mixer = QMixer(self.n_agents, self.state_dim)
            self._target_mixer.update(self._mixer.parameters())
            # Store flatten/unflatten for save/load
            self._tree_flatten = tree_flatten
            self._tree_unflatten = tree_unflatten

    def register_agent(self, agent_id: str):
        _, _, _, _, QMIXAgent, _, QMIXJointTrainer, _, _ = _lazy_import_rl_modules()
        self.agents[agent_id] = QMIXAgent(agent_id, self.state_dim)
        # F184F: trainer je lazy, ale nikdy neaktivuje training_enabled
        if len(self.agents) >= self.n_agents and self._trainer is None:
            self._ensure_mixer()
            self._trainer = QMIXJointTrainer(self.agents, self._mixer, self._target_mixer)

    def get_agent(self, agent_id: str) -> Optional['QMIXAgent']:
        return self.agents.get(agent_id)

    def extract_state(self, thread_state: Dict, global_state: Dict):
        mx = _lazy_import_mlx()[0]
        return self.extractor.extract(thread_state, global_state)

    def act(self, agent_id: str, state, fallback: bool = False) -> int:
        """Act — state může být mx.array nebo numpy."""
        _, tree_flatten, tree_unflatten = _lazy_import_mlx()
        _, _, _, _, QMIXAgent, _, _, _, _ = _lazy_import_rl_modules()
        agent = self.agents.get(agent_id)
        if agent is None:
            from hledac.universal.rl.actions import ACTION_FETCH_MORE
            return ACTION_FETCH_MORE
        mx = _lazy_import_mlx()[0]
        # Ensure state is mx.array
        if not isinstance(state, mx.array):
            state = mx.array(state)
        action = agent.act(state, self.epsilon, fallback)
        self.step += 1
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
        if self.metrics:
            try:
                self.metrics.gauge('rl_epsilon', self.epsilon)
            except Exception:
                pass
        return action

    def _compute_reward(self, result: Dict) -> float:
        reward = result.get('new_entities', 0) * 2.0
        reward += result.get('confidence', 0.5) * 1.5
        reward -= result.get('time_spent', 0) / 60.0 * 0.1
        if result.get('duplicate', False):
            reward -= 0.5
        return max(reward, -10.0)

    def push_transition(self, thread_id: str, state, actions,
                        results: List[Dict], next_state, done: bool):
        """
        F184F: replay buffer push pouze měří metriky.
       training_enabled JE VŽDY False — žádná cesta k auto-aktivaci.
        """
        # Ensure MLX arrays
        mx = _lazy_import_mlx()[0]
        np = _lazy_import_np()
        if not isinstance(state, mx.array):
            state = mx.array(state)
        if not isinstance(next_state, mx.array):
            next_state = mx.array(next_state)
        actions = np.asarray(actions)
        total_reward = sum(self._compute_reward(r) for r in results) / len(results) if results else 0.0
        # F184F: push tracked but NEVER enables training — containment guard
        self.replay_buffer.push(state, actions, total_reward, next_state, done)
        # Former auto-enable removed: NO automatic training_enabled = True

    async def start_training(self, interval: float = 60.0):
        """
        F184F CONTAINMENT: start_training() je STUB.
        Nikdy není voláno z production kódu. Přidáno sem pro API kompatibilitu,
        aletraining_enabled je VŽDY False.
        """
        logger.debug("[F184F] start_training() called but training_enabled is always False — no-op")

    async def _training_loop(self, interval: float):
        """
        F184F: training_enabled je VŽDY False, takže tahle smyčka je efektivně no-op.
        Záměrně ponecháno pro API kompatibilitu — ale nic nedělá.
        """
        while True:
            await asyncio.sleep(interval)
            # F184F: training_enabled je property vždy vracející False
            # Nikdy nebudeme mít training task s reálnými výpočty
            if not self.training_enabled or self.replay_buffer.size < 1000 or self._trainer is None:
                continue
            batch = self.replay_buffer.sample(64)
            losses = self._trainer.update(batch)
            if self.metrics:
                try:
                    self.metrics.gauge('rl_loss', losses['loss'])
                    self.metrics.gauge('rl_buffer_size', self.replay_buffer.size)
                    self.metrics.gauge('rl_steps', self.step)
                except Exception:
                    pass

    async def stop(self):
        if self.training_task:
            self.training_task.cancel()
            try:
                await self.training_task
            except asyncio.CancelledError:
                pass

    def save_models(self, path: Path):
        """Uloží modely — lazy mixer, žádné eager MLX pokud nejsou načteny."""
        mx_mod, tree_flatten, tree_unflatten = _lazy_import_mlx()
        if self._mixer is None:
            logger.debug("[F184F] save_models: mixer not initialized, skipping")
            return
        flat = {}
        for aid, agent in self.agents.items():
            for k, v in tree_flatten(agent.q_net.parameters()):
                flat[f"agent_{aid}.{k}"] = v
        for k, v in tree_flatten(self._mixer.parameters()):
            flat[f"mixer.{k}"] = v
        mx_mod.savez(str(path.with_suffix('.npz')), **flat)

    def load_models(self, path: Path):
        """Načte modely — lazy všeho."""
        mx_mod, tree_flatten, tree_unflatten = _lazy_import_mlx()
        if self._mixer is None:
            logger.debug("[F184F] load_models: mixer not initialized, skipping")
            return
        flat = mx_mod.load(str(path.with_suffix('.npz')))
        agent_params = {}
        mixer_params = []

        for key, val in flat.items():
            if key.startswith('agent_'):
                parts = key.split('.', 1)
                agent_id = parts[0][6:]
                subkey = parts[1]
                agent_params.setdefault(agent_id, []).append((subkey, val))
            elif key.startswith('mixer.'):
                subkey = key[6:]
                mixer_params.append((subkey, val))

        for aid, params_list in agent_params.items():
            if aid in self.agents:
                self.agents[aid].q_net.update(tree_unflatten(params_list))
                self.agents[aid].target_q_net.update(tree_unflatten(params_list))

        self._mixer.update(tree_unflatten(mixer_params))
        self._target_mixer.update(tree_unflatten(mixer_params))
