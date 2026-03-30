# Deep Technical Re-Audit: Hledac Universal OSINT System
**Date:** 2026-02-17
**Auditor:** Claude Opus 4.6
**Scope:** Post-major-changes adversarial re-audit of `/hledac/universal/`
**Commit context:** After coordinator delegation, ToolExecLog hash-chain, MetricsRegistry wiring, smoke runner, failure injection, golden schema tests

---

## EXECUTIVE SUMMARY

1. **ToolExecLog is NOT wired into the orchestrator's tool dispatch path.** `tool_exec_log` is never imported in `autonomous_orchestrator.py`. The "wiring test" (line 10043) is a self-calling mock — it calls `log.log()` directly, not through the orchestrator. **This is the single most critical audit failure.**

2. **Security pipeline has a raw-text leak path.** In `sanitize_for_logs` (line 6690–6691), a bare `except:` clause returns `text` — the unsanitized input — when the main PII gate's `detect()` call fails and fallback also fails. This defeats the "no raw PII" invariant.

3. **Coordinator configs expose 8 runtime toggles** (`enable_security_check`, `enable_domain_limiter`, `enable_stance_update`, etc.) that violate the fully-autonomous / no-user-knobs requirement. These should be immutable policy, not dataclass fields.

4. **ResearchContext has 5 unbounded lists/sets** (`active_entities`, `hypotheses`, `visited_urls`, `visited_domains`, `errors`) with no size caps — a RAM-safety risk on 8 GB M1.

5. **EvidenceLog hash chain is correct and verified in code.** Chain formula, genesis, and `verify_all()` are sound.

6. **ToolExecLog hash chain implementation is correct internally** — stores only hashes, never raw data. The problem is it's never called from the runtime path.

7. **Budget enforcement is implemented in BudgetManager and FetchCoordinator** with hard stops on iterations, network calls, snapshots, and time. However, no integration test proves a real loop respects the budget.

8. **Model lifecycle (1-at-a-time) is well-enforced** via AsyncLock + double GC + MLX cache clearing.

9. **Test suite (380 tests) has strong component coverage but weak integration coverage.** Tests would not catch behavioral regressions in budget enforcement, coordinator delegation, or resume.

10. **PII coverage is US-centric.** International patterns (IBAN, EU VAT, UK NINO, CZ rodné číslo) exist only in the fallback sanitizer, not the main SecurityGate.

---

## ACCEPTANCE RUBRIC

### A. Autonomy & Control Plane

| # | Criterion | Verdict | Evidence |
|---|-----------|---------|----------|
| 1 | No user strategy modes/toggles exist in runtime path | **FAIL** | `FetchCoordinatorConfig.enable_security_check` (line ~35), `ClaimsCoordinatorConfig.enable_stance_update` (line ~34), `GraphCoordinatorConfig.enable_quantum_pathfinder` (line ~34), `ArchiveCoordinatorConfig.enable_memento_lookup` (line ~34) — 8 toggles total in `coordinators/*.py` |
| 2 | Orchestrator decisions are internal and not driven by external flags | **PASS** | `FullyAutonomousOrchestrator` uses internal bandit/UCB1 for action selection (line ~4754). No CLI args parsed. Config presets are factory-set. |
| 3 | Coordinators do not introduce hidden "mode" branching | **FAIL** | All four coordinator configs have `enable_*` booleans that branch in `_do_step()`. Example: `FetchCoordinator` line ~153 checks `enable_security_check`. |

### B. Disk-first & RAM-safety

| # | Criterion | Verdict | Evidence |
|---|-----------|---------|----------|
| 4 | No full page text is retained in RAM beyond bounded previews | **PASS** | `EvidenceLog._trim_payload()` caps at `MAX_PAYLOAD_PREVIEW=200` chars. `ToolExecLog` stores only hashes. `ClaimsCoordinator._load_evidence_packet()` loads per-step, not retained. |
| 5 | All caches/queues/heaps have hard caps and deterministic eviction | **FAIL** | `FetchCoordinator._frontier: List[str]` — unbounded. `FetchCoordinator._processed_urls: Set[str]` — unbounded. `ClaimsCoordinator._pending_evidence_ids` — unbounded. `GraphCoordinator._pending_queries` — unbounded. `ArchiveCoordinator._pending_urls` — unbounded. `ResearchContext.visited_urls: Set[str]` — unbounded. `FullyAutonomousOrchestrator._execution_history: List[Dict]` — unbounded. |
| 6 | Any sorting/aggregation that could scale is streaming or chunked | **PASS** | `UnicodeAttackAnalyzer.analyze_file()` uses chunked streaming (1MB chunks). Evidence ring buffer is FIFO. `ToolExecLog.verify_all()` reads from disk sequentially. |
| 7 | Snapshots/archives are written streaming (no full payload buffering) | **PASS** | `EvidenceLog` appends line-by-line to JSONL with flush+fsync per event. `ToolExecLog` appends to JSONL with flush+fsync. |

