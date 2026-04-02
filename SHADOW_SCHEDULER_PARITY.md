# Shadow Scheduler Parity — F3.5 Fact Parity (Sprint 8VN)

## Bird's-Eye View: Proč je teď správný čas na Fact Parity

Scheduler shadow parity je přirozený další krok po Sprint 8SA (lifecycle bridge) a Sprint 8SB (scheduler runtime audit). Systém má nyní:

1. **Stable runtime/lifecycle API** — SprintLifecycleManager je canonical, utils verze je bridge
2. **Typed fact contracts** — AnalyzerResult, ExportHandoff, BranchDecision, RunCorrelation jsou v types.py
3. **Shadow inputs scaffold** — shadow_inputs.py definuje pure collect_* funkcí a bundle dataklasy
4. **Žádný nový framework** — nepřidáváme scheduler-owned state, žádné nové truth store

Fact parity != decision parity. Teď je správný čas porovnávat facts (co systém ví), ale ještě ne porovnávat rozhodnutí (co systém dělá s vědomím). Rozhodnutí vyžadují plnou scheduler_active, což přijde po F4.

---

## Runtime Modes Matrix

| Mode | Description | Default | Env Var |
|------|-------------|---------|---------|
| `legacy_runtime` | Dnešní runtime path — přímé volání z __main__.py | YES | — |
| `scheduler_shadow` | Shadow mode — čte facts, žádné řízení, žádné side effects | NO | `HLEDAC_RUNTIME_MODE=scheduler_shadow` |
| `scheduler_active` | Plný scheduler-driven režim (budoucí) | NO | `HLEDAC_RUNTIME_MODE=scheduler_active` |

**Activation**: Přes `HLEDAC_RUNTIME_MODE` env var. Default je vždy `legacy_runtime`.

**Key invariant**: `scheduler_shadow` a `scheduler_active` jsou striktně behind-flag. Legacy runtime běží beze změny.

---

## Typed vs Compat Facts

### Typed Facts (canonical, v types.py)
- `AnalyzerResult` → model/control facts
- `ExportHandoff` → export handoff facts
- `BranchDecision` → branch decision facts
- `RunCorrelation` → correlation carrier

### Compat/Local Facts (scaffold, v runtime/shadow_inputs.py)
- `LifecycleSnapshotBundle` → workflow_phase, control_phase, windup_local_phase
- `GraphSummaryBundle` → graph nodes/edges/backend/top_nodes
- `ModelControlFactsBundle` → tools/sources/privacy/depth/models_needed
- `WorkflowPhase`, `ControlPhase`, `WindupLocalPhase` → SEPARATED phase dataklasy

**Pravidlo**: Local shadow dataclasses (z runtime/shadow_inputs.py) NESMÍ být povýšeny na shared contracts. Zůstávají v scaffold modulu.

---

## Fact Stability Classification

Každý shadow input bundle má `fact_stability: STABLE | COMPAT | UNKNOWN`:

| Bundle | STABLE path | COMPAT path | UNKNOWN path |
|--------|-------------|-------------|--------------|
| LifecycleSnapshotBundle | workflow_phase, control_phase (from SprintLifecycleManager) | windup_local_phase (hardcoded in windup_engine) | — |
| GraphSummaryBundle | from_ioc_graph_stats (DuckPGQGraph) | from_scorecard_top_nodes (legacy) | no inputs provided |
| ModelControlFactsBundle | from_analyzer_result (AnalyzerResult) | from raw_profile dict | no inputs provided |

**Důležité**: `__future_owner__` je **ClassVar** (třídní atribut), nikdy ne instance atribut. Instance může mít pouze `__compat_note__`.

---

## Co se porovnává v F3.5 (Fact Parity)

1. **Lifecycle Snapshot Parity**
   - workflow_phase: BOOT | WARMUP | ACTIVE | WINDUP | EXPORT | TEARDOWN
   - control_phase_mode: normal | prune | panic
   - windup_local_mode: synthesis | structured | minimal (pouze v WINDUP)
   - kontroluje PHASE_FIELD_MERGE invariant (phase fields nesmí být slité do jednoho pole)

2. **Export Handoff Parity**
   - sprint_id, synthesis_engine, gnn_predictions, top_nodes_count, ranked_parquet_present

3. **Graph Summary / Capability Facts**
   - node_count, edge_count, pgq_active, backend, top_nodes_count

4. **Model/Control Fact Parity**
   - tools_count, sources_count, privacy_level, depth, models_needed

5. **Branch/Provider Precursor Facts**
   - branch_decision_id, provider_recommend (budoucí)

