# F025 — Legacy Containment Inventory Report
**Datum:** 2026-04-01
**Scope:** `hledac/universal/` — legacy, dormant a latent bloky
**Cíl:** Inventory scan pro rozhodnutí o migraci, odstranění, nebo zachování

---

## 1. Executive Summary

### Block Classification Overview

| Kategorie | Počet bloků | Klíčové příklady |
|-----------|-------------|------------------|
| **Dormant Canonical Provider** | 3 | `legacy/autonomous_orchestrator.py`, `legacy/atomic_storage.py`, `legacy/persistent_layer.py` |
| **Capability Donor** | 4 | `dht/`, `federated/`, `rl/`, `layers/hive_coordination.py` |
| **Compat Shim** | 2 | `autonomous_orchestrator.py` facade, `orchestrator_integration.py` |
| **True Removable Legacy** | 2 | `federated/federated_engine.py` (duplikátní v2), `layers/content_layer.py` (částečně) |
| **Canonical Replacement (migrated)** | 1 | `runtime/sprint_scheduler.py` — nahradil legacy orchestrator |

### Klíčová zjištění:

1. **`legacy/` obsahuje 1.36MB monolithic orchestrator** — canonical path pro backward compatibility, ale **není v hot path** (`__main__.py` používá `runtime/sprint_scheduler.py`)

2. **4 latentní capability donory** — DHT crawl, federated ML, RL agent coordination, sketch algorithms

3. ** Compat shimy jsou nebezpečné** — `autonomous_orchestrator.py` facade načítá celý legacy modul při jakémkoliv importu

4. **`orchestrator_integration.py` je orphaned** — `IntegratedOrchestrator` není v `__main__.py`, pouze v tests

5. **Runtime canonical path** = `runtime/sprint_scheduler.py` + `runtime/sprint_lifecycle.py` + `runtime/windup_engine.py`

---

## 2. Containment Matrix

### 2.1 Legacy/ bloky (PRIMARY LEGACY CONTAINMENT)

#### `legacy/autonomous_orchestrator.py`
| Atribut | Hodnota |
|---------|---------|
| **Runtime Status** | DORMANT — pouze backward compat facade |
| **Authority Status** | **DEPRECATED** — import způsobuje DeprecationWarning |
| **Donor Capability List** | `_StateManager`, `_MemoryManager`, `_BrainManager`, `_SecurityManager`, `_ForensicsManager`, `_ToolRegistryManager`, `_ResearchManager`, `_SynthesisManager`, DHT integrace, FederatedEngine |
| **Replacement Owner** | `runtime/sprint_scheduler.py` (canonical), `runtime/sprint_lifecycle.py` |
| **Migration Blocker** | Velké množství kódu závisí na interních strukturách přes facade |
| **Removal Precondition** | Všechny importy z `autonomous_orchestrator.py` musí přejít na `runtime/sprint_scheduler.py` |
| **Runtime Impact if Removed** | VYSOKÝ — pokud něco importuje z facade bez přechodu na canonical path |

#### `legacy/atomic_storage.py`
| Atribut | Hodnota |
|---------|---------|
| **Runtime Status** | DORMANT — DEPRECATED, pouze varování při importu |
| **Authority Status** | **DEPRECATED** — `knowledge.atomic_storage is DEPRECATED. Use knowledge.duckdb_store instead.` |
| **Donor Capability List** | `KnowledgeEntry`, `AtomicJSONKnowledgeGraph`, snapshot storage, ZSTD compression |
| **Replacement Owner** | `knowledge/duckdb_store.py` |
| **Migration Blocker** | `knowledge/__init__.py` stále re-exportuje z legacy |
| **Removal Precondition** | `knowledge/` musí přestat proxy-importovat z legacy |
| **Runtime Impact if Removed** | STŘEDNÍ — pokud `knowledge/` ještě není plně migrováno |

#### `legacy/persistent_layer.py`
| Atribut | Hodnota |
|---------|---------|
| **Runtime Status** | DORMANT — DEPRECATED |
| **Authority Status** | **DEPRECATED** — `knowledge.persistent_layer is DEPRECATED. Use knowledge.duckdb_store instead.` |
| **Donor Capability List** | `PersistentKnowledgeLayer`, HNSW indexy, Model2Vec integrace, MementoResolver |
| **Replacement Owner** | `knowledge/duckdb_store.py` |
| **Migration Blocker** | `knowledge/graph_layer.py`, `knowledge/graph_rag.py`, `knowledge/graph_builder.py` importují zde |
| **Removal Precondition** | Graph builder musí přejít na duckdb_store |
| **Runtime Impact if Removed** | STŘEDNÍ — graph builder závisí na tomto |

