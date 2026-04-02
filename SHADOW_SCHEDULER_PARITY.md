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

---

## F3.9: Richer Readiness Preview (Sprint 8VQ)

### Bird's-Eye View: Proč je zúžený readiness preview správný mezikrok

Scheduler-shadow v F3.8 uměl číst ParityArtifact a skládat PreDecisionSummary,
ale postrádal explicitní rozlišení **co přesně brání** decision gate.

**Rozlišení blocker vs compat seam vs unknown** je kritické pro další kroky:
- Blockers → musí být opraveny před dispatch
- Compat seams → fyziologický stav, ne blocker
- Unknowns → defer, ne block

**Provider activation deferred/unknown note** zabraňuje vzniku pseudo-authority:
- NEsimuluje load order
- NEsimuluje provider state machine
- Pouze říká "deferred" s důvodem

Toto NENÍ provider plane simulace — pouze diagnostický note.

### Co je nové v F3.9

#### 1. DecisionGateReadiness
Explicitní rozlišení pro scheduler decision gate:

| Status | Meaning | is_proceed_allowed |
|--------|---------|---------------------|
| `ready` | Žádné blockers, může proceed | True |
| `blocked` | Hard blockers present | False |
| `insufficient` | Příliš mnoho unknowns | False |
| `unknown` | Cannot determine readiness | False |

#### 2. ToolReadinessPreview
DIAGNOSTIC ONLY, no dispatch, no execute_with_limits.

| Readiness | Meaning |
|-----------|---------|
| `ready` | Tools available, can execute |
| `degraded` | Some tools unavailable due to resource pressure |
| `pruned` | Tools heavily pruned (panic mode) |
| `unknown` | Cannot determine tool readiness |

Čte POUZE z existujících fact bundles (control_phase_mode, graph readiness).
NESMÍ volat acquire() ani load_model().

#### 3. WindupReadinessPreview
From existing fact bundles only — NEaktivuje windup engine.

| Readiness | Meaning |
|-----------|---------|
| `ready` | Windup facts sufficient |
| `partial` | Some windup facts missing |
| `insufficient` | Windup facts insufficient |
| `not_active` | Not in WINDUP phase |

#### 4. ProviderActivationNote
**Deferred/unknown only, NO simulation.**

| Status | Meaning |
|--------|---------|
| `deferred` | Activation deferred to future phase |
| `unknown` | Cannot determine provider readiness |
| `not_ready` | Provider not ready |
| `blocked` | Blocked by hard constraint |

NESMÍ:
- Simulovat load order providerů
- Simulovat provider state machine
- Vzniknout pseudo-authorita provider plane

### Scheduler Shadow Readiness Matrix

| Readiness Domain | Source | Read-only | No Dispatch | Deferred Note |
|-----------------|--------|-----------|-------------|---------------|
| Lifecycle | SprintLifecycleManager | ✅ | ✅ | N/A |
| Graph | DuckPGQGraph | ✅ | ✅ | N/A |
| Export | ExportHandoff/scorecard | ✅ | ✅ | N/A |
| Model/Control | AnalyzerResult/raw_profile | ✅ | ✅ | N/A |
| Decision Gate | blockers/unknowns/compat | ✅ | ✅ | Provider only |
| Tool Readiness | control_phase + graph hints | ✅ | ✅ | N/A |
| Windup Readiness | lifecycle + export facts | ✅ | ✅ | N/A |
| Provider Activation | precursors + lifecycle | ✅ | ✅ | ✅ Deferred only |

### Co scheduler-shadow TEĎ UMÍ previewovat (F3.9)

1. **Decision gate readiness** — explicit blocker/compat_seam/unknown rozlišení
2. **Tool readiness preview** — read-only, no dispatch, resource hints from control mode
3. **Windup readiness preview** — from fact bundles only, no windup activation
4. **Provider activation note** — deferred/unknown only, no simulation

### Co scheduler-shadow STÁLE NESMÍ (hard boundaries)

| Zakázáno | Proč |
|----------|------|
| Tool execution (execute_with_limits) | Side effect |
| Provider activation (acquire/load_model) | Mění runtime state |
| Provider state machine simulation | Vznik pseudo-authority |
| Provider load order simulation | Vznik pseudo-authority |
| Windup engine activation | Mění runtime state |
| Ledger writes | Není truth store |
| Dispatch/enqueue work | Čistě diagnostické |

