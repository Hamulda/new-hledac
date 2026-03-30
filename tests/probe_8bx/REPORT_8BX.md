# SPRINT 8BX — MCTS CURRENT STATE AUDIT REPORT

**Datum:** 2026-03-24
**Probe workspace:** `tests/probe_8bx/`

---

## EXECUTIVE SUMMARY

**`planning/mcts_director.py` NEEXISTUJE.** Tento soubor nikdy nebyl vytvořen.
Místo něj existují dva samostatné systémy:

| Soubor | Klasa | Princip | MCTS? |
|--------|-------|---------|-------|
| `autonomy/planner.py` | `SerializedTreePlanner` | ToT + DFS serializace | ❌ Ne |
| `tot_integration.py` | `TotIntegrationLayer` | Complexity analyzer + ToT wrapper | ❌ Ne |
| `planning/htn_planner.py` | `HTNPlanner` | HTN + anytime beam search | ❌ Ne |

**Závěr:** Žádný skutečný MCTS (Monte Carlo Tree Search s UCB1, rollouts, backpropagation) není implementován.

---

## STEP 1 — CODE ANALYSIS

### A. `autonomy/planner.py` (694 LOC)

#### Classes
- `ResearchPlanner` — stateless plan generator (quick/standard/deep/extreme/autonomous)
- `TreeNodeStatus` (Enum)
- `Thought` (dataclass)
- `TreeNode` (dataclass)
- `PlannerState` (dataclass)
- `SerializedTreePlanner` — hlavní ToT implementace
- `create_tree_planner()` — factory

#### Key Methods
| Method | LOC | Parametry |
|--------|-----|-----------|
| `generate_robust_plan()` | ~50 | `goal`, `knowledge_layer` |
| `_dfs_search()` | ~50 | `goal`, `depth` |
| `_generate_alternatives()` | ~70 | `goal`, `depth` |
| `_evaluate_thought()` | ~35 | `thought`, `goal`, `depth` |
| `_fallback_thoughts()` | ~20 | `goal`, `depth` |
| `set_brain()` | ~5 | `hermes_engine` |
| `_serialize_state()` | ~20 | `goal`, `depth` |

#### Parameters
```python
max_depth: int = 5
max_branches: int = 3
max_evaluations: int = 15
use_disk_serialization: bool = False
hermes_engine: Optional[Any] = None
```

#### Algoritmus — NENÍ MCTS
`SerializedTreePlanner` používá **Depth-First Search**, ne MCTS:

```
DFS:
1. Generate 3 alternatives via Hermes-3
2. For each thought:
   a. Evaluate (LLM call) → promising/complete
   b. If promising & not complete → recurse DFS
   c. If failed → backtrack (pop from _current_plan)
3. Max 15 evaluations total
```

**Proč to není MCTS:**
- Žádné **UCB1** pro výběr child node
- Žádné **rollouts** (náhodné simulace)
- Žádné **backpropagation** (propagace reward zpět stromem)
- Strom není strom — je to lineární `_current_plan` s jedním aktuálním větví
- Chybí **exploitation vs exploration** tradeoff

---

### B. `planning/htn_planner.py` (170 LOC)

#### HTNPlanner Methods
| Method | LOC | Popis |
|--------|-----|-------|
| `register_task_type()` | 5 | Registruje typ + expander |
| `plan()` | ~120 | Hlavní async plan |
| `_estimate_cost()` | 5 | **VŽDY 1.0** |
| `_estimate_ram()` | 5 | **VŽDY 50.0** |
| `_estimate_network()` | 5 | **VŽDY 0.1** |
| `_estimate_value()` | 5 | **VŽDY 1.0** |

#### FAILURE MODE #1 — Dummy Estimation
```python
def _estimate_cost(self, task: Dict) -> float:
    return 1.0  # VŽDY konstanta!

def _estimate_ram(self, task: Dict) -> float:
    return 50.0  # VŽDY konstanta!

def _estimate_value(self, task: Dict) -> float:
    return 1.0  # VŽDY konstanta!
```

**Dopad:** Beam search nemá žádné užitečné heuristiky — všechny úkoly jsou rovnocenné.

#### FAILURE MODE #2 — Žádný Registry Wiring
`register_task_type()` existuje, ale **nikdo ji nikdy nevolá** z hlavního kódu. Testy ukazují:
```python
planner.register_task_type('fetch', dummy_expander, is_primitive=True)
```
V produkčním kódu `HTNPlanner` nemá žádné registrované task typy.

