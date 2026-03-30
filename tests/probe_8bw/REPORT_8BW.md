# SPRINT 8BW — PROBE: RL/QMIX WIRING GAP
**Datum:** 2026-03-24
**Typ:** READ-ONLY PROBE
**Status:** COMPLETE

---

## 1. RL MODULE INVENTORY

### Soubory v `rl/`

| Soubor | Ucel | Klicove tridy |
|--------|------|---------------|
| `rl/actions.py` | Akcni konstanty | `ACTION_CONTINUE=0`, `ACTION_FETCH_MORE=1`, `ACTION_DEEP_DIVE=2`, `ACTION_BRANCH=3`, `ACTION_YIELD=4` |
| `rl/qmix.py` | QMIX algorithm (MLX) | `QNetwork`, `QMixer`, `QMIXAgent`, `QMIXJointTrainer` |
| `rl/marl_coordinator.py` | Koordinace RL | `MARLCoordinator` — spravuje agenty, replay buffer, trénink |
| `rl/replay_buffer.py` | Pamet pro prechody | `MARLReplayBuffer` — numpy-backed, perzistentni |
| `rl/state_extractor.py` | Extrakce stavu | `StateExtractor` — 12-dim vektor z thread+global state |

### Architektura QMIX
```
QMIXAgent.act(state) → int (0-4)
  ↓
MARLCoordinator.act(agent_id, state) → int
  ↓
MARLCoordinator.push_transition(...) → replay buffer
  ↓
MARLCoordinator.start_training() → _training_loop (kazdych 60s)
  ↓
QMIXJointTrainer.update(batch) → gradient descent
```

---

## 2. AO ACTION SELECTION MECHANISM

### Primarni metoda: `autonomous_orchestrator._decide_next_action(state)` (radka 9427)

**Vstup:** `state: Dict[str, Any]` — obsahuje:
- `query`, `phase`, `recent_novelty`, `contradiction_relevant`
- `propagation_hints`, `sources_count`, `new_domain_detected`
- `thermal_state`, `on_battery`

**Mechanismus:**
1. Iterace pres `_action_registry` (name → (handler, scorer))
2. Pro kazdou akci: vola `scorer(state)` → (score, params)
3. Aplikuje: thermal/battery penalty, EMA bias, exploration bonus, Thompson Sampling bias
4. Vyber nejlepsiho kandidata

**Vystup:** `Tuple[str, Dict[str, Any]]` — (action_name, params)

**Schranka pro RL integraci:**
- AO **nema** prime volani `MARLCoordinator`
- RL moduly existuji, ale **nejsou propojeny** s `_decide_next_action`

---

## 3. INTERFACE SPECIFICATION

### RL Input (state vector)
```python
StateExtractor.extract(thread_state, global_state) → mx.array  # shape (12,)
# Features: entity_centrality, novelty, contradiction, source_type, depth,
#           queue_size, memory_pressure, graph_entropy, avg_reward,
#           num_pending_tasks, time_since_last_finding, resource_concurrency
```

### RL Output (action)
```python
QMIXAgent.act(state, epsilon=0.1) → int  # 0-4 dle rl/actions.py
MARLCoordinator.act(agent_id, state) → int  # stejny API
```

### AO → RL Gap
| AO koncept | RL koncept | Rozdil |
|------------|------------|--------|
| `action_name: str` ("surface_search") | `action_index: int` (0-4) | **Jina reprezentace** |
| `candidates: List[(score, name, params)]` | `state: mx.array` (12-dim) | **Jina struktura** |
| `scorer(state) → (score, params)` | `QMIXAgent.act(state) → action` | **Jiny mechanismus** |

---

## 4. WIRING EFFORT ESTIMATE

### Minimalni zmeny pro RL aktivaci:

| Krok | Soubor | Zmena | LOC |
|------|--------|-------|-----|
| 1 | `autonomous_orchestrator.py` | Pridat `_marl_coord: MARLCoordinator` do `__init__` | ~5 |
| 2 | `autonomous_orchestrator.py` | Mapovat `action_name → action_index` (5 akci) | ~15 |
| 3 | `autonomous_orchestrator.py` | V `_decide_next_action`: volani `marl_coord.act()` misto scorers | ~20 |
| 4 | `autonomous_orchestrator.py` | Push transitions do replay buffer po akci | ~10 |
| 5 | Test | Otestovat RL rezim | ~50 |

**CELKEM: ~100 LOC**

### Hlavni komplikace:
1. **Akcni prostor mismatch:** AO ma ~20 akci (registry), RL ma pouze 5 akci
2. **State representation:** AO predava Dict, RL ocekava 12-dim vector
3. **Reward function:** AO nema explicitni reward signal jako RL
4. **Warmup:** RL potrebuje 1000+ transitions pred treningem

---

## 5. RISK ASSESSMENT

| Aspekt | Riziko | Mitigation |
|--------|--------|------------|
| Akcni prostor mismatch | **Vysoke** | Mapovat AO akce → top-5 RL akci |
| Memory overhead | **Stredni** | MARLReplayBuffer ~2MB numpy |
| Training latency | **Nizke** | 60s interval, async |
| Breaking existing TS/UCB1 | **Vysoke** | RL jako dalsi "scorer" spolu s existujicimi |

---

## 6. RECOMMENDATION

### WIRE LATER

**Duvody:**
1. RL moduly jsou **kompletni a testovane** (Sprint 58A: 16 testu)
2. AO action selection je **slozity hybrid** (Thompson Sampling + UCB1 + EMA + propagation hints)
3. Mismatch mezi 20 AO akcemi a 5 RL akcemi vyzaduje peclive mapovani
4. Existujici TS/UCB1 mechanismy funguji dobre — RL by bylo "sidegrade", ne upgrade

**Pokud ano:** Zacet s jednoduchym A/B mode: 10% RL vs 90% existujici, bez treningu (fallback=True)

**Pokud ne:** Pokracovat s optimalizacemi stavajiciho TS/UCB1 systemu

---

## PRILOHA: Klicove import paths
```
hledac.universal.rl.actions         # ACTION_FETCH_MORE, ACTION_DIM
hledac.universal.rl.marl_coordinator  # MARLCoordinator
hledac.universal.rl.qmix            # QMIXAgent, QMixer
hledac.universal.rl.state_extractor # StateExtractor
hledac.universal.rl.replay_buffer   # MARLReplayBuffer
```
