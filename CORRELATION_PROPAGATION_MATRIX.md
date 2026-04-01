# Correlation Propagation Matrix

## Canonical Schema

```python
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class RunCorrelation:
    run_id: Optional[str]     # Unique run identifier
    branch_id: Optional[str]  # Research branch/sub-session
    provider_id: Optional[str] # LLM provider (e.g. "mlx", "openai")
    action_id: Optional[str]  # Action/event identifier

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "branch_id": self.branch_id,
            "provider_id": self.provider_id,
            "action_id": self.action_id,
        }
```

Canonical location: `hledac/universal/types.py` (lines 1277-1321)

## Storage vs Serialization vs Queryability

| Plane | File | Storage Shape | Serialization Shape | Queryability | Corr Support |
|-------|------|--------------|---------------------|--------------|--------------|
| **Evidence** | `evidence_log.py` | SQLite + JSONL | `EvidenceEvent.to_dict()` | `log.query(event_type, min_confidence)` | **FULL** |
| **Tool Audit** | `tool_exec_log.py` | JSONL | `ToolExecEvent.to_dict()` | `verify_all()`, `get_stats()` | **FULL** |
| **Metrics** | `metrics_registry.py` | JSONL | Inline dict per metric | `get_summary()` | **FULL** (registry-level) |
| **Shadow** | `analytics_hook.py` | DuckDB | `record` dict | DuckDB SQL | **FULL** (partial in hook) |

## Minimal Insertion Points

### EvidenceLog — `create_event()` (line 649)
```python
def create_event(
    self,
    event_type: Literal[...],
    payload: Dict[str, Any],
    source_ids: Optional[List[str]] = None,
    confidence: float = 1.0,
    correlation: Optional[Dict[str, Optional[str]]] = None,  # NEW
) -> EvidenceEvent:
```
- Correlation stored in `event.payload["_correlation"]`
- Flattened, query-friendly
- Backward compatible: `correlation=None` works

### ToolExecLog — `log()` (line 159)
```python
def log(
    self,
    tool_name: str,
    input_data: bytes,
    output_data: bytes,
    status: str,
    error: Optional[Exception] = None,
    correlation: Optional[Dict[str, Optional[str]]] = None,  # NEW
) -> ToolExecEvent:
```
- Correlation stored in `ToolExecEvent.correlation` field
- Serialized in JSONL via `to_dict()`
- Backward compatible: `correlation=None` works

### MetricsRegistry — `__init__()` (line 96)
```python
def __init__(
    self,
    run_dir: Path,
    run_id: str = "default",
    correlation: Optional[Dict[str, Optional[str]]] = None,  # NEW
) -> None:
```
- Correlation stored at registry level, emitted with every metric flush
- Serialized in JSONL per-metric entries
- Backward compatible: `correlation=None` works

### analytics_hook — `shadow_record_finding()` (line 277)
```python
def shadow_record_finding(
    ...
    run_id: Optional[str] = None,
    branch_id: Optional[str] = None,     # NEW
    provider_id: Optional[str] = None,   # NEW
    action_id: Optional[str] = None,    # NEW
) -> None:
```
- Correlation keys stored in DuckDB record dict
- Fail-open: never raises

## Full Support Map

| Feature | EvidenceLog | ToolExecLog | MetricsRegistry | analytics_hook |
|---------|-------------|-------------|----------------|----------------|
| `run_id` | ✅ (already) | ✅ (now) | ✅ (via registry) | ✅ (already) |
| `branch_id` | ✅ (now) | ✅ (now) | ✅ (now) | ✅ (now) |
| `provider_id` | ✅ (now) | ✅ (now) | ✅ (now) | ✅ (now) |
| `action_id` | ✅ (now) | ✅ (now) | ✅ (now) | ✅ (now) |
| Backward compat | ✅ | ✅ | ✅ | ✅ |
| Serialized in JSONL | ✅ | ✅ | ✅ | ✅ |
| Queryable | ✅ (payload) | ✅ (field) | ✅ (per-metric) | ✅ (SQL) |

## What is NOT

- **NOT a unified envelope** — ledgers remain separate
- **NOT a base logger** — each ledger has distinct write authority
- **NOT auto-generated IDs** — correlation dict passed by caller
- **NOT a super-ledger** — no single store aggregating all planes
- **NOT an EventBus** — no pub/sub or routing logic

## Design Decisions

### Why flattened in EvidenceLog payload?
EvidenceLog uses Pydantic `EvidenceEvent` with a fixed schema. Adding correlation as a top-level field would require schema migration. Storing in `payload["_correlation"]` achieves:
1. No schema change to EvidenceEvent
2. Queryable via `event.payload["_correlation"]["branch_id"]`
3. Backward compatible — old payloads without `_correlation` still work

### Why registry-level for MetricsRegistry?
Metrics are fire-and-forget (counters/gauges). Individual metric events don't warrant per-event correlation. Registry-level correlation applies to all metrics in a run segment without per-call overhead.

### Why ToolExecEvent.correlation field?
ToolExecLog is hash-chained and forensic. Adding correlation as an explicit field keeps it queryable without payload parsing, and it serialize naturally via `to_dict()`.

## TODO Debt

1. **EvidenceLog**: Consider promoting `payload["_correlation"]` to top-level field in EvidenceEvent (requires schema migration)
2. **MetricsRegistry**: Add `inc_with_corr()` / `set_gauge_with_corr()` for per-event correlation if needed
3. **Cross-ledger queries**: No cross-ledger JOIN support yet — future phase

## Test Coverage

See `tests/test_correlation_propagation.py`:
- `TestEvidenceLogCorrelation` — 5 tests
- `TestToolExecLogCorrelation` — 4 tests
- `TestMetricsRegistryCorrelation` — 3 tests
- `TestAnalyticsHookCorrelation` — 2 tests
- `TestCorrelationSchema` — 5 tests

**Total: 19 tests, all passing**
