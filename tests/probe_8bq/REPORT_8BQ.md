# Sprint 8BQ — Environment / Dependency / Test Guardrail Truth Audit

## 1. Environment Truth

| Property | Value |
|----------|-------|
| Python | 3.11.8 (.venv/bin/python3) |
| Installed packages | 825 |
| requirements.txt | 2 lines (torch==2.5.1, torchvision==0.20.1) |
| pyproject.toml | DOES NOT EXIST |
| requirements-dev.txt | DOES NOT EXIST |

### Installed Package Truth

| Package | Status |
|---------|--------|
| mlx | **MISSING** (mlx_lm found, which wraps mlx) |
| mlx_lm | **FOUND** |
| coremltools | **MISSING** |
| torch | FOUND |
| orjson, lmdb, duckdb, kuzu, lancedb | FOUND |
| curl_cffi, aiohttp, httpx, websockets | FOUND |
| lxml, bs4, xxhash, faiss, msgspec | FOUND |
| pydantic, fastapi | FOUND |
| asyncpg, psycopg2, redis | FOUND |
| playwright | FOUND |
| numpy, scipy, pandas | FOUND |
| transformers, tokenizers | FOUND |
| structlog, loguru, yara | FOUND |
| psutil | FOUND |
| selectolax | **MISSING** |
| pyahocorasick | **MISSING** |
| vectorscan | **MISSING** |
| igraph | **MISSING** |
| nodriver | **MISSING** |
| pyppeteer | **MISSING** |
| aioredis | **MISSING** |
| flask | **MISSING** |

## 2. Declared vs Installed vs Imported

| Package | Declared | Installed | Imported in Code |
|---------|----------|-----------|-----------------|
| torch | YES (requirements.txt) | YES | YES (5 project files) |
| torchvision | YES (requirements.txt) | YES | NO (unused) |
| mlx | NO | **MISSING** | N/A (mlx_lm wraps it) |
| mlx_lm | NO | YES | YES (hermes3_engine, moe_router) |
| coremltools | NO | **MISSING** | YES (9 files import it) |
| duckdb | NO | YES | YES (1 file: duckdb_store) |
| kuzu | NO | YES | YES (1 file: persistent_layer) |
| lancedb | NO | YES | YES (1 file: lancedb_store) |
| orjson | NO | YES | YES (14 files) |
| lmdb | NO | YES | YES (19 files) |
| curl_cffi | NO | YES | YES (4 files) |
| selectolax | NO | **MISSING** | YES (2 files) |
| pyahocorasick | NO | **MISSING** | NO (0 imports) |
| igraph | NO | **MISSING** | YES (3 files) |
| nodriver | NO | **MISSING** | YES (1 file) |

**CRITICAL**: coremltools is imported by 9 project files but NOT installed.
This means ANE embedder cannot work at runtime without installing it.

**CRITICAL**: selectolax is imported by 2 project files but NOT installed.
**CRITICAL**: igraph is imported by 3 project files but NOT installed.
**CRITICAL**: nodriver is imported by 1 file but NOT installed.

## 3. Module-Level MLX Import Analysis

- Total `import mlx` occurrences: 144
- At line <= 50 (true module-level): 69
- At line > 50 (inside function, lazy): 75

**Pattern**: autonomous_orchestrator.py has 9 lazy `import mlx.core as mx` inside functions.
This is intentional lazy-loading to avoid cold-start MLX cost.
Other files with lazy MLX imports: model_lifecycle.py, tot_integration.py,
coordinators/memory_coordinator.py, tools/vlm_analyzer.py, core/mlx_embeddings.py.

## 4. Unbounded Queues (Invariant Risk)

9 unbounded `asyncio.Queue()` found in project code:

