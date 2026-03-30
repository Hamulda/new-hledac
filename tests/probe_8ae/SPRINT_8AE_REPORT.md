# SPRINT 8AE — Final Report

## Změněné soubory

| Soubor | Change |
|--------|--------|
| `hledac/universal/pipeline/live_public_pipeline.py` | **NEW** — 632 řádků |
| `hledac/universal/tests/probe_8ae/__init__.py` | **NEW** |
| `hledac/universal/tests/probe_8ae/test_live_public_pipeline.py` | **NEW** — 41 testů |

## Python/Interpreter Truth
- Python 3.12.12 (pyenv, `.pyenv/shims/python3`)
- `msgspec_1000_alloc_ms=0.056` — msgspec zero-copy alloc OK
- Modul se importuje bez chyb

## Ground-Truth Gate Existence
```
hledac/universal/discovery/duckduckgo_adapter.py:
  class DiscoveryHit(msgspec.Struct, frozen=True, gc=False)
  class DiscoveryBatchResult(msgspec.Struct, frozen=True, gc=False)
  async def async_search_public_web(...)

hledac/universal/fetching/public_fetcher.py:
  class FetchResult(msgspec.Struct, frozen=True, gc=False)
  async def async_fetch_public_text(...)

hledac/universal/patterns/pattern_matcher.py:
  class PatternHit(NamedTuple)
  def get_pattern_matcher() -> _PatternMatcherState
  def match_text(text: str, *, boundary_policy: str = "none") -> list[PatternHit]

hledac/universal/knowledge/duckdb_store.py:
  class CanonicalFinding(msgspec.Struct, frozen=True, gc=False)
  class FindingQualityDecision(msgspec.Struct, frozen=True, gc=False)
  async def async_ingest_finding(...) -> FindingQualityDecision | ActivationResult
  async def async_ingest_findings_batch(...) -> list[FindingQualityDecision | ActivationResult]

hledac/universal/network/session_runtime.py:
  def _check_gathered(results) — [I6] CancelledError re-raised, [I7] BaseException re-raised

hledac/universal/core/resource_governor.py:
  class UMAStatus(frozen dataclass)
  def evaluate_uma_state(system_used_gib: float) -> str
  def sample_uma_status() -> UMAStatus
```

## Discovery/Fetch/Matcher/Storage Surface Truth
- **Discovery**: `_ASYNC_DISCOVERY_SEARCH` — patchable global; `_ensure_discovery_patched()` na module init
- **Fetch**: `_ASYNC_FETCH_PUBLIC_TEXT` — patchable global; `_ensure_patched()` v `async_run_live_public_pipeline`
- **Matcher**: `_SYNC_MATCH_TEXT` — patchable global; `match_text()` z 8X volán přes `run_in_executor`
- **Storage**: duck-typed `store.async_ingest_findings_batch()` — isinstance NOT used

## PipelineRunResult Contract
```python
PipelinePageResult(url, fetched, matched_patterns, accepted_findings, stored_findings, error?)
PipelineRunResult(query, discovered, fetched, matched_patterns, accepted_findings,
                  stored_findings, patterns_configured, pages: tuple[...], error?)
```

## Extraction Policy Truth
- `markdownify`: NOT installed → fallback `html.parser.HTMLParser` (fail-soft, always available)
- HTML→text běží přes `asyncio.run_in_executor(None, _html_to_text, html_content)` — thread, ne event loop
- Text cap: `MAX_EXTRACTED_TEXT_CHARS = 200_000`
- Plain text pass-through: HTMLParser falls back to regex strip on exception

## Pattern-Backed Finding Mapping
```
DiscoveryHit → FetchResult → _html_to_text() → match_text()
                                                  ↓
                                              PatternHit
                                                  ↓
                        _extract_live_public_findings_from_page()
                                                  ↓
                                          CanonicalFinding
                                          (query, source_type, confidence,
                                           provenance, payload_text)
```
- Per-page dedup: `(value, label, pattern)` exact set
- `source_type = "live_public_pipeline"`
- `confidence = 0.8`
- `provenance = ("duckduckgo", url, label, pattern)`
- `payload_text = _pattern_context(text, hit_start, hit_end, radius=100)`
- `finding_id = SHA-256(... )[:16]` — hash() forbidden

## UMA Interaction Truth
- `sample_uma_status()` + `evaluate_uma_state()` volány lazy uvnitř `_get_uma_state()`
- `uma_state == "emergency"` → fail-soft abort s `error="uma_emergency_abort"`, `pages=()`
- `uma_state in {"critical","emergency"}` → `effective_concurrency = 1` (clamps from default 5)
-UMA state checked BEFORE discovery (fail-fast on emergency)

## Benchmarks
- `msgspec_1000_alloc_ms=0.056`
- HTML extraction 1000 iterations < 500ms ✓
- Pattern context 1000 iterations < 50ms ✓
- Finding construction 100 findings < 1s ✓
- `finding_id` determinism: 100 iterací → 1 unique ID ✓

## Gates
```
pytest probe_8ae/                     → 41 passed
pytest probe_8ac/ probe_8ad/ probe_8w/ probe_8x/ probe_8s/ probe_8ab/ ao_canary
                                 → 259 passed
COMBINED                             → 300 passed (0 failures)
```

## Memory Impact (M1 8GB)
- Pipeline je stateless orchestration — žádné vlastní modely, žádné LMDB
- `asyncio.Semaphore` per-call (ne global)
- `del fetched_text` po HTML extrakci — uvolňuje referenci
- Text cap 200k znaků na stránku — hard limit
- Všechen heavy I/O přes `run_in_executor` — event loop non-blocking

## Deferred Položky
- `markdownify` není v environmentu — fallback HTMLParser plně funkční
- `_patch_discovery` / `_patch_fetcher_and_matcher` — pouze pro testy (pyright unused warning)
- `hit_title`, `hit_snippet`, `hit_rank` — passed do `_fetch_and_process_page` pro budoucí telemetry (no-op dnes)
- `fetch_elapsed` — commented out, available for future telemetry

## Známé Limity
1. **PatternMatcher case-insensitivity**: `match_text()` lowercases text globally — known limit per 8X surface
2. **Per-page dedup only**: mezi-stránkové duplicity nejsou řešeny (8W quality gate handles)
3. **UMA hysteresis**: lokální hysteresis state není persistována mezi voláními (každé volání startuje s `previous_io_only=False`)
4. **No retry on fetch timeout**: `asyncio.wait_for` timeout → stránka označena jako error, další stránky pokračují
5. **discovery `error` attribute**: duck-typed přes `hasattr` — správně funguje s DiscoveryBatchResult i dict
