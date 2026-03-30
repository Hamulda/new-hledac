# PLANNER_AUDIT_8E — Read-Only Planner Surface Audit

## 1. Scope a metodika

**Scope**: `hledac/universal/planning/` (read-only audit)
**Datum**: 2026-03-25
**Sprint**: 8E (PLANNER READ-ONLY AUDIT)
**Metodika**:
- Grep-based AO coupling scan (autonomous_orchestrator, AO, autonomous imports)
- Grep-based runtime/storage/model coupling scan
- Grep-based concurrency/async scan
- Grep-based HTN/planner primitives scan
- Code inspection all 6 planner modules
- NO production code edits

---

## 2. Ground-truth inventory `planning/`

```
planning/
├── __init__.py          (7 lines)   — public API exports
├── cost_model.py        (242 lines) — AdaptiveCostModel + MLX/Mamba
├── htn_planner.py       (169 lines) — HTNPlanner (async plan method)
├── search.py            (107 lines) — anytime_beam_search + SearchNode
├── slm_decomposer.py    (142 lines) — SLMDecomposer (mlx_lm, async)
└── task_cache.py         (57 lines) — TaskCache (LMDB, async)

Total: 6 Python files, ~724 lines
```

---

## 3. Top 10 souborů podle velikosti

| Pořadí | Soubor | Řádků | Role |
|--------|--------|-------|------|
| 1 | `cost_model.py` | 242 | Dvoustupňový cost model (ridge + Mamba) |
| 2 | `htn_planner.py` | 169 | HTNPlanner hlavní orchestrátor |
| 3 | `slm_decomposer.py` | 142 | SLM dekompozice (mlx_lm async) |
| 4 | `search.py` | 107 | Anytime beam search |
| 5 | `task_cache.py` | 57 | LMDB cache pro dekompozice |
| 6 | `__init__.py` | 7 | Public API exports |

---

## 4. AO coupling matrix

**VÝSLEDEK: ŽÁDNÁ PŘÍMÁ AO COUPLING NENALEZENA**

```
grep -R "autonomous_orchestrator|AO|from .*autonomous|import autonomous" planning --include="*.py"
→ No matches found
```

### Detailní analýza závislostí:

| Soubor | Importuje AO? | Závislost na AO skrze |
|--------|---------------|----------------------|
| `htn_planner.py` | NE | Pouze `ResourceGovernor` z `core/` |
| `cost_model.py` | NE | Žádné AO importy |
| `search.py` | NE | Pouze `ResourceGovernor` z `core/` |
| `slm_decomposer.py` | NE | Žádné AO importy |
| `task_cache.py` | NE | Pouze `SPRINT_LMDB_ROOT` z `paths.py` |
| `__init__.py` | NE | Pouze intra-planning importy |

### Kritický závěr:
`planning/` je **TOTÁLNĚ IZOLOVANÝ** od `autonomous_orchestrator.py`. Komunikuje POUZE přes:
1. `ResourceGovernor` (z `core/resource_governor.py` — 131 řádků)
2. LMDB storage přes `paths.py`
3. Evidence log (předáván jako parameter, ne importován)

---

## 5. Runtime/storage/model coupling matrix

### Runtime coupling (async/await, threading):

| Soubor | Async? | Kontext |
|--------|--------|---------|
| `htn_planner.py` | YES | `async def plan()` — jediny async entry point |
| `slm_decomposer.py` | YES | `async def decompose()`, `async def _load_model()`, `asyncio.gather` |
| `task_cache.py` | YES | `async def get()`, `async def put()`, `asyncio.Lock` |
| `cost_model.py` | YES | `async def update()` — MLX training |
| `search.py` | NO | Synchronous beam search |

### Storage coupling:

| Soubor | Storage | Detail |
|--------|---------|--------|
| `task_cache.py` | LMDB | `open_lmdb()`, `orjson` serialization |
| `cost_model.py` | NONE | Dummy `EvidenceLog = None` placeholder |

### Model/Inference coupling:

| Soubor | Model | Detail |
|--------|-------|--------|
| `cost_model.py` | MLX | `mlx.core`, `mlx.nn`, `mlx.optimizers`, `Mamba` |
| `slm_decomposer.py` | MLX-LM | `from mlx_lm import load, generate`, lazy import |

### Klicove nalezy:
1. `cost_model.py` má `EvidenceLog = None` jako **placeholder** — skutecna evidence_log coupling NENI implementovana
2. `htn_planner.py` prijima `evidence_log` jako konstruktor parametr ale nikde ho nepouziva (nedotceny placeholder)
3. Zadny planner modul neimportuje `ActivationResult`, `duckdb_store`, `rag_engine`, `kuzu`, `parquet`, `arrow`

---

## 6. Tier 1 / Tier 2 / Tier 3 patch map

### Tier 1 — SAFE-TO-TOUCH (non-AO, low coupling)