### Guardraily Implementované v F3.9

1. **Provider activation je deferred note** — nesimuluje se load order ani state machine
2. **Tool readiness jen z fact bundles** — žádné ToolRegistry.execute_with_limits()
3. **Windup readiness read-only** — žádné windup_engine.run_windup() volání
4. **Decision gate rozlišuje blockers vs unknowns vs compat_seams**
5. **No bg tasks in compose functions** — pure functions only
6. **Local scaffold zůstává local scaffold** — žádné shared contracts

### Soubory Změněné v F3.9

| Soubor | Změna |
|--------|--------|
| `runtime/shadow_pre_decision.py` | Přidány DiffTaxonomy enum values, DecisionGateReadiness, ToolReadinessPreview, WindupReadinessPreview, ProviderActivationNote dataclasses, _compose_* funkce |
| `runtime/sprint_scheduler.py` | Rozšířen `_build_shadow_readiness_preview()` o 4 nové readiness sekce |
| `SHADOW_SCHEDULER_PARITY.md` | Přidána F3.9 sekce |

---

## F3.10: Advisory Decision-Gate Hook (Sprint 8VQ)

### Bird's-Eye View: Proč je advisory gate hook mezikrok

Shadow scheduler uměl WINDUP-entry advisory snapshot (export-time), ale:
- Advisory gate snapshot neběžel v scheduler loopu, pouze v diagnostice
- Chybělo explicitní rozlišení gate_outcome (proceed/blocked/insufficient/unknown)
- Advisory snapshot nebyl připojen do scheduler telemetry

**Advisory gate hook** posouvá scheduler-shadow z čistě export-time preview na advisory decision-gate:
- V scheduler loopu na WINDUP entry se zavolá `evaluate_advisory_gate()`
- Výsledek jde do `_advisory_gate_snapshot` (ephemeral cache)
- Připojí se do diagnostic reportu pod klíčem `advisory_gate`
- Neovlivňuje dispatch ani source ordering

### Co je nové v F3.10

#### 1. AdvisoryGateSnapshot
Explicitní snapshot advisory gate evaluation:

| Field | Meaning |
|-------|---------|
| `gate_outcome` | "proceed" \| "blocked" \| "insufficient" \| "unknown" |
| `gate_status` | "ready" \| "blocked" \| "insufficient" \| "unknown" |
| `blocker_count`, `unknown_count`, `compat_seam_count` | Počty |
| `blocker_reasons`, `unknown_reasons`, `compat_seam_reasons` | Konkrétní důvody |
| `defer_to_provider` | Zda je provider activation deferred |
| `gate_evaluated_at_*` | Timestamp evaluation |

#### 2. compose_advisory_gate()
Pure function která sestaví `AdvisoryGateSnapshot` z `PreDecisionSummary`.

#### 3. evaluate_advisory_gate() v SprintScheduler
- Volán na WINDUP entry (vedle `_flush_dedup()`)
- Čte z cached `consume_shadow_pre_decision()` result
- NIC neaktivuje, NIC neovlivňuje dispatch
- Ukládá do `_advisory_gate_snapshot` (ephemeral)

#### 4. _build_shadow_readiness_preview() rozšířeno
Přidána sekce `advisory_gate` s flat gate_outcome fields.

### Scheduler Shadow Advisory-Gate Matrix

| Hook Point | Kdy | Co se volá | Výstup | Side Effect |
|-----------|-----|-------------|--------|-------------|
| `_build_diagnostic_report()` | Export time | `consume_shadow_pre_decision()` | `PreDecisionSummary` → `shadow_pre_decision` key | Žádný |
| `evaluate_advisory_gate()` | WINDUP entry | `compose_advisory_gate()` | `AdvisoryGateSnapshot` → `advisory_gate` key | Žádný |
| `_build_shadow_readiness_preview()` | Export time | `compose_pre_decision()` | dict pro report | Žádný |

### Co scheduler-shadow TEĎ UMÍ (F3.10)

