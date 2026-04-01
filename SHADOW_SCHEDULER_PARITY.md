# Shadow Scheduler Parity — F3.5 Fact Parity (Sprint 8VK)

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
| `legacy_runtime` | Dnešní runtime path — přímé volání z __main__.py | ✅ YES | — |
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

## Co ještě chybí do plné Decision Parity (F4+)

1. **Tool Execution Decision Parity** — porovnání jak scheduler rozhoduje o tool selection vs runtime
2. **Provider Activation Parity** — které LLM providery se aktivují a kdy
3. **Windup Execution Parity** — co windup skutečně dělá (nejen facts o tom, ale execution flow)
4. **Fetch/Runtime Side Effect Parity** — network calls, rate limiting, retry decisions
5. **Findings Write Parity** — co se zapisuje do knowledge store a jak

---

## Co ještě chybí do scheduler_active (F5+)

1. **Actual Scheduler Decision Loop** — scheduler active musí řídit workflow, ne jen číst facts
2. **Scheduler-owned State** — dnes žádný persistent scheduler state (správně, to je deferred)
3. **Tool Dispatch Integration** — napojení na tool_registry pro skutečné volání
4. **Windup Engine Ownership** — scheduler_active musí řídit windup, ne jen facts o něm
5. **Branch/Provider Activation** — scheduler_active musí aktivovat branches a providers

---

## Soubory Změněné v F3.5

| Soubor |Změna |
|--------|-------|
| `runtime/shadow_inputs.py` | Přidán `RuntimeMode` s `get_current()`, `is_shadow_mode()`, `is_active_mode()`, `is_legacy_mode()` |
| `runtime/shadow_parity.py` | **NOVÝ** — `ParityArtifact`, `run_shadow_parity()`, `_check_phase_field_merge()` |
| `tests/probe_8vk_shadow_parity.py` | **NOVÝ** — 33 testů pro fact parity invarianty |
| `SHADOW_SCHEDULER_PARITY.md` | **NOVÝ** — tato dokumentace |

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

### Phase Separation (F3.6) — STRIKTNĚ ODDĚLENÉ

`PreDecisionSummary.lifecycle` má TŘI oddělené atributy:
- `workflow_phase` — BOOT|WARMUP|ACTIVE|WINDUP|EXPORT|TEARDOWN
- `control_phase_mode` — normal|prune|panic
- `windup_local_mode` — synthesis|structured|minimal (pouze v WINDUP)

Žádné slité `phase` pole neexistuje.

### Soubory Změněné v F3.6

| Soubor | Změna |
|--------|-------|
| `runtime/shadow_pre_decision.py` | **NOVÝ** — `compose_pre_decision()`, `PreDecisionSummary`, DiffTaxonomy |
| `tests/probe_8vl_shadow_pre_decision/` | **NOVÝ** — 25 testů pro pre-decision invarianty |
| `SHADOW_SCHEDULER_PARITY.md` | Aktualizován — F3.6 sekce |

### Co stále zůstává DEFERRED

| Co | Proč deferred |
|----|---------------|
| Decision parity | Vyžaduje plný scheduler_active režim |
| Scheduler_active | Vyžaduje cutover + parity verification + rollback plán |
| Tool execution parity | Nesmí do pre-decision layer |
| Provider activation parity | Nesmí do pre-decision layer |
| Windup execution parity | Nesmí do pre-decision layer |
| Findings write parity | Nesmí do pre-decision layer |

### Co chybí do prvního runtime behind-flag hooku

1. **Shadow inputs injection point** — runtime musí injectnout `ParityArtifact` do pre-decision consumer
2. **Orchestrator integration** — kde přesně se `compose_pre_decision()` volá v lifecycle
3. **Decision gate** — za jakých podmínek by pre-decision summary ovlivnil scheduler decisions (zatím NIC)
4. **Flag mechanism** — `HLEDAC_RUNTIME_MODE=scheduler_shadow` aktivuje pre-decision logging

### Co chybí do scheduler_active