| Soubor | Funkce | Důvod bezpečnosti | Odhad rizika |
|--------|--------|-------------------|--------------|
| `search.py` | `SearchNode`, `anytime_beam_search()` | Synchronous, pure functions, žádné AO importy | LOW |
| `task_cache.py` | `TaskCache` | Malý scope (57 lines), async seam jasný, LMDB přes paths.py | LOW |
| `cost_model.py` | `_estimate_*` metody | Placeholder metody (`_estimate_cost` vrací 1.0, `_estimate_ram` vrací 50.0) | LOW |
| `htn_planner.py` | `_estimate_*` metody | Placeholder metody (155-169 řádků) | LOW |

### Tier 2 — PATCHNUTELNÉ (vyšší riziko / coupling)

| Soubor | Funkce | Důvod rizika | Odhad rizika |
|--------|--------|--------------|--------------|
| `cost_model.py` | `AdaptiveCostModel` MLX training | Závislost na MLX, async training loop, `mx.eval()` | MEDIUM |
| `slm_decomposer.py` | `SLMDecomposer.decompose()` | MLX-LM lazy import, async model loading, RAM sensing | MEDIUM |
| `htn_planner.py` | `HTNPlanner.plan()` | Async entry point s `governor.reserve()`, complex state machine | MEDIUM |

### Tier 3 — AO-BOUND / FORBIDDEN

| Soubor | Důvod |
|--------|-------|
| `autonomous_orchestrator.py` | EXPLICITNE ZAKAZANO |
| `tests/test_autonomous_orchestrator.py` | EXPLICITNE ZAKAZANO |
| `knowledge/duckdb_store.py` | EXPLICITNE ZAKAZANO |
| `knowledge/rag_engine.py` | EXPLICITNE ZAKAZANO |
| `brain/` | EXPLICITNE ZAKAZANO |
| `utils/sprint_lifecycle.py` | EXPLICITNE ZAKAZANO |
| `utils/uma_budget.py` | EXPLICITNE ZAKAZANO |

---

## 7. První realistický non-AO insertion point

### Doporučený entry point: `htn_planner.py` — `_estimate_cost`, `_estimate_ram`, `_estimate_network`, `_estimate_value` metody

**Lokace**: `hledac/universal/planning/htn_planner.py`, radky 155-169

```python
def _estimate_cost(self, task: Dict) -> float:
    """Odhad nákladů úkolu (čas v sekundách)."""
    return 1.0  # TRIVIALNI PLACEHOLDER

def _estimate_ram(self, task: Dict) -> float:
    """Odhad RAM (MB)."""
    return 50.0  # TRIVIALNI PLACEHOLDER

def _estimate_network(self, task: Dict) -> float:
    """Odhad network (MB)."""
    return 0.1  # TRIVIALNI PLACEHOLDER

def _estimate_value(self, task: Dict) -> float:
    """Odhad prínosu úkolu."""
    return 1.0  # TRIVIALNI PLACEHOLDER
```

### Proc je toto idealni entry point:
1. **Fully izolovane** — zadne AO imports, zadne storage imports
2. **Malý scope** — 4 trivialni metody, kazda ~3 radky
3. **Jasne boundaries** — vstup: `Dict`, vystup: `float`
4. **Bez vedlejsich efektu** — pure functions
5. **Zadna AO zavislost** — pouziva pouze `task` dict
6. **Primo ovlivnuje planovani** — output ovlivnuje beam search scoring

### Alternativni insertion point: `cost_model.py` — `predict()` method
- Lepsi MLX integrace pro sophisticated estimation
- Vyssi riziko (async training, MX eval)
- Vhodne pro Sprint 8G

---

## 8. Navrh bezpecne posloupnosti po 8E

```
Sprint 8E (CURRENT): Read-only audit

Sprint 8F: Non-AO insertion point patch
  Sub-problem 8F.1: Real cost estimation v htn_planner._estimate_* (Tier 1)
  Sub-problem 8F.2: Wire evidence_log placeholder in cost_model.py (Tier 2)
  Sub-problem 8F.3: task_cache persistence verification (Tier 1)

Sprint 8G: Advanced cost model
  Sub-problem 8G.1: AdaptiveCostModel.predict() real features (Tier 2)
  Sub-problem 8G.2: SLMDecomposer production hardening (Tier 2)
  Sub-problem 8G.3: LMDB version migration in task_cache (Tier 1)

Sprint 8H: Full HTN integration
  Sub-problem 8H.1: HTNPlanner.plan() end-to-end test (Tier 2)
  Sub-problem 8H.2: ResourceGovernor integration testing (Tier 2)
  Sub-problem 8H.3: AO wiring (Tier 3 - HIGH RISK)
```

---

## 9. Co je explicitne zakazano patchovat dal

### ZAKAZANE (AO-bound / forbidden zones):