1. **Advisory decision-gate evaluation** — gate_outcome rozlišení v scheduler loopu
2. **Ephemeral advisory cache** — `_advisory_gate_snapshot` cleared per sprint
3. **Diagnostic gate telemetry** — připojeno do diagnostic reportu
4. **Provider deferral awareness** — defer_to_provider flag

### Co scheduler-shadow STÁLE NESMÍ (hard boundaries)

| Zakázáno | Proč |
|----------|------|
| Tool execution (execute_with_limits) | Side effect |
| Provider activation (acquire/load_model) | Mění runtime state |
| Dispatch / enqueue work | Čistě diagnostické |
| Persistent state kromě ephemeral cache | Shadow zůstává read-only |

### Guardraily Implementované v F3.10

1. **Advisory gate je ephemeral cache** — `_advisory_gate_snapshot` cleared v `_reset_result()`
2. **evaluate_advisory_gate() neaktivuje nic** — pouze volá `compose_advisory_gate()`
3. **WINDUP entry bod** — voláno vedle `_flush_dedup()`, ne v decision loopu
4. **Žádné nové bg_tasks** — žádné asyncio tasky
5. **Žádné ledger writes** — pouze diagnostic dict output

### Soubory Změněné v F3.10

| Soubor | Změna |
|--------|--------|
| `runtime/shadow_pre_decision.py` | Přidán `AdvisoryGateSnapshot` dataclass, `compose_advisory_gate()` funkce |
| `runtime/sprint_scheduler.py` | Přidán `evaluate_advisory_gate()`, pole `_advisory_gate_snapshot`, volání na WINDUP entry, rozšířen `_build_shadow_readiness_preview()` |
| `tests/probe_8vm/test_shadow_consumer_seam.py` | Přidány testy pro advisory gate |
| `SHADOW_SCHEDULER_PARITY.md` | Přidána F3.10 sekce |

---

## F3.11: Dispatch Parity Preview (Sprint F3.11)

### Bird's-Eye View: Proč je dispatch parity preview správný mezikrok

Scheduler-shadow uměl WINDUP-entry advisory snapshot a tool readiness preview,
ale postrádal explicitní rozlišení **jak scheduler-shadow previewuje dispatch readiness**
pro jednotlivé task/tool kandidáty.

**Dispatch parity preview** přidává:
- Rozlišení mezi `canonical_tool_dispatch` (ToolRegistry) a `runtime_only_compat_dispatch` (inline task handlers)
- Capability gap analysis bez volání `execute_with_limits()`
- Explicitní rozlišení: `dispatch_ready`, `dispatch_blocked`, `dispatch_pruned`, `dispatch_unknown`
- Rozpoznání že některé task types nemají ToolRegistry mapping a jsou `runtime_only_compat`

Klíčové pravidlo: preview **NENÍ** simulace dnešního pivot dispatche.
Pokud kandidát nemá čistý canonical ToolRegistry mapping, označí se jako `runtime_only_compat_dispatch`.

### Co je nové v F3.11

#### 1. DispatchTaxonomy Enum
Explicitní taxonomie pro dispatch parity:

| Kategorie | Meaning |
|-----------|---------|
| `CANONICAL_TOOL_DISPATCH` | Task/tool má čistý ToolRegistry mapping, jde přes `execute_with_limits` |
| `RUNTIME_ONLY_COMPAT_DISPATCH` | Task/type používá inline `get_task_handler()`, nemá canonical ToolRegistry mapping |
| `DISPATCH_READY` | Všechny podmínky pro dispatch jsou splněny |
| `DISPATCH_BLOCKED` | Capability missing nebo hard constraint |
| `DISPATCH_PRUNED` | Control mode prune/panic |
| `DISPATCH_UNKNOWN` | Nelze určit readiness |
| `CAPABILITY_MISSING` | Tool vyžaduje capabilities které nejsou v available set |
| `NO_TOOL_MAPPING` | Task type nemá ToolRegistry tool mapping |

#### 2. DispatchReadinessPreview
Diagnostic artifact pro dispatch parity:

| Field | Meaning |
|-------|---------|
| `readiness` | "ready" \| "blocked" \| "pruned" \| "unknown" |
| `dispatch_path` | "canonical_tool" \| "runtime_only_compat" |
| `tool_candidates` | Mapování task_type → tool_name |
| `capability_gaps` | Detailní gap per tool (required, available, missing) |
| `runtime_only_handlers` | Task types bez ToolRegistry mapping |
| `canonical_count` | Počet tools s canonical dispatch path |
| `runtime_only_count` | Počet task types s runtime_only_compat path |

