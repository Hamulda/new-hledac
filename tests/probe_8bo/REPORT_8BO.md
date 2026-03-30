# Sprint 8BO — Storage / State Ownership Truth Audit

## 1. Executive Summary

| State Area | Canonical Owner | Readiness | Top Risk |
|------------|----------------|-----------|----------|
| Analytics | `knowledge/duckdb_store.py` | READY | DuckDB is shadow-only; not primary store |
| Graph storage | `knowledge/persistent_layer.py` (KuzuDBBackend) | PARTIAL | Kuzu stub falls back to JSON; no real queries |
| Vector/ANN | `knowledge/lancedb_store.py` + persistent_layer HNSW | READY | Two vectors paths (Lance + HNSWlib); overlap |
| Entity metadata | `knowledge/atomic_storage.py` (LMDB) | READY | Solid; only one real issues is competition with persistent_layer |
| Snapshots/priors | `atomic_storage.py` + persistent_layer + planning/ | CONFLICT | Three files claim ownership; no clear winner |
| Evidence/provenance | `evidence_log.py` | READY | Append-only ring buffer; SQLite WAL; well isolated |
| Model cache | `brain/hermes3_engine.py` + `brain/moe_router.py` | READY | Prompt cache + KV cache; well managed |
| Transport session | `coordinators/fetch_coordinator.py` | READY | Session pool; cookies; Tor |

## 2. Storage Inventory (files touching each backend)

### DuckDB (shadow analytics sidecar)
- `knowledge/duckdb_store.py` (646 lines) — `DuckDBShadowStore` class
- Deferred import (never at module level of boot-path files)
- RAMDISK-first: `shadow_analytics.duckdb` → `analytics.duckdb` fallback
- Tables: `shadow_findings`, `shadow_runs`
- Clients: `knowledge/analytics_hook.py`, `tests/live_8be/test_live_searxng_8be.py`
- Verdict: **SHADOW ONLY** — not the primary knowledge store

### Kuzu (graph storage stub)
- `knowledge/persistent_layer.py` — `KuzuDBBackend` class (lines 181-444)
- 5 files reference kuzu; actual import only in persistent_layer.py
- Falls back to `JSONBackend` when kuzu unavailable
- No Cypher queries visible in codebase; schema init exists but unused
- Verdict: **STUB ONLY** — either activate or remove; currently adds confusion

### LanceDB (vector + FTS store)
- `knowledge/lancedb_store.py` (many lines) — `LanceDBStore` class
- Hybrid search: vector similarity + full-text search
- Used by `rag_engine.py` for RAG embeddings
- Referenced by 142 files (mostly keyword hits, not imports)
- Real import sites: `knowledge/lancedb_store.py`, `autonomous_orchestrator.py`
- Verdict: **READY** — primary vector store, well integrated

### LMDB (entity/claim metadata)
- `knowledge/atomic_storage.py` — `AtomicJSONKnowledgeGraph` + `Claim`, `ClaimCluster`, `ClaimClusterIndex`
- 19 project files use lmdb directly
- Zero-copy with orjson; bounded collections; checkpoint integration
- Verdict: **READY** — primary entity store; stable

### HNSW / ANN (in-memory index)
- `knowledge/persistent_layer.py` — `IncrementalHNSW` (Sprint 55)
- PQ Index (Sprint 57) for memory-efficient compression
- LanceDB has its own HNSW via `lancedb.vectords()`
- Verdict: **PARTIAL** — two HNSW paths; persistent_layer HNSW is fallback for small graphs

### Evidence Log
- `evidence_log.py` (1270 lines) — `EvidenceLog` class
- SQLite WAL mode; batched async writes; ring buffer (deque maxlen)
- Encrypted payload support (cryptography hazmat)
- 25058 hits in boundary audit (mostly keyword matches, not direct use)
- Verdict: **READY** — well isolated, clear ownership

## 3. Snapshot / Priors — Ownership Conflict

