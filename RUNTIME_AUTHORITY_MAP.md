# RUNTIME_AUTHORITY_MAP — Sprint 8SC
**Datum:** 2026-03-31
**Scope:** boot, runtime, control, assembly plane

---

## Table Legend

| Role | Význam |
|------|--------|
| **canonical** | Oficiální, aktivně používaný zdroj pravdy |
| **helper** | Podpůrná utilita — volána z canonical |
| **compat** | Backward-compat re-export nebo shim |
| **legacy** | Deprecated, plánované k odstranění |
| **facade** | Přesměrovává na jiný modul |
| **unknown** | Nedostatek důkazů pro klasifikaci |

---

## 1. Root Module Authority

| Oblast | Soubor | Role dnes | Status | Poznámka |
|--------|--------|-----------|--------|-----------|
| **Entry point** | `__main__.py` | Boot, signal handlers, async main, teardown | **canonical** | 2781 lines, Sprint 8AI |
| **Facade** | `__init__.py` | Massive re-export všech modulů | **facade** | 17k+ řádků, lazy imports |
| **Facade** | `autonomous_orchestrator.py` | Deprecated facade → legacy/ | **facade** | 98 lines, DeprecationWarning |
| **Config SSOT** | `config.py` | UniversalConfig, M1Presets, ResearchPresets | **canonical** | 665 řádků |
| **Paths SSOT** | `paths.py` | RAMDISK, LMDB, SOCKETS paths | **canonical** | 455 řádků, stdlib-only |
| **Arch docs** | `ARCHITECTURE_MAP.py` | Live architecture documentation | **helper** | 1500+ lines, popisuje stav |
| **Types** | `types.py` | Všechny enums a dataclasses | **canonical** | 33587 bytes |
| **Research context** | `research_context.py` | ResearchContext Pydantic model | **canonical** | 410 lines |
| **Comprehensive tests** | `run_comprehensive_tests.py` | Test runner | **helper** | 30674 bytes |
| **Smoke runner** | `smoke_runner.py` | Smoke test entry | **helper** | 8751 bytes |

---

## 2. Runtime Authority

| Oblast | Soubor | Role dnes | Status | Poznámka |
|--------|--------|-----------|--------|-----------|
| **Lifecycle** | `runtime/sprint_lifecycle.py` | SprintLifecycleManager, 6-phase state machine | **canonical** | 14363 bytes |
| **Lifecycle (old)** | `utils/sprint_lifecycle.py` | Starší verze lifecycle | **legacy** | Nemá SprintLifecycleManager |
| **Scheduler** | `runtime/sprint_scheduler.py` | SprintScheduler, Tier-aware scheduling | **legacy** | UNPLUGGED — není volán z __main__ |
| **Windup** | `runtime/windup_engine.py` | WINDUP synthesis, Parquet, GNN | **canonical** | Volán z _run_sprint_mode |
| **UMA Governor** | `core/resource_governor.py` | evaluate_uma_state, UMAAlarmDispatcher | **canonical** | 20468 bytes, thresholds 6.0/6.5/7.0 GiB |
| **Core init** | `core/__init__.py` | Empty | **unknown** | 0 bytes |
| **Loops init** | `loops/__init__.py` | Empty | **unknown** | 0 bytes |

---

## 3. Pipeline Authority

| Oblast | Soubor | Role dnes | Status | Poznámka |
|--------|--------|-----------|--------|-----------|
| **Public pipeline** | `pipeline/live_public_pipeline.py` | Web search → pattern → DuckDB | **canonical** | Volán z _run_public_passive_once |
| **Feed pipeline** | `pipeline/live_feed_pipeline.py` | RSS/Atom → pattern → DuckDB | **canonical** | Volán z obou režimů |
| **Pipeline base** | `pipeline/__init__.py` | Re-exports | **facade** | 102 bytes |

---

## 4. Storage Authority

