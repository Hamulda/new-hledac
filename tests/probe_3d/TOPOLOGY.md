# Sprint 3D: LMDB Topology Manifest
# Generated during Sprint 3D LMDB topology completion

## Canonical LMDB Roots (from paths.py)

### Sprint/Ephemeral LMDB
Location: `{RAMDISK_ROOT}/db/lmdb/sprint/` (under `SPRINT_LMDB_ROOT`)
- `tools/lmdb_kv.py` — ephemeral KV store (64MB explicit, domain-specific)
- `planning/task_cache.py` — ephemeral task decomposition cache (param `max_size_mb`)
- `prefetch/prefetch_cache.py` — ephemeral prefetch cache (param `max_size_mb`)

### Persistent LMDB
Location: `{RAMDISK_ROOT}/db/lmdb/` (under `LMDB_ROOT`)
- `tools/source_bandit.py` — cross-sprint bandit learning (10MB explicit)
- `dht/local_graph.py` — persistent graph state (100MB via `open_lmdb`)
- `federated/model_store.py` — persistent model weights (100MB via `open_lmdb`)
- `security/key_manager.py` — persistent encryption keys (10MB via `open_lmdb`)

### Already Canonical (using open_lmdb correctly)
- `dht/local_graph.py` ✅
- `federated/model_store.py` ✅
- `security/key_manager.py` ✅
- `utils/sketches.py` ✅ (LMDB cold storage)

## Files Migrated in Sprint 3D
- `tools/lmdb_kv.py` — now uses `open_lmdb()` with SPRINT_LMDB_ROOT + fallback
- `planning/task_cache.py` — now uses `open_lmdb()` with SPRINT_LMDB_ROOT
- `prefetch/prefetch_cache.py` — now uses `open_lmdb()` with SPRINT_LMDB_ROOT
- `tools/source_bandit.py` — now uses `open_lmdb()` (lazy import) with LMDB_ROOT + backward-compat fallback

## Out of Scope / Prohibited
- `knowledge/atomic_storage.py` — prohibited
- `knowledge/lancedb_store.py` — prohibited
- `coordinators/fetch_coordinator.py` — prohibited
- `knowledge/duckdb_store.py` — prohibited
- `tools/session_manager.py` — not audited (not in allowed files list)

## map_size Discipline
- Env var: `GHOST_LMDB_MAX_SIZE_MB` (default 512MB)
- Sprint caches: small explicit sizes (64MB, 100MB) — intentional domain-specific bounds
- Persistent stores: `open_lmdb()` with env-driven size or explicit domain-specific sizes
- Hardcoded `lmdb.open()` remaining only in prohibited files

## Env-Driven Helpers (in paths.py)
- `lmdb_map_size()` — returns env-driven map_size in bytes
- `get_lmdb_max_size_mb()` — returns env var value in MB
- `open_lmdb(path, map_size=None, **kw)` — canonical opener with lock recovery
