# Architektonická Analýza: hledac/universal

**Datum analýzy:** 2026-02-13
**Verze:** v1.0
**Analytik:** Claude Code + Ralph Loop
**Cíl:** Kompletní architektonická analýza autonomního výzkumného systému

---

## 🎯 EXECUTIVE SUMMARY

Systém `hledac/universal` je **plně autonomní multi-agentní výzkumná platforma** s pokročilými schopnostmi OSINT, AI inference a bezpečnostní analýzy. Jádrem je `FullyAutonomousOrchestrator` (4500+ řádků) - komplexní fasáda která deleguje operace na 8 interních manažerů (`_StateManager`, `_MemoryManager`, `_BrainManager`, `_SecurityManager`, `_ForensicsManager`, `_ToolRegistryManager`, `_ResearchManager`, `_SynthesisManager`).

**Klíčová architektonická rozhodnutí:**
- **M1 8GB Optimalizace:** Sekvenční načítání modelů (nikdy nejsou 2 velké modely současně v RAM), agresivní garbage collection, kontext swap mezi fázemi
- **Lazy Loading:** Všechny heavy komponenty se načítají na vyžádání přes `_LazyImportCoordinator`
- **Layered Architecture:** 13 vrstev (communication, coordination, ghost, memory, privacy, research, security, stealth...)
- **Coordinator Pattern:** 20+ specializovaných koordinátorů pro různé domény (research, security, swarm, quantum...)

**Hlavní rizika:**
1. **God Object:** Orchestrator má 4500+ řádků, i po refaktoringu na interní koordinátory
2. **Duplicitní logika:** Více implementací entity extraction (GLiNER vs regex vs custom)
3. **Memory lifecycle:** Není zcela jasné kdy se modely skutečně uvolňují z MLX cache
4. **Circular import potential:** Komplexní síť lazy importů může vést k problémům

---

## 📋 TOP 10 PRIORITY TODO (Seřazeno podle dopadu)

| # | Priorita | Problém | Dopad | Navrhovaný fix |
|---|----------|---------|-------|----------------|
| 1 | 🔴 Kritická | `autonomous_orchestrator.py` 4500+ řádků | Nedržitelná komplexita, dlouhé načítání | Rozdělit na samostatné moduly podle manažerů |
| 2 | 🔴 Kritická | Duplicitní entity extraction | Nekonzistentní výsledky, plýtvání RAM | Sjednotit pod `brain/ner_engine.py` |
| 3 | 🟠 Vysoká | Nejednoznačný memory lifecycle | Memory leaky na M1 8GB | Explicitní context manager pro modely |
| 4 | 🟠 Vysoká | `_LazyImportCoordinator` vs manuální lazy load | Dvě různé konvence | Refactor vše na `_LazyImportCoordinator` |
| 5 | 🟡 Střední | 20+ koordinátorů, mnoho neaktivních | Zmatená odpovědnost, dead code | Audit koordinátorů, označit nepoužité |
| 6 | 🟡 Střední | Duplicitní embed logika | `utils/semantic.py` vs `brain/` | Consolidace do `brain/embeddings/` |
| 7 | 🟡 Střední | Testovací soubory v produkčním kódu | Zmatek v struktuře | Přesunout `test_*.py` do `tests/` |
| 8 | 🟢 Nízká | Vulture nalezl 80+ unused imports | Technický dluh | Pročistit importy |
| 9 | 🟢 Nízká | Chybějící type hints v koordinátorech | Horší IDE support | Postupně doplnit |
| 10 | 🟢 Nízká | Inconsistent error handling | Někde `try/except/pass` | Standardizovat na `ResilientExecutionManager` |

---

## 🗑️ WHAT TO DELETE (Safe k odstranění)

**High Confidence (Safe odstranit):**
1. `infrastructure/outdated/memory_coordinator.py` - explicitně označen jako outdated
2. Všechny `test_*.py` soubory v kořenovém adresáři - patří do `tests/`
3. Unused imports podle vulture (viz sekce Reality Check)

**Medium Confidence (Prověřit):**
1. `coordinators/quantum_coordinator.py` - pokud není použit v hlavním workflow
2. `coordinators/nas_coordinator.py` - Neural Architecture Search, možná experimentální
3. `coordinators/federated_learning_coordinator.py` - pokud není aktivně používán
4. `graph/quantum_pathfinder.py` - pokud není volán z orchestrátoru