6. **Correlation-Aware Parity Metadata**
   - run_id, branch_id (pokud jsou dostupné)

---

## Co se NEPOROVNÁVÁ (deferred to F4/F5)

- Tool execution decisions (jaké tooly se volají)
- Fetch/runtime side effects (skutečné network calls)
- Provider activation (který LLM provider se aktivuje)
- Windup execution outcomes (co windup skutečně udělá)
- Findings writes (zápisy do DuckDB/knowledge)
- Network behavior (skutečné HTTP/TCP operace)
- Actual tool-level dispatch parity (dispatch decision parity)
- Scheduler Active mode decision outputs

---

## Mismatch Categories

| Category | Meaning |
|----------|---------|
| `NONE` | Všechny facts shodné |
| `LIFECYCLE` | Lifecycle phase mismatch (unexpected phase value, missing windup_local_phase v WINDUP, atd.) |
| `GRAPH_CAPABILITY` | Graph backend unknown nebo kapacita mismatch |
| `MODEL_CONTROL` | Model/control configuration mismatch |
| `EXPORT_HANDOFF` | Export handoff facts mismatch |
| `PHASE_FIELD_MERGE` | **BUG**: pokus slít workflow_phase + control_phase + windup_local_phase do jednoho `phase` pole |

---

## Phase Systems — STRICTLY SEPARATED

Jsou TŘI ODDĚLENÉ phase systémy, NIKDY neslité do jednoho pole:

### 1. Workflow Phase (`workflow_phase`)
- **Owner**: `SprintLifecycleManager` (runtime/sprint_lifecycle.py)
- **Values**: BOOT | WARMUP | ACTIVE | WINDUP | EXPORT | TEARDOWN
- **Řídí**: celý sprint lifecycle timing

### 2. Control Phase (`control_phase_mode`)
- **Owner**: `SprintLifecycleManager.recommended_tool_mode()`
- **Values**: normal | prune | panic
- **Řídí**: tool pruning / resource governance intensity
- **Independent osa**: JINÁ než workflow_phase

### 3. Windup Local Phase (`windup_local_mode`)
- **Owner**: windup_engine (future, dnes hardcoded "synthesis")
- **Values**: synthesis | structured | minimal
- **Řídí**: synthesis mode uvnitř WINDUP fáze
- **Smysl**: Oddělený režim uvnitř WINDUP, NE další timing fáze

**Invariant**: Pokud workflow_phase == WINDUP, windup_local_phase MUSÍ být set. Pokud workflow_phase != WINDUP, windup_local_phase MUSÍ být None.

---

## F3.6: Pre-Decision Consumer Layer (Sprint 8VL)

### Bird's-Eye View: Proč je pre-decision consumer správný mezikrok

Po **Fact Parity (F3.5)** systém ověřil, že fakta ze shadow inputs jsou konzistentní —
`ParityArtifact` má flat mismatch list.

**Pre-decision (F3.6)** jde nad to: skládá z ParityArtifact interpretaci toho,
**co to znamená pro scheduler decision**, aniž by do něj sahalo.

Klíčové vlastnosti:
- Shadow-only, read-only vrstva
- Čte `ParityArtifact` z `run_shadow_parity()`
- Neskládá scheduler decisions, pouze interpretace
- Produkuje `PreDecisionSummary` artifact
- Žádné side effects, žádné I/O, žádné network
- Žádné nové mutable fields na SprintScheduler
- Žádné background tasks
- Žádné nové caches

### Co pre-decision consumer UMÍ

| Schopnost | Detail |
|-----------|--------|
| Lifecycle interpretation | `is_active`, `is_windup`, `can_accept_work`, `should_prune`, `phase_conflict` |
| Graph capability summary | `readiness`: unknown/sparse/ready/rich |
| Export readiness summary | `readiness`: unknown/partial/ready |
| Model/control summary | `readiness`: unknown/partial/ready |
| Precursor summary | branch/provider/correlation readiness |
| Diff taxonomy | 9 kategorií (viz níže) |
| Blockers/unknowns/mismatch reasons | diagnostická metadata |

### Diff Taxonomy (F3.6)

| Kategorie | Meaning |
|-----------|---------|
| `NONE` | Všechny pre-decision vstupy dostatečné |
| `INSUFFICIENT_INPUT` | Fact bundles nemají dost informací |
| `LIFECYCLE_MISMATCH` | Lifecycle fáze v nekonzistentním stavu |
| `PHASE_LAYER_CONFLICT` | Dvě+ phase vrstvy si odporují |
| `GRAPH_CAPABILITY_AMBIGUITY` | Graph backend/neural capability nejasná |
| `EXPORT_HANDOFF_AMBIGUITY` | Export handoff facts neúplné |
| `MODEL_CONTROL_AMBIGUITY` | Model/control konfigurace nejasná |
| `PROVIDER_PRECURSOR_AMBIGUITY` | Provider doporučení nejasné |
| `BRANCH_PRECURSOR_AMBIGUITY` | Branch rozhodnutí nejasné |
| `COMPAT_SEAM_ACTIVE` | Compat seam je aktivní (fyziologický stav, ne blocker) |