---

### 2.2 Facade/Compat Shim bloky

#### `autonomous_orchestrator.py` (ROOT FACADE)
| Atribut | Hodnota |
|---------|---------|
| **Runtime Status** | ACTIVE GATE — aktivně přesměrovává importy |
| **Authority Status** | **DEPRECATED** — celý file je deprecated |
| **Donor Capability List** | Pouze re-export z legacy, žádné vlastní capability |
| **Replacement Owner** | Přímé importy z `runtime/sprint_scheduler.py` |
| **Migration Blocker** | Jakýkoliv kód, který dělá `from hledac.universal import FullyAutonomousOrchestrator` |
| **Removal Precondition** | Migrace všech consumerů na direct imports |
| **Runtime Impact if Removed** | VYSOKÝ — okamžitý ImportError pro všechny legacy consumery |

#### `orchestrator_integration.py`
| Atribut | Hodnota |
|---------|---------|
| **Runtime Status** | DORMANT — není v `__main__.py` |
| **Authority Status** | **UNMAINTAINED** — pouze v tests, ne v production pipeline |
| **Donor Capability List** | ArXiv API integration, GitHub API integration, MetaReasoningCoordinator, SwarmCoordinator, ValidationCoordinator |
| **Replacement Owner** | `coordinators/` — jednotlivé coordinators jsou dostupné samostatně |
| **Migration Blocker** | Žádný — není v hot path |
| **Removal Precondition** | Ověřit že žádný production kód nepoužívá |
| **Runtime Impact if Removed** | NÍZKÝ — pouze test coverage loss |

---

### 2.3 Latent Capability Donor bloky

#### `dht/` — DHT Network Capability
| Atribut | Hodnota |
|---------|---------|
| **Runtime Status** | LATENT — není v `__main__.py` |
| **Authority Status** | **AVAILABLE** — plně implementováno, otestováno (`test_sprint62b.py`, `test_dht_crawl_returns_list.py`) |
| **Donor Capability List** | `KademliaNode` (DHT routing), `crawl_dht_for_keyword()` (BEP-9 metadata extension), `LocalGraphStore`, `SketchExchange` |
| **Replacement Owner** | OSINT module — pro torrent metadata extraction |
| **Migration Blocker** | Žádný hard blocker — pouze nevyužívané |
| **Removal Precondition** | Potvrdit že DHT crawl není nikde v roadmap |
| **Runtime Impact if Removed** | STŘEDNÍ — ztráta DHT OSINT capability |
| **Donor Warning** | **CRITICAL DONOR** — `crawl_dht_for_keyword()` má plnou BEP-9/BEP-10 implementaci |

#### `federated/` — Federated Learning & Privacy
| Atribut | Hodnota |
|---------|---------|
| **Runtime Status** | LATENT — lazy-loaded pouze v legacy AO |
| **Authority Status** | **AVAILABLE** — plně implementováno, ale ne v pipeline |
| **Donor Capability List** | `FederatedEngine` (v2), `PQCProvider` (post-quantum crypto), `SecureAggregator`, `DPNoise`/`RDPCalculator` (differential privacy), `CountMinSketch`/`MinHashSketch`/`SimHashSketch`, `TorTransport` |
| **Replacement Owner** | Privacy/security features, federated learning future |
| **Migration Blocker** | Žádný — pouze nevyužívané |
| **Removal Precondition** | Potvrdit že federated learning není v roadmap |
| **Runtime Impact if Removed** | VYSOKÝ pro budoucí privacy features |
| **Donor Warning** | **CRITICAL DONOR** — PQC, secure aggregation, differential privacy jsou premium capabilities |

#### `rl/` — Reinforcement Learning
| Atribut | Hodnota |
|---------|---------|
| **Runtime Status** | LATENT — pouze v tests (`test_sprint58a.py`) |
| **Authority Status** | **AVAILABLE** — QMIX implementace kompletní |
| **Donor Capability List** | `MARLCoordinator` (multi-agent RL), `QMIXAgent`, `QMixer`, `QMIXJointTrainer`, `MARLReplayBuffer`, `StateExtractor` |
| **Replacement Owner** | Agent learning / adaptive research |
| **Migration Blocker** | Žádný |
| **Removal Precondition** | Potvrdit že RL není v roadmap |
| **Runtime Impact if Removed** | STŘEDNÍ — ztráta RL coordination capability |
| **Donor Warning** | QMIX je solidní implementace, ne废弃 |