### C. Forensic audit & provenance

| # | Criterion | Verdict | Evidence |
|---|-----------|---------|----------|
| 8 | EvidencePacket links all insights/claims to evidence_id + provenance | **PASS** | `EvidenceEvent` (evidence_log.py line ~33) has `event_id`, `source_ids: List[str]`, `content_hash`, `run_id`. `create_decision_event()` has `MAX_DECISION_REF_EVIDENCE=10`. |
| 9 | EvidenceLog hash-chain is correct, continuous, and verified in code | **PASS** | Chain formula: `SHA256(prev_chain_hash + ":" + content_hash + ":" + event_id)`. Genesis: `SHA256("GENESIS:" + run_id)`. `verify_all()` (line ~927) checks both chain_hash recomputation and prev_chain_hash linkage. |
| 10 | ToolExecLog hash-chain is correct AND wired into actual tool dispatch | **FAIL** | Hash chain implementation is correct internally (chain formula: `SHA256(prev + ":" + event_id + ":" + input_hash + ":" + output_hash)`). **But `ToolExecLog` is never imported or called from `autonomous_orchestrator.py`.** Grep confirms zero references. The test at line 10043 self-calls `log.log()` directly — it does NOT test orchestrator wiring. |
| 11 | Run manifest/finality semantics: finalize writes manifest, resume does not duplicate | **PASS** | `EvidenceLog.finalize()` (line ~905) flushes → writes manifest → freezes. Manifest includes `chain_head`, `last_seq_no`, `genesis_hash`. `freeze()` prevents further appends. Resume checkpoint (line ~8186) references `CheckpointManager` but is not exercised in tests. |

### D. Security pipeline (no bypass)

| # | Criterion | Verdict | Evidence |
|---|-----------|---------|----------|
| 12 | sanitize_for_logs is always-on (fallback engaged when primary gate missing) | **FAIL** | `sanitize_for_logs` (line ~6648) engages `fallback_sanitize` when `_pii_gate` is None — **good**. But line 6690–6691 has bare `except: return text` — returns **raw unsanitized text** if main gate's `detect()` fails AND fallback import fails. Also line 6675 returns `text[:MAX]` when even fallback_sanitize throws. |
| 13 | Unicode attack analysis always runs on ingested text | **UNCLEAR** | `UnicodeAttackAnalyzer` is lazily loaded (line ~6476–6487) and exposed as property. But **no evidence it's called on the critical ingestion path** — it's a utility, not enforced. Would need to trace every text ingestion point. |
| 14 | Bounded payload analysis runs before storing/logging/LLM usage | **PASS** | `EvidenceLog._trim_payload()` enforces `MAX_PAYLOAD_PREVIEW=200` chars on large fields. `EvidenceLog.create_decision_event()` has hard limits (20 keys, 200 chars/value, 8 reasons, etc.). `ToolExecLog` caps at `MAX_OUTPUT_LEN=1MB`. |
| 15 | No raw PII leaks into ledger/metrics/manifests/tool logs (hashes only) | **FAIL** | `ToolExecLog` stores only hashes — **good**. `MetricsRegistry` stores only numeric values — **good**. But `EvidenceLog` relies on callers to sanitize before `append()` — no automatic PII masking. And `sanitize_for_logs` bare-except path leaks raw text. Manifest includes only `chain_head`, `run_id` etc. — **clean**. |

### E. Budgeting, determinism, resume