Three locations claim snapshot/prior ownership:

| Location | Class/Module | Lines | Claim |
|----------|-------------|-------|-------|
| `knowledge/atomic_storage.py` | `SnapshotStorage`, `SnapshotEntry` | ~200 | Sprint 6 checkpoint storage |
| `knowledge/persistent_layer.py` | `PersistentKnowledgeLayer` | 3575 | WARC/WACZ snapshot, MementoResolver |
| `planning/` | `htn_planner.py`, `cost_model.py` | 242+169 | HTN task decomposition state |
| `autonomous_orchestrator.py` | `_CheckpointStore` | ~500 | Sprint 6 checkpoint |

**Problem**: No single `SnapshotManager`. Checkpoint state is fragmented.
The `_CheckpointStore` in autonomous_orchestrator overlaps with `SnapshotStorage` in atomic_storage.

**Resolution needed**: Designate ONE canonical owner — likely `atomic_storage.py` `SnapshotStorage`.

## 4. Boundary Audit Summary

| Area | Total Hits | Real Signal |
|------|-----------|-------------|
| analytics | 250 | DuckDB shadow only |
| graph | 40631 | Mostly 'graph' keyword noise |
| vectors | 9488 | Mix of LanceDB + HNSW + Embedding mentions |
| snapshots | 1637 | Fragmented across 4+ locations |
| evidence | 25058 | Mostly keyword noise; evidence_log is the real owner |

## 5. Duplication and Boundary Conflicts

### D-1: Two vector search paths
- `LanceDBStore` (knowledge/lancedb_store.py) — full hybrid search
- `PersistentKnowledgeLayer.find_similar_vectors()` — HNSWlib + PQ fallback
Both do ANN vector search. persistent_layer is used when graph is small (<100 nodes).
**Risk**: Split brain — same vector found by different paths with different scores.
**Resolution**: LanceDB is primary; persistent_layer HNSW is fine as small-graph fallback.

### D-2: Kuzu vs JSONBackend in persistent_layer
`KuzuDBBackend` and `JSONBackend` both implement same interface.
Kuzu is loaded lazily and falls back to JSON when unavailable.
**Risk**: Active code path is JSONBackend. Kuzu is dead weight until activated.
**Resolution**: Either activate Kuzu (implement real Cypher queries) or remove KuzuDBBackend class.

### D-3: SnapshotStorage vs _CheckpointStore
Both store checkpoint state. `SnapshotStorage` (atomic_storage) and `_CheckpointStore` (orchestrator).
**Risk**: Two checkpoint formats, two load/save paths.
**Resolution**: Deprecate one. Keep `SnapshotStorage` in atomic_storage as canonical.

### D-4: analytics_hook vs duckdb_store
`knowledge/analytics_hook.py` wraps `DuckDBShadowStore` for shadow analytics.
`knowledge/duckdb_store.py` is the actual store.
**Risk**: Low — hook is a thin wrapper. Fine as-is.

## 6. Decision Points Before v12

| Decision | Options | Recommended |
|----------|---------|-------------|
| Graph store canonical | Kuzu vs JSONBackend | Activate Kuzu OR remove KuzuDBBackend — decide one |
| Snapshot canonical owner | atomic_storage vs orchestrator | atomic_storage SnapshotStorage |
| Vector primary | LanceDB vs persistent_layer HNSW | LanceDB primary; persistent_layer HNSW small-graph fallback |
| Analytics canonical | DuckDB shadow vs primary | DuckDB stays shadow; not primary store |
| Kuzu future | Keep stub or remove | Remove stub if not activated in v12 |

## 7. Required Output Table

