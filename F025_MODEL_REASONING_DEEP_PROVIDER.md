# F025: Model & Reasoning Plane — Deep Provider Inventory

**Datum:** 2026-04-01
**Scope:** `hledac/universal/` — MODEL + REASONING plane
**Zaměření:** Model split ownership, Windup reality, Reasoning pipeline, EnhancedResearch readiness

---

## 1. Executive Summary

### 1.1 Model Plane — 3-Way Split (SSOT)

| Model | Role | Canonical Owner | Bounded RAM |
|--------|------|-----------------|-------------|
| **Hermes-3-3B** | PLAN / DECIDE / SYNTHESIZE | `Hermes3Engine` (brain) | ~2 GB |
| **ModernBERT** | EMBED / DEDUP / ROUTING | `ModernBERTEngine` (brain) | ~400 MB |
| **GLiNER** | NER / ENTITY extraction | `GLiNEREngine` (brain) | ~200 MB |

**Model swap arbiter:** `ModelSwapManager` (Sprint 8Z) — race-free Qwen↔Hermes swap s drain timeout 3.0s.

### 1.2 Reasoning Plane — 4-Layer Pipeline

```
inference_engine     →  hypothesis_engine  →  insight_engine  →  synthesis_runner
(abductive reason)      (adversarial test)    (multi-level synth)   (WINDUP only)
```

**Canonical orchestrator:** žádný — každý engine běží independently, windup_engine aggreguje.

### 1.3 Key Finding: Windup Creates Its OWN Model World

`windup_engine.py:136` volá `SynthesisRunner(ModelLifecycle())` — **nevstřikuje** lifecycle z hlavního scheduleru. Vytváří izolovanou model world pro synthesis. Toto je ARCHITEKTURNÍ ROZKLAD, ne bug.

### 1.4 research_flow_decider.py — HELPER, Not Canonical

```python
# brain/research_flow_decider.py — header comment:
# "Používá se pouze jako pomocný nástroj pro hermes3_engine.
#  Pro decision making použijte CANONICAL verzi:
#      from hledac.universal.brain.hermes3_engine import Hermes3Engine"
```

### 1.5 enhanced_research.py — Dormant Canonical Provider

`UnifiedResearchEngine` je plně vybudovaný (2307 lines) s:
- Lazy-loaded tools (21+ intelligence tools)
- RRF fusion (ReciprocalRankFusion)
- Research depth levels: BASIC → ADVANCED → EXHAUSTIVE
- HybridRAG, QueryExpansion, BehaviorSimulator

**Blokátor:** Závislost na `intelligence` modulech, které nejsou v scope `universal/` (import guards fungují).

---

## 2. Model Split Owners — Reconciliation Table

| Model | Primary Owner | Phase Enforcer | Swap Arbiter | Memory Governor |
|-------|--------------|----------------|--------------|-----------------|
| Hermes-3-3B | `Hermes3Engine` | `ModelLifecycleManager` (capabilities.py) | `ModelSwapManager` | `resource_governor` |
| ModernBERT | `ModernBERTEngine` | `ModelLifecycleManager` | `ModelSwapManager` | `resource_governor` |
| GLiNER | `GLiNEREngine` | `ModelLifecycleManager` | N/A (stateless) | `resource_governor` |
| Qwen-0.5B (synthesis) | `ModelLifecycle` (synthesis_runner) | WINDUP-only guard | N/A | `evaluate_uma_state` |

### 2.1 Phase Model Enforcement (BRAIN/TOOLS/SYNTHESIS/CLEANUP)

**Canonical:** `capabilities.py` → `ModelLifecycleManager.enforce_phase_models()`

```python
# Canonical phase → model mapping (SSOT)
PHASE_MODEL_MAP = {
    "BRAIN": ["hermes", "modernbert"],
    "TOOLS": ["hermes"],
    "SYNTHESIS": ["hermes", "qwen"],
    "CLEANUP": [],
}
```

### 2.2 MoE Router — 2 Public Activation Functions

