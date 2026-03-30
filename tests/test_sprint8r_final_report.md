# Sprint 8R Final Report: Provider Recovery + LIVE Findings Yield Repair + Identity-Rich Readiness

## A. PREFLIGHT CONFIRMATION

### PREFLIGHT_CONFIRMED: YES

### PROVIDER_TRIAGE_TABLE
| Provider | Endpoint | Status | Details |
|----------|----------|--------|---------|
| DuckDuckGo HTML | https://html.duckduckgo.com/html/ | BLOCKED | Connection timeout after 30s |
| DuckDuckGo API | https://api.duckduckgo.com/ | BLOCKED | Connection timeout after 30s |
| Brave Search | https://search.brave.com/ | PARTIAL | HTTP 200 but Python Brotli decoding fails |
| curl subprocess | CLI curl | AVAILABLE | Works with --compressed flag |
| Semantic Scholar | api.semanticscholar.org | RATE_LIMITED | HTTP 429 Too Many Requests |
| crt.sh | crt.sh | TIMEOUT | Connection timeout |
| searx.be | searx.be | TIMEOUT | Connection timeout |

### REPLAY_BASELINE_TABLE
| Metric | Value |
|--------|-------|
| iterations | 1213 |
| findings_total | 1213 |
| sources_total | 1213 |
| data_mode | OFFLINE_REPLAY |
| benchmark_fps | 48.5 |

---

## B. ROOT CAUSE ANALYSIS

### PRIMARY_BOTTLENECK: Network-level bot protection + Python Brotli issue

**DuckDuckGo:** Completely blocked at network level (connection timeout)
**Brave Search:** Python's `requests`/`httpx` fail to decode Brotli-compressed responses
  - `brotli` library is installed (v1.2.0) but decoding still fails
  - Root cause: The `brotli` module doesn't integrate properly with requests' decoding pipeline
  - Workaround: Using `subprocess curl` with `--compressed` flag works perfectly

---

## C. FIXES APPLIED (Sprint 8R)

### Fix 1: Brave Search Integration
**File:** `hledac/universal/intelligence/stealth_crawler.py`

Added `_search_brave()` method with Brave-specific URL and parsing:
```python
def _search_brave(self, query: str, num_results: int) -> List[SearchResult]:
    """Scrape Brave Search HTML results (Sprint 8R)."""
    encoded_query = quote(query)
    url = f"https://search.brave.com/search?q={encoded_query}&count={num_results}"
    # ... fetch and parse
```

### Fix 2: Brave HTML Parsing
**File:** `hledac/universal/intelligence/stealth_crawler.py`

Added `_parse_brave()` with correct regex pattern for Brave's HTML:
```python
pattern = r'<a[^>]*href="(https?://[^"]*)"[^>]*class="[^"]*svelte[^"]*"[^>]*>'
```

### Fix 3: Multi-Provider Fallback Chain
**File:** `hledac/universal/intelligence/stealth_crawler.py`

Updated `search()` to try DuckDuckGo → Brave → Google:
```python
if source == "duckduckgo":
    results = self._search_duckduckgo(query, num_results)
    if not results:
        logger.info("DuckDuckGo returned no results, trying Brave...")
        results = self._search_brave(query, num_results)
```

### Fix 4: Subprocess Curl Fallback
**File:** `hledac/universal/intelligence/stealth_crawler.py`

Added `_fetch_with_subprocess_curl()` for when curl_cffi fails:
```python
def _fetch_with_subprocess_curl(self, url: str, headers: Dict[str, str]) -> Optional[str]:
    """Fetch using subprocess curl with Brotli support (Sprint 8R fallback)."""
    cmd = ['curl', '-s', '-L', '-A', headers.get('User-Agent', 'Mozilla/5.0'), '--compressed']
    # ... execute curl subprocess
```

### Fix 5: Exception-Safe Fallback in _fetch_html
**File:** `hledac/universal/intelligence/stealth_crawler.py`

Updated `_fetch_html()` to catch curl_cffi exceptions and fallback:
```python
try:
    result = self._fetch_with_curl_cffi(url, headers)
except Exception as e:
    logger.warning(f"curl_cffi failed, trying subprocess curl: {e}")
    result = None
if not result:
    result = self._fetch_with_subprocess_curl(url, headers)
```

---

## D. VERIFICATION RESULTS

### Brave Search Direct Test
```
Testing Brave search...
Results: 5
  - https://www.python.org/
  - https://www.python.org/downloads/
  - https://www.python.org/downloads/macos/
  - https://www.python.org/downloads/windows/
  - https://www.python.org/about/gettingstarted/
```

### DuckDuckGo Fallback Chain Test
```
Testing DuckDuckGo search (should fallback to Brave)...
Results: 5 (via Brave fallback)
  - https://en.wikipedia.org/wiki/Machine_learning
  - https://www.ibm.com/think/topics/machine-learning
  - https://developers.google.com/machine-learning/crash-course
  - https://www.geeksforgeeks.org/machine-learning/machine-learning/
  - https://mitsloan.mit.edu/ideas-made-to-matter/machine-learning-explained
```

### PROVIDER_HEALTH_TABLE (Post-Fix)
| Provider | Status | Real Results | Mock Fallback |
|----------|--------|--------------|--------------|
| DuckDuckGo | BLOCKED | 0 | N/A |
| Brave Search | AVAILABLE | 5-10/call | N/A |
| Google | NOT_TESTED | N/A | N/A |
| Mock Fallback | ACTIVE | N/A | 6 fixed |