- `autonomous_orchestrator.py:3305`: self._streaming_findings_queue: asyncio.Queue = asyncio.Queue()
- `coordinators/fetch_coordinator.py:298`: self._available = asyncio.Queue()
- `transport/inmemory_transport.py:13`: self._queue = asyncio.Queue()
- `layers/communication_layer.py:155`: self._batch_queue: asyncio.Queue = asyncio.Queue()
- `intelligence/dark_web_intelligence.py:285`: self.url_queue: asyncio.Queue = asyncio.Queue()
- `utils/async_utils.py:175`: q: asyncio.Queue = asyncio.Queue()
- `prefetch/prefetch_cache.py:27`: self._write_queue = asyncio.Queue()
- `brain/hermes3_engine.py:168`: self._batch_queue = asyncio.Queue()

**Risk**: Unbounded queues can accumulate infinite items if consumers are slow.
**Mitigation**: All queues have dedicated consumer tasks. Monitor for memory growth.

## 5. Hardcoded Paths

88 `Path.home()` / `.hledac` references in project code (88 total, mostly in autonomous_orchestrator).
All use `~/.hledac/` as base. This is a convention, not a violation.

## 6. Test Guardrail Map

| Target | Test Hits | Guardrail Value |
|--------|-----------|----------------|
| autonomous_orchestrator | 875 | CRITICAL — any refactor needs this coverage |
| pattern | 1285 | HIGH — pattern mining core invariant |
| paths | 1297 | HIGH — path resolution correctness |
| queue | 318 | MEDIUM — async message passing |
| shutdown | 131 | MEDIUM — graceful shutdown invariant |
| snapshot | 184 | MEDIUM — state recovery |
| hermes3_engine | 85 | HIGH — LLM inference correctness |
| lance | 88 | MEDIUM — vector search |
| fetch_coordinator | 57 | MEDIUM — HTTP transport |
| duckdb_store | 22 | LOW — shadow analytics only |
| mlx_memory | 27 | LOW — memory management |
| moe_router | 25 | MEDIUM — MoE routing |
| kuzu | 1 | LOW — stub only |
| ddgs | 60 | MEDIUM — search integration |
| uvloop | 0 | NONE — not used in tests |

## 7. Invariant Scan Results

| Invariant | Violations | Status |
|-----------|-----------|--------|
| forbidden_gpu_pragma | 0 | ✅ CLEAN |
| module_level_mlx_imports | 144 total (69 true module-level, 75 lazy inside functions) | ⚠️ LAZY OK |
| unbounded_queues | 9 | ⚠️ MONITOR |
| taskgroup_usage | 1 | ✅ CLEAN |
| time.sleep in async | 168 (mostly venv noise, 1 in memory_coordinator) | ⚠️ 1 REAL RISK |
| hardcoded_paths | 88 | ✅ CONVENTION |

**time.sleep risk**: `coordinators/memory_coordinator.py:520` has `time.sleep(0.1)` in async context.
All other time.sleep hits are in venv/site-packages.

## 8. Required Output Table

| ITEM | DECLARED | INSTALLED | IMPORTED | READINESS | BLAST_RADIUS | KEEP/REMOVE/DEV_ONLY | NOTES |
|------|----------|-----------|----------|-----------|--------------|---------------------|------|
| mlx | NO | MISSING* | via mlx_lm | READY | LOW | KEEP | mlx_lm wraps mlx; no direct import needed |
| mlx_lm | NO | YES | YES | READY | MEDIUM | KEEP | hermes3_engine + moe_router |
| coremltools | NO | **MISSING** | YES (9 files) | **CONFLICT** | HIGH | ADD or BREAK | MUST install before ANE works |
| torch | YES | YES | YES (5 files) | READY | MEDIUM | DEV_ONLY | Heavy dep; only 5 real users; consider mlx replacement |
| torchvision | YES | YES | NO | PARTIAL | LOW | REMOVE | Declared but unused in project |
| selectolax | NO | **MISSING** | YES (2 files) | **CONFLICT** | MEDIUM | ADD | Needed by some intelligence modules |
| pyahocorasick | NO | **MISSING** | NO | MISSING | LOW | ADD if needed | O(n) pattern matching |
| igraph | NO | **MISSING** | YES (3 files) | **CONFLICT** | MEDIUM | ADD | relationship_discovery imports it |
| nodriver | NO | **MISSING** | YES (1 file) | **CONFLICT** | LOW | ADD | stealth_crawler may need it |
| duckdb | NO | YES | YES | READY | LOW | KEEP | shadow analytics only |
| kuzu | NO | YES | YES | PARTIAL | LOW | KEEP | stub; activate or remove |
| lancedb | NO | YES | YES | READY | MEDIUM | KEEP | primary vector store |
| orjson | NO | YES | YES | READY | LOW | KEEP | everywhere |
| lmdb | NO | YES | YES | READY | LOW | KEEP | entity storage |
| curl_cffi | NO | YES | YES | READY | MEDIUM | KEEP | stealth HTTP |
| faiss | NO | YES | NO | READY | LOW | KEEP | available but not imported |
| yara | NO | YES | NO | READY | LOW | KEEP | available for IoC matching |
| websockets | NO | YES | YES | READY | LOW | KEEP | certstream client ready |
| redis | NO | YES | YES | READY | LOW | KEEP | available |

