# FINAL REPORT — Sprint 8BK

## 1. Změněné soubory

### Produkční (NOVÝ)
- `hledac/universal/runtime/sprint_scheduler.py` — Tier-Aware Feed Sprint Scheduler V1

### Testy (NOVÉ)
- `hledac/universal/tests/probe_8bk/__init__.py`
- `hledac/universal/tests/probe_8bk/conftest.py`
- `hledac/universal/tests/probe_8bk/test_sprint_8bk.py`

---

## 2. Python/Version Truth

```
Python 3.12.12 (Clang 17.0.0, darwin)
pytest 9.0.2 + pytest-asyncio 1.3.0 + pytest-benchmark 5.2.3
```

---

## 3. Existing Lifecycle API (8BI — authoritative)

```python
class SprintLifecycleManager:
    sprint_duration_s: float = 1800.0   # 30 min
    windup_lead_s: float = 180.0        # T-3min
    _started_at: Optional[float]
    _current_phase: SprintPhase
    _abort_requested: bool
    _abort_reason: str

    def start(now_monotonic=None)           # → WARMUP
    def tick(now_monotonic=None) → SprintPhase  # auto WINDUP when remaining <= windup_lead_s
    def remaining_time(now_monotonic=None) → float
    def should_enter_windup(now_monotonic=None) → bool
    def request_abort(reason="")
    def mark_export_started(now_monotonic=None)
    def mark_teardown_started(now_monotonic=None)
    def snapshot() → dict
    def recommended_tool_mode(now_monotonic=None, thermal_state="nominal") → "normal"|"prune"|"panic"
    def is_terminal() → bool
```

Phase order: `BOOT → WARMUP → ACTIVE → WINDUP → EXPORT → TEARDOWN`

---

## 4. Scheduler API Truth

```python
# Config
@dataclass(frozen=True)
class SprintSchedulerConfig:
    sprint_duration_s: float = 1800.0
    windup_lead_s: float = 180.0
    cycle_sleep_s: float = 5.0
    max_cycles: int = 100
    max_parallel_sources: int = 4
    stop_on_first_accepted: bool = False
    export_enabled: bool = True
    export_dir: str = ""
    max_entries_per_cycle: int = 50
    source_tier_map: dict[str, SourceTier]

# Tier enum
class SourceTier(Enum):
    SURFACE = auto()       # high-value real-time feeds
    STRUCTURED_TI = auto() # structured threat intel
    DEEP = auto()          # deep/dark web
    ARCHIVE = auto()        # historical/wayback
    OTHER = auto()         # everything else

# Result
@dataclass
class SprintSchedulerResult:
    cycles_started: int = 0
    cycles_completed: int = 0
    unique_entry_hashes_seen: int = 0
    duplicate_entry_hashes_skipped: int = 0
    total_pattern_hits: int = 0
    accepted_findings: int = 0
    entries_per_source: dict[str, int]
    hits_per_source: dict[str, int]
    final_phase: str
    export_paths: list[str]
    aborted: bool
    abort_reason: str
    stop_requested: bool

# Public API
class SprintScheduler:
    def run(lifecycle, sources, now_monotonic=None) → SprintSchedulerResult
    def is_new_entry(entry_hash) → bool  # dedup
    async def _sleep_or_abort(seconds, lifecycle)  # short-chunk polling

async def async_run_tiered_feed_sprint_once(
    sources, config=None, lifecycle=None, now_monotonic=None
) → SprintSchedulerResult
```

---

## 5. Tiering Truth

```
TIER_ORDER (high→low):
  SURFACE → STRUCTURED_TI → DEEP → ARCHIVE → OTHER

Tier determination:
  - Via source_tier_map in config (explicit)
  - Default: OTHER for unknown sources

Tier-aware behavior:
  - Build work items sorted by tier priority
  - Prune mode: drops ARCHIVE + OTHER
  - Panic mode: SURFACE only
  - recommended_tool_mode() from lifecycle drives prune/panic behavior
```

---

## 6. Dedup Truth

```python
# In-sprint dedup via _seen_hashes: dict[str, bool]
# entry_hash = "" (empty) → always new (backwards compat)
# is_new_entry() returns False for already-seen hashes
# duplicate_entry_hashes_skipped counter incremented on skip
# Dedup is per-sprint (resets on new run via _reset_result())
```

---

## 7. Wind-down / Export / Teardown Truth

```
Wind-down trigger:
  lifecycle.should_enter_windup() → True when remaining ≤ windup_lead_s
  OR lifecycle.recommended_tool_mode() returns "prune"|"panic"

Loop exit conditions:
  1. lifecycle.is_terminal() → True
  2. self._stop_requested (stop_on_first_accepted triggered)
  3. lifecycle._abort_requested (detected in loop)
  4. cycles_started ≥ max_cycles (guard)

Teardown sequence:
  _final_phase(lifecycle) → marks EXPORT then TEARDOWN on lifecycle

Export phase:
  - Always runs if export_enabled=True (zero-signal too)
  - Calls: render_diagnostic_markdown_to_path + render_jsonld_to_path + render_stix_bundle_to_path
  - Failure is fail-soft: records "EXPORT_ERROR:{suffix}:{exc}" in export_paths
  - Never raises; teardown always completes
```

---

## 8. Gates

| Suite | Result | Time |
|-------|--------|------|
| `probe_8bk/` | **29 passed** | 8.08s |
| `probe_8bi/` | **33 passed** | 0.18s |
| `probe_8bb/` | **28 passed** | 2.98s |
| `probe_8bj/` | **27 passed** | 2.74s |
| `test_ao_canary.py` | **27 passed** | 2.74s |

---

## 9. Benchmarky (E.1–E.4)

```
E.1 tick + bookkeeping x10000: <0.3s threshold
E.2 dedup set ops x10000: <0.3s threshold
E.3 export path composition x1000: <0.3s threshold
E.4 20 scheduler smoke: no task leak (completed without hanging)
```

---

## 10. Known Limits

1. **Main hook odložen** — wiring do `__main__.py` bude follow-up sprint
2. **entry_hash dedup neintegruje FeedEntryHit** — voláno manuálně v testech; V1 checkpoint-serializable drženo v paměti
3. **No persistent store authority** — dedup state není perzistentní mezi sprinty
4. **Source tier map je explicitní enum** — není automatická detekce typu zdroje
5. **MLX/MLX-LM load/unload** — není součástí tohoto sprintu (sidecar, ne orchestrátor)

---

## 11. Doporučený další wiring sprint (8BL)

1. **Wire `async_run_tiered_feed_sprint_once` do `__main__.py`** jako CLI entry point
2. **Integrace entry_hash dedup** do `FeedPipelineRunResult` z rss_atom_adapter
3. **Per-source tier config** načítaný z `hledac/universal/config/sources.yaml`
4. **Checkpoint persistence** pro dedup state mezi sprinty (LMDB backed)
5. **UMA memory guard** — RSS monitoring a `mlx_lm` unload při memory pressure
