# Sprint 8AU Final Report: Aho-Corasick Shadow Pilot

## 1. PREFLIGHT RESULTS

### Smoke Test
`pyahocorasick` installed and working on Apple Silicon M1.
`ahocorasick.iter()` returns all matches; `iter_long()` returns only longest.
Overlap behavior confirmed: `bc1` + `bc1q` coexist at positions 2 and 3.

### Cold Import Baseline
| Run | Value |
|-----|-------|
| 1 | 1.392s |
| 2 | 1.040s |
| 3 | 1.042s |
| **Median** | **1.042s** |

Baseline (before 8AU): 0.972s → Delta: **+0.070s** ✅ (within 0.1s threshold)

### Candidate Pattern Family
**`document_intelligence.py:253` — `suspicious_keywords`**

```python
self.suspicious_keywords = [
    "confidential", "classified", "secret", "proprietary",
    "internal use only", "do not distribute", "draft",
    "redacted", "sensitive"
]
```

Ground truth: `keyword in text_lower` (case-insensitive substring, document_intelligence.py:539).

---

## 2. PATTERN FAMILY DECISION

| Criterion | Status |
|-----------|--------|
| Exact-match-safe | ✅ No checksums/ranges needed |
| Non-overlapping | ✅ Verified — no prefix collisions among 9 patterns |
| Ground truth available | ✅ `keyword in text_lower` |
| Good Aho-Corasick candidate | ✅ Fixed string set, multi-pattern, O(n) scan |

**Deferred (not pilot candidates):**
- BTC/Monero/onion address patterns — need checksum validation
- Email/IPv4/IPv6 validators — generic context-sensitive patterns
- `critical/high_keywords` in stealth_crawler — severity classification, not IOC extraction

---

## 3. IMPLEMENTATION

### File Created
`utils/aho_extractor.py` — shadow-only Aho-Corasick utility

### API Surface

```python
# Cached automaton (built once, reused)
get_suspicious_keywords_automaton() -> Automaton

# Scan text (case-insensitive, lowercase haystack)
aho_scan_text(automaton, text) -> List[Dict[str, Any]]
# Returns: [{"start": int, "end": int, "match": str}, ...]
# end is EXCLUSIVE (converted from pyahocorasick's inclusive end_index)

# Ground truth for A/B comparison
regex_scan_suspicious_keywords(text) -> List[Dict[str, Any]]

# A/B comparison
compare_aho_vs_regex(text) -> (aho_matches, regex_matches, are_identical)

# Lazy import guard
is_ahocorasick_loaded() -> bool
```

### Design Decisions

1. **Case sensitivity**: `aho_scan_text` lowercases haystack before scanning, matching ground truth `keyword in text_lower`. Patterns are stored lowercase.

2. **Output normalization**: pyahocorasick returns inclusive `end_index`. Converted to exclusive end: `start = end_index - len(value) + 1`, `end = end_index + 1`.

3. **Caching**: `_automaton_cache` singleton — built on first call, reused for all subsequent scans. Thread-safe (automaton is read-only after `make_automaton()`).

4. **Lazy import**: `pyahocorasick` is NOT imported until first `get_suspicious_keywords_automaton()` call. Orchestrator boot does NOT load it.

---

## 4. OUTPUT SHAPE

| Field | Type | Description |
|-------|------|-------------|
| `start` | int | 0-based inclusive start index |
| `end` | int | Exclusive end index (matches regex convention) |
| `match` | str | Matched keyword |

Example:
```python
aho_scan_text(auto, "This is classified")
# -> [{"start": 8, "end": 18, "match": "classified"}]
```

---

## 5. OVERLAP POLICY

The 9 pilot patterns are verified non-overlapping (no prefix collisions).
If overlaps occur in future patterns, `iter()` returns all matches — ground truth substring search also returns all matches, so no dedup is applied. Pattern families requiring prefix dedup are explicitly deferred.

---

## 6. TEST RESULTS — 20/20 PASSED