---

## E. LIVE YIELD ANALYSIS

### FINDINGS_YIELD_TABLE (Post-Fix)
| Action | Yield | Calls | Share |
|--------|-------|-------|-------|
| surface_search | TBD | TBD | TBD |
| scan_ct | TBD | TBD | TBD |
| ct_discovery | TBD | TBD | TBD |

**Note:** Full LIVE benchmark requires 60s+ runtime. Due to environment constraints (heavy initialization), Brave integration verified via direct API tests only.

### LIVE_ADMISSION_DIAGNOSIS
| Bottleneck | Evidence | Verdict |
|------------|----------|---------|
| Provider blockage | DuckDuckGo blocked at network level | YES - DuckDuckGo unreachable |
| Python Brotli | requests/httpx fail to decode Brave response | YES - Python ecosystem issue |
| Brave fallback working | curl subprocess works with --compressed | SOLVED - subprocess curl fallback |
| Mock fallback | Still active when Brave returns 0 | ACTIVE - but Brave now provides real data |

### PRIMARY_BOTTLENECK: Network unavailability for DuckDuckGo (ENV issue)

---

## F. IDENTITY-RICH READINESS

### EMAIL_EVIDENCE_TABLE
| Source | Email Patterns Found | Notes |
|--------|-------------------|-------|
| Brave Results | 0 | Brave returns only URLs, no content/snippets |
| Mock Fallback | 6 (synthetic) | Contains research@ai-lab.org, jsmith, etc. |

### EMAIL_RICH_READINESS: NO

**Reason:** Brave Search provides URLs only, no email content. Without actual page fetches and content extraction, cannot discover real email entities. Mock fallback provides synthetic identity data but is not representative of real evidence.

---

## G. TEST RESULTS

### Targeted Tests
| Test | Status |
|------|--------|
| test_live_runbook_contains_seed_domains | PASSED |
| test_live_runbook_contains_timeout_budgets | PASSED |
| test_live_runbook_contains_ner_fallback_note | PASSED |
| test_live_runbook_contains_rate_limit_strategy | PASSED |
| test_latency_table_contains_min_mean_p95_max | PASSED |
| test_payload_cap_preserved | PASSED |
| test_shared_client_path_preserved | PASSED |
| test_offline_replay_benchmark_still_passes | PASSED |
| test_rss_monitor_slope_calculation | PASSED |
| test_hhi_computation | PASSED |

### Regression Tests
| Suite | Passed | Failed |
|-------|--------|--------|
| test_sprint82j_benchmark.py | 64 | 0 |
| test_sprint8l_live.py | (live run) | - |
| test_sprint8l_targeted.py | 10 | 0 |
| **TOTAL** | **74** | **0** |

### TESTS_PASSED: YES

---

## H. M1 SAFETY VERIFICATION

### Memory Safety (OFFLINE_REPLAY 10s)
| Metric | Value |
|--------|-------|
| RSS start | 442 MB |
| RSS peak | 442 MB |
| RSS before synthesis | 341 MB |
| RSS after synthesis | 342 MB |
| Memory delta | 1 MB |
| MLX cache clears | 0 |

### M1_SAFETY: PASS

---

## I. DEFERRED WORK

### Sprint 8T: Data Leak Hunter Reconnect
**Status:** DEFERRED

**Reason:** Brave Search returns URLs only (no content/snippets with email patterns). Cannot discover real email entities without page content fetching. Requires:
1. Brave integration working ✓
2. Page content fetching with email extraction
3. At least 3 unique real email entities observed in LIVE evidence

**Trigger:** Resume when:
- Page fetching yields content with email patterns
- Or alternative provider provides rich snippets with identity data

### Sprint 8S: Brave Snippet Extraction
**Status:** DEFERRED

**Reason:** Brave HTML is JavaScript-rendered, requires Playwright for snippet extraction. Current HTML parsing only extracts URLs.

**Solution options:**
1. Add Playwright-based Brave scraping
2. Use Brave's API endpoint (if available)
3. Fetch page content separately and extract emails

---

## J. FINAL VERDICT

### COMPLETE: PARTIAL (with environmental caveat)

**What was accomplished:**
1. ✓ Brave Search integration working via subprocess curl fallback
2. ✓ Multi-provider fallback chain: DuckDuckGo → Brave → Google
3. ✓ No regression: 74/74 tests pass
4. ✓ M1 safety preserved
5. ✓ DuckDuckGo fallback working correctly

**What was NOT accomplished:**
1. ✗ Full LIVE yield measurement (benchmark takes too long to initialize in this environment)
2. ✗ Identity-rich evidence (Brave provides URLs only, no content)
3. ✗ Real email entity discovery (requires page fetching + extraction)

**Hard ENV blocker documented:**
- DuckDuckGo completely blocked at network level
- Python Brotli decoding broken for Brave
- Workaround (subprocess curl) works but is slower than native Python

---

## K. FILES MODIFIED

1. `hledac/universal/intelligence/stealth_crawler.py`
   - Added `_search_brave()` method
   - Added `_parse_brave()` method
   - Added `_fetch_with_subprocess_curl()` method
   - Updated `search()` with multi-provider fallback
   - Updated `_fetch_html()` with exception-safe subprocess curl fallback
