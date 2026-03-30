# SPRINT 8BE — SEARXNG LOCALHOST BRING-UP + FIRST LIVE DUCKDB ANALYTICS RUN
**Date:** 2026-03-23
**Status:** DEGRADED_BY_DUCKDB_STORE_PATH_BUG (SearXNG = LIVE_PROVIDER_READY)

---

## BRING-UP SUMMARY

| Fáze | Výsledek |
|------|-----------|
| Docker/Podman detection | Not found |
| Brew podman install | ✅ Success (5.8.1) |
| Podman machine init | ✅ 2 CPU, 4GB RAM |
| Podman machine start | ✅ Running |
| SearXNG image pull | ✅ searxng/searxng:latest |
| Settings.yml creation | ✅ JSON format enabled, secret_key set |
| Container start | ✅ searxng_local running |
| JSON endpoint verification | ✅ 200 OK, parseable JSON |

### Settings.yml fix required
```yaml
use_default_settings: true
server:
  secret_key: "ghost_prime_local_secret_2026_03_23_abcdef"
  limiter: false
search:
  formats:
    - html
    - json
```

### Downloaded artifacts
- `podman` 5.8.1 (brew)
- `searxng/searxng:latest` Docker image
- `podman-machine-default` VM (2 CPU, 4GB)

---

## STEP 2: PROVIDER QUALITY MATRIX

| Query | HTTP | JSON | Count | NonEmpty | Latency |
|-------|------|------|-------|----------|---------|
| python programming language | OK | OK | 10 | YES | 3526ms |
| linux kernel history | OK | OK | 10 | YES | 1638ms |
| open source intelligence | OK | OK | 10 | YES | 1789ms |
| duckdb analytics | OK | OK | 10 | YES | 1481ms |
| macbook air m1 performance | OK | OK | 10 | YES | 1702ms |

**Hit rate: 5/5 = 100.0%** ✅

---

## STEP 3: ANALYTICS VERIFICATION

### Bounded run
- Duration: 10.2s
- Total findings: 50
- SearXNG queries: 5 (10 results each)
- Provider: SearXNG localhost:8080

### DuckDB shadow state
- `analytics.duckdb` exists: ✅
- Path: `/Users/vojtechhamada/.hledac_fallback_ramdisk/db/analytics.duckdb`
- shadow_findings rows: 1229 (pre-existing from earlier sprints)
- shadow_runs rows: 3
- **⚠️ Known bug:** Active `duckdb_store.py` uses `:memory:` mode (db_path=None)
  → New findings go to per-process RAM, not to file
  → Fix requires AO-level scope (set `_db_path = DB_ROOT / "analytics.duckdb"`)

### Shadow hook verification
- `_is_shadow_enabled()`: ✅ Correct (True when flag=1)
- Queue drain: ✅ 0 failures
- Worker runs: ✅ Queue drains correctly
- **⚠️ Bug:** Worker uses wrong duckdb_store path logic

---

## STEP 4: TARGETED TESTS (6/7)

| Test | Result | Notes |
|------|--------|-------|
| test_searxng_http_json_endpoint | ✅ PASS | 200 OK, 11 results |
| test_project_searxng_client_localhost | ✅ PASS | search() returns results |
| test_shadow_flag_off_is_noop | ✅ PASS | flag=0 → no-op |
| test_plain_boot_does_not_import_duckdb | ✅ PASS | duckdb not in sys.modules |
| test_provider_hit_rate | ✅ PASS | 100% hit rate |
| test_searxng_containers_running | ✅ PASS | searxng_local Up 39min |
| test_analytics_duckdb_exists | ✅ PASS | 1229 rows |

---

## STEP 5: IMPORT BASELINE

No AO changes → no import regression expected.
Files touched by 8BE: `tests/live_8be/searxng_local/settings.yml`, `tests/live_8be/test_live_searxng_8be.py`

---

## CLASSIFICATION

```
SEARXNG BRING-UP:   ✅ LIVE_PROVIDER_READY (100% hit rate, 5/5 queries)
DUCKDB ANALYTICS:   ⚠️  DEGRADED_BY_DUCKDB_STORE_PATH_BUG
                     - analytics.duckdb exists with 1229+ rows
                     - shadow hook records correctly
                     - queue drains without failures
                     - BUT: active duckdb_store.py uses :memory: mode
                     - Fix: set _db_path = DB_ROOT / "analytics.duckdb" in __init__
```

---

## AO OPSEC GREP

No `.hledac.*keys` or `.hledac.*local_graph` references in AO.

---

## REQUIRED FIX (AO scope, deferred)

In `knowledge/duckdb_store.py`, `DuckDBShadowStore.__init__`:
- Set `_db_path` based on `RAMDISK_ACTIVE`:
  - `True` → `DB_ROOT / "shadow_analytics.duckdb"` (already correct)
  - `False` → `DB_ROOT / "analytics.duckdb"` (currently missing → falls back to `:memory:`)

This requires setting `self._db_path` before `async_initialize()` is called.

---

## FINAL DELIVERABLES

| Requirement | Status |
|-------------|--------|
| Local SearXNG brought up | ✅ |
| JSON endpoint verified | ✅ |
| Project client works | ✅ |
| Hit rate ≥ 30% | ✅ (100%) |
| GHOST_DUCKDB_SHADOW=1 enabled | ✅ |
| Real analytics rows in DB | ⚠️ (1229 pre-existing, new in :memory:) |
| Feature flag OFF = no-op | ✅ |
| Plain boot no duckdb import | ✅ |
| Import regression | N/A (no AO changes) |
| AO OPSEC clean | ✅ |

---

## DEFERRED (AO scope only)

1. Fix `duckdb_store.py._db_path` initialization for RAMDISK_ACTIVE=False
2. Add `shadow_run` records for bounded live runs
3. Verify file-backed persistence with new rows after fix