#### 3. preview_dispatch_parity()
Pure function — DIAGNOSTIC ONLY, žádné `execute_with_limits()`, žádné provider activation.

### Dispatch Matrix

| Co | Read-only | No Dispatch | Capability Gap | Runtime Only Compat |
|----|-----------|-------------|----------------|---------------------|
| ToolRegistry metadata | ✅ | ✅ | ✅ | ✅ |
| required_capabilities | ✅ | ✅ | ✅ | ❌ (není v registry) |
| tool_cards | ✅ | ✅ | ✅ | ❌ |
| execute_with_limits | ❌ | ❌ | ❌ | ❌ |
| Provider activation | ❌ | ❌ | ❌ | ❌ |

### Scheduler Shadow Dispatch-Parity Matrix

| Readiness Domain | Source | Read-only | No Dispatch | Deferred Note |
|-----------------|--------|-----------|-------------|---------------|
| Lifecycle | SprintLifecycleManager | ✅ | ✅ | N/A |
| Graph | DuckPGQGraph | ✅ | ✅ | N/A |
| Export | ExportHandoff/scorecard | ✅ | ✅ | N/A |
| Model/Control | AnalyzerResult/raw_profile | ✅ | ✅ | N/A |
| Decision Gate | blockers/unknowns/compat | ✅ | ✅ | Provider only |
| Tool Readiness | control_phase + graph hints | ✅ | ✅ | N/A |
| Windup Readiness | lifecycle + export facts | ✅ | ✅ | N/A |
| Provider Activation | precursors + lifecycle | ✅ | ✅ | ✅ Deferred only |
| **Dispatch Parity** | ToolRegistry + task candidates | ✅ | ✅ | **runtime_only_compat only** |

### Co scheduler-shadow TEĎ UMÍ previewovat (F3.11)

1. **Dispatch readiness** — explicitní rozlišení dispatch_ready/blocked/pruned/unknown
2. **Canonical vs runtime_only_compat** — které task types mají ToolRegistry mapping
3. **Capability gap analysis** — které tools mají missing capabilities
4. **Control mode impact** — které tools budou pruned při prune/panic módu

### Co scheduler-shadow STÁLE NESMÍ (hard boundaries)

| Zakázáno | Proč |
|----------|------|
| Tool execution (execute_with_limits) | Side effect |
| Provider activation (acquire/load_model) | Mění runtime state |
| Provider state machine simulation | Vznik pseudo-authority |
| Provider load order simulation | Vznik pseudo-authority |
| Windup engine activation | Mění runtime state |
| Ledger writes | Není truth store |
| Dispatch/enqueue work | Čistě diagnostické |

### Canonical Read-Side Owner (Sprint F3.11 normalization)

`TASK_TYPE_TO_TOOL_PREVIEW` mapping (task_type → tool_name) má nyní **canonical read-side ownera**:

| Owner | Role | Location |
|-------|------|----------|
| `tool_registry.py` | **CANONICAL READ-SIDE OWNER** — `TASK_TYPE_TO_TOOL_PREVIEW` constant + `get_task_tool_preview_mapping()` | `tool_registry.py:1340-1392` |
| `shadow_pre_decision.py` | **CONSUMER** — volá `get_task_tool_preview_mapping()`, nevlastní mapping | `shadow_pre_decision.py:1447-1450` |

**Drift prevention**: dříve byl `TASK_TYPE_TO_TOOL` lokální konstanta v `shadow_pre_decision.py`. Nyní je centralizovaný v `tool_registry.py` jako read-side metadata seam. `shadow_pre_decision.py` už mapping nevlastní, pouze čte přes getter.

**Rozlišení ownership**:
- `tool_registry.py` — canonical read-side owner (metadata seam)
- `runtime_only_compat_dispatch` — task types bez ToolRegistry mappingu (inline `get_task_handler()`)

### Co NENÍ v tomto sprintu