#### Integrace s `anytime_beam_search`
```python
plan = anytime_beam_search(
    initial_state=initial_state,
    goal_check=goal_check,
    expand=expand,
    heuristic=heuristic,
    governor=self.governor,
    time_budget=time_budget,
    ram_budget_mb=ram_budget_mb,
    net_budget_mb=net_budget_mb,
    beam_width=5
)
```

---

### C. `planning/search.py` (108 LOC)

#### anytime_beam_search Signature
```python
def anytime_beam_search(
    initial_state: Dict[str, Any],
    goal_check: Callable[[Dict], bool],
    expand: Callable[[Dict], List[Tuple[...]]],
    heuristic: Callable[[Dict], Tuple[float, float, float]],
    governor: ResourceGovernor,
    time_budget: float,
    ram_budget_mb: float,
    net_budget_mb: float,
    beam_width: int = 10
) -> Optional[List[Dict]]
```

#### Score Formula
```python
if expected_time > 0:
    new_node.score = expected_value / expected_time
else:
    new_node.score = expected_value
```

**Problém:** `expected_value` pochází z dummy `_estimate_value()` (vždy 1.0), takže score = 1.0 / time. Závisí pouze na čase.

---

### D. `planning/cost_model.py` (243 LOC)

#### AdaptiveCostModel
Plnohodnotná implementace Ridge + Mamba ML, **ALE:**

| Feature | Status |
|---------|--------|
| Online ridge regression | ✅ Funguje |
| Mamba/MLP residual model | ✅ Funguje (s fallback) |
| Feature building (8 task types) | ✅ |
| `_estimate_*` voláno z HTNPlanner | ❌ **Nikdy nevoláno** |

**FAILURE MODE #3:** `AdaptiveCostModel` je plně implementován, ale `HTNPlanner` má vlastní hardcoded `_estimate_*` metody, které ho nepoužívají.

---

### E. `planning/slm_decomposer.py` (143 LOC)

#### SLMDecomposer
```python
def __init__(self, governor, cache,
             model_name: str = "mlx-community/Qwen2.5-0.5B-4bit",
             max_parallel: int = 2):
```

| Feature | Status |
|---------|--------|
| Lazy model loading | ✅ |
| Parallel prompt variants | ✅ (až 3) |
| Cache s verzí modelu | ✅ |
| Rule-based fallback | ✅ |
| **Async executor pro generate()** | ❌ **Synchronní volání v executoru** |

**FAILURE MODE #4:** `generate()` z `mlx_lm` je synchroní, spouští se v `loop.run_in_executor()`. To je správně, ALE žádná konfrontace s MLX modelem při paralelním volání (pouze 1 model instance).

---

## STEP 2 — ACTION REGISTRY

**Žádný action registry neexistuje.**

- `HTNPlanner.register_task_type()` — definováno, ale nepoužito
- Žádné mapování akcí na OSINT moduly
- `_task_types` dict zůstává prázdný

Aktuální stav:
```python
planner = HTNPlanner(...)
# _task_types = {}  # vždy prázdné!
```

---

## STEP 3 — INTEGRATION WITH AUTONOMOUS_ORCHESTRATOR

### grep výsledky
```
autonomous_orchestrator.py    — řádky obsahující "planner", "htn", "tot", "mcts"
tot_integration.py            — lazy import TotOrchestrator
autonomy/planner.py           — create_tree_planner() factory
```

### TotIntegrationLayer
Pouze **analyzuje složitost** dotazu a rozhoduje, zda aktivovat ToT. Nepoužívá `SerializedTreePlanner` přímo — pouze lazy-loaduje `tot_orchestrator` z `tree_of_thoughts/`.

**Varování:** `tree_of_thoughts/tot_orchestrator.py` neexistuje (import selže, `TOT_AVAILABLE = False`).

---

## STEP 4 — DELTA ANALYSIS: WHAT TO REWRITE vs KEEP

### KEEP (good infrastructure)
| Komponenta | Důvod |
|------------|-------|
| `planning/search.py` — anytime beam search | Solidní implementace, správná score formula |
| `planning/cost_model.py` — AdaptiveCostModel | Ridge+Mamba funguje, jen není propojen |
| `planning/task_cache.py` — LMDB TaskCache | Bounded, async, verze modelu |
| `tot_integration.py` — complexity analysis | Czech+English, jazykové prahy, memory pressure |
| `autonomy/planner.py` — `ResearchPlanner` | 5 režimů (quick/standard/deep/extreme/autonomous) |