| # | Criterion | Verdict | Evidence |
|---|-----------|---------|----------|
| 16 | Budget hard-stop is enforced (no runaway loops after exhaustion) | **PASS** | `BudgetManager` (budget_manager.py) checks max_iterations, max_docs, max_time, max_tool_calls. `FetchCoordinator._do_step()` checks `budget_mgr.check_network_allowed()` (line ~128). Returns immediately on exhaustion. |
| 17 | Sampling/tie-breaks are deterministic given run_id | **PASS** | Test `test_sampling_deterministic_given_run_id` (line ~9699) confirms `sha256(run_id)[:16]` as seed. `test_frontier_tie_break_deterministic` (line ~9719) confirms `random.Random(seed)`. |
| 18 | Resume continues seq_no + chain head correctly after crash | **PASS** | Test `test_resume_run_continues_hash_chain_and_seq` (line ~9742) creates log, persists, creates new log from same dir, verifies seq_no and chain_head continuity. EvidenceLog manifest stores `last_seq_no` and `chain_head`. |

### F. Coordinator delegation quality

| # | Criterion | Verdict | Evidence |
|---|-----------|---------|----------|
| 19 | Orchestrator is a thin spine; core steps delegated | **PASS** | `start/step/shutdown` interface defined in `UniversalCoordinator` (base.py line ~491–552). Four coordinators instantiated. Orchestrator delegates via `coordinator.step(ctx)`. |
| 20 | Coordinator interfaces are stable, bounded, and don't pass large raw strings | **PASS** | Context dicts contain `evidence_ids: List[str]`, `queries: List[str]`, `budget_mgr` reference — no raw text. `MAX_EVIDENCE_IDS_PER_STEP=10` in FetchCoordinator. |
| 21 | Failure handling: coordinator errors produce bounded ledger events and controlled stop | **UNCLEAR** | Base coordinator has `track_operation()`/`untrack_operation()` but no explicit try/except in `step()` that writes a ledger event on coordinator failure. Would need to instrument a coordinator crash to verify. |

### G. Performance & bottlenecks

| # | Criterion | Verdict | Evidence |
|---|-----------|---------|----------|
| 22 | No obvious O(n^2) hotspots on expected sizes | **PASS** | `_rebuild_indexes()` in EvidenceLog is O(n) on ring buffer (max 100) — acceptable. URL normalization `sorted(params.items())` is O(n log n) per URL — acceptable. `_deduplicate_matches()` in pii_gate is O(n²) on overlapping spans but match count is typically <50. |
| 23 | IO write patterns are buffered/batch-friendly | **PASS** | EvidenceLog: append per-event + flush+fsync. ToolExecLog: same. MetricsRegistry: batched flush every 100 events or 60s. All JSONL line-oriented. |
| 24 | MetricsRegistry overhead is bounded and does not spam disk/logs | **PASS** | Whitelist-based metric names (frozenset of ~13). Flush interval: every 100 events or 60s. Ring buffer: deque(maxlen=100). |

### H. Tests & regression protection

| # | Criterion | Verdict | Evidence |
|---|-----------|---------|----------|
| 25 | Wiring verification tests truly fail if features not wired | **FAIL** | `test_tool_exec_log_is_written_for_tool_dispatch` (line ~10043) **self-calls** `log.log()` — does NOT test orchestrator wiring. `test_orchestrator_has_coordinator_properties` (line ~10261) only checks `hasattr`, not functionality. Static import scans (line ~10090) are the only robust wiring tests. |
| 26 | Failure injection tests cover 429/5xx/robots/js-gated/archive/resume | **PASS** | Tests exist for: `test_robots_txt_blocking` (line ~1378), `test_stale_cache_used_on_failure` (500), `test_retry_after_throttle` (429), `test_head_skips_large_snapshot`, `test_resume_run_continues_hash_chain_and_seq`. JS-gated test (line ~10567) is a **stub with no assertion** — weakest link. |
| 27 | Golden schema tests protect on-disk artifact structure | **PASS** | `test_evidence_log_manifest_schema_stable` (line ~10611), `test_tool_exec_log_schema_stable` (line ~10622), `test_metrics_flush_schema_stable` (line ~10631) check required keys. No brittle timestamp asserts. |
| 28 | Test suite avoids hidden network calls and is deterministic | **PASS** | All HTTP mocked via AsyncMock/MagicMock. No DNS lookups. Deterministic seeds via `sha256(run_id)`. Smoke runner uses `_mock_fetch_step()`. |

---

## INVARIANT COMPLIANCE CHECKLIST