1. **Actual Scheduler Decision Loop** — scheduler_active musí řídit workflow, ne jen číst facts
2. **Scheduler-owned State** — dnes žádný persistent scheduler state
3. **Tool Dispatch Integration** — napojení na tool_registry
4. **Windup Engine Ownership** — scheduler_active musí řídit windup
5. **Branch/Provider Activation** — scheduler_active musí aktivovat branches a providers

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

### Phase Separation (F3.6) — STRIKTNĚ ODDĚLENÉ

`PreDecisionSummary.lifecycle` má TŘI oddělené atributy:
- `workflow_phase` — BOOT|WARMUP|ACTIVE|WINDUP|EXPORT|TEARDOWN
- `control_phase_mode` — normal|prune|panic
- `windup_local_mode` — synthesis|structured|minimal (pouze v WINDUP)

Žádné slité `phase` pole neexistuje.

### Soubory Změněné v F3.6

| Soubor | Změna |
|--------|-------|
| `runtime/shadow_pre_decision.py` | **NOVÝ** — `compose_pre_decision()`, `PreDecisionSummary`, DiffTaxonomy |
| `tests/probe_8vl_shadow_pre_decision/` | **NOVÝ** — 25 testů pro pre-decision invarianty |
| `SHADOW_SCHEDULER_PARITY.md` | Aktualizován — F3.6 sekce |

### Co stále zůstává DEFERRED

| Co | Proč deferred |
|----|---------------|
| Decision parity | Vyžaduje plný scheduler_active režim |
| Scheduler_active | Vyžaduje cutover + parity verification + rollback plán |
| Tool execution parity | Nesmí do pre-decision layer |
| Provider activation parity | Nesmí do pre-decision layer |
| Windup execution parity | Nesmí do pre-decision layer |
| Findings write parity | Nesmí do pre-decision layer |

### Co chybí do prvního runtime behind-flag hooku

1. **Shadow inputs injection point** — runtime musí injectnout `ParityArtifact` do pre-decision consumer
2. **Orchestrator integration** — kde přesně se `compose_pre_decision()` volá v lifecycle
3. **Decision gate** — za jakých podmínek by pre-decision summary ovlivnil scheduler decisions (zatím NIC)
4. **Flag mechanism** — `HLEDAC_RUNTIME_MODE=scheduler_shadow` aktivuje pre-decision logging

### Co chybí do scheduler_active

1. **Actual Scheduler Decision Loop** — scheduler_active musí řídit workflow, ne jen číst facts
2. **Scheduler-owned State** — dnes žádný persistent scheduler state
3. **Tool Dispatch Integration** — napojení na tool_registry
4. **Windup Engine Ownership** — scheduler_active musí řídit windup
5. **Branch/Provider Activation** — scheduler_active musí aktivovat branches a providers

---

## Guardraily Implementované

1. **Žádné network imports** — shadow_parity.py a shadow_inputs.py neimportují aiohttp, httpx, curl_cffi, nodriver
2. **Pure functions** — collect_* funkcí nemají side effects
3. **Žádné asyncio.sleep** — run_shadow_parity je synchroní
4. **Žádné nové state soubory** — test kontroluje suspicous naming
5. **Local dataclasses stay local** — LifecycleSnapshotBundle atd. nejsou v types.py
6. **Phase fields separated** — workflow_phase, control_phase_mode, windup_local_mode jsou vždy oddělené

7. **Žádné network imports (F3.6)** — shadow_pre_decision.py neimportuje aiohttp, httpx, curl_cffi, nodriver
8. **Pure function (F3.6)** — compose_pre_decision() nemá side effects
9. **Žádné SprintScheduler modifikace (F3.6)** — pre-decision layer NESMÍ přidávat field na SprintScheduler
10. **Žádné nové caches (F3.6)** — pre-decision layer nepřidává žádné cache state
11. **Žádné nové background tasks (F3.6)** — pre-decision layer neruší žádné bg tasks
7. **Default unchanged** — bez env var běží legacy_runtime