**Low Confidence (Potřeba analýzy):**
1. Některé vrstvy v `layers/` - prověřit které jsou skutečně používané
2. Část `intelligence/` modulů - mnoho specializovaných modulů

---

## 🏗️ C4-STYLE ARCHITEKTURA

### Level 1: System Context

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SYSTEM CONTEXT                                       │
│                    Autonomous Research Platform                             │
└─────────────────────────────────────────────────────────────────────────────┘

     ┌──────────┐      ┌──────────────┐      ┌─────────────┐
     │  User    │──────│   CLI/API    │──────│  Orchestrator│
     │  Query   │      │   Interface  │      │  (Universal) │
     └──────────┘      └──────────────┘      └──────┬──────┘
                                                    │
                       ┌────────────────────────────┼────────────────────────────┐
                       │                            │                            │
                       ▼                            ▼                            ▼
              ┌────────────────┐         ┌──────────────────┐         ┌──────────────────┐
              │   External     │         │   AI/ML Models   │         │   Data Sources   │
              │   APIs         │         │   (MLX/Hermes3)  │         │   (Web/Academic) │
              │   (Kimi/etc)   │         │   ModernBERT     │         │   Dark Web/Archives│
              └────────────────┘         │   GLiNER         │         └──────────────────┘
                                          └──────────────────┘
```

**Vstupy:**
- Uživatelské dotazy (text)
- Konfigurace (YAML/JSON)
- Data k analýze (dokumenty, URL, hashe)

**Výstupy:**
- Výzkumné reporty
- Entity extrakce
- Bezpečnostní analýzy
- Grafové vizualizace

**Hranice:**
- Externí API volání (Kimi, vyhledávače)
- Model inference (MLX, PyTorch)
- File system (cache, knowledge graph)

---

### Level 2: Containers/Subsystems

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                           CONTAINERS / SUBSYSTEMS                                     │
└──────────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│   🧠 BRAIN           │  │   🎛️ COORDINATORS    │  │   🔧 UTILS           │
│   (AI/ML Core)       │  │   (Orchestration)    │  │   (Helpers)          │
├──────────────────────┤  ├──────────────────────┤  ├──────────────────────┤
│ • model_manager.py   │  │ • base.py            │  │ • deduplication.py   │
│ • decision_engine.py │  │ • agent_coordination │  │ • semantic.py        │
│ • hermes3_engine.py  │  │ • research_optimizer │  │ • entity_extractor.py│
│ • ner_engine.py      │  │ • execution_coord    │  │ • query_expansion.py │
│ • moe_router.py      │  │ • (20+ coordinators) │  │ • intelligent_cache  │
│ • distillation.py    │  │                      │  │ • validation.py      │
│ • hypothesis.py      │  │                      │  │ • workflow_engine.py │
│ • insight.py         │  │                      │  │                      │
└──────────┬───────────┘  └──────────┬───────────┘  └──────────┬───────────┘
           │                         │                         │
           └─────────────────────────┼─────────────────────────┘
                                     │
                                     ▼
┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│   🧩 LAYERS          │  │   📚 KNOWLEDGE       │  │   🕵️ INTELLIGENCE   │
│   (Architecture)     │  │   (RAG/Graphs)       │  │   (OSINT Modules)    │
├──────────────────────┤  ├──────────────────────┤  ├──────────────────────┤
│ • communication      │  │ • rag_engine.py      │  │ • web_intelligence   │
│ • coordination       │  │ • graph_rag.py       │  │ • academic_search    │
│ • ghost_layer        │  │ • graph_builder.py   │  │ • dark_web_intel     │
│ • memory_layer       │  │ • entity_linker.py   │  │ • blockchain_analyzer│
│ • privacy_layer      │  │ • atomic_storage.py  │  │ • document_intel     │
│ • research_layer     │  │ • context_graph.py   │  │ • (21+ modules)      │
│ • security_layer     │  │ • persistent_layer   │  │                      │
│ • stealth_layer      │  │                      │  │                      │
└──────────────────────┘  └──────────────────────┘  └──────────────────────┘

┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│   🛡️ SECURITY        │  │   🔬 FORENSICS       │  │   🚀 EXECUTION       │
│   (Protection)       │  │   (Analysis)         │  │   (Runtime)          │
├──────────────────────┤  ├──────────────────────┤  ├──────────────────────┤
│ • audit.py           │  │ • metadata_extractor │  │ • ghost_executor     │
│ • ram_vault.py       │  │                      │  │                      │
│ • vault_manager.py   │  │                      │  │                      │
│ • pii_gate.py        │  │                      │  │                      │
│ • stego_detector.py  │  │                      │  │                      │
│ • (12 modules)       │  │                      │  │                      │
└──────────────────────┘  └──────────────────────┘  └──────────────────────┘
```