## 9. Guardrail Test Subset (Pre-Refactor)

Before any v12 refactor touching these areas, run these test files:

### MLX/Inference (run if touching brain/ or mlx_memory)
- `tests/test_autonomous_orchestrator.py` — 875 hits on autonomous_orchestrator
- `tests/test_sprint37_kv_cache.py` — KV cache correctness
- `tests/test_sprint57.py` — PQ/HNSW index correctness
- `tests/test_sprint54.py` — Arrow/LMDB integration

### Storage/Graph (run if touching knowledge/ or evidence_log)
- `tests/test_sprint50.py` — Kuzu/graph operations
- `tests/test_sprint8as_duckdb_async/` — DuckDB async safety
- `tests/test_sprint8ao_duckdb_sidecar.py` — DuckDB sidecar isolation
- `tests/test_sprint71/test_kernel_optimizations.py` — memory ops

### Network/Transport (run if touching coordinators/ or network/)
- `tests/test_sprint82j_benchmark.py` — FPS benchmark + throughput
- `tests/test_sprint7a.py` — token bucket + M1 thread pools
- `tests/live_8be/test_live_searxng_8be.py` — real search integration

## 10. Final Recommendations

### Immediate actions (before any v12 sprint):
- **Install coremltools**: pip install coremltools — ANE embedder will not work without it; 9 files import it
- **Install selectolax**: pip install selectolax — 2 files import it; needed for HTML parsing
- **Install igraph system dep + python**: brew install igraph; pip install igraph — relationship_discovery.py imports it
- **Install nodriver**: pip install nodriver — stealth_crawler may need it
- **Remove torchvision from requirements.txt**: requirements.txt — Declared but zero imports in project code

### High-risk dependency changes:
- Replacing torch with mlx in ner_engine — 5 files affected; test with tests/test_sprint71/ first
- Adding pyahocorasick — native C extension; may fail to build on M1; test on CI
- Changing coremltools version — ANE compatibility may break
- Adding/removing igraph — C dependency; graph algorithms in relationship_discovery rely on it

### Invariants to enforce automatically:
- **No new `import torch` in boot-path files** (check: autonomous_orchestrator.py, coordinators/, brain/)
- **No new `time.sleep()` in async contexts** (check: coordinators/, brain/, intelligence/)
- **No new unbounded `asyncio.Queue()` without maxsize** (check: All async modules)
- **coremltools must be in requirements.txt if any file imports it** (check: pyproject.toml / requirements.txt)
- **selectolax must be in requirements.txt if any file imports it** (check: pyproject.toml / requirements.txt)

## 11. Summary — Declared vs Reality

The project has a 2-line `requirements.txt` but 825 installed packages.
This means dependency truth is managed by the venv, NOT by a manifest.
This is a maintenance risk: no one knows what's intentional vs accidental.

**Recommendation**: Create `requirements.txt` from the venv snapshot
and divide into `requirements.txt` (prod) and `requirements-dev.txt` (test/dev).
Use `pip freeze > requirements.txt` as the starting point.