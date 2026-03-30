# Sprint 8AQ Final Report: Shadow-Only msgspec Pilot

## SHADOW-ONLY STATEMENT
**This sprint is SHADOW-ONLY and did NOT modify live orchestrator DTOs.**
No changes were made to `autonomous_orchestrator.py` or any live DTO definitions.

---

## 1. PREFLIGHT RESULTS

### DTO Location Table
| DTO | File | Line | MUST-NOT-EDIT? |
|-----|------|------|----------------|
| AdmissionResult | autonomous_orchestrator.py | 286 | YES |
| BacklogCandidate | autonomous_orchestrator.py | 296 | YES |

### Mutation Audit
- **Result**: ZERO post-construction mutation
- Both DTOs are simple `dataclass(slots=True)` with 5 and 8 plain fields
- Only attribute access (`.status`, `.score`) — no field assignment after construction
- No `__post_init__` on either DTO

### Serialization Shape
- **Result**: No JSON/msgpack/cpickle encoding of these DTOs anywhere in codebase
- Only in-memory usage: construction → field access → discard
- No `asdict()`, `astuple()`, `replace()` calls on either DTO
- Wire shape is just the Python dict of fields (no special encoding)

### Call Sites
| DTO | Location | Usage |
|-----|----------|-------|
| AdmissionResult | Line 9950 | `return AdmissionResult(status="reject", ...)` |
| AdmissionResult | Line 10025 | `return AdmissionResult(status=status, score=final_score, ...)` |
| BacklogCandidate | Line 10498 | `backlog_candidate = BacklogCandidate(url=source_url, ...)` |

---

## 2. SHADOW IMPLEMENTATION

### Shadow Module
**Path**: `utils/shadow_dtos.py`

### Shadow Twins
| Shadow Class | frozen | gc | Fields |
|---|---|---|---|
| AdmissionResultShadow | True | False | 5 (status, score, content_hint, source_family, reason) |
| BacklogCandidateShadow | True | False | 8 (url, score, source_family, content_hint, title_snippet, contradiction_value, enqueued_at_cycle, lane_id) |

### Adapter Strategy
- `from_live(live_obj)` — converts any object with matching attributes to shadow Struct
- `to_dict(shadow)` — `msgspec.structs.asdict()` for parity testing
- Baseline dataclasses clone for fair comparison

---

## 3. BENCHMARK RESULTS

```
constructor_msgspec:     77.9 ns/op
constructor_baseline:   337.3 ns/op
constructor_speedup:     4.33x  (msgspec faster)

to_dict_msgspec:        169.1 ns/op
to_dict_baseline:      6148.6 ns/op
to_dict_speedup:       36.36x  (msgspec faster)
```

**Interpretation**: msgspec.Struct construction is 4.3× faster and `asdict()` serialization is 36× faster than dataclass equivalents. These are microbenchmarks — actual production speedup depends on how frequently these DTOs are created/destroyed in the hot path.

---

## 4. COLD IMPORT DELTA

| Measurement | Median |
|---|---|
| Baseline (before) | 1.052s |
| After shadow_dtos | 1.020s |
| Delta | -0.032s (within noise) |

**Stdev = 0.215s across 5 runs** — delta is not statistically significant.

---

## 5. TEST RESULTS

```
14/14 tests PASSED

TestCoverage:
  - AdmissionResultShadow constructor parity (3 tests)
  - BacklogCandidateShadow constructor parity (2 tests)
  - Wire-shape to_dict parity (2 tests)
  - Frozen immutability (2 tests)
  - from_live adapter (2 tests)
  - Cold import regression (1 test)
  - Benchmark sanity (2 tests)
```

---

## 6. FILES CREATED

| File | Purpose |
|------|---------|
| `utils/shadow_dtos.py` | Shadow msgspec Struct twins + adapters + benchmark |
| `tests/test_sprint8aq_shadow.py` | 14 targeted tests |
| `tests/test_sprint8aq_final_report.md` | This report |

---

## 7. DEFERRED (Future Sprints)

- Live merge of shadow twins into `autonomous_orchestrator.py`
- `ActionResult` msgspec conversion (larger, more complex)
- `ResearchFinding` msgspec conversion
- DuckDB async-safety fix before sidecar hot-path integration
- Aho-Corasick pilot
- Model-layer boot isolation (`types.py` / `mlx_lm` / `mlx.core` / `onnxruntime`)

---

## 8. msglag SPEC VERSION

`msgspec 0.20.0` — API uses `msgspec.structs.asdict()` (not `msgspec.to_dict()`)

## 9. VERDICT

**COMPLETE** — All success criteria met:
- ✅ Shadow-only pilot for exactly 2 DTOs (AdmissionResult, BacklogCandidate)
- ✅ No orchestrator/live DTO file modified
- ✅ Constructor/default semantics mirrored
- ✅ Wire-shape parity documented (dict of fields — no special encoding)
- ✅ 14/14 targeted tests pass
- ✅ Cold import delta ≤ 0.1s (measured -0.03s, within noise)
- ✅ Benchmark: 4.3× construction speedup, 36× to_dict speedup
- ✅ Final report clearly states SHADOW-ONLY