---

### Level 3: Components (Klíčové třídy)

#### Hlavní Orchestrátor

| Komponent | Odpovědnost | Kdo volá | Vstupy/Výstupy | Stav |
|-----------|-------------|----------|----------------|------|
| `FullyAutonomousOrchestrator` | Hlavní fasáda, deleguje na manažery | CLI/API | Query → Report | ✅ **USED** |
| `_StateManager` | Stav orchestrátoru, fázová logika | Orchestrator | Events → State | ✅ **USED** |
| `_MemoryManager` | Cache, RAG, Knowledge Graph | Orchestrator | Data → Cached | ✅ **USED** |
| `_BrainManager` | AI modely, inference | Orchestrator | Prompts → Results | ✅ **USED** |
| `_SecurityManager` | Bezpečnost, stealth, privacy | Orchestrator | Data → Secured | ✅ **USED** |
| `_ForensicsManager` | Forenzní analýza | Orchestrator | Files → Metadata | ⚠️ **UNCERTAIN** |
| `_ToolRegistryManager` | Registr nástrojů | Orchestrator | Tool calls → Results | ✅ **USED** |
| `_ResearchManager` | Výzkumné operace | Orchestrator | Query → Findings | ✅ **USED** |
| `_SynthesisManager` | Syntéza reportů | Orchestrator | Findings → Report | ✅ **USED** |
| `_IntelligenceManager` | Inteligenční moduly | Orchestrator | Data → Intelligence | ⚠️ **UNCERTAIN** |

#### Brain (AI/ML)

| Komponent | Odpovědnost | Kdo volá | Vstupy/Výstupy | Stav |
|-----------|-------------|----------|----------------|------|
| `ModelManager` | Životní cyklus modelů | `_BrainManager` | Model name → Instance | ✅ **USED** |
| `Hermes3Engine` | LLM inference | `ModelManager` | Prompt → Response | ✅ **USED** |
| `DecisionEngine` | Rozhodovací logika | `_BrainManager` | Context → Decision | ✅ **USED** |
| `NEREngine` | Entity extraction | Various | Text → Entities | ✅ **USED** |
| `MoERouter` | Mixture of Experts routing | `_BrainManager` | Input → Expert | ⚠️ **UNCERTAIN** |
| `DistillationEngine` | Knowledge distillation | Voláno? | Teacher → Student | ❓ **MAYBE UNUSED** |
| `InferenceEngine` | Multi-hop reasoning | Voláno? | Query → Reasoning | ❓ **MAYBE UNUSED** |
| `InsightEngine` | Insight generation | `_ResearchManager` | Data → Insights | ✅ **USED** |
| `HypothesisEngine` | Hypothesis testing | Voláno? | Hypothesis → Result | ❓ **MAYBE UNUSED** |

#### Coordinators (20 modulů)

| Koordinátor | Účel | Stav |
|-------------|------|------|
| `AgentCoordinationEngine` | Koordinace agentů | ✅ **USED** (importován v orchestrátoru) |
| `ResearchOptimizer` | Optimalizace výzkumu | ✅ **USED** (importován) |
| `PrivacyEnhancedResearch` | Privacy-aware výzkum | ✅ **USED** (importován) |
| `ExecutionCoordinator` | Vykonávání úloh | ❓ **UNCERTAIN** |
| `SecurityCoordinator` | Bezpečnostní koordinace | ❓ **UNCERTAIN** |
| `SwarmCoordinator` | Swarm intelligence | ❓ **UNCERTAIN** |
| `QuantumCoordinator` | Kvantové výpočty | ❓ **LIKELY UNUSED** |
| `NASCoordinator` | Neural Architecture Search | ❓ **LIKELY UNUSED** |
| `FederatedLearningCoordinator` | Federated learning | ❓ **LIKELY UNUSED** |
| `MemoryCoordinator` | Správa paměti | ❓ **UNCERTAIN** |
| `MetaReasoningCoordinator` | Meta-reasoning | ❓ **UNCERTAIN** |
| `MonitoringCoordinator` | Monitoring | ❓ **UNCERTAIN** |
| `MultimodalCoordinator` | Multimodalní data | ❓ **UNCERTAIN** |
| `PerformanceCoordinator` | Výkon | ❓ **UNCERTAIN** |
| `ResourceAllocator` | Alokace zdrojů | ❓ **UNCERTAIN** |
| `ValidationCoordinator` | Validace | ❓ **UNCERTAIN** |
| `BenchmarkCoordinator` | Benchmarking | ❓ **LIKELY UNUSED** |
| `AdvancedResearchCoordinator` | Pokročilý výzkum | ❓ **UNCERTAIN** |
| `ResearchCoordinator` | Základní výzkum | ❓ **UNCERTAIN** |
| `ResearchOptimizer` | Optimalizace | ✅ **USED** |