| Co | Proč deferred |
|----|---------------|
| Skutečný dispatch přes ToolRegistry | Vyžaduje scheduler_active mode |
| Provider plane simulace | Vznik pseudo-authority |
| Plná capability enforcement | Vyžaduje real capability provider |
| Nový scheduler-owned persistent state | Shadow zůstává read-only diagnostic |

### Guardraily Implementované v F3.11

1. **Žádné execute_with_limits()** — pouze read-only ToolRegistry metadata
2. **Žádné provider activation** — pouze deferred/unknown notes
3. **Rozlišení canonical vs runtime_only_compat** — runtime_only neprezentuje jako canonical
4. **Pure function** — žádné side effects v preview_dispatch_parity()
5. **No bg_tasks** — dispatch parity počítáno synchronně v consume_shadow_pre_decision()
6. **Mapping ownership normalized** — `TASK_TYPE_TO_TOOL_PREVIEW` v tool_registry.py, ne shadow_pre_decision.py

### Soubory Změněné v F3.11

| Soubor | Změna |
|--------|--------|
| `tool_registry.py` | Přidán `TASK_TYPE_TO_TOOL_PREVIEW` constant + `get_task_tool_preview_mapping()` (canonical read-side owner) |
| `runtime/shadow_pre_decision.py` | Importuje mapping z tool_registry, odstraněna lokální definice |
| `SHADOW_SCHEDULER_PARITY.md` | Aktualizována F3.11 sekce — canonical read-side owner, mapping ownership normalized |
| `TOOL_CAPABILITY_EXECUTION_ENFORCEMENT.md` | Aktualizováno — canonical/read-only seams rozšířeny o dispatch preview mapping |
| `tests/probe_8vm/test_shadow_consumer_seam.py` | Přidány testy pro mapping ownership normalization |

---

## F3.12: Provider Readiness Preview (Sprint F3.5-F3.6)

### Bird's-Eye View: Proč je provider readiness preview správný další krok

Dispatch preview už uměl rozlišovat canonical vs runtime_only_compat dispatch path.
Chyběla explicitní klasifikace **provider readiness** — ne simulace provider plane,
ale read-only diagnostická klasifikace readiness z dostupných facts.

**Provider readiness preview** přidává:
- Explicitní rozlišení TŘÍ různých věcí: recommendation fact, readiness preview, actual activation
- Read-only diagnostická klasifikace: ready/deferred/blocked/unknown/compat
- Žádné domýšlení chybějících facts jako ready
- Žádné load_model(), acquire(), unload(), execute_with_limits()

### Proč je to PARITY PREVIEW, ne activation

| Aktivita | Co dělá | V čem je parity? |
|----------|----------|------------------|
| Recommendation fact | Co `capabilities.py` doporučuje (`models_needed`) | Čte facts z model_control |
| Readiness preview | Diagnostická klasifikace readiness z lifecycle+model_control facts | Porovnává lifecycle state vs readiness门槛 |
| Actual activation | Skutečné volání provider pool přes `acquire()`/`load_model()` | **NENÍ součástí parity** |

Provider readiness preview čte pouze **facts** (lifecycle phase, control mode, thermal state, models_needed).
NESMÍ volat žádné activation API.

### Co je nové v F3.12

#### 1. ProviderReadinessPreview dataclass
Explicitní readiness preview bez activation:

| Field | Meaning |
|-------|---------|
| `has_recommendation` | models_needed fact available |
| `recommendation` | Raw models_needed string |
| `readiness` | "ready" \| "deferred" \| "blocked" \| "unknown" \| "compat" |
| `lifecycle_ready` | is_active or is_windup |
| `control_ready` | control_mode in (normal, prune) |
| `thermal_safe` | thermal_state != critical |
| `has_facts` | models_needed non-empty |
| `blockers` | Hard constraints |
| `unknowns` | Insufficient facts |
| `deferred_reasons` | Why deferred |

**NESMÍ obsahovat**: `load_order`, `provider_state`, `activation_sequence`, `actual_model_loaded`

#### 2. _compose_provider_readiness_preview()
Pure function — DIAGNOSTIC ONLY, žádné activation API.