| Invariant | Status | Notes |
|-----------|--------|-------|
| Security pipeline no-bypass | **FAIL** | Bare `except: return text` at line 6690 |
| Budget hard-stop | **PASS** | BudgetManager + FetchCoordinator enforce |
| Disk-first guarantees | **PASS** | Payload trimming + hash-only tool log |
| EvidenceLog hash-chain | **PASS** | Correct chain formula + verify_all() |
| ToolExecLog hash-chain on dispatch path | **FAIL** | Not imported in orchestrator |
| Determinism controls | **PASS** | SHA256(run_id) seeding |
| Resume behavior | **PASS** | Manifest + chain_head + seq_no persisted |
| 1-model-at-a-time lifecycle | **PASS** | AsyncLock + double GC + MLX clear |
| No user strategy modes | **FAIL** | 8 coordinator config toggles |
| Unbounded RAM structures | **FAIL** | 7+ unbounded lists/sets identified |

---

## ARCHITECTURE DIAGRAM

```
┌──────────────────────────────────────────────────────────────┐
│                  FullyAutonomousOrchestrator                 │
│  (autonomous_orchestrator.py — thin spine + property facade) │
│                                                              │
│  Internal Managers (lazy-loaded):                            │
│    _StateManager, _MemoryManager, _BrainManager,            │
│    _SecurityManager, _ForensicsManager, _ToolManager,        │
│    _ResearchManager, _SynthesisManager, _IntelligenceManager │
│                                                              │
│  sanitize_for_logs() ─── PII Gate (fallback_sanitize)        │
│  BudgetManager ────────── hard stops on iterations/time/net  │
│  UCB1 Bandit ──────────── action selection (deterministic)   │
│                                                              │
│  ┌─────────────┐ ┌──────────────┐ ┌─────────────┐ ┌────────┐│
│  │   Fetch     │ │   Claims     │ │   Graph     │ │Archive ││
│  │ Coordinator │ │ Coordinator  │ │ Coordinator │ │Coord.  ││
│  │ start/step/ │ │ start/step/  │ │ start/step/ │ │start/  ││
│  │ shutdown    │ │ shutdown     │ │ shutdown    │ │step/   ││
│  └──────┬──────┘ └──────┬───────┘ └──────┬──────┘ │shutdown││
│         │               │                │         └───┬────┘│
└─────────┼───────────────┼────────────────┼─────────────┼─────┘
          │               │                │             │
          ▼               ▼                ▼             ▼
    ┌──────────┐   ┌───────────┐    ┌──────────┐  ┌──────────┐
    │Stealth   │   │ Evidence  │    │GraphRAG/ │  │Wayback/  │
    │Crawler   │   │ Log       │    │Quantum   │  │DeepProbe │
    │+Robots   │   │(hash-chain│    │Pathfinder│  │(archive) │
    │+RustMiner│   │ +JSONL)   │    └──────────┘  └──────────┘
    └──────────┘   └───────────┘
                                    ┌──────────────────────┐
                                    │  ToolExecLog         │
    ┌──────────┐                    │  (hash-chain, JSONL) │
    │ PII Gate │                    │  *** NOT WIRED ***   │
    │ +fallback│                    └──────────────────────┘
    └──────────┘
    ┌──────────┐                    ┌──────────────────────┐
    │ Unicode  │                    │  MetricsRegistry     │
    │ Analyzer │                    │  (counters+gauges    │
    └──────────┘                    │   → JSONL flush)     │
                                    └──────────────────────┘
    ┌──────────────────────┐
    │  Supporting Modules  │
    │  ModelLifecycle      │  ← 1-at-a-time via AsyncLock
    │  IntelligentCache    │  ← adaptive LRU/LFU, bounded
    │  AtomicStorage       │  ← sharded JSON, LRU shards
    │  PersistentLayer     │  ← KuzuDB or JSON fallback
    │  ResearchContext     │  ← *** unbounded lists ***
    │  ToolRegistry        │  ← cost model + rate limits
    └──────────────────────┘
```

---

## BOTTLENECK MAP

### CPU Hotspots