---

### Level 4: Code-Level Notes

#### Kritické soubory (klíčové pro funkčnost)

| Soubor | Řádků | Důležitost | Poznámky |
|--------|-------|------------|----------|
| `autonomous_orchestrator.py` | ~4500 | 🔴 **Kritická** | Hlavní vstupní bod, příliš velký |
| `brain/model_manager.py` | ~200 | 🟢 **Vysoká** | Řídí memory lifecycle na M1 |
| `brain/hermes3_engine.py` | ~150 | 🟢 **Vysoká** | Hlavní LLM inference |
| `coordinators/base.py` | ~200 | 🟡 **Střední** | Base class pro koordinátory |
| `utils/entity_extractor.py` | ~? | 🟢 **Vysoká** | Entity extraction (duplicitní?) |
| `brain/ner_engine.py` | ~? | 🟢 **Vysoká** | NER s GLiNER (duplicitní?) |
| `types.py` | ~? | 🟢 **Vysoká** | Všechny dataclass definice |
| `config.py` | ~? | 🟢 **Vysoká** | Konfigurační systém |

#### Rizikové části kódu

**1. Memory Management (M1 8GB)**
```python
# brain/model_manager.py:111-150
# ModelManager.acquire() - sekvenční načítání
# Riziko: asyncio.run() v synchr. kontextu může být problém
```

**2. God Object Anti-pattern**
```python
# autonomous_orchestrator.py
# FullyAutonomousOrchestrator má 4500+ řádků
# Příliš mnoho odpovědností v jedné třídě
```

**3. Lazy Loading Inconsistency**
```python
# Dvě konvence:
# 1) _LazyImportCoordinator (nový, centrální)
# 2) Manuální funkce _load_*() (starší, rozptýlené)
# Potřeba konsolidace
```

**4. Async/Sync Mix**
```python
# Někde se volá asyncio.run() uvnitř sync metod
# Potenciální problém s event loop v embedded kontextu
```

---

## 🔍 REALITY CHECK: CO JE OPRAVDU POUŽÍVANÉ

### Analýza importů z autonomous_orchestrator.py

**Direct importy (CORE):**
```python
# Konfigurace a typy
from .config import UniversalConfig, create_config
from .types import (...)  # Všechny typy

# Vrstvy
from .layers import (CommunicationLayer, CoordinationLayer, GhostLayer,
                     MemoryLayer, PrivacyLayer, ResearchLayer,
                     SecurityLayer, StealthLayer)

# Koordinátory (pouze 3 z 20!)
from .coordinators.agent_coordination_engine import AgentCoordinationEngine
from .coordinators.research_optimizer import ResearchOptimizer
from .coordinators.privacy_enhanced_research import PrivacyEnhancedResearch

# Utils (pouze 5 z 19)
from .utils.query_expansion import QueryExpander
from .utils.ranking import ReciprocalRankFusion
from .utils.intelligent_cache import IntelligentCache
from .utils.validation import ValidationSeverity
from .utils.language import LanguageDetector

# Knowledge (všechny)
from .knowledge.rag_engine import RAGEngine
from .knowledge.atomic_storage import AtomicJSONKnowledgeGraph
from .knowledge.context_graph import ContextGraph

# Brain (pouze 2 z 9)
from .brain.decision_engine import DecisionEngine
from .brain.hermes3_engine import Hermes3Engine
```