#### 3. Read-only fact sources
| Source | Fact | Read-only |
|--------|------|-----------|
| LifecycleInterpretation | `is_active`, `is_windup`, `is_terminal`, `control_phase_mode`, `control_phase_thermal`, `phase_conflict` | ✅ |
| ModelControlSummary | `models_needed`, `readiness` | ✅ |
| Žádné provider API | `acquire()`, `load_model()`, `unload()`, `execute_with_limits()` | ❌ |

### Provider Readiness Matrix

| Readiness | Lifecycle | Control | Thermal | Facts | Co to znamená |
|-----------|-----------|---------|---------|-------|---------------|
| ready | ACTIVE/WINDUP | normal/prune | non-critical | non-empty | Všechny podmínky splněny |
| deferred | not ACTIVE/WINDUP | any | any | any | Lifecycle not ready |
| blocked | any | panic | any | any | Hard constraint |
| unknown | ACTIVE/WINDUP | normal/prune | non-critical | empty | Facts insufficient |
| compat | WARMUP | normal | non-critical | any | COMPAT path, indeterminate |

### Scheduler Shadow Provider-Readiness Matrix

| Readiness Domain | Source | Read-only | No Activation | Deferred Note |
|-----------------|--------|-----------|---------------|---------------|
| Lifecycle | SprintLifecycleManager | ✅ | ✅ | N/A |
| Graph | DuckPGQGraph | ✅ | ✅ | N/A |
| Export | ExportHandoff/scorecard | ✅ | ✅ | N/A |
| Model/Control | AnalyzerResult/raw_profile | ✅ | ✅ | N/A |
| Decision Gate | blockers/unknowns/compat | ✅ | ✅ | Provider only |
| Tool Readiness | control_phase + graph hints | ✅ | ✅ | N/A |
| Windup Readiness | lifecycle + export facts | ✅ | ✅ | N/A |
| Provider Activation | precursors + lifecycle | ✅ | ✅ | ✅ Deferred only |
| **Provider Readiness** | **lifecycle + model_control** | **✅** | **✅** | **✅ all states** |

### Co scheduler-shadow TEĎ UMÍ previewovat (F3.12)

1. **Provider readiness classification** — explicitní ready/deferred/blocked/unknown/compat
2. **Per-dimension facts** — lifecycle_ready, control_ready, thermal_safe, has_facts
3. **No simulation** — žádné load_order, provider_state, activation_sequence
4. **Missing facts → unknown/deferred** — ne heuristické "ready"

### Co scheduler-shadow STÁLE NESMÍ (hard boundaries)

| Zakázáno | Proč |
|----------|------|
| load_model() | Mění runtime state |
| acquire() | Aktivuje provider pool |
| unload() | Deaktivace provideru |
| execute_with_limits() | Tool execution |
| Provider state machine simulation | Vznik pseudo-authority |
| Provider load order simulation | Vznik pseudo-authority |
| Domýšlení facts jako ready | Facts insufficient → unknown/deferred |

### Tři různé věci NESMÍ splývat

1. **Recommendation fact** (`has_recommendation`, `models_needed`) — co `capabilities.py` říká
2. **Readiness preview** (`ProviderReadinessPreview.readiness`) — diagnostická klasifikace
3. **Actual activation** (volání `acquire()`/`load_model()`) — **NIKDY součástí parity**

### Guardraily Implementované v F3.12

1. **Žádné activation API** — _compose_provider_readiness_preview() nevolá load_model/acquire/unload/execute_with_limits
2. **Žádné simulation fields** — ProviderReadinessPreview NESMÍ mít load_order/provider_state/activation_sequence
3. **Facts-based classification** — missing facts → unknown/deferred, ne heuristické ready
4. **Pure function** — žádné side effects v _compose_provider_readiness_preview()
5. **No bg_tasks** — readiness počítáno synchronně v consume_shadow_pre_decision()
6. **Three-way distinction** — recommendation fact vs readiness preview vs actual activation NESMÍ splývat

### Co NENÍ v tomto sprintu

| Co | Proč deferred |
|----|---------------|
| Skutečná provider activation | Vyžaduje scheduler_active mode + provider pool API |
| Provider plane simulace | Vznik pseudo-authority |
| Provider load order | Vyžaduje runtime provider state |
| Plná provider readiness parity | Vyžaduje live provider facts |

### Co chybí do reálné provider activation parity (F4+)