| STATE_AREA | CURRENT_OWNER | OTHER_FILES | READINESS | DUPLICATION_RISK | CANONICAL_OWNER | PRE-REQ_FIXES | NOTES |
|------------|--------------|-------------|-----------|------------------|-----------------|---------------|-------|
| analytics storage | knowledge/duckdb_store.py | analytics_hook.py | READY | LOW | duckdb_store.py | None | Shadow mode only |
| graph storage | knowledge/persistent_layer.py (KuzuDBBackend) | graph_rag.py | PARTIAL | HIGH | persistent_layer.py | Activate Kuzu or remove | Kuzu is stub; falls back to JSON |
| vector/ANN | knowledge/lancedb_store.py + persistent_layer | rag_engine.py | READY | MEDIUM | lancedb_store.py | Define small-graph boundary | LanceDB primary; HNSW fallback |
| entity/claim metadata | knowledge/atomic_storage.py | persistent_layer.py | READY | LOW | atomic_storage.py | None | LMDB-backed; stable |
| snapshots/priors | CONFLICT (atomic_storage + orchestrator + planning) | multiple | CONFLICT | HIGH | atomic_storage.py SnapshotStorage | Unify checkpoint format | Remove _CheckpointStore |
| evidence/provenance | evidence_log.py | autonomous_orchestrator.py | READY | LOW | evidence_log.py | None | Ring buffer; SQLite WAL |
| model cache state | brain/hermes3_engine.py | moe_router.py | READY | LOW | hermes3_engine.py | None | KV cache + prompt cache |
| transport session | coordinators/fetch_coordinator.py | security_coordinator.py | READY | LOW | fetch_coordinator.py | None | Session pool + Tor |

## 8. Final Recommendations

### 10 items to extend (existing files):
- Canonicalize snapshots → *knowledge/atomic_storage.py SnapshotStorage*: Remove _CheckpointStore from orchestrator; migrate to SnapshotStorage
- Define vector boundary → *knowledge/lancedb_store.py*: Document: LanceDB for >100 nodes, HNSW fallback below; no split-brain scoring
- Activate or remove Kuzu → *knowledge/persistent_layer.py KuzuDBBackend*: Implement real Cypher queries OR delete KuzuDBBackend class entirely
- Extend DuckDB analytics → *knowledge/duckdb_store.py*: Add query_recent_findings() + analytics_hook integration for run analytics
- Consolidate evidence queries → *evidence_log.py*: Ensure all evidence reads go through EvidenceLog.query(), not raw file access
- HNSW/PQ tuning → *knowledge/persistent_layer.py*: PQ training threshold already set (1000 vectors); tune ef_construction and M parameters
- LanceDB FTS integration → *knowledge/lancedb_store.py*: Use LanceDB FTS for keyword search instead of separate regex-based search
- atomic_storage LMDB expansion → *knowledge/atomic_storage.py*: Expand ClaimCluster coverage; integrate with pattern_mining heavy hitters
- graph_rag orchestration → *knowledge/graph_rag.py*: GraphRAGOrchestrator already has multi-hop + centrality; wire into autonomous_orchestrator
- WARC archival path → *knowledge/persistent_layer.py WarcWriter*: WarcWriter + MementoResolver already exist; wire into Wayback rescue pipeline

### 5 items NOT to add (would create storage chaos):
- New graph database — Kuzu or LanceDB is sufficient; adding Neo4j/Arango would triple the graph stack
- Separate snapshots module — consolidate into atomic_storage SnapshotStorage first
- Another analytics backend — DuckDB shadow is sufficient; don't add ClickHouse/Parquet pipeline
- Vector store migration — LanceDB + HNSW already cover ANN; don't add Faiss as third layer
- Evidence file format changes — SQLite WAL is correct; don't add JSONL or Parquet evidence store

### Critical pre-v12 decisions:
- **Kuzu decision**: Remove KuzuDBBackend stub or implement real Cypher queries within 1 sprint
- **Snapshot ownership**: Deprecate autonomous_orchestrator._CheckpointStore; migrate to atomic_storage.SnapshotStorage
- **Vector boundary**: Document the LanceDB vs HNSW fallback boundary formally in docstring
- **DuckDB scope**: Confirm DuckDB stays shadow-only; do NOT promote to primary graph/knowledge store