**Lazy loaded (OPTIONAL):**
- `ArchiveDiscovery` - načítáno dynamicky
- `StealthCrawler` - načítáno dynamicky
- `StegoDetector` - načítáno dynamicky
- `TemporalAnalyzer` - načítáno dynamicky
- `InsightEngine` - načítáno dynamicky
- `PersonalPrivacyManager` - načítáno dynamicky
- `DeepResearchSecurity` - načítáno dynamicky
- `ResearchObfuscator` - načítáno dynamicky
- `SelfHealingManager` - přes `_LazyImportCoordinator`
- `ExposedServiceHunter` - přes `_LazyImportCoordinator`
- `InferenceEngine` - přes `_LazyImportCoordinator`
- `RelationshipDiscoveryEngine` - přes `_LazyImportCoordinator`
- `TemporalArchaeologist` - přes `_LazyImportCoordinator`
- `PatternMiningEngine` - přes `_LazyImportCoordinator`
- `QuantumInspiredPathFinder` - přes `_LazyImportCoordinator`
- `DistillationEngine` - přes `_LazyImportCoordinator`
- `AgentMetaOptimizer` - přes `_LazyImportCoordinator`

### Seznamy používanosti

#### ✅ USED IN MAIN WORKFLOW (z orchestrátoru)

**Core:**
- `config.py`, `types.py` - základní konfigurace
- `layers/*` - všech 8 vrstev je importováno

**Brain (2/9):**
- `brain/model_manager.py`
- `brain/hermes3_engine.py`
- `brain/decision_engine.py`

**Coordinators (3/20):**
- `coordinators/agent_coordination_engine.py`
- `coordinators/research_optimizer.py`
- `coordinators/privacy_enhanced_research.py`

**Utils (5/19):**
- `utils/query_expansion.py`
- `utils/ranking.py`
- `utils/intelligent_cache.py`
- `utils/validation.py`
- `utils/language.py`

**Knowledge (3/8):**
- `knowledge/rag_engine.py`
- `knowledge/atomic_storage.py`
- `knowledge/context_graph.py`

**Intelligence (lazy loaded, conditional):**
- `intelligence/archive_discovery` - pokud dostupné
- `intelligence/stealth_crawler` - pokud dostupné
- `intelligence/temporal_analysis` - pokud dostupné

#### ⚠️ POSSIBLY UNUSED / UNCERTAIN

**Brain (6/9 možná nepoužito):**
- `brain/distillation_engine.py` - přes lazy load, nejisté použití
- `brain/inference_engine.py` - přes lazy load
- `brain/hypothesis_engine.py` - přes lazy load
- `brain/insight_engine.py` - možná použito v research
- `brain/moe_router.py` - MoE routing, nejisté
- `brain/ner_engine.py` - možná duplicitní s `utils/entity_extractor.py`

**Coordinators (17/20 pravděpodobně nepoužito):**
- `coordinators/execution_coordinator.py`
- `coordinators/federated_learning_coordinator.py`
- `coordinators/memory_coordinator.py`
- `coordinators/meta_reasoning_coordinator.py`
- `coordinators/monitoring_coordinator.py`
- `coordinators/multimodal_coordinator.py`
- `coordinators/nas_coordinator.py`
- `coordinators/performance_coordinator.py`
- `coordinators/quantum_coordinator.py`
- `coordinators/resource_allocator.py`
- `coordinators/security_coordinator.py`
- `coordinators/swarm_coordinator.py`
- `coordinators/validation_coordinator.py`
- `coordinators/benchmark_coordinator.py`
- `coordinators/advanced_research_coordinator.py`
- `coordinators/research_coordinator.py`

**Utils (14/19 nejisté):**
- `utils/bloom_filter.py`
- `utils/deduplication.py` - možná použito
- `utils/encryption.py`
- `utils/entity_extractor.py` - DUPLICITNÍ s brain/ner_engine
- `utils/execution_optimizer.py`
- `utils/filtering.py`
- `utils/lazy_imports.py`
- `utils/performance_monitor.py`
- `utils/predictive_planner.py`
- `utils/rate_limiter.py`
- `utils/robots_parser.py`
- `utils/semantic.py` - možná duplicitní
- `utils/tech_detection.py`
- `utils/workflow_engine.py`

**Security (11/12 nejisté):**
- Většina security modulů je lazy loaded, použití závisí na konfiguraci

#### ❌ NOT USED / LEGACY

- `infrastructure/outdated/memory_coordinator.py` - explicitně označen

### Vulture Report (Dead Code Detection)

**Nejvýznamnější nálezy:**