| Oblast | Soubor | Role dnes | Status | Poznámka |
|--------|--------|-----------|--------|-----------|
| **DuckDB store** | `knowledge/duckdb_store.py` | RAMDISK-first storage, async | **canonical** | create_owned_store() entry |
| **LMDB KV** | `knowledge/lmdb_kv.py` | LMDB wrapper | **helper** | Voláno z více míst |
| **LMDB boot guard** | `knowledge/lmdb_boot_guard.py` | Stale lock cleanup | **canonical** | Voláno z _run_boot_guard |
| **LanceDB** | `knowledge/lancedb_store.py` | RAG embedding storage | **legacy** | Není v hot path |
| **IOC Graph** | `knowledge/ioc_graph.py` | Graph management | **helper** | Buffer/flush pattern |
| **Graph RAG** | `knowledge/graph_rag.py` | Graph RAG orchestration | **legacy** | Torch import, latent |
| **Knowledge init** | `knowledge/__init__.py` | Re-exports | **facade** | 773 bytes |

---

## 5. Coordinator Authority

| Oblast | Soubor | Role dnes | Status | Poznámka |
|--------|--------|-----------|--------|-----------|
| **Coordinator base** | `coordinators/base.py` | BaseCoordinator ABC | **canonical** | Všechny coordinators dědí |
| **Research** | `coordinators/research_coordinator.py` | Research coordination | **canonical** | |
| **Execution** | `coordinators/execution_coordinator.py` | Execution coordination | **canonical** | |
| **Security** | `coordinators/security_coordinator.py` | Security coordination | **canonical** | |
| **Monitoring** | `coordinators/monitoring_coordinator.py` | Monitoring coordination | **canonical** | |
| **Agent engine** | `coordinators/agent_coordination_engine.py` | Multi-agent orchestration | **helper** | LATENT |
| **Privacy enhanced** | `coordinators/privacy_enhanced_research.py` | Privacy research | **helper** | LATENT |
| **Research optimizer** | `coordinators/research_optimizer.py` | Caching, dedup | **helper** | LATENT |
| **Benchmark** | `coordinators/benchmark_coordinator.py` | Benchmarking | **helper** | |
| **Swarm** | `coordinators/swarm_coordinator.py` | Swarm coordination | **helper** | |
| **Meta reasoning** | `coordinators/meta_reasoning_coordinator.py` | Meta reasoning | **helper** | |
| **Coordinators init** | `coordinators/__init__.py` | Consolidated re-exports | **facade** | 273 lines |
| **Legacy coordinators** | `legacy/coordinators/` | Deprecated coordinators | **legacy** | Moved 2025-02-14 |

---

## 6. Brain/AI Authority

| Oblast | Soubor | Role dnes | Status | Poznámka |
|--------|--------|-----------|--------|-----------|
| **Hermes3 LLM** | `brain/hermes3_engine.py` | Primary LLM inference | **helper** | ~75k, NOT in hot path |
| **Hypothesis** | `brain/hypothesis_engine.py` | Hypothesis generation/testing | **helper** | ~98k, called in WINDUP only |
| **Synthesis** | `brain/synthesis_runner.py` | Constrained JSON generation | **helper** | ~41k, called in WINDUP |
| **Inference** | `brain/inference_engine.py` | Abductive reasoning | **helper** | ~60k, LATENT |
| **Model manager** | `brain/model_manager.py` | Model lifecycle | **helper** | ~29k |
| **Model swap** | `brain/model_swap_manager.py` | Race-free swap arbiter | **helper** | ~15k |
| **Model lifecycle** | `brain/model_lifecycle.py` | Sprint-based lifecycle | **helper** | ~15k |
| **NER engine** | `brain/ner_engine.py` | GLiNER-X + NaturalLanguage | **helper** | |
| **GNN predictor** | `brain/gnn_predictor.py` | GraphSAGE/GCN in MLX | **helper** | ~32k |
| **ANE embedder** | `brain/ane_embedder.py` | CoreML ANE acceleration | **helper** | ~9k, EXPERIMENTAL |
| **Prompt cache** | `brain/prompt_cache.py` | Trigram similarity cache | **helper** | |
| **MoE router** | `brain/moe_router.py` | Mixture of Experts | **helper** | EXPERIMENTAL |
| **DSPy optimizer** | `brain/dspy_optimizer.py` | DSPy MIPROv2 | **helper** | EXPERIMENTAL |
| **Distillation** | `brain/distillation_engine.py` | MLX MLP critic | **helper** | EXPERIMENTAL |
| **Brain init** | `brain/__init__.py` | Re-exports | **facade** | |

