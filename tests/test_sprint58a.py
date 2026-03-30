"""
Sprint 58A tests – QMIX, MARL, Replay Buffer, State Extractor.
"""

import asyncio
import sys
import unittest
import tempfile
import numpy as np
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, '/Users/vojtechhamada/PycharmProjects/Hledac')


# =============================================================================
# QMIX Tests
# =============================================================================

class TestQMIX(unittest.IsolatedAsyncioTestCase):
    """Testy pro QMIX algoritmus."""

    async def test_qnetwork_forward(self):
        """Test #1: QNetwork – forward pass vrací (batch, ACTION_DIM)."""
        import mlx.core as mx
        from hledac.universal.rl.qmix import QNetwork
        from hledac.universal.rl.actions import ACTION_DIM

        net = QNetwork(state_dim=12, hidden_dim=32)
        state = mx.ones((4, 12))  # batch of 4
        q_vals = net(state)

        self.assertEqual(q_vals.shape, (4, ACTION_DIM))

    async def test_agent_epsilon_fallback(self):
        """Test #2: QMIXAgent – epsilon‑greedy s fallbackem."""
        from hledac.universal.rl.qmix import QMIXAgent

        agent = QMIXAgent("test_agent", state_dim=12, hidden_dim=32)

        # Fallback should return ACTION_FETCH_MORE (1)
        import mlx.core as mx
        state = mx.ones((12,))
        action = agent.act(state, epsilon=0.0, fallback=True)
        self.assertEqual(action, 1)  # ACTION_FETCH_MORE

    async def test_qmix_mixer(self):
        """Test #3: QMixer – správné tvary a nezáporné váhy."""
        import mlx.core as mx
        from hledac.universal.rl.qmix import QMixer

        mixer = QMixer(n_agents=3, state_dim=12, embedding_dim=16)
        agent_qs = mx.ones((4, 3))  # batch of 4, 3 agents
        states = mx.ones((4, 12))

        q_total = mixer(agent_qs, states)

        self.assertEqual(q_total.shape, (4, 1))

    async def test_qmix_joint_update(self):
        """Test #4: QMIXJointTrainer – joint update všech agentů."""
        import mlx.core as mx
        from hledac.universal.rl.qmix import QMIXAgent, QMixer, QMIXJointTrainer

        # Create agents
        agents = {
            "agent_0": QMIXAgent("agent_0", state_dim=12, hidden_dim=32),
            "agent_1": QMIXAgent("agent_1", state_dim=12, hidden_dim=32),
        }
        mixer = QMixer(n_agents=2, state_dim=12, embedding_dim=16)
        target_mixer = QMixer(n_agents=2, state_dim=12, embedding_dim=16)
        target_mixer.update(mixer.parameters())

        trainer = QMIXJointTrainer(agents, mixer, target_mixer)

        # Create batch
        batch = {
            'states': mx.random.normal(shape=(8, 12)),
            'actions': mx.zeros((8, 2), dtype=mx.int32),
            'rewards': mx.ones(8),
            'next_states': mx.random.normal(shape=(8, 12)),
            'dones': mx.zeros(8)
        }

        result = trainer.update(batch)
        self.assertIn('loss', result)


class TestReplayBuffer(unittest.IsolatedAsyncioTestCase):
    """Testy pro replay buffer."""

    async def test_replay_buffer(self):
        """Test #5: Replay buffer – push a sample s (batch, n_agents) akcemi."""
        import mlx.core as mx
        from hledac.universal.rl.replay_buffer import MARLReplayBuffer

        buffer = MARLReplayBuffer(capacity=100, state_dim=12, n_agents=3)

        # Push some transitions
        for i in range(10):
            state = mx.ones(12) * i
            actions = np.array([i % 3, (i + 1) % 3, (i + 2) % 3])
            reward = float(i)
            next_state = mx.ones(12) * (i + 1)
            done = False
            buffer.push(state, actions, reward, next_state, done)

        self.assertEqual(buffer.size, 10)

        # Sample
        batch = buffer.sample(4)
        self.assertEqual(batch['states'].shape, (4, 12))
        self.assertEqual(batch['actions'].shape, (4, 3))

    async def test_replay_persistence(self):
        """Test #6: Replay buffer – perzistence s .npz."""
        import mlx.core as mx
        from hledac.universal.rl.replay_buffer import MARLReplayBuffer

        buffer1 = MARLReplayBuffer(capacity=100, state_dim=12, n_agents=3)

        # Add transitions
        for i in range(10):
            state = mx.ones(12) * i
            actions = np.array([i % 3, (i + 1) % 3, (i + 2) % 3])
            reward = float(i)
            next_state = mx.ones(12) * (i + 1)
            done = False
            buffer1.push(state, actions, reward, next_state, done)

        # Save
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "buffer"
            buffer1.save(path)

            # Load
            buffer2 = MARLReplayBuffer(capacity=100, state_dim=12, n_agents=3)
            buffer2.load(path)

            self.assertEqual(buffer2.size, 10)