```
autonomous_orchestrator.py:52: unused import 'Type' (90% confidence)
autonomous_orchestrator.py:61: unused import 'mlx_generate' (90% confidence)
autonomous_orchestrator.py:4202: unreachable code after 'try' (100% confidence)

brain/inference_engine.py:32: unused import 'heapq' (90% confidence)
brain/moe_router.py:253: unused import 'nullcontext' (90% confidence)

coordinators/advanced_research_coordinator.py:71: unused variable 'target_url'
coordinators/base.py:26: unused import 'Generic' (90% confidence)
coordinators/security_coordinator.py:1131: unreachable code after 'return'

layers/privacy_layer.py:33-60: mnoho unused imports (BrowserFingerprint, TorConfig, ...)

intelligence/*: mnoho unused imports v různých modulech
security/*: některé unused imports
utils/execution_optimizer.py: unused imports (KMeans, DaskClusterManager, ...)
```

---

## ⚠️ DUPLICITY & ARCHITECTURAL SMELLS

### Duplicity

#### 1. Entity Extraction (3 implementace!)

| Implementace | Soubor | Stav |
|--------------|--------|------|
| GLiNER-based | `brain/ner_engine.py` | Lazy loaded |
| Regex-based | `utils/entity_extractor.py` | ? |
| Custom | `intelligence/pattern_mining.py` | ? |

**Dopad:** Nekonzistentní výsledky, zmatek který použít, větší memory footprint.

**Fix:** Sjednotit pod `brain/ner_engine.py` s fallback strategiemi.

#### 2. Embedding/Semantic Logika

| Implementace | Soubor | Účel |
|--------------|--------|------|
| `utils/semantic.py` | Utility | Semantic similarity |
| `brain/` | Brain | Model-based embeddings |
| `knowledge/graph_rag.py` | Knowledge | Graph embeddings |

**Dopad:** Není jasné která vrstva je zodpovědná za embeddování.

**Fix:** Přesunout všechny embed operace do `brain/embeddings/`.

#### 3. Deduplication Logika

| Implementace | Soubor |
|--------------|--------|
| `utils/deduplication.py` | Utils |
| `utils/bloom_filter.py` | Utils |
| `intelligence/relationship_discovery.py` | Intelligence |

#### 4. Decision/Routing Logika

| Implementace | Soubor |
|--------------|--------|
| `brain/decision_engine.py` | Brain |
| `brain/moe_router.py` | Brain |
| `intelligence/decision_engine.py` | Intelligence |
| `utils/predictive_planner.py` | Utils |

### Architectural Smells

#### 1. God Object

**Kde:** `autonomous_orchestrator.py:FullyAutonomousOrchestrator`
**Velikost:** 4500+ řádků
**Dopad:** Nedržitelný kód, dlouhé načítání, obtížné testování
**Fix:** Rozdělit na samostatné moduly:
```
orchestrator/
  ├── __init__.py
  ├── main.py              # Jen fasáda
  ├── state_manager.py     # _StateManager
  ├── memory_manager.py    # _MemoryManager
  ├── brain_manager.py     # _BrainManager
  ├── security_manager.py  # _SecurityManager
  ├── tool_manager.py      # _ToolRegistryManager
  ├── research_manager.py  # _ResearchManager
  └── synthesis_manager.py # _SynthesisManager
```

#### 2. Inconsistent Lazy Loading

**Problém:** Dvě různé konvence pro lazy loading:
- `_LazyImportCoordinator` (nový, centrální)
- Manuální funkce `_load_*()` (starší, rozptýlené)

**Dopad:** Zmatek, duplicitní kód, těžší maintenance
**Fix:** Refactor všechny manuální funkce na `_LazyImportCoordinator`.

#### 3. Async/Sync Mix

**Kde:** `brain/model_manager.py:147-150`
```python
if asyncio.iscoroutinefunction(model.initialize):
    asyncio.run(model.initialize())  # ⚠️ Riziko!
else:
    model.initialize()
```

**Dopad:** `asyncio.run()` uvnitř sync kódu může selhat pokud již běží event loop
**Fix:** Použít `asyncio.get_event_loop().run_until_complete()` nebo čistě async API.

#### 4. Memory Lifecycle Nejednoznačnost

**Problém:** Není jasné kdy se modely skutečně uvolňují z MLX cache
**Dopad:** Memory leaky na M1 8GB
**Fix:** Explicitní context manager:
```python
async with ModelContext('hermes') as model:
    result = await model.generate(prompt)
# Auto-release zde
```