### Blockers vs Unknowns vs Compat Seams

| Kategorie | Kam patří | Proč |
|-----------|-----------|------|
| UNKNOWN readiness (STABLE path) | blockers | Měl by být známý, ale není |
| UNKNOWN readiness (COMPAT/UNKNOWN path) | unknowns | Fyziologický stav compat/legacy path |
| COMPAT seam active | compat_seams | FYZIOLOGICKÝ stav, ne blocker |
| Phase conflict | blockers | Strukturální invariant violation |
| Lifecycle not ready | blockers | Systém nemůže pokračovat |

### Phase Separation (F3.6) — STRIKTNĚ ODDĚLENÉ

`PreDecisionSummary.lifecycle` má TŘI oddělené atributy:
- `workflow_phase` — BOOT|WARMUP|ACTIVE|WINDUP|EXPORT|TEARDOWN
- `control_phase_mode` — normal|prune|panic
- `windup_local_mode` — synthesis|structured|minimal (pouze v WINDUP)

Žádné slité `phase` pole neexistuje.

---

## F3.7: Shadow Layer Hardening (Sprint 8VN)

### Bird's-Eye View: Proč je hardening potřeba

Po F3.5+F3.6 shadow vrstva funguje, ale existují potenciální body kde by
shadow scaffold mohl začít působit jako authority:

1. **Instance-level `__future_owner__`** — mohl by být použit jako přepsání, což by umožnilo local scaffold "unbundling"
2. **`to_dict()` nezahrnoval fact stability metadata** — diagnostika bez přístupu k atributům byla nemožná
3. **UNKNOWN readiness vždy → blocker** — UNKNOWN z compat/legacy path by neměl být blocker
4. **windup_stability computed but not used** — proměnná byla vypočítána ale nikdy nepřiřazena správně

### Co F3.7 dělá

1. **`__future_owner__` jako ClassVar** — class-level atribut, nelze přepsat na instanci
2. **`to_dict()` zahrnuje fact_stability, future_owner, __compat_note__** — plná diagnostika
3. **UNKNOWN readiness rozlišeno podle stability path** — STABLE unknown → blocker, COMPAT/UNKNOWN unknown → unknown
4. **Opravena proměnná windup_stability → fact_stability** — správně použita v LifecycleSnapshotBundle

### Hardening Invariants (enforced by tests)

1. `bundle.fact_stability in ("STABLE", "COMPAT", "UNKNOWN")`
2. `bundle.__future_owner__` je ClassVar, ne instance atribut
3. `bundle.fact_stability == "COMPAT"` iff `bundle.__compat_note__` is not None
4. `ParityArtifact.compat_seams` neobsahuje items které jsou v `blockers`
5. `PreDecisionSummary.compat_seams` neobsahuje items které jsou v `blockers`
6. `DiffTaxonomy.COMPAT_SEAM_ACTIVE` se neobjevuje v blockers (je v compat_seams)
7. `to_dict()` obsahuje `fact_stability`, `future_owner`, `__compat_note__`

---

## Soubory Změněné v F3.7

| Soubor | Změna |
|--------|-------|
| `runtime/shadow_inputs.py` | ClassVar pro __future_owner__, opraven to_dict(), opravena windup_stability → fact_stability |
| `runtime/shadow_parity.py` | Žádné změny (fact_stability breakdown již správně implementován) |
| `runtime/shadow_pre_decision.py` | Opravena _compose_diagnostic_metadata — UNKNOWN rozlišeno podle stability path |
| `SHADOW_SCHEDULER_PARITY.md` | Odstraněna duplicitní F3.6 sekce, aktualizována F3.7 sekce |

---

## Co zůstává local scaffold