---

## 7. Orchestrator Sub-system Authority

| Oblast | Soubor | Role dnes | Status | Poznámka |
|--------|--------|-----------|--------|-----------|
| **Orch init** | `orchestrator/__init__.py` | Thin facade re-exports | **facade** | 924 bytes |
| **Research manager** | `orchestrator/research_manager.py` | Research management | **helper** | 480 bytes |
| **Security manager** | `orchestrator/security_manager.py` | Security management | **helper** | 480 bytes |
| **Global scheduler** | `orchestrator/global_scheduler.py` | ProcessPoolExecutor scheduler | **helper** | 8136 bytes, NOT in hot path |
| **Lane state** | `orchestrator/lane_state.py` | Lane state management | **helper** | ~15k |
| **Memory pressure** | `orchestrator/memory_pressure_broker.py` | Memory pressure handling | **helper** | ~12k |
| **Phase controller** | `orchestrator/phase_controller.py` | Phase management | **helper** | ~15k |
| **Request router** | `orchestrator/request_router.py` | Request routing | **helper** | ~7k |
| **Subsystem semaphores** | `orchestrator/subsystem_semaphores.py` | Concurrency control | **helper** | ~6k |

---

## 8. Intelligence Tools Authority

| Oblast | Soubor | Role dnes | Status | Poznámka |
|--------|--------|-----------|--------|-----------|
| **Web intelligence** | `intelligence/web_intelligence.py` | Multi-platform intelligence | **helper** | LAZY loaded |
| **Temporal analysis** | `intelligence/temporal_analysis.py` | Time-series analysis | **helper** | LAZY loaded |
| **Archive discovery** | `intelligence/archive_discovery.py` | Wayback, archive.today | **helper** | LAZY loaded |
| **Stealth crawler** | `intelligence/stealth_crawler.py` | Stealth web crawling | **helper** | LAZY loaded |
| **Data leak hunter** | `intelligence/data_leak_hunter.py` | Breach detection | **helper** | LAZY loaded |
| **Crypto intelligence** | `intelligence/cryptographic_intelligence.py` | Cryptanalysis | **helper** | LAZY loaded |
| **Document intel** | `intelligence/document_intelligence.py` | PDF/Office analysis | **helper** | LAZY loaded |
| **Blockchain forensics** | `intelligence/blockchain_analyzer.py` | Crypto tracing | **helper** | LAZY loaded |
| **Identity stitching** | `intelligence/identity_stitching.py` | Cross-platform linking | **helper** | LAZY loaded |
| **Intelligence init** | `intelligence/__init__.py` | Lazy exports | **facade** | LAZY loaded |

---

## 9. Infrastructure Authority

| Oblast | Soubor | Role dnes | Status | Poznámka |
|--------|--------|-----------|--------|-----------|
| **Plugin manager** | `infrastructure/plugin_manager.py` | Plugin management | **helper** | ~15k |
| **System monitor** | `infrastructure/system_monitor.py` | System monitoring | **helper** | ~4k |
| **Infra init** | `infrastructure/__init__.py` | Empty | **unknown** | 102 bytes |

---

## 10. Context Optimization Authority

| Oblast | Soubor | Role dnes | Status | Poznámka |
|--------|--------|-----------|--------|-----------|
| **Context cache** | `context_optimization/context_cache.py` | Cache management | **helper** | ~28k |
| **Context compressor** | `context_optimization/context_compressor.py` | Compression | **helper** | ~24k |
| **Dynamic context** | `context_optimization/dynamic_context_manager.py` | Dynamic management | **helper** | ~24k |
| **Context opt init** | `context_optimization/__init__.py` | Re-exports | **facade** | 83 bytes |