```python
# brain/moe_router.py — public API pro routing
route_synthesis(findings_count, has_gnn, memory_pressure, sprint_query)  # → "hermes3" | "inference" | "heuristic"
route_embedding(memory_pressure)  # → "ane_minilm" | "hash_fallback"
```

---

## 3. Windup Model/Reality — Own World vs. Injection

### 3.1 The Architecture Decision

```python
# runtime/windup_engine.py:133-136
runner = SynthesisRunner(ModelLifecycle())  # ← VLASTNÍ ModelLifecycle
if hasattr(scheduler, "_ioc_graph") and scheduler._ioc_graph is not None:
    runner.inject_graph(scheduler._ioc_graph)  # ← graf se injektuje
```

**Důsledek:** Windup synthesis běží v izolované model world. Nezávisí na hlavním scheduler lifecycle. Toto je záměr — synthesis potřebuje garantované prostředky.

### 3.2 SynthesisRunner — 3-Tier Model Discovery

```python
# brain/synthesis_runner.py:675-738
Tier 1: cached path from previous call
Tier 2: scan ~/.cache/huggingface/hub and ~/.mlx for existing models
Tier 3: download Qwen2.5-0.5B-Instruct-4bit (~400MB) then SmolLM2-135M fallback (~70MB)
```

### 3.3 Synthesis Guards (B.7)

```python
# WINDUP-only (nebo force_synthesis=True)
_is_windup_allowed(force: bool) → bool

# M1 8GB RSS > 5.5GiB guard
_check_uma_guard() → bool

# xgrammar guaranteed-JSON (Sprint 8UC B.1)
_run_xgrammar_generation(prompt) → tuple[dict | None, bool]
```

### 3.4 Synthesis Cascade (B.1)

```
xgrammar → streaming (mlx_lm) → constrained (Outlines) → None
```

### 3.5 Scorecard Data Flow

```
windup_engine.run_windup()
  → ranked_path (Parquet dedup)
  → gnn_predictions + anomalies (GNN inference)
  → ioc_graph_stats + top_nodes (DuckPGQ)
  → deduped findings (ANE semantic)
  → synthesis_result (MoE + SynthesisRunner)
  → hypotheses enqueued (HypothesisEngine)
  → DuckPGQ checkpoint
  → scorecard dict
```

---

## 4. Reasoning Pipeline Map

### 4.1 Complete Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     SPRINT LIFECYCLE                             │
│  WARMUP → ACTIVE → WINDUP                                        │
└──────────────┬──────────────────────┬───────────────────────────┘
               │                      │
               ▼                      ▼
     ┌─────────────────┐      ┌──────────────────┐
     │ inference_engine│      │  hypothesis_engine│
     │ (abductive)     │ ←──→ │  (adversarial)   │
     └────────┬────────┘      └────────┬─────────┘
              │                         │
              └──────────┬──────────────┘
                         ▼
              ┌──────────────────────┐
              │   insight_engine      │
              │  (multi-level synth) │
              └──────────┬───────────┘
                         │ WINDUP only
                         ▼
              ┌──────────────────────┐
              │  synthesis_runner     │
              │  (OSINTReport)       │
              └──────────────────────┘