### REWRITE or REPLACE
| Komponenta | Důvod | Náhrada |
|------------|-------|---------|
| `SerializedTreePlanner` | Není MCTS, pouze DFS | Přepsat na skutečný MCTS s UCB1, rollouts, backprop |
| `HTNPlanner._estimate_*` | Hardcoded konstanty | Použít `AdaptiveCostModel.predict()` |
| `HTNPlanner` bez registry | Prázdný `_task_types` | Implementovat wiring akcí na OSINT moduly |
| `create_tree_planner()` factory | Nepoužívá se | Odstranit nebo integrovat |

### REWRITE: True MCTS Implementation

```python
# CHYBJ: Současný stav — DFS, ne MCTS
async def _dfs_search(self, goal, depth):
    thoughts = await _generate_alternatives(goal, depth)
    for thought in thoughts:
        evaluation = await _evaluate_thought(thought, goal, depth)
        if evaluation['promising']:
            deeper = await _dfs_search(goal, depth + 1)  # lineární

# SPRÁVNĚ: MCTS — UCB1 + rollouts + backprop
class MCTSNode:
    def __init__(self, state, parent=None, action=None):
        self.state = state
        self.parent = parent
        self.action = action
        self.children: Dict[Action, MCTSNode] = {}
        self.visits = 0
        self.value = 0.0  # cumulative reward

def ucb1(node: MCTSNode, exploration: float = 1.414) -> float:
    if node.visits == 0:
        return float('inf')
    exploit = node.value / node.visits
    explore = exploration * math.sqrt(math.log(node.parent.visits) / node.visits)
    return exploit + explore

async def mcts_search(self, root_state, budget):
    root = MCTSNode(root_state)
    while budget > 0:
        node = _select(root, ucb1)  # UCB1 selection
        if not node.children:  # Leaf → expand
            children = await _expand(node)
            node = random.choice(children)
        rollout_result = await _rollout(node.state)  # Random/heuristic simulation
        _backpropagate(node, rollout_result)  # Propagate reward
        budget -= 1
    return _best_child(root)
```

### REWRITE: HTNPlanner Integration

```python
# CURRENT: Dummy estimates
def _estimate_cost(self, task):
    return 1.0

# REWRITE: Use AdaptiveCostModel
def _estimate_cost(self, task: Dict) -> float:
    pred = self.cost_model.predict(
        task_type=task.get('type', 'other'),
        params=task.get('params', {}),
        system_state=self._get_system_state()
    )
    return pred[0]  # time estimate
```

---

## RECOMMENDATIONS SUMMARY

| Priorita | Akce | Soubor |
|----------|------|--------|
| 🔴 HIGH | Odstranit `SerializedTreePlanner` — není MCTS | `autonomy/planner.py` |
| 🔴 HIGH | Implementovat true MCTS (UCB1, rollouts, backprop) | `planning/mcts_director.py` (nový) |
| 🔴 HIGH | Propojit `HTNPlanner._estimate_*` s `AdaptiveCostModel` | `planning/htn_planner.py` |
| 🟡 MEDIUM | Implementovat action registry wiring | `planning/htn_planner.py` |
| 🟡 MEDIUM | Ověřit `tree_of_thoughts/tot_orchestrator.py` existenci | imports |
| 🟢 LOW | Odstranit nepoužitou `create_tree_planner()` factory | `autonomy/planner.py` |

---

## TEST INVENTORY

Sprint 60 testy (`tests/test_sprint60.py`) pokrývají:
- ✅ `TestResourceGovernor` — 6 testů
- ✅ `TestCostModel` — 7 testů
- ✅ `TestTaskCache` — 3 testy
- ✅ `TestSearch` — 2 testy (SearchNode, anytime_beam_search)
- ✅ `TestHTNPlanner` — 3 testy (init, register_task_type)
- ✅ `TestHypothesis` — 3 testy (DempsterShafer, EIGCalculator)
- ✅ `TestExplainer` — 4 testy
- ✅ `TestSLMDecomposer` — 3 testy

**Žádné testy pro MCTS (neexistuje).**

---

## FINAL VERDICT

> **`mcts_director.py` neexistuje. Existující "MCTS" je DFS with JSON serialization. True MCTS s UCB1 a rollouts je třeba napsat od nuly.**

Klíčové dilema: MCTS je vhodný pro **deterministické stavové prostory** (hry, puzzle). Pro OSINT orchestrátor s并行ními async akcemi je beam search s MLX cost modelem **praktičtější volba**.

Doporučení: **NESPIRATOVAT MCTS director, pokud není jasný stavový prostor akcí.**