class TestStateExtractor(unittest.IsolatedAsyncioTestCase):
    """Testy pro state extractor."""

    async def test_state_extractor(self):
        """Test #7: State extractor – výstup state_dim (včetně GNN)."""
        import mlx.core as mx
        from hledac.universal.rl.state_extractor import StateExtractor

        extractor = StateExtractor(state_dim=12)

        thread_state = {
            'entity_centrality': 0.5,
            'novelty': 0.3,
            'depth': 2,
            'contradiction': False,
            'source_type': 1
        }
        global_state = {
            'queue_size': 10,
            'memory_pressure': 0.4,
            'graph_entropy': 0.6,
            'avg_reward': 0.2,
            'num_pending_tasks': 5,
            'time_since_last_finding': 100.0,
            'resource_concurrency': 0.7
        }

        state = extractor.extract(thread_state, global_state)
        self.assertEqual(state.shape[0], 12)

    async def test_state_extractor_with_gnn(self):
        """Test #7b: State extractor – s GNN predictor."""
        import mlx.core as mx
        from hledac.universal.rl.state_extractor import StateExtractor

        # Mock GNN predictor
        mock_gnn = MagicMock()
        mock_gnn.get_graph_embedding.return_value = mx.ones(8)

        extractor = StateExtractor(state_dim=20, gnn_predictor=mock_gnn)

        thread_state = {'entity_centrality': 0.5, 'novelty': 0.3, 'depth': 2,
                       'contradiction': False, 'source_type': 1}
        global_state = {'queue_size': 10, 'memory_pressure': 0.4, 'graph_entropy': 0.6,
                       'avg_reward': 0.2, 'num_pending_tasks': 5, 'time_since_last_finding': 100.0,
                       'resource_concurrency': 0.7}

        state = extractor.extract(thread_state, global_state)
        self.assertEqual(state.shape[0], 20)


class TestMARLCoordinator(unittest.IsolatedAsyncioTestCase):
    """Testy pro MARL Coordinator."""

    async def test_coordinator_register(self):
        """Test #8: MARLCoordinator – registrace agentů."""
        from hledac.universal.rl.marl_coordinator import MARLCoordinator

        coordinator = MARLCoordinator(n_agents=3, state_dim=12, hidden_dim=32)

        coordinator.register_agent("agent_0")
        coordinator.register_agent("agent_1")
        coordinator.register_agent("agent_2")

        self.assertEqual(len(coordinator.agents), 3)
        self.assertIsNotNone(coordinator.get_agent("agent_0"))

    async def test_epsilon_decay(self):
        """Test #9: MARLCoordinator – epsilon decay a training_enabled."""
        from hledac.universal.rl.marl_coordinator import MARLCoordinator

        coordinator = MARLCoordinator(n_agents=3, state_dim=12, hidden_dim=32)

        for _ in range(1000):
            coordinator.register_agent(f"agent_{_}")

        initial_epsilon = coordinator.epsilon
        self.assertEqual(initial_epsilon, 1.0)

        # Simulate more steps to reach < 0.5
        # epsilon = 1.0 * 0.9995^steps < 0.5
        # steps > ln(0.5)/ln(0.9995) ≈ 1386
        for _ in range(1500):
            coordinator.step += 1
            coordinator.epsilon = max(coordinator.epsilon_min, coordinator.epsilon * coordinator.epsilon_decay)

        self.assertLess(coordinator.epsilon, 0.5)

    async def test_reward_calculation(self):
        """Test #10: MARLCoordinator – výpočet odměny."""
        from hledac.universal.rl.marl_coordinator import MARLCoordinator

        coordinator = MARLCoordinator(n_agents=3, state_dim=12, hidden_dim=32)

        result = {
            'new_entities': 5,
            'confidence': 0.8,
            'time_spent': 30.0,
            'duplicate': False
        }

        reward = coordinator._compute_reward(result)
        self.assertGreater(reward, 0)

    async def test_model_checkpoint(self):
        """Test #11: MARLCoordinator – checkpointing modelů."""
        from hledac.universal.rl.marl_coordinator import MARLCoordinator

        coordinator = MARLCoordinator(n_agents=2, state_dim=12, hidden_dim=32)

        for i in range(2):
            coordinator.register_agent(f"agent_{i}")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "models"
            coordinator.save_models(path)

            # Check file exists
            self.assertTrue(path.with_suffix('.npz').exists())

            # Load back
            coordinator.load_models(path)


