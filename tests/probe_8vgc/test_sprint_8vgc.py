"""
tests/probe_8vgc/test_sprint_8vgc.py
Sprint 8VG-C: ML Intelligence — GNN + RL + Adaptive Concurrency
"""
from __future__ import annotations
import asyncio
import json
import pytest

# ── Test 1: RL Q-learning ──────────────────────────────────────────────────
def test_rl_q_prioritizer_importable():
    """rl.q_prioritizer importuje bez chyby."""
    import importlib
    mod = importlib.import_module("rl.q_prioritizer")
    assert mod is not None

def test_rl_state_key_deterministic():
    """RLState.to_key() je deterministická pro stejné vstupy."""
    from rl.q_prioritizer import RLState
    state = RLState(
        query_type="infrastructure",
        memory_pressure=1,
        actions_executed=5,
        findings_so_far=3,
    )
    key1 = state.to_key()
    key2 = state.to_key()
    assert key1 == key2, "to_key() musí být deterministická"

def test_rl_select_action_returns_valid():
    """QLearningPrioritizer.select_action() vrátí akci ze available_actions."""
    from rl.q_prioritizer import QLearningPrioritizer, RLState

    prioritizer = QLearningPrioritizer(epsilon=0.0)  # pure exploitation pro test
    state = RLState("infrastructure", 0, 2, 1)
    actions = ["surface_search", "scan_ct", "bgp_passive_dns", "fingerprint_jarm"]
    scores = {"surface_search": 0.8, "scan_ct": 0.6, "bgp_passive_dns": 0.9, "fingerprint_jarm": 0.5}

    selected = prioritizer.select_action(state, actions, scores)
    assert selected in actions, f"Vybraná akce '{selected}' není v available_actions"

def test_rl_update_changes_q_values():
    """update() po akci mění Q-values v tabulce."""
    from rl.q_prioritizer import QLearningPrioritizer, RLState

    prioritizer = QLearningPrioritizer(epsilon=0.0, alpha=0.5)
    state = RLState("technical", 0, 0, 0)
    actions = ["surface_search", "scan_ct"]
    scores = {"surface_search": 0.5, "scan_ct": 0.5}

    # První výběr
    selected = prioritizer.select_action(state, actions, scores)
    state_key = state.to_key()
    q_before = prioritizer._q_table[state_key].get(selected, 0.0)

    # Update s pozitivní reward
    next_state = RLState("technical", 0, 1, 1)
    prioritizer.update(reward=10.0, next_state=next_state, next_available_actions=actions)

    q_after = prioritizer._q_table[state_key].get(selected, 0.0)
    assert q_after > q_before, f"Q-value se musí zvýšit po pozitivní reward: {q_before} → {q_after}"

def test_classify_query_type():
    """classify_query_type() správně klasifikuje různé query typy."""
    from rl.q_prioritizer import classify_query_type
    assert classify_query_type("APT28 malware C2 infrastructure") == "infrastructure"
    assert classify_query_type("who is the CEO of company") == "person"
    assert classify_query_type("APT threat actor campaign attribution") == "entity"

# ── Test 2: Adaptive concurrency ──────────────────────────────────────────────
def test_adaptive_concurrency_importable():
    """resource_allocator.get_adaptive_concurrency() existuje."""
    import resource_allocator
    assert hasattr(resource_allocator, "get_adaptive_concurrency"), \
        "get_adaptive_concurrency() chybí v resource_allocator"

def test_adaptive_concurrency_returns_valid_range():
    """get_adaptive_concurrency() vrací hodnotu v rozsahu 1-3."""
    import resource_allocator
    result = resource_allocator.get_adaptive_concurrency()
    assert 1 <= result <= 3, f"Concurrency {result} mimo povolený rozsah 1-3 (M1 limit)"

def test_adaptive_semaphore_importable():
    """AdaptiveSemaphore importuje a je použitelný jako async context manager."""
    from resource_allocator import AdaptiveSemaphore
    sem = AdaptiveSemaphore(initial_limit=2)
    assert sem.current_limit == 2

async def _use_semaphore(sem):
    async with sem:
        return True

def test_adaptive_semaphore_works_as_context_manager():
    """AdaptiveSemaphore funguje jako async context manager."""
    from resource_allocator import AdaptiveSemaphore
    sem = AdaptiveSemaphore(initial_limit=2)
    result = asyncio.get_event_loop().run_until_complete(_use_semaphore(sem))
    assert result is True

# ── Test 3: MLX clear_cache ────────────────────────────────────────────────
def test_clear_mlx_cache_function_exists():
    """clear_mlx_cache_if_needed() existuje v resource_allocator."""
    import resource_allocator
    assert hasattr(resource_allocator, "clear_mlx_cache_if_needed"), \
        "clear_mlx_cache_if_needed() chybí"

def test_clear_mlx_cache_does_not_crash():
    """clear_mlx_cache_if_needed() nepadá ani na non-Darwin nebo bez MLX."""
    import resource_allocator
    result = resource_allocator.clear_mlx_cache_if_needed(threshold_mb=0.0)  # force clear
    assert isinstance(result, bool), "Musí vrátit bool"