---

### 2.4 Active-ish bloky (mohou být nadbytečné)

#### `orchestrator/` modul
| Atribut | Hodnota |
|---------|---------|
| **Runtime Status** | ACTIVE-ISH — využíváno částečně |
| **Authority Status** | **MIGRATED** — `research_manager.py`, `security_manager.py` jsou thin wrappers |
| **Donor Capability List** | `LaneState`, `MemoryPressureBroker`, `PhaseController`, `SubsystemSemaphores` |
| **Replacement Owner** | Části mohou být redundantní s `runtime/sprint_scheduler.py` |
| **Migration Blocker** | Nutná analýza co přesně `orchestrator/` poskytuje navíc |
| **Removal Precondition** | Audit overlap s `runtime/` |
| **Runtime Impact if Removed** | NÍZKÝ-STŘEDNÍ |

#### `layers/` — Velké soubory
| Soubor | Řádků | Status | Donor Capability |
|--------|-------|--------|-----------------|
| `stealth_layer.py` | 94KB | ACTIVE | Browser fingerprinting, behavior simulation |
| `coordination_layer.py` | 76KB | ACTIVE | Multi-agent coordination, hive coordination |
| `layer_manager.py` | 32KB | ACTIVE | Unified layer management |
| `ghost_layer.py` | 31KB | ACTIVE | GhostDirector integration |
| `memory_layer.py` | 52KB | ACTIVE | RAM disk, shared memory management |
| `security_layer.py` | 36KB | ACTIVE | Crypto, obfuscation, secure destruction |
| `hive_coordination.py` | 30KB | LATENT? | `ConnectedCoordinationSystem` — možná duplikát `coordination_layer.py` |
| `smart_coordination.py` | 24KB | LATENT? | `SmartSpawnedCoordinationIntegration` — možná redundantní |

---

## 3. Donor Capability Map

### Critical Donors (NEODSTANOVAT bez náhrady)

```
dht/kademlia_node.py
├── crawl_dht_for_keyword()     — BEP-9/BEP-10 torrent metadata extraction
├── KademliaNode               — DHT routing table management
└── Bootstrap peers (IPv4)     — router.bittorrent.com, dht.transmissionbt.com

dht/local_graph.py
└── LocalGraphStore            — local graph storage for DHT

federated/post_quantum.py
├── PQCProvider                — Post-quantum cryptography (kyber, dilithium)
└── Hybrid KEM                 — PQ/Tybrid hybrid encryption

federated/secure_aggregator.py
└── SecureAggregator           — Secure aggregation for federated learning

federated/differential_privacy.py
├── DPNoise                    — Gaussian/Exponential noise for DP
└── RDPCalculator             — Rényi DP privacy accountant

federated/sketches.py
├── CountMinSketch            — Frequency estimation
├── MinHashSketch             — Set similarity (Jaccard)
└── SimHashSketch             — Similarity hashing

rl/marl_coordinator.py
├── MARLCoordinator           — Multi-agent RL coordination
├── QMIXAgent                  — QMIX agent implementation
└── MARLReplayBuffer           — Replay buffer pro multi-agent learning

layers/hive_coordination.py
└── ConnectedCoordinationSystem — Distributed coordination topology
```

### Low-Risk Donors (lze extrahovat/migrovat)

```
layers/smart_coordination.py
├── SmartSpawnedCoordinationIntegration — Role-based agent spawning
└── SmartSpawnedAgent                   — Agent s přiřazenou rolí

orchestrator/lane_state.py
└── LaneState — Prioritní fronta pro správu research lanes
```

---

## 4. Public API Drift from Legacy/Facades

### 4.1 Primary Drift: `FullyAutonomousOrchestrator`

**Canonical path:** `runtime/sprint_scheduler.py` (SprintScheduler)
**Legacy path:** `legacy/autonomous_orchestrator.py` (FullyAutonomousOrchestrator)
**Facade:** `autonomous_orchestrator.py` re-export