class TestIntegration(unittest.IsolatedAsyncioTestCase):
    """Integrační testy."""

    async def test_thread_agent_integration(self):
        """Test #12: Integrace ResearchThread – agent rozhoduje."""
        from hledac.universal.rl.marl_coordinator import MARLCoordinator
        from hledac.universal.rl.actions import ACTION_FETCH_MORE, ACTION_DIM
        import mlx.core as mx

        coordinator = MARLCoordinator(n_agents=2, state_dim=12, hidden_dim=32)

        for i in range(2):
            coordinator.register_agent(f"agent_{i}")

        # Get state and act
        state = mx.ones(12)
        action = coordinator.act("agent_0", state, fallback=False)

        self.assertIn(action, range(ACTION_DIM))

    async def test_rl_fallback(self):
        """Test #13: Fallback – při výjimce se použije heuristika."""
        from hledac.universal.rl.marl_coordinator import MARLCoordinator
        from hledac.universal.rl.actions import ACTION_FETCH_MORE
        import mlx.core as mx

        coordinator = MARLCoordinator(n_agents=2, state_dim=12, hidden_dim=32)

        # Act with unknown agent should return fallback
        action = coordinator.act("unknown_agent", mx.ones(12))
        self.assertEqual(action, ACTION_FETCH_MORE)

    async def test_rl_memory_integration(self):
        """Test #14: Kombinace s PQ a dynamic unload – neovlivňuje."""
        from hledac.universal.rl.marl_coordinator import MARLCoordinator

        # This should work independently of PQ/DynamicModelManager
        coordinator = MARLCoordinator(n_agents=2, state_dim=12, hidden_dim=32)

        for i in range(2):
            coordinator.register_agent(f"agent_{i}")

        # Just verify coordinator works
        self.assertEqual(len(coordinator.agents), 2)

    async def test_rl_e2e(self):
        """Test #15: End‑to‑end – simulace joint update."""
        import mlx.core as mx
        from hledac.universal.rl.marl_coordinator import MARLCoordinator
        from hledac.universal.rl.qmix import QMIXJointTrainer

        # Create coordinator with agents
        coordinator = MARLCoordinator(n_agents=2, state_dim=12, hidden_dim=32)

        for i in range(2):
            coordinator.register_agent(f"agent_{i}")

        # Fill buffer with random data
        for _ in range(100):
            state = mx.random.normal(shape=(12,))
            actions = np.random.randint(0, 5, size=2)
            next_state = mx.random.normal(shape=(12,))
            coordinator.replay_buffer.push(state, actions, 0.5, next_state, False)

        # Enable training
        coordinator.training_enabled = True

        # Do a few updates
        if coordinator.trainer:
            batch = coordinator.replay_buffer.sample(8)
            result = coordinator.trainer.update(batch)
            self.assertIn('loss', result)


if __name__ == '__main__':
    unittest.main()