```

### 4.2 Inference Engine (`brain/inference_engine.py`)

- **Bounded evidence:** MAX_GRAPH_NODES=10_000, MAX_EVIDENCE_ITEMS=10_000
- **LRU eviction** pro evidence i graph nodes
- **Abductive reasoning:** multi-hop inference
- **3-tier evidence/chaining**

### 4.3 Hypothesis Engine (`brain/hypothesis_engine.py`)

- **Adversarial Verification (Devil's Advocate):** `AdversarialVerifier` s `SourceCredibility`, `Contradiction`, `TemporalConsistency`
- **Falsification attempts:** Popperian approach
- **Bayesian confidence updating**
- **Sprint-aware:** `generate_sprint_hypotheses(findings, ioc_graph, max_hypotheses=3)`

### 4.4 Insight Engine (`brain/insight_engine.py`)

- **Multi-level synthesis:** Surface → Deep → Meta → Conceptual → Paradigm
- **Async execution** s bounded evidence

### 4.5 Synthesis Runner (`brain/synthesis_runner.py`)

- **WINDUP-only** (B.7 guard)
- **OSINTReport schema:** msgspec.Struct s IOC entities, threat actors, confidence
- **3-engine cascade:** xgrammar → streaming → constrained
- **RAG + GraphRAG context** (Sprint 8VA)

---

## 5. DeepResearch Provider Readiness

### 5.1 enhanced_research.py — UnifiedResearchEngine

| Capability | Status | Notes |
|------------|--------|-------|
| Lazy-loaded tools (21+) | ✅ | Import guards handle missing deps |
| RRF fusion | ✅ | `ReciprocalRankFusion` |
| Research depth levels | ✅ | BASIC / ADVANCED / EXHAUSTIVE |
| HybridRAG | ✅ | `RAGEngine` integration |
| QueryExpansion | ✅ | `IntelligentWordlistGenerator` |
| BehaviorSimulator | ✅ | Stealth mode |
| Academic Search | ✅ | ArXiv, CrossRef, Semantic Scholar |
| Archive Discovery | ✅ | Wayback, IPFS, GitHub history |
| Stealth Crawler | ✅ | Anti-detection crawling |
| Data Leak Hunter | ✅ | Breach detection |

### 5.2 Dependency Map

```
enhanced_research.py
  ├── intelligence.* (lazy, import guard)
  │     ├── AcademicSearchEngine
  │     ├── ArchiveDiscovery
  │     ├── StealthCrawler
  │     └── ...
  ├── utils.ranking.ReciprocalRankFusion
  ├── knowledge.rag_engine.RAGEngine
  └── layers.stealth_layer.BehaviorSimulator
```

### 5.3 Blokátory pro Fulfillment

| Blocker | Severity | Workaround |
|---------|----------|------------|
| `intelligence` modul není v `universal/` | MEDIUM | Import guard — degraded mode |
| Memory pressure (M1 8GB) | HIGH | Research depth = BASIC na AMA |
| Neexistence `Hermes3Engine` v scope | HIGH | Helper pouze, ne canonical |

---

## 6. Analyzer vs. Decider Reality

### 6.1 autonomous_analyzer.py — TOOL/SOURCE/MODEL Dispatcher

```python
# autonomous_analyzer.py — klíčové mappingy
TOOL_SOURCE_MAPPING = {
    "academic_search": {"arxiv", "crossref", "semantic_scholar"},
    "web_intelligence": {"surface", "deep", "dark"},
    "archive_discovery": {"wayback", "ipfs", "github"},
    ...
}