| Export | Legacy | Canonical | Status |
|--------|--------|-----------|--------|
| `FullyAutonomousOrchestrator` | ✅ legacy/ | ❌ N/A | MIGRATED — používat `SprintScheduler` |
| `autonomous_research()` | ✅ | ❌ N/A | DEPRECATED |
| `deep_research()` | ✅ | ⚠️ v enhanced_research.py | DIFFERENT |
| Manager classes | ✅ | ❌ N/A | MIGRATED |

### 4.2 Secondary Drift: `IntegratedOrchestrator`

**Canonical path:** NIC — není v production pipeline
**Current path:** `orchestrator_integration.py`

| Export | Status |
|--------|--------|
| `IntegratedOrchestrator` | ORPHANED — pouze test |
| `integrated_research()` | ORPHANED |
| ArXiv/GitHub API | UNUSED v production |
| MetaReasoning | UNUSED v production |

### 4.3 Tertiary Drift: `knowledge/` proxy imports

```python
# knowledge/__init__.py re-export z legacy:
from ..legacy.atomic_storage import AtomicJSONKnowledgeGraph  # DEPRECATED
from ..legacy.persistent_layer import PersistentKnowledgeLayer  # DEPRECATED
```

**Canonical:** `knowledge/duckdb_store.py`

---

## 5. Safe-to-Remove Candidates

### 5.1 HIGH CONFIDENCE — Safe to Remove

#### `orchestrator_integration.py`
- **Důvod:** Orphaned — není v `__main__.py`, pouze v tests
- **Podmínka:** Ověřit že žádný production kód nepoužívá
- **Riziko:** NÍZKÉ
- **Toto:** Odstranit file, odstranit z `__init__.py` exporty

#### `federated/federated_engine.py` (v1, non-v2)
- **Důvod:** Duplikát — `FederatedCoordinatorV2` a `ModelStoreV2` jsou novější verze
- **Podmínka:** Ověřit že legacy AO nepoužívá v1
- **Riziko:** STŘEDNÍ — `legacy/autonomous_orchestrator.py` lazy-loaduje FederatedEngine
- **Toto:** Odstranit v1, ponechat v2

### 5.2 MEDIUM CONFIDENCE — Candidate for Removal

#### `layers/smart_coordination.py`
- **Důvod:** Možná redundantní s `coordination_layer.py`
- **Podmínka:** Audit overlap
- **Riziko:** STŘEDNÍ — může mít unique capability

#### `orchestrator/memory_pressure_broker.py`
- **Důvod:** Možná redundantní s `resource_governor.py`
- **Podmínka:** Audit overlap
- **Riziko:** NÍZKÉ-STŘEDNÍ

---

## 6. Unsafe-to-Remove Candidates

### 6.1 NEVER REMOVE without full migration

#### `dht/` (celý modul)
- **Proč:** `crawl_dht_for_keyword()` je plná BEP-9/BEP-10 implementace
- **Riziko pokud odstranit:** Ztráta DHT OSINT capability navždy
- **Co dělat místo odstranění:** Zakonzervovat jako dormant donor, dokumentovat API

#### `federated/` (celý modul)
- **Proč:** PQCProvider, SecureAggregator, DPNoise, sketches jsou premium privacy/security capabilities
- **Riziko pokud odstranit:** Ztráta federated learning a post-quantum crypto
- **Co dělat místo odstranění:** Zakonzervovat jako dormant donor

#### `rl/` (celý modul)
- **Proč:** QMIX je solidní multi-agent RL implementace
- **Riziko pokud odstranit:** Ztráta RL capability
- **Co dělat místo odstranění:** Zakonzervovat jako dormant donor

#### `legacy/autonomous_orchestrator.py`
- **Proč:** Stále může mít active consumers
- **Riziko pokud odstranit:** ImportError pro backward-compat
- **Co dělat místo odstranění:** Ponechat jako dormant, migrace consumerů na canonical path

#### `legacy/atomic_storage.py` + `legacy/persistent_layer.py`
- **Proč:** `knowledge/` stále proxy-importuje
- **Riziko pokud odstranit:** Breaking change pokud duckdb_store není ready
- **Co dělat místo odstranění:** Dokončit migraci `knowledge/` → duckdb_store

---

## 7. Canonical Replacement Candidates

### 7.1 Migrated (complete)