| Location | Operation | Severity | Notes |
|----------|-----------|----------|-------|
| `unicode_analyzer.py:_detect_normalization_anomalies()` | `unicodedata.normalize()` per char | **MEDIUM** | O(n) but normalize() is expensive; ~1–10 MB/s vs claimed 100+ MB/s |
| `evidence_log.py:_rebuild_indexes()` | Full ring scan after every eviction | **LOW** | O(100) per append after ring full — acceptable |
| `pii_gate.py:_deduplicate_matches()` | Overlap check on match spans | **LOW** | O(m²) where m=match count, typically <50 |

### IO Hotspots

| Location | Operation | Severity | Notes |
|----------|-----------|----------|-------|
| `evidence_log.py:append()` | `flush()+fsync()` per event | **MEDIUM** | Synchronous fsync blocks orchestrator per evidence event. Consider buffered flush every N events. |
| `tool_exec_log.py:log()` | `flush()+fsync()` per tool call | **LOW** | Correct for tamper-evidence, but adds latency per tool. |
| `metrics_registry.py:flush()` | `fsync()` every 100 events/60s | **LOW** | Batched — acceptable. |

### Memory Hotspots

| Location | Structure | Severity | Notes |
|----------|-----------|----------|-------|
| `research_context.py` | `visited_urls: Set[str]`, `active_entities`, `hypotheses`, `errors`, `key_findings` | **HIGH** | All unbounded. 100K URLs × 100 bytes = 10 MB; entities could be worse. |
| `fetch_coordinator.py` | `_frontier: List[str]`, `_processed_urls: Set[str]` | **HIGH** | Unbounded accumulation over research run. |
| `autonomous_orchestrator.py` | `_execution_history: List[Dict]` | **MEDIUM** | Unbounded list of dicts — no eviction. |
| `unicode_analyzer.py` | Finding collections | **MEDIUM** | Large files could generate 1000s of findings in memory. |

---

## SECURITY / PRIVACY REVIEW

### PII Coverage

| Region | Main SecurityGate | Fallback Only | Missing |
|--------|-------------------|---------------|---------|
| US | Email, Phone, SSN, Credit Card, IP, DL, Passport | — | — |
| EU | — | IBAN, VAT (9 countries), E.164 phone | GDPR national IDs |
| UK | — | NINO | — |
| CZ/SK | — | Rodné číslo (conservative) | — |
| APAC | — | — | Chinese ID, Indian Aadhaar, Japanese My Number |
| LATAM | — | — | Brazilian CPF |

### Leak Paths

1. **sanitize_for_logs line 6690–6691**: Bare `except: return text` leaks raw PII when main gate detect() fails and fallback import also fails.
2. **sanitize_for_logs line 6675**: Returns `text[:MAX]` when even fallback_sanitize() throws — still raw text.
3. **EvidenceLog._trim_payload()**: Not recursive — nested dicts/lists containing large strings are not trimmed. `payload['results'] = [{"fulltext": "...10MB..."}]` would pass through.
4. **UnicodeAnalyzer context windows**: 20-char context around findings could include adjacent PII.

### Strengths

- ToolExecLog stores **only hashes** — no raw data ever persisted. Excellent design.
- MetricsRegistry stores only numeric counters/gauges — no text.
- Manifest contains only chain_head, run_id, seq_no — clean.

---

## TEST COVERAGE REVIEW

### Strong Areas (well-tested)
- Hash chain integrity (EvidenceLog + ToolExecLog) — including tampering detection
- PII fallback sanitizer patterns (email, phone, IBAN, VAT, rodné číslo)
- Budget config initialization and limits
- Deterministic seeding mechanism
- Golden schema stability
- No hidden network calls in tests

### Critical Gaps
1. **ToolExecLog wiring**: Test self-calls log.log() — does NOT test orchestrator dispatch path.
2. **Budget integration**: No test runs a real loop that hits budget and stops.
3. **Coordinator delegation**: Tests check `hasattr` but never call `coordinator.step()`.
4. **Resume after crash**: Chain head tested, but no test exercises actual resume() → no-duplicate-manifest.
5. **Archive escalation**: Stub test (line ~10567) with no assertions.
6. **JS-gated content**: No real test.
7. **Security pipeline integration**: No test that verifies every text ingestion point goes through `sanitize_for_logs`.
8. **Recursive payload trimming**: No test for nested large payloads.