1. `autonomous_orchestrator.py` — Hlavni orchestrator, vsechny manazery
2. `tests/test_autonomous_orchestrator.py` — E2E test suite
3. `knowledge/duckdb_store.py` — DuckDB storage backend
4. `knowledge/rag_engine.py` — RAG engine
5. `brain/` — Brain management modules
6. `utils/sprint_lifecycle.py` — Sprint lifecycle utilities
7. `utils/uma_budget.py` — UMA budget manager

### HIGH-RISK patches bez explicitni approval:

1. `htn_planner.py:async def plan()` — async entry point s governor.reserve()
2. `slm_decomposer.py:_load_model()` — MLX-LM async loading
3. `cost_model.py:async def update()` — MLX training loop
4. Jakkoli zmeny v `planning/__init__.py` public API

---

## 10. Doporuceny dalsi implementacni sprint

### Sprint 8F: Real Cost Estimation (Non-AO Insertion Point)

**Cil**: Nahradit placeholder cost estimation v `htn_planner.py` realnou logikou

**Bezpecne zmeny**:
1. `htn_planner.py:_estimate_cost()` — task-type aware cost (fetch=0.5s, deep_read=5.0s, atd.)
2. `htn_planner.py:_estimate_ram()` — task-type aware RAM (fetch=10MB, deep_read=200MB, atd.)
3. `htn_planner.py:_estimate_network()` — task-type aware network (fetch=0.5MB, deep_read=5.0MB, atd.)
4. `htn_planner.py:_estimate_value()` — domain-adjusted value scoring

** Nezmeni**:
- Zadny AO orchestrator
- Zadne storage vrstvy
- Zadny async entry point signature

**Gates**:
- `pytest tests/probe_8e/ -q` musi projit
- Planner smoke test musi projit
- Probe_8e test musi overit Tier 1 non-empty

---

## AO Canary Status

**Test file**: `tests/test_ao_canary.py`
**Status**: EXISTUJE a OBSAHUJE RUNNABLE testy
**Coverage**: 382 radku, 25+ test cases napric 9 test class
**Canary testy**: TestAOOrchestratorCanary, TestWindupGatingCanary, TestCheckpointProbeCanary, TestBgTaskTrackingCanary, TestShutdownUnificationCanary, TestRemainingTimeSignalCanary, TestCapabilityGatingCanary, TestActionRegistryCanary, TestBudgetManagerCanary, TestGraphKnowledgeLayerCanary, TestModelLifecycleCanary

---

## Benchmarky / Gates

| Gate | Status | Detail |
|------|--------|--------|
| `probe_8e/` existence | NENI VYTVOREN | Vytvorit `tests/probe_8e/` |
| `PLANNER_AUDIT_8E.md` existence | EXISTUJE | Tento dokument |
| AO canary | NETESTOVANO | Overit runnable |
| Kumulativni gate < 30s | NETESTOVANO | Cil: < 30s |

---

## Memory Impact Assessment (M1 8GB)

**Planning modul RAM naroky**:
- `cost_model.py`: MLX Mamba model (~10-20MB pri load)
- `slm_decomposer.py`: Qwen2.5-0.5B (~400-800MB pri load, lazy)
- `task_cache.py`: LMDB (rizeno `max_size_mb=100` param)
- Celkem: < 1GB i pri plnem load

**Dopad na M1 8GB**: LOW — zadny primy RAM tlak na AO stack

---

## Zname limity

1. **Evidence log placeholder**: `cost_model.py:19` ma `EvidenceLog = None` — skutecna evidence_log coupling neni implementovana
2. **Synchronous expand()**: `htn_planner.py:89` — expander je synchronni, coz muze byt bottleneck pro slozene ukoly
3. **MLX-LM fallback**: `slm_decomposer.py` ma rule-based fallback, ale ten je trivialni (`_rule_based_fallback` vraci jeden fetch)
4. **Zadny ACTUAL usage**: Planner moduly nejsou aktualne volany z AO — jsou pripraveny, ale ne integrovany

---

## Appendix: Planner Module Dependency Graph

```
                    +------------------------------------------+
                    |         HTNPlanner (169 lines)         |
                    |  async plan() -> anytime_beam_search()  |
                    +-----------------+------------------------+
                                      |
          +-------------------------+-------------------------+
          |                         |                         |
          v                         v                         v
+-------------------+  +---------------------+  +---------------------+
|  AdaptiveCostModel|  |   SLMDecomposer     |  |   ResourceGovernor  |
|   (242 lines)     |  |   (142 lines)       |  |   (131 lines)       |
|   MLX + Mamba    |  |   mlx_lm async      |  |   (core/)           |
|   OnlineRidge     |  |   TaskCache         |  |                     |
+--------+----------+  +---------+----------+  +---------------------+
         |                         |
         v                         v
+-------------------+  +---------------------+
|    TaskCache      |  |      LMDB           |
|   (57 lines)     |  |  (via paths.py)     |
|   async + LMDB   |  |                     |
+-------------------+  +---------------------+

AO Coupling: NONE (planning is fully isolated)
```