| Class | Local scaffold | Shared contract | Důvod |
|-------|----------------|-----------------|-------|
| LifecycleSnapshotBundle | YES | NO | DIAGNOSTIC SCAFFOLD, __future_owner__ = sprint_lifecycle.py (ClassVar) |
| GraphSummaryBundle | YES | NO | DIAGNOSTIC SCAFFOLD, __future_owner__ = duckdb_store.py (ClassVar) |
| ModelControlFactsBundle | YES | NO | DIAGNOSTIC SCAFFOLD, __future_owner__ = autonomous_analyzer.py (ClassVar) |
| WorkflowPhase | YES | NO | Local scaffold pro packaging, canonical owner = SprintLifecycleManager |
| ControlPhase | YES | NO | Local scaffold, canonical owner = SprintLifecycleManager |
| WindupLocalPhase | YES | NO | Local scaffold, canonical owner = windup_engine (future) |
| ParityArtifact | YES | NO | DIAGNOSTIC OUTPUT, není truth store |
| PreDecisionSummary | YES | NO | DIAGNOSTIC ARTIFACT, není truth store |

---

## Co chybí do plné Decision Parity (F4+)

1. **Tool Execution Decision Parity** — porovnání jak scheduler rozhoduje o tool selection vs runtime
2. **Provider Activation Parity** — které LLM providery se aktivují a kdy
3. **Windup Execution Parity** — co windup skutečně dělá (nejen facts o tom, ale execution flow)
4. **Fetch/Runtime Side Effect Parity** — network calls, rate limiting, retry decisions
5. **Findings Write Parity** — co se zapisuje do knowledge store a jak

---

## Co chybí do scheduler_active (F5+)

1. **Actual Scheduler Decision Loop** — scheduler_active musí řídit workflow, ne jen číst facts
2. **Scheduler-owned State** — dnes žádný persistent scheduler state (správně, to je deferred)
3. **Tool Dispatch Integration** — napojení na tool_registry pro skutečné volání
4. **Windup Engine Ownership** — scheduler_active musí řídit windup, ne jen facts o něm
5. **Branch/Provider Activation** — scheduler_active musí aktivovat branches a providers

---

## Co chybí do prvního runtime behind-flag hooku

1. **Shadow inputs injection point** — runtime musí injectnout `ParityArtifact` do pre-decision consumer
2. **Orchestrator integration** — kde přesně se `compose_pre_decision()` volá v lifecycle
3. **Decision gate** — za jakých podmínek by pre-decision summary ovlivnil scheduler decisions (zatím NIC)
4. **Flag mechanism** — `HLEDAC_RUNTIME_MODE=scheduler_shadow` aktivuje pre-decision logging

---

## Guardraily Implementované

1. **Žádné network imports** — shadow_parity.py a shadow_inputs.py neimportují aiohttp, httpx, curl_cffi, nodriver
2. **Pure functions** — collect_* funkcí nemají side effects
3. **Žádné asyncio.sleep** — run_shadow_parity je synchroní
4. **Žádné nové state soubory** — test kontroluje suspicious naming
5. **Local dataclasses stay local** — LifecycleSnapshotBundle atd. nejsou v types.py
6. **Phase fields separated** — workflow_phase, control_phase_mode, windup_local_mode jsou vždy oddělené
7. **__future_owner__ je ClassVar** — nelze přepsat na instanci
8. **to_dict() obsahuje fact stability** — plná diagnostika bez přístupu k atributům
9. **UNKNOWN readiness rozlišeno** — STABLE unknown → blocker, COMPAT/UNKNOWN unknown → unknown
10. **Default unchanged** — bez env var běží legacy_runtime

---

## F3.8: Shadow Scheduler Consumer Seam (Sprint 8VM)

### Bird's-Eye View: Proč je scheduler-side consumer správný další krok

Po F3.5+F3.6+F3.7 shadow vrstva existuje jako nezávislý scaffold.
Nyní je čas ji přiblížit ke SprintScheduleru — ale pouze jako **read-only diagnostický
seam**, ne jako nový execution path.

Cíl F3.8:
- SprintScheduler může **read-only** konzumovat ParityArtifact a PreDecisionSummary
- Scheduler-side consumer **nevytváří** nový mutable scheduler state
- Tool/capability readiness preview je **čistě diagnostický** — žádný dispatch
- Local shadow scaffold zůstává local scaffold

### Co scheduler-side consumer UMÍ

| Schopnost | Detail |
|-----------|--------|
| `consume_shadow_pre_decision()` | Read-only method, vrací PreDecisionSummary |
| `_build_shadow_readiness_preview()` | Strojově čitelný dict pro diagnostiku/logging |
| Caching | Výsledek uložen do `_shadow_pd_summary`, cleared v `_reset_result()` |
| Legacy mode guard | Vrací None v legacy módu (výpočet se neprovádí) |
| Tool readiness preview | Read-only přehled z ToolRegistry (list_tools, get_tool_cards_for_hermes) |

### Injection Point