#### 5. "Try/Except/Pass" Anti-pattern

**Kde:** Mnoho lazy load funkcí
```python
try:
    from .module import Something
    AVAILABLE = True
except ImportError:
    pass  # ⚠️ Potlačení chyby
```

**Dopad:** Tiché selhání, obtížné debugování
**Fix:** Alespoň logovat: `logger.debug("Module X not available")`.

#### 6. Circular Import Risk

**Kde:** Komplexní síť importů mezi `brain/`, `coordinators/`, `utils/`
**Dopad:** Potenciální circular imports při změnách
**Fix:** Definovat jasné vrstvy závislostí, použít protokoly/interfaces.

---

## 🔄 MAIN WORKFLOW: AUTONOMOUS ORCHESTRATOR

### ASCII Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         MAIN WORKFLOW PIPELINE                                       │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   START      │────▶│ INITIALIZE   │────▶│   BRAIN      │────▶│   TOOLS      │
│  (Query)     │     │ Coordinators │     │  (Planning)  │     │ (Execution)  │
└──────────────┘     └──────────────┘     └──────────────┘     └──────┬───────┘
                                                                      │
    ┌─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   SYNTHESIS  │◀────│   NER/ENTITY │◀────│  RETRIEVAL   │◀────│  TOOL RESULT │
│   (Report)   │     │  Extraction  │     │  (Knowledge) │     │   Storage    │
└──────┬───────┘     └──────────────┘     └──────────────┘     └──────────────┘
       │
       ▼
┌──────────────┐
│   OUTPUT     │
│  (Result)    │
└──────────────┘

PHASE DETAIL:
═════════════

PHASE 1: INITIALIZATION
───────────────────────
_FullyAutonomousOrchestrator.__init__()
  ├── _initialize_coordinators()
  │   ├── _StateManager(self)
  │   ├── _MemoryManager(self)
  │   ├── _BrainManager(self)
  │   ├── _SecurityManager(self)
  │   ├── _ForensicsManager(self)
  │   ├── _ToolRegistryManager(self)
  │   ├── _ResearchManager(self)
  │   ├── _SynthesisManager(self)
  │   └── _IntelligenceManager(self)
  └── Log: "FullyAutonomousOrchestrator v6.1 initialized"

PHASE 2: BRAIN / PLANNING
─────────────────────────
_BrainManager.plan_research(query)
  ├── DecisionEngine.analyze(query)
  ├── Hermes3Engine.generate() [MODEL LOAD: hermes]
  │   └── ModelManager.acquire('hermes')
  │       └── _create_hermes_engine()
  │           └── Hermes3Engine()
  ├── Vytvoření AutonomousStrategy
  │   ├── depth: DiscoveryDepth
  │   ├── selected_sources: List[SourceType]
  │   ├── selected_agents: List[AgentType]
  │   └── optimization: OptimizationStrategy
  └── [MODEL RELEASE: hermes]

PHASE 3: TOOLS / EXECUTION
───────────────────────────
_ToolRegistryManager.execute(tool_name)
  ├── Lookup tool v _tools dict
  ├── Zavolání handleru (async)
  │   ├── _surface_search_handler → _ResearchManager.execute_surface_search()
  │   ├── _academic_handler → _ResearchManager.execute_academic_search()
  │   ├── _osint_handler → _ResearchManager.execute_osint_search()
  │   └── ... další handlery
  └── Update success_rate

_ResearchManager.execute_*_search()
  ├── Lazy load příslušného modulu (pokud potřeba)
  ├── Volání externího API nebo crawleru
  ├── Výsledky → ResearchFinding
  └── Uložení do _findings list

PHASE 4: RETRIEVAL / KNOWLEDGE
───────────────────────────────
_MemoryManager (přístup přes property)
  ├── RAG query (pokud RAG dostupný)
  ├── Knowledge graph update
  └── Context graph build

PHASE 5: NER / ENTITY
─────────────────────
V jednom z handlerů:
_entity_handler()
  ├── from .utils.entity_extractor import EntityExtractor
  ├── extractor = EntityExtractor()
  └── entities = extractor.extract(text)

⚠️ POZNÁMKA: Toto může být DUPLICITNÍ s brain/ner_engine.py!