| Legacy | Canonical | Status |
|--------|-----------|--------|
| `legacy/autonomous_orchestrator.py` | `runtime/sprint_scheduler.py` | ✅ MIGRATED (Sprint 8BK) |

### 7.2 In Progress

| Legacy | Target | Status |
|--------|--------|--------|
| `legacy/atomic_storage.py` | `knowledge/duckdb_store.py` | ⚠️ PARTIAL — knowledge/__init__.py stále re-exportuje |
| `legacy/persistent_layer.py` | `knowledge/duckdb_store.py` | ⚠️ PARTIAL — graph_* moduly stále importují |

### 7.3 Not Started

| Legacy | Target | Notes |
|--------|--------|-------|
| `orchestrator_integration.py` | NIC (odstranit) | Orphaned |
| `layers/hive_coordination.py` | `layers/coordination_layer.py`? | Audit overlap |
| `layers/smart_coordination.py` | `layers/coordination_layer.py`? | Audit overlap |

---

## 8. Top 20 Konkrétních Ticketů

| # | Ticket | Block | Akce | Priority |
|---|--------|-------|------|----------|
| 1 | F025-T001 | `orchestrator_integration.py` | **REMOVE** — orphaned, není v hot path | P0 |
| 2 | F025-T002 | `__init__.py` | Remove `IntegratedOrchestrator` exporty | P0 |
| 3 | F025-T003 | `federated/federated_engine.py` | REMOVE v1 — ponechat pouze v2 | P1 |
| 4 | F025-T004 | `legacy/__init__.py` | Přidat explicitní DeprecationWarning na všechny moduly | P1 |
| 5 | F025-T005 | `knowledge/__init__.py` | Migrace proxy-importů z legacy na duckdb_store | P1 |
| 6 | F025-T006 | `knowledge/graph_layer.py` | Odstranit import z `legacy/persistent_layer.py` | P1 |
| 7 | F025-T007 | `knowledge/graph_rag.py` | Odstranit import z `legacy/persistent_layer.py` | P1 |
| 8 | F025-T008 | `knowledge/graph_builder.py` | Odstranit import z `legacy/persistent_layer.py` | P1 |
| 9 | F025-T009 | `autonomous_orchestrator.py` facade | Přidat explicitní DeprecationWarning při každém importu | P2 |
| 10 | F025-T010 | `dht/` | ZAKONSERVOVAT jako dormant donor, dokumentovat `crawl_dht_for_keyword` API | P2 |
| 11 | F025-T011 | `federated/` | ZAKONSERVOVAT jako dormant donor, dokumentovat PQC/sketch API | P2 |
| 12 | F025-T012 | `rl/` | ZAKONSERVOVAT jako dormant donor, dokumentovat QMIX API | P2 |
| 13 | F025-T013 | `layers/hive_coordination.py` | AUDIT overlap s `coordination_layer.py` | P2 |
| 14 | F025-T014 | `layers/smart_coordination.py` | AUDIT overlap s `coordination_layer.py` | P2 |
| 15 | F025-T015 | `orchestrator/memory_pressure_broker.py` | AUDIT overlap s `resource_governor.py` | P3 |
| 16 | F025-T016 | `orchestrator/lane_state.py` | AUDIT — je využíváno v runtime? | P3 |
| 17 | F025-T017 | `orchestrator/request_router.py` | AUDIT — je využíváno? | P3 |
| 18 | F025-T018 | `orchestrator/subsystem_semaphores.py` | AUDIT — je využíváno? | P3 |
| 19 | F025-T019 | `layers/coordination_layer.py` | REFACTOR — extrahovat `ConnectedCoordinationSystem` pokud redundantní | P3 |
| 20 | F025-T020 | `__main__.py` | Verifikovat že runtime canonical path je kompletní | P1 |

---

## 9. Exit Criteria

### F017: Legacy Orchestrator Facade Removal

| Criteria | Status |
|----------|--------|
| Všichni consumeri přesunuti na `runtime/sprint_scheduler.py` | ❌ NOT MET |
| Žádné importy z `autonomous_orchestrator.py` v production kódu | ❌ NOT MET |
| `autonomous_orchestrator.py` facade odstraněn | ❌ NOT MET |
| DeprecationWarning při každém importu facade | ✅ MET |

**Exit pro F017:** Odstranit facade AŽ KDYŽ všichni consumeri migrovali

### F018: Legacy Knowledge Layer Migration