1. **Provider activation API** — acquire(), load_model(), unload() volání v scheduler_active
2. **Provider state tracking** — který provider je aktuálně loaded
3. **Provider readiness live facts** — skutečný provider state z runtime
4. **Provider load order** — pořadí provider activation

### Co chybí do scheduler_active (F5+)

1. **Actual provider activation** — scheduler_active musí aktivovat providery přes provider pool
2. **Provider orchestration** — scheduler řídí provider lifecycle
3. **Provider-aware dispatch** — dispatch přes aktivní provider

### Soubory Změněné v F3.12

| Soubor | Změna |
|--------|--------|
| `runtime/shadow_pre_decision.py` | Přidán `ProviderReadinessPreview` dataclass, `_compose_provider_readiness_preview()` funkce, integrace do `compose_pre_decision()` |
| `runtime/sprint_scheduler.py` | Rozšířen `_build_shadow_readiness_preview()` o `provider_readiness` sekci |
| `SHADOW_SCHEDULER_PARITY.md` | Přidána F3.12 sekce |
| `tests/probe_8vm/test_shadow_consumer_seam.py` | Přidány testy pro `TestProviderReadinessPreview` |

---

## F3.13: Provider Runtime Facts Seam (Sprint F3.13)

### Bird's-Eye View: Proč je runtime facts seam potřeba

Provider readiness preview (F3.12) rozlišil mezi:
- `has_recommendation` — fact o tom, že existuje `models_needed` doporučení (STABLE)
- `has_facts` — heuristika odvozená z `models_needed` (COMPAT)

Chyběl ale explicitní **runtime state** — co aktuálně běží v provider poolu:
- `current_model_name` — jaký model je aktuálně loaded
- `is_loaded` — zda vůbec nějaký model běží
- `initialized` — zda je provider initialized

**Audit existing surfaces** ukázal, že tyto facts jsou dostupné přes:
- `brain/model_manager.py::get_current_model()` — vrací model name nebo None
- `brain/model_lifecycle.py::get_model_lifecycle_status()` — vrací `{loaded, current_model, initialized, last_error}`

### Co je nové v F3.13

1. **`ProviderRuntimeFactsBundle`** — nový read-only bundle v `shadow_inputs.py`
   - Sbírá runtime facts z `ModelManager.get_current_model()` a `get_model_lifecycle_status()`
   - `fact_stability`: STABLE (ModelManager available) | COMPAT (lifecycle_status only) | UNKNOWN (nothing)
   - Canonical owner: `brain/model_manager.py` / `brain/model_lifecycle.py`

2. **`collect_provider_runtime_facts()`** — pure function v `shadow_inputs.py`
   - Přijímá `model_manager` (volitelné) a `lifecycle_status` (volitelné)
   - Vrací `ProviderRuntimeFactsBundle`
   - Žádné side effects, žádné I/O

3. **Provider readiness preview rozšířen** — nové fieldy v `ProviderReadinessPreview`:
   - `runtime_loaded` — zda je aktuálně loaded
   - `runtime_current_model` — jméno aktuálně loaded modelu
   - `runtime_initialized` — zda je provider initialized

4. **Wiring do `compose_pre_decision()`** — nový `runtime_facts` parametr

### Fact Stability Matrix (F3.13)

| Zdroj | Fact Stability | Podmínka |
|-------|----------------|----------|
| `ModelManager.get_current_model()` | STABLE | model_manager je dostupný |
| `ModelManager.is_loaded()` | STABLE | model_manager je dostupný |
| `get_model_lifecycle_status()` | COMPAT | pouze lifecycle_status bez ModelManager |
| Nic dostupné | UNKNOWN | model_manager=None, lifecycle_status=None |

### Provider Runtime Facts Matrix

| Field | STABLE path | COMPAT path | UNKNOWN path |
|-------|-------------|-------------|--------------|
| `current_model` | `model_manager.get_current_model()` | `lifecycle_status["current_model"]` | None |
| `is_loaded` | `model_manager.is_loaded()` | `lifecycle_status["loaded"]` | False |
| `initialized` | `model_manager.is_loaded() and model_manager.initialized_placeholder` | `lifecycle_status["initialized"]` | False |
| `fact_stability` | "STABLE" | "COMPAT" | "UNKNOWN" |