| Test | Result |
|------|--------|
| `test_automaton_is_cached_singleton` | ✅ |
| `test_pattern_subset_is_non_overlapping` | ✅ |
| `test_normalize_aho_match_exclusive_end` | ✅ |
| `test_regex_span_parity` | ✅ |
| `test_aho_matches_regex_on_representative_cases[10 cases]` | ✅ All 10 |
| `test_aho_handles_no_match_cases` | ✅ |
| `test_aho_handles_multiple_matches_in_one_pass` | ✅ |
| `test_py_ahocorasick_not_imported_on_orchestrator_boot` | ✅ |
| `test_aho_extractor_module_not_imported_on_orchestrator_boot` | ✅ |
| `test_benchmark_build_and_scan` | ✅ |
| `test_aho_module_lazy_import_flag` | ✅ |

---

## 7. BENCHMARK RESULTS

```
Benchmark results:
  aho_build_time_ms:         0.020 ms
  aho_scan_time_us_per_kb:  16.5 µs/KB
  regex_scan_time_us_per_kb: 21.9 µs/KB
  scan speedup:               1.3x
  A/B parity:               True
```

- **Build**: 0.020ms (automaton construction is ~instant at this pattern count)
- **Scan**: Aho ~1.3× faster than N×substring scan for this 9-keyword set
- **A/B parity**: 100% exact match on all test cases

---

## 8. COLD IMPORT DELTA

| Measurement | Value |
|-------------|-------|
| Baseline (before 8AU) | 0.972s |
| After 8AU | 1.042s |
| Delta | +0.070s |
| Threshold | 0.1s |

**Result**: Within noise. Boot isolation preserved. `pyahocorasick` NOT loaded on orchestrator boot.

---

## 9. FILES CREATED

| File | Purpose |
|------|---------|
| `utils/aho_extractor.py` | Shadow Aho-Corasick utility module |
| `tests/test_sprint8au_aho_shadow.py` | 20 targeted tests |
| `tests/test_sprint8au_final_report.md` | This report |

---

## 10. KEY VERIFICATION POINTS

- ✅ Shadow module (`aho_extractor.py`) exists
- ✅ Live regex path untouched (authoritative path unchanged)
- ✅ Pilot uses 9 non-overlapping exact-match-safe patterns
- ✅ A/B parity: 100% exact on all 10 deterministic test cases
- ✅ Benchmark split: aho_build_time_ms + aho_scan_time_us_per_kb vs regex equivalents
- ✅ Cold import delta: +0.070s (within 0.1s)
- ✅ Boot isolation: pyahocorasick NOT imported on orchestrator boot
- ✅ 20/20 targeted tests pass
- ✅ No DuckDB/msgspec/orchestrator files touched

---

## 11. DEFERRED

- Live orchestrator integration (wiring into hot path)
- Email patterns (context-sensitive validation)
- IPv4/IPv6 validators (generic, need range checks)
- BTC/Monero/onion address patterns (checksum-based)
- Overlapping prefix families (need prefix dedup strategy)
- ahocorasick Rust/PyO3 comparison on M1
- Broader regex families needing contextual logic
- Queue-pattern background flush
- DuckDB shadow ingest wiring
- Model-layer boot isolation

---

## 12. RECOMMENDED NEXT STEPS

1. **Shadow-only for now** — keep `aho_extractor.py` as shadow, monitor in production
2. **Live integration candidate** — the `suspicious_keywords` path in `document_intelligence.py:_detect_suspicious_keywords()` is the lowest-risk integration point (pure substring scan, bounded output, no checksum logic)
3. **Future pilots** — fixed string blocklists, known IOC token lists, malware family name detection

---

## 13. VERDICT

**COMPLETE** — All success criteria met:
- ✅ Shadow module exists
- ✅ Live regex path untouched
- ✅ Non-overlapping exact-match-safe patterns only
- ✅ 100% parity on 10 deterministic A/B cases
- ✅ Benchmark splits build vs scan time
- ✅ Cold import delta ≤ 0.1s
- ✅ 20/20 targeted tests pass
- ✅ Final report complete