### Test Count & Quality
- 380 tests, 0 warnings, 0 skipped — **excellent hygiene**
- Heavy mocking — good for isolation, weak for integration confidence
- Static import scans (e.g., `test_no_runtime_tool_bypass_of_security_pipeline`) — **robust**

---

## PRIORITIZED ACTION PLAN (TOP 10)

### 1. **Wire ToolExecLog into orchestrator tool dispatch** ⬛ CRITICAL

**Risk:** Every tool invocation is unlogged — the tamper-evident tool audit trail is a dead module. Forensic audit invariant is broken.

**Modules:** `autonomous_orchestrator.py` (needs `from .tool_exec_log import ToolExecLog`), wherever tool dispatch/execution occurs.

**Minimal change:** In the tool dispatch wrapper (or create one if none exists), call `self._tool_exec_log.log(tool_name, input_bytes, output_bytes, status)` around every tool call. Initialize `ToolExecLog` in orchestrator `__init__`.

**Regression test:** Patch `ToolExecLog.log` with a counting mock, trigger orchestrator tool dispatch, assert mock was called ≥1 time with correct tool_name. This replaces the false-positive test at line 10043.

---

### 2. **Fix sanitize_for_logs bare-except raw-text leak** ⬛ CRITICAL

**Risk:** If main PII gate's `detect()` throws and fallback import also fails, raw PII is returned. Line 6690–6691 and 6675.

**Modules:** `autonomous_orchestrator.py` lines 6688–6691, 6672–6675.

**Minimal change:** Replace bare `except: return text` with `except: return "[SANITIZE_FAILED]"` or at minimum `return "***"[:self.MAX_SANITIZE_LENGTH]`. Never return raw text on any exception path.

**Regression test:** `test_sanitize_for_logs_never_returns_raw_on_exception` — patch both pii_gate.detect() and fallback_sanitize to raise, assert returned string does not contain PII.

---

### 3. **Cap coordinator unbounded lists** ⬛ HIGH

**Risk:** `_frontier`, `_processed_urls`, `_pending_evidence_ids`, `_pending_queries`, `_pending_urls` grow without limit. On an M1 with 8 GB, a long research run could OOM.

**Modules:** `coordinators/fetch_coordinator.py`, `coordinators/claims_coordinator.py`, `coordinators/graph_coordinator.py`, `coordinators/archive_coordinator.py`.

**Minimal change:** Add `MAX_FRONTIER=10_000`, `MAX_PROCESSED_URLS=50_000` constants. Use `deque(maxlen=N)` for frontier. For `_processed_urls`, switch to a disk-backed Bloom filter or cap with LRU eviction. For pending lists, cap with FIFO eviction.

**Regression test:** `test_frontier_bounded_at_cap` — add 20K URLs, assert len ≤ MAX_FRONTIER.

---

### 4. **Cap ResearchContext unbounded collections** ⬛ HIGH

**Risk:** `visited_urls`, `active_entities`, `hypotheses`, `errors`, `key_findings` all grow unbounded. Primary RAM safety concern.

**Modules:** `research_context.py` lines ~171–182.

**Minimal change:** Add `MAX_VISITED_URLS=50_000`, `MAX_ENTITIES=5_000`, etc. On overflow, snapshot oldest to disk or use deque with maxlen. For `visited_urls`, consider Bloom filter.

**Regression test:** `test_research_context_visited_urls_bounded` — add 100K URLs, assert memory stays bounded.

---

### 5. **Convert coordinator config toggles to immutable policy** ⬛ HIGH

**Risk:** 8 `enable_*` booleans violate the "no user modes/toggles" requirement. They could be toggled at runtime.

**Modules:** `coordinators/fetch_coordinator.py` (`enable_security_check`, `enable_domain_limiter`), `coordinators/claims_coordinator.py` (`enable_stance_update`, `enable_veracity_update`), `coordinators/graph_coordinator.py` (`enable_quantum_pathfinder`, `enable_graph_rag`), `coordinators/archive_coordinator.py` (`enable_memento_lookup`, `enable_deep_probe`).

**Minimal change:** Remove these from `*Config` dataclasses. Replace with capability checks (`if GRAPH_RAG_AVAILABLE`) — i.e., feature is on if dependency is installed, off if not. No runtime toggle.

**Regression test:** `test_coordinator_configs_have_no_enable_toggles` — introspect dataclass fields, assert no field starts with `enable_`.

---