---

## 11. Policy Authority

| Oblast | Soubor | Role dnes | Status | Poznámka |
|--------|--------|-----------|--------|-----------|
| **Nym policy** | `policy/nym_policy.py` | Nym policy | **helper** | ~5k |
| **Policy init** | `policy/__init__.py` | Empty | **unknown** | 83 bytes |

---

## 12. Legacy/Orphan Authority

| Oblast | Soubor | Role dnes | Status | Poznámka |
|--------|--------|-----------|--------|-----------|
| **Legacy AO** | `legacy/autonomous_orchestrator.py` | 31k God Object | **legacy** | DEPRECATED, not in hot path |
| **Legacy persistent** | `legacy/persistent_layer.py` | Persistent storage | **legacy** | |
| **Legacy atomic** | `legacy/atomic_storage.py` | Atomic storage | **legacy** | |
| **Orchestrator v2** | `outdated/hledac/orchestrator_v2.py` | Old orchestrator | **legacy** | |
| **Orch integration** | `orchestrator_integration.py` | Integrated orchestrator | **legacy** | |
| **Enhanced research** | `enhanced_research.py` | Enhanced research | **legacy** | NOT in hot path |
| **Deep probe** | `deep_probe.py` | Deep probing | **legacy** | NOT in hot path |
| **Autonomous analyzer** | `autonomous_analyzer.py` | Query analysis | **legacy** | NOT in hot path |

---

## 13. Tool/Library Authority

| Oblast | Soubor | Role dnes | Status | Poznámka |
|--------|--------|-----------|--------|-----------|
| **Tool registry** | `tool_registry.py` | Tool schema/cost model | **canonical** | ~39k |
| **Capabilities** | `capabilities.py` | M1 8GB capability gating | **canonical** | ~15k |
| **Evidence log** | `evidence_log.py` | Evidence logging | **canonical** | ~48k |
| **Metrics registry** | `metrics_registry.py` | Metrics collection | **helper** | ~8k |
| **Tool exec log** | `tool_exec_log.py` | Tool execution log | **helper** | ~11k |
| **Resource allocator** | `resource_allocator.py` | Resource allocation | **helper** | ~12k |

---

## 14. Network/Transport Authority

| Oblast | Soubor | Role dnes | Status | Poznámka |
|--------|--------|-----------|--------|-----------|
| **Session runtime** | `network/session_runtime.py` | aiohttp session factory | **canonical** | ~9k |
| **Circuit breaker** | `transport/circuit_breaker.py` | Per-host penalty tracking | **canonical** | |
| **Network init** | `network/__init__.py` | Re-exports | **facade** | |
| **Transport init** | `transport/__init__.py` | Re-exports | **facade** | |

---

## 15. Observations Summary

### Canonical (aktivní, v hot path)
- `__main__.py` — entry point
- `runtime/sprint_lifecycle.py` — lifecycle
- `core/resource_governor.py` — memory
- `pipeline/live_public_pipeline.py` + `live_feed_pipeline.py` — pipelines
- `knowledge/duckdb_store.py` — storage
- `paths.py` — paths
- `config.py` — config
- `knowledge/lmdb_boot_guard.py` — LMDB hygiene

### Facade (přesměrování)
- `__init__.py` — massive re-export
- `autonomous_orchestrator.py` — deprecated facade
- `orchestrator/__init__.py` — thin facade

### Legacy (deprecated)
- `legacy/autonomous_orchestrator.py` — 31k God Object
- `utils/sprint_lifecycle.py` — old lifecycle
- `runtime/sprint_scheduler.py` — UNPLUGGED
- `legacy/coordinators/` — deprecated coordinators
- `outdated/` — old orchestrators

### Helper (mimo hot path)
- Brain moduly — latent capabilities
- Intelligence tools — LAZY loaded
- Context optimization — helper modules
- RL/planning modules — LATENT