Voláno z `_build_diagnostic_report()` těsně před export — to je nejbezpečnější místo:
- Lifecycle snapshot je k dispozici
- Scheduler má všechny potřebné references
- Žádný vliv na decision loop
- Výstup jde pouze do diagnostického reportu

### Tool Readiness Preview — DIAGNOSTIC ONLY

Čte z ToolRegistry pouze tyto read-only metody:
- `list_tools()` — seznam názvů
- `get_tool_cards_for_hermes()` — kartičky pro hermes
- `get_network_tools()`, `get_high_memory_tools()` — filtrování

**NIKDY** se nevolá:
- `execute_with_limits()` — tool execution
- `acquire()` na provider pool — provider activation
- `load_model()` — model load
- Žádný dispatch

### Scheduler-Side Consumer Matrix

| Co | Kam | Jak |
|----|-----|-----|
| Lifecycle snapshot | `consume_shadow_pre_decision()` | `collect_lifecycle_snapshot(self._lc_adapter._lc, ...)` |
| Graph summary | stejná methoda | `collect_graph_summary(self._ioc_graph)` |
| Model control facts | stejná methoda | `collect_model_control_facts(raw_profile=...)` z config |
| ParityArtifact | stejná methoda | `run_shadow_parity(...)` |
| PreDecisionSummary | stejná methoda | `compose_pre_decision(parity)` |
| Tool readiness preview | v except bloku | `create_default_registry().list_tools()` — try/except |
| Výstup | `_build_diagnostic_report()` | `shadow_pre_decision` key v reportu |

### Co NESMÍ (hard boundaries)

| Zakázáno | Proč |
|----------|------|
| Tool execution (execute_with_limits) | Bylo by side effect |
| Provider activation (acquire/load_model) | Mění runtime state |
| Ledger writes (DuckDB/LMDB/parquet) | Není truth store pro shadow data |
| Nový scheduler framework | Nesmí vzniknout nový execution path |
| Background tasks (asyncio.create_task) | V shadow consumer nemají co dělat |
| Dispatch/enqueue work | Čistě diagnostické, ne execution |

### Co zůstává local scaffold

| Class | Local scaffold | Proč |
|-------|----------------|------|
| `_shadow_pd_summary` | YES (field na SprintScheduler) | Ephemeral cache, cleared per sprint, NOT canonical truth |
| ParityArtifact | YES (z shadow_parity.py) | DIAGNOSTIC OUTPUT, není truth store |
| PreDecisionSummary | YES (z shadow_pre_decision.py) | DIAGNOSTIC ARTIFACT, není truth store |
| `_tool_readiness_preview` | YES (attr na PreDecisionSummary) | Attachnutý diagnostický metadata, ne scheduler-owned state |

### Co chybí do skutečného runtime hooku (F4+)

1. **Decision gate** — za jakých podmínek by PreDecisionSummary ovlivnil scheduler decisions (zatím NIC)
2. **Tool dispatch parity** — porovnání tool selection decision vs actual execution
3. **Provider activation parity** — scheduler-side view vs actual provider state
4. **Windup execution parity** — scheduler's windup readiness vs actual windup flow
5. **Flag mechanism pro runtime injection** — `HLEDAC_RUNTIME_MODE=scheduler_shadow` dnes jen zpřístupňuje diagnostiku

### Guardraily Implementované v F3.8

1. **Legacy mode guard** — bez `HLEDAC_RUNTIME_MODE=scheduler_shadow` se nic nepočítá
2. **Caching** — `_shadow_pd_summary` se plní pouze jednou per sprint
3. **No bg tasks** — consume_shadow_pre_decision nespuští žádné asyncio tasky
4. **No ledger writes** — žádné zápisy do DuckDB/LMDB během consume
5. **No dispatch** — tool readiness je pouze `list_tools()`, nikdy `execute_with_limits()`
6. **Only one field mutated** — jediný persistent field změněný je `_shadow_pd_summary`
7. **Reset propaguje** — `_reset_result()`clears `_shadow_pd_summary`

### Soubory Změněné v F3.8

| Soubor | Změna |
|--------|-------|
| `runtime/sprint_scheduler.py` | Přidán `consume_shadow_pre_decision()`, `_build_shadow_readiness_preview()`, `_shadow_pd_summary` field, integrace do `_build_diagnostic_report()` |
| `runtime/sprint_scheduler.py` | Import shadow vrstvy (lazy, za TYPE_CHECKING guard) |
| `tests/probe_8vm/test_shadow_consumer_seam.py` | 11 testů ověřujících read-only seam, caching, boundary |
| `SHADOW_SCHEDULER_PARITY.md` | Přidána F3.8 sekce |