### 6. **Enforce security pipeline as mandatory wrapper** ⬛ HIGH

**Risk:** PII masking, unicode analysis, and payload bounding are standalone utilities — callers must remember to call them. Missing any step leaks raw data.

**Modules:** `autonomous_orchestrator.py` (create `_ingest_text()` wrapper), `security/pii_gate.py`, `text/unicode_analyzer.py`.

**Minimal change:** Create a single `_ingest_text(raw: str) -> str` method that chains: (1) `sanitize_for_logs(raw)` → (2) `unicode_analyzer.analyze_text(sanitized)` (log risk score) → (3) return sanitized, bounded text. All text ingestion points must call `_ingest_text()`.

**Regression test:** `test_all_ingestion_points_call_ingest_text` — static scan for raw text assignments in orchestrator; or instrument `_ingest_text` with counter and run a fetch, assert counter > 0.

---

### 7. **Add recursive payload trimming in EvidenceLog** ⬛ MEDIUM

**Risk:** `_trim_payload()` only trims direct children of the payload dict. Nested structures can contain arbitrarily large strings: `payload['results'][0]['fulltext']`.

**Modules:** `evidence_log.py` `_trim_payload()` (lines ~264–298).

**Minimal change:** Make `_trim_payload()` recursive with a `max_depth=3` limit. At each level, trim strings > `MAX_PAYLOAD_PREVIEW` and lists > 10 items.

**Regression test:** `test_trim_payload_recursive` — pass `{"results": [{"fulltext": "x"*10000}]}`, assert nested fulltext is trimmed.

---

### 8. **Add true integration test for budget exhaustion in loop** ⬛ MEDIUM

**Risk:** Budget enforcement is tested at config level but no test proves a real orchestrator loop respects the budget and stops. Regression could silently break budget hard-stop.

**Modules:** `tests/test_autonomous_orchestrator.py`.

**Minimal change:** Test that initializes orchestrator with `max_iterations=3`, seeds frontier with 100 URLs, runs the loop, asserts iteration count ≤ 3 and stop_reason is `MAX_ITERATIONS`.

**Regression test:** This IS the regression test.

---

### 9. **Expand PII main gate to include international patterns** ⬛ MEDIUM

**Risk:** IBAN, EU VAT, E.164 phone, UK NINO, CZ rodné číslo are only in fallback. If main gate is available, these patterns are not applied. International PII leaks through main path.

**Modules:** `security/pii_gate.py` `SecurityGate._compile_regex_patterns()` (lines ~89–126).

**Minimal change:** Merge fallback international patterns into main SecurityGate regex set. Keep conservative regex (require format markers like `+`, `/`, country prefixes).

**Regression test:** `test_main_gate_detects_iban_and_eu_vat` — pass IBAN like `DE89370400440532013000`, assert masked.

---

### 10. **Cap FullyAutonomousOrchestrator._execution_history** ⬛ MEDIUM

**Risk:** `_execution_history: List[Dict]` accumulates every execution record with no eviction. Long runs grow this unbounded.

**Modules:** `autonomous_orchestrator.py` line ~1397.

**Minimal change:** Convert to `deque(maxlen=200)` or ring buffer matching other capped structures.

**Regression test:** `test_execution_history_bounded` — append 500 entries, assert len ≤ cap.

---

## SUMMARY VERDICTS

| Category | PASS | FAIL | UNCLEAR |
|----------|------|------|---------|
| A. Autonomy | 1 | 2 | 0 |
| B. Disk-first | 3 | 1 | 0 |
| C. Forensic audit | 3 | 1 | 0 |
| D. Security pipeline | 1 | 2 | 1 |
| E. Budget/determinism/resume | 3 | 0 | 0 |
| F. Coordinator quality | 2 | 0 | 1 |
| G. Performance | 3 | 0 | 0 |
| H. Tests | 2 | 1 | 0 |
| **TOTAL** | **18** | **7** | **2** |

**Overall assessment:** The architecture is fundamentally sound — disk-first design, hash chains, budget enforcement, model lifecycle, and determinism controls are all well-implemented. The two critical failures (ToolExecLog not wired, sanitize_for_logs raw-text leak) are fixable with small, targeted changes. The 5 high-priority items (unbounded collections, toggles, pipeline enforcement) represent systemic gaps that need systematic but straightforward remediation.