TOOL_MODEL_MAPPING = {
    "hermes": {"abductive_reasoning", "hypothesis_generation"},
    "modernbert": {"embed", "rerank", "dedup"},
    "gliner": {"ner", "entity_extraction"},
}
```

### 6.2 research_flow_decider.py — HELPER pro Hermes3Engine

```python
# brain/research_flow_decider.py — header (!!)
"""
Používá se pouze jako pomocný nástroj pro hermes3_engine.
Pro decision making použijte CANONICAL verzi:
    from hledac.universal.brain.hermes3_engine import Hermes3Engine
"""
```

**Reality:** `research_flow_decider` je helper, ne canonical. Rozhodování je v `Hermes3Engine`.

### 6.3 Hermes3Engine — Canonical Decision Surface

`Hermes3Engine` obsahuje:
- Decision logic (PLAN → EXECUTE → DECIDE)
- Phase-aware model loading
- Structured generation pro decision outputs
- Tool routing callback

---

## 7. Canonical Candidates

| Domain | Canonical | Helper/Deprecated |
|--------|-----------|-------------------|
| Model lifecycle | `model_lifecycle.py` | N/A |
| Hermes engine | `hermes3_engine.py` | N/A |
| Model swap | `model_swap_manager.py` | N/A |
| MoE routing | `moe_router.py` (activation functions) | N/A |
| Synthesis | `synthesis_runner.py` | N/A |
| Hypothesis | `hypothesis_engine.py` | N/A |
| Inference | `inference_engine.py` | N/A |
| Insight | `insight_engine.py` | N/A |
| DeepResearch | `enhanced_research.py` | N/A |
| Decision | `hermes3_engine.py` | `research_flow_decider.py` (HELPER) |
| Tool dispatch | `autonomous_analyzer.py` | N/A |

### 7.1 Unified Provider Candidates

| Capability | Current Provider | Canonical Candidate | Readiness |
|------------|------------------|---------------------|-----------|
| Research orchestration | `enhanced_research.py` | `UnifiedResearchEngine` | 85% (blokátory viz 5.3) |
| Tool-to-source dispatch | `autonomous_analyzer.py` | `AutonomousAnalyzer` | 70% |
| Decision making | `hermes3_engine.py` | `Hermes3Engine` | 90% |
| Hypothesis generation | `hypothesis_engine.py` | `HypothesisEngine` | 95% |

---

## 8. What Must NOT Be Unified Too Early

### 8.1 Model Lifecycle Isolation

**Never merge:** `SynthesisRunner(ModelLifecycle())` with main scheduler lifecycle.

**Why:** Windup potřebuje guarantee isolation — synthesis nesmí selhat kvůli scheduler memory pressure. Sloučení by vytvořilo coupling mezi WINDUP a ACTIVE fází.

### 8.2 Hypothesis Engine Independence

**Never merge:** `HypothesisEngine` adversarial verification s inference engine.

**Why:** AdversarialVerifier je self-contained s vlastním bounded storage (`MAX_SOURCE_ITEMS=5000`, `MAX_EVIDENCE_ITEMS=10000`). Integrace by vyžadovala redesign bounded eviction.

### 8.3 MoE Router Activation Functions

**Never merge:** `route_synthesis()` a `route_embedding()` do jedné funkce.

**Why:** Oddělené activation functions umožňují independent evolution. Sloučení by zvýšilo coupling mezi synthesis a embedding domain.

### 8.4 research_flow_decider vs. Hermes3Engine

**Never redirect:** Helper → Canonical přesměrování bez verify.

**Why:** `research_flow_decider.py` má vlastní DecisionEngine s rule-based a LLM-based strategiemi. Hermes3Engine decision surface může mít jiné invarianty.

---

## 9. Top 20 Konkrétních Ticketů

| # | Ticket | Component | Priority | Effort |
|---|--------|-----------|----------|--------|
| 1 | Hermès3Engine implementovat jako SAMOTNY singleton s load/unload cycle | brain/hermes3_engine | P0 | 8h |
| 2 | ModelSwapManager drain timeout snížit z 3.0s na 1.5s (M1 latency) | brain/model_swap_manager | P1 | 1h |
| 3 | WINDUP synthesis guard refactor — extrahovat do vlastní `SynthesisWINDUPGuard` | brain/synthesis_runner | P1 | 2h |
| 4 | ANE embedder lazy init — přidat `get_ane_embedder()` do `brain/ane_embedder.py` | brain/ane_embedder | P1 | 1h |
| 5 | HypothesisEngine adversarial verification LRU eviction test | brain/hypothesis_engine | P1 | 2h |
| 6 | DuckPGQ checkpoint v windup_engine — ověřit že `ioc_graph.checkpoint()` volá flush_buffers | runtime/windup_engine | P1 | 1h |
| 7 | MoE router KNOWN_MODEL_SIZES aktualizovat o Qwen-0.5B-Instruct-4bit | brain/moe_router | P2 | 0.5h |
| 8 | enhanced_research intelligence module import guard — doplnit fallback pro universal/ | enhanced_research | P2 | 2h |
| 9 | autonomous_analyzer TOOL_SOURCE_MAPPING rozšířit o "leaked" source | autonomous_analyzer | P2 | 1h |
| 10 | ModelLifecycle structured_generate fallback order — xgrammar→Outlines→mlx_lm | brain/model_lifecycle | P2 | 1h |
| 11 | HypothesisEngine `generate_sprint_hypotheses` → použít InferenceEngine abductive reasoning | brain/hypothesis_engine | P2 | 3h |
| 12 | insight_engine multi-level synthesis implementovat fallback pro M1 8GB | brain/insight_engine | P2 | 2h |
| 13 | DuckDB ghost_global.duckdb path constant — extrahovat do `paths.py` | brain/synthesis_runner | P3 | 0.5h |
| 14 | synthesis_runner RAG context token budget — explicitně dokumentovat limit 7200 znaků | brain/synthesis_runner | P3 | 0.5h |
| 15 | tot_integration Czech boost 1.75x — přidat explicitní test pro CS locale | tot_integration | P3 | 1h |
| 16 | research_flow_decider DecisionEngine → přidat `get_decision()` method pro Hermes3Engine | brain/research_flow_decider | P3 | 1h |
| 17 | ModelLifecycle _set_qos_background — ověřit že darwin-only fail-open funguje | brain/model_lifecycle | P3 | 0.5h |
| 18 | inference_engine MAX_GRAPH_NODES constant — přidat do `types.py` jako invariant | brain/inference_engine | P3 | 0.5h |
| 19 | synthesis_runner OSINTReport confidence scoring — přidat test coverage | brain/synthesis_runner | P3 | 1h |
| 20 | windup_engine scorecard — přidat `hypotheses_enqueued` count | runtime/windup_engine | P3 | 0.5h |

---

## 10. Exit Criteria — F6.5 / F11 / F14

### F6.5: Windup Model World Isolation

- [ ] `windup_engine` volá `SynthesisRunner(ModelLifecycle())` bez modification
- [ ] `SynthesisRunner` má vlastní 3-tier model discovery
- [ ] WINDUP guard (`_is_windup_allowed`) je testován
- [ ] RSS guard (`_check_uma_guard`) je testován s `evaluate_uma_state`
- [ ] DuckPGQ checkpoint volá `flush_buffers()` před persist

### F11: DeepResearch UnifiedResearchEngine Activation

- [ ] `UnifiedResearchEngine` má lazy-loaded tools s import guards
- [ ] RRF fusion (`ReciprocalRankFusion`) je integrován
- [ ] Research depth levels BASIC/ADVANCED/EXHAUSTIVE jsou funcionalní
- [ ] BehaviorSimulator stealth mode je dostupný
- [ ] Memory pressure adaptive depth degradation funguje

### F14: Model Swap Race-Free Operation

- [ ] `ModelSwapManager.async_swap_to()` drain timeout = 1.5s
- [ ] Strict ordering: drain → unload → load je enforced
- [ ] Best-effort rollback na swap failure
- [ ] `is_safe_to_clear_emergency()` preconditions jsou testované
- [ ] No race condition mezi swap a inference requests

---

## What This Changes in Integration Order

### Before This Analysis

```
EnhancedResearch → autonomous_analyzer → research_flow_decider → Hermes3Engine
                                    (HELPER ↑)