PHASE 6: SYNTHESIS
──────────────────
_SynthesisManager.synthesize_report()
  ├── Shromáždění všech findings
  ├── Generování reportu (Hermes3)
  │   └── ModelManager.acquire('hermes')
  ├── Formátování a strukturování
  └── [MODEL RELEASE: hermes]
```

### Inicializace a závislosti

**Init pořadí:**
1. `UniversalConfig` načtena
2. `FullyAutonomousOrchestrator` vytvořen
3. `_initialize_coordinators()` voláno explicitně nebo lazy
4. Každý manažer inicializuje své komponenty
5. `_ToolRegistryManager` registruje všechny nástroje

**Závislosti:**
```
Orchestrator
├── závisí na: Config, Types
├── inicializuje: Všechny manažery
├── používá: Layers (importované)
├── volá: Coordinators (3 importované, ostatní lazy)
└── lazy load: Většina intelligence modulů
```

### Typy dat (context/state/result)

**Context:** `DecisionContext`, `ExecutionContext` - předávány mezi fázemi
**State:** `OrchestratorState`, `WorkflowState` - udržováno v `_StateManager`
**Result:** `ResearchFinding`, `ResearchResult`, `ComprehensiveResearchResult` - výstupy

### Hook points pro rozšíření

**1. Nový nástroj:**
```python
# V _ToolRegistryManager.__init__()
self._register(ToolCapability(
    name="my_new_tool",
    category=ToolCategory.ANALYSIS,
    handler=self._my_handler,
    ...
))
```

**2. Nový koordinátor:**
- Vytvořit třídu dědící z `UniversalCoordinator`
- Přidat do orchestrátoru jako nový manažer

**3. Nová vrstva:**
- Přidat do `layers/`
- Importovat v orchestrátoru

### Rizika synchronizace

**1. Event Log / Shared State:**
- `_execution_history` - seznam v orchestrátoru
- Není thread-safe!
- **Riziko:** Race conditions při paralelním zpracování

**2. Memory Manager:**
- `_loaded_models` - shared dict
- `_current_model` - shared state
- **Riziko:** Při async operacích může dojít k souběhu

**3. Lazy Loading:**
- Globální proměnné jako `HERMES_AVAILABLE`
- **Riziko:** Race condition při současném prvním přístupu

---

## 📊 SOUHRNNÉ STATISTIKY

| Metrika | Hodnota |
|---------|---------|
| Celkem souborů | 152 Python souborů |
| Celkem řádků kódu | ~30,000+ (odhad) |
| Koordinátorů | 20 (3 aktivní, 17 nejistých) |
| Brain modulů | 9 (2-3 aktivní) |
| Utils | 19 (5 aktivních) |
| Intelligence modulů | 21 (lazy loaded) |
| Security modulů | 12 (lazy loaded) |
| Vrstev | 13 (všechny importované) |
| Testovacích souborů | 9 (mimo tests/ adresář) |
| Unused imports (vulture) | 80+ |
| Potenciálně mrtvý kód | ~30-40% (odhad) |

---

## 🔧 DOPORUČENÉ AKCE

### Okamžitě (High Priority)
1. **Rozdělit orchestrátor** - 4500 řádků je příliš
2. **Audit koordinátorů** - identifikovat skutečně používané
3. **Sjednotit entity extraction** - odstranit duplicity

### Krátkodobě (Medium Priority)
4. **Pročistit unused imports** - snížit technický dluh
5. **Přesunout testy** do `tests/` adresáře
6. **Standardizovat lazy loading**
7. **Dokumentovat memory lifecycle**

### Dlouhodobě (Low Priority)
8. **Circular import analýza**
9. **Kompletní test coverage**
10. **Performance profiling na M1**

---

## 📝 POZNÁMKY K ANALÝZE

**Omezení této analýzy:**
- Statická analýza kódu (nebylo spuštěno)
- Některé lazy loaded moduly mohou být použity v runtime
- Vulture může hlásit false positives
- Async flow není plně trasován

**Doporučené další kroky:**
1. Spustit systém s profilingem a sledovat které moduly se skutečně načítají
2. Použít `coverage.py` pro zjištění testovanosti
3. Provést dynamickou analýzu importů přes `sys.modules`
4. Memory profiling na M1 8GB za běhu

---

*Dokument vygenerován automaticky pomocí Claude Code s Ralph Loop*
*Pro aktualizace spusťte: `/oh-my-claudecode:ralph aktualizuj analýzu`*