### Scheduler Shadow Provider-Readiness Matrix (F3.13)

| Field | F3.12 | F3.13 |
|-------|-------|-------|
| `has_recommendation` | ✅ (STABLE) | ✅ (STABLE) |
| `has_facts` | ✅ (COMPAT) | ✅ (COMPAT) |
| `lifecycle_ready` | ✅ | ✅ |
| `control_ready` | ✅ | ✅ |
| `thermal_safe` | ✅ | ✅ |
| `runtime_loaded` | ❌ | ✅ (STABLE/COMPAT/UNKNOWN) |
| `runtime_current_model` | ❌ | ✅ (STABLE/COMPAT/UNKNOWN) |
| `runtime_initialized` | ❌ | ✅ (STABLE/COMPAT/UNKNOWN) |

### Co scheduler-shadow TEĎ UMÍ previewovat (F3.13)

1. **Provider runtime state** — explicitní facts o tom, co aktuálně běží
2. **Read-only facts surface** — žádné activation, žádné load_model()
3. **Compat fallback** — lifecycle_status dict jako COMPAT alternativa
4. **Unknown state** — graceful degradation když nic není dostupné

### Co scheduler-shadow STÁLE NESMÍ (hard boundaries)

1. **Activation** — žádné `acquire()`, `load_model()`, `unload()`
2. **Simulation** — žádné provider state machine simulation
3. **Provider framework** — žádné nové provider pool/selection framework
4. **Scheduler modification** — žádné změny scheduler decision loopu

### Triad Invariant (F3.13)

Stále přísně platí:
- **Recommendation fact** ≠ **Readiness preview** ≠ **Actual activation**
- Preview zůstává DIAGNOSTIC ONLY
- Neaktivuje žádné providery

### Guardraily Implementované v F3.13

1. **Žádné nové public API** — `collect_provider_runtime_facts()` je internal seam
2. **Žádné side effects** — pure function, žádné I/O
3. **Graceful degradation** — UNKNOWN když nic není dostupné
4. **Narrow surface** — pouze read-only facts, žádná activation
5. **Canonical owner** — `brain/model_manager.py` / `brain/model_lifecycle.py`

### Co NENÍ v tomto sprintu

- Provider activation
- load_model() integrace
- Provider state machine implementation
- Nový provider orchestrator
- scheduler_active režim

### Co chybí do plné provider activation parity (F4+)

1. **Actual provider activation** — skutečné `acquire()` / `release()` volání
2. **Provider pool awareness** — scheduler ví, které providery má k dispozici
3. **Provider selection** — scheduler vybírá provider podle workload
4. **Provider lifecycle management** — unload/reload strategie

### Co chybí do scheduler_active (F5+)

1. **Plná scheduler activation** — scheduler_active mód s actual dispatch
2. **Provider-aware dispatch** — dispatch přes aktivní provider pool
3. **Provider lifecycle orchestration** — scheduler řídí provider lifecycle

### Soubory Změněné v F3.13

| Soubor | Změna |
|--------|--------|
| `runtime/shadow_inputs.py` | Přidán `ProviderRuntimeFactsBundle` dataclass a `collect_provider_runtime_facts()` funkce |
| `runtime/shadow_pre_decision.py` | Přidány `runtime_loaded`, `runtime_current_model`, `runtime_initialized` do `ProviderReadinessPreview`; rozšířena `compose_pre_decision()` o `runtime_facts` parametr; aktualizovány všechny `ProviderReadinessPreview` konstruktory; `PreDecisionSummary.to_dict()` serializuje `runtime_facts` |
| `runtime/sprint_scheduler.py` | `consume_shadow_pre_decision()` nyní volá `get_model_lifecycle_status()` a předává `lifecycle_status` do `collect_provider_runtime_facts()` — COMPAT path místo UNKNOWN |
| `SHADOW_SCHEDULER_PARITY.md` | Přidána F3.13 sekce |
| `tests/probe_8vm/test_shadow_consumer_seam.py` | Přidány testy pro `TestProviderRuntimeFactsBundle` a `TestProviderRuntimeFactsIntegration` včetně `to_dict()` serializace a COMPAT/UNKNOWN stability |