```

### After This Analysis

```
1. canonical: Hermes3Engine (decision surface)
2. canonical: HypothesisEngine (adversarial verification)
3. canonical: UnifiedResearchEngine (enhanced_research.py)
4. HELPER: research_flow_decider (do not depend on for integration)
5. HELPER: autonomous_analyzer (dispatch only, no reasoning)
```

**Integration order:**
1. Nejprve stabilizovat `Hermes3Engine` decision surface
2. Pak integrovat `HypothesisEngine` adversarial verification do inference pipeline
3. Pak aktivovat `UnifiedResearchEngine` (enhanced_research) s lazy tools
4. Nikdy nespoléhat na `research_flow_decider` pro canonical rozhodování

---

## Appendix: Key File References

| File | Role | Lines |
|------|------|-------|
| `brain/model_lifecycle.py` | Model lifecycle SSOT | 779 |
| `brain/synthesis_runner.py` | Windup synthesis | 1034 |
| `brain/moe_router.py` | MoE routing | 860 |
| `brain/hypothesis_engine.py` | Adversarial hypothesis | 2581 |
| `brain/inference_engine.py` | Abductive reasoning | ~1200 |
| `enhanced_research.py` | DeepResearch provider | 2307 |
| `autonomous_analyzer.py` | Tool dispatcher | ~1500 |
| `runtime/windup_engine.py` | WINDUP orchestration | 245 |