| Criteria | Status |
|----------|--------|
| `knowledge/__init__.py` neimportuje z `legacy/` | ❌ NOT MET |
| `knowledge/graph_layer.py` nepoužívá `PersistentKnowledgeLayer` | ❌ NOT MET |
| `knowledge/graph_rag.py` nepoužívá `KnowledgeNode` z legacy | ❌ NOT MET |
| `knowledge/duckdb_store.py` je plná náhrada | ⚠️ PARTIAL |
| `legacy/atomic_storage.py` odstraněn | ❌ NOT MET |
| `legacy/persistent_layer.py` odstraněn | ❌ NOT MET |

**Exit pro F018:** Dokončit migraci graph modulů, pak odstranit legacy

### F019: Latent Donor Containment

| Criteria | Status |
|----------|--------|
| `dht/` zakonzervován jako dormant donor | ❌ NOT MET |
| `federated/` zakonzervován jako dormant donor | ❌ NOT MET |
| `rl/` zakonzervován jako dormant donor | ❌ NOT MET |
| Dokumentace API pro každý donor block | ❌ NOT MET |
| Decision made: extract nebo discard každý donor | ❌ NOT MET |

**Exit pro F019:** Rozhodnout o osudu každého donoru (extract to separate package vs discard)

---

## 10. What Must Be Contained, Not Deleted

### 10.1 Critical Infrastructure (NEODSTRANOVAT)

```
⚠️  dht/crawl_dht_for_keyword()
    → Plná BEP-9/BEP-10 implementace pro torrent metadata
    → Jediná existující DHT OSINT capability
    → ACTION: Zakonservovat, zdokumentovat, NEODSTANOVAT

⚠️  federated/post_quantum.py (PQCProvider)
    → Post-quantum cryptography (Kyber, Dilithium)
    → Premium security capability
    → ACTION: Zakonservovat, NEODSTANOVAT

⚠️  federated/secure_aggregator.py
    → Secure aggregation pro federated learning
    → ACTION: Zakonservovat, NEODSTANOVAT

⚠️  federated/differential_privacy.py
    → DP noise + RDP privacy accountant
    → ACTION: Zakonservovat, NEODSTANOVAT

⚠️  federated/sketches.py
    → CountMinSketch, MinHashSketch, SimHashSketch
    → ACTION: Zakonservovat, NEODSTANOVAT

⚠️  rl/marl_coordinator.py
    → QMIX multi-agent RL coordination
    → ACTION: Zakonservovat, NEODSTANOVAT
```

### 10.2 Transitional Bloks (MIGRACE, ne deletion)

```
⚠️  legacy/atomic_storage.py
    → Čeká na dokončení migrace knowledge/ → duckdb_store
    → ACTION: Migrovat graph moduly, pak odstranit

⚠️  legacy/persistent_layer.py
    → Čeká na dokončení migrace knowledge/ → duckdb_store
    → ACTION: Migrovat graph moduly, pak odstranit

⚠️  autonomous_orchestrator.py (facade)
    → Čeká na migraci všech consumerů
    → ACTION: Migrace consumerů na sprint_scheduler, pak odstranit facade
```

### 10.3 Orphaned but Removable (DELETE)

```
✅  orchestrator_integration.py
    → Orphaned, není v hot path
    → ACTION: DELETE (P0 ticket F025-T001)

✅  federated/federated_engine.py v1
    → Duplikát v2
    → ACTION: DELETE v1, ponechat v2 (ticket F025-T003)
```

---

## 11. Summary

| Kategorie | Count | Akce |
|-----------|-------|------|
| Dormant Canonical Provider | 3 | Migrace/dokončení |
| Capability Donor | 4 | ZAKONSERVOVAT |
| Compat Shim | 2 | Migrace/removal |
| True Removable Legacy | 2+ | DELETE |
| Canonical Replacement | 1 | ✅ SPLNĚNO |

**Klíčové principy:**
1. **"Není v hot path" ≠ "je odpad"** — DHT, federated, RL jsou hodnotné dormant donory
2. **Import graph ≠ skutečné použití** — Ověřovat runtime volání, ne jen imports
3. **Odstranění bez migrace = ztráta capability** — Neodstraňovat dokud nejsou consumery migrovány
4. **Konzervace > náhodné smazání** — dormant donory mohou být future assets

---

*Report generated: 2026-04-01*
*Primary investigator: F025 Legacy Containment Scan*
