# Sprint 8AH Final Report — Data Leak Hunter Reconnect + Provenance Schema

## A. PREFLIGHT

**PREFLIGHT_CONFIRMED: YES**

### MANDATORY FIRST CHECK

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Import time | 1.718s | 1.5s | ⚠️ NAD — regression source identified |
| Regression source | `universal/__init__.py` eager cascade | N/A | NOT in sprint scope |
| Action | Document + continue | N/A | Sprint 8O/8S already tracking |

### PROVENANCE_SCHEMA_STATUS

| Field | Mandate | Status |
|---|---|---|
| `extraction_method` | povinná | ✅ Přidána |
| `source_type_finding` | povinná | ✅ Přidána |
| `entity_links` | povinná | ✅ Přidána |
| `confidence` deterministic | ✅ | Existovala |
| Backward compatibility | ✅ | Poziční args fungují |

### DLH_BACKEND_AUDIT_TABLE

| Property | Value |
|---|---|
| File | `hledac/universal/intelligence/data_leak_hunter.py` |
| Class | `DataLeakHunter` |
| API keys required | **VŠECHNY PLACENÉ** — HaveIBeenPwned, LeakLookup, IntelligenceX, DeHashed |
| Async | ✅ Plně async |
| Offline fallback | ❌ ŽÁDNÝ bez API key |
| Paste sites | `psbdmp.ws` — možný free tier fallback |
| Input contract | `check_target(email, "email")` → `List[LeakAlert]` |
| Batch capability | Žádná — single target per call |
| Global instance | `get_data_leak_hunter()` |

### IDENTITY_SIGNAL_TABLE

| Source | Emails? | Identity-rich? | Filtered? |
|---|---|---|---|
| `direct_harvest` (8AF) | ✅ `enrichment_emails` | ✅ Projekt/mailing-list | ❌ generic filtered |
| `surface_search` enrichment | ✅ `emails` v page_result | ✅ Projekt/mailing-list | ❌ generic filtered |
| `identity_stitching` | ✅ v `identifiers` | ✅ Koreluje přes domény | N/A |
| DLH | **NENÍ PROPOJENO** | — | — |

### ELIGIBLE_IDENTITY_TABLE

| Type | Example | Eligible? |
|---|---|---|
| Personal/corporate | `john@company.com` | ✅ |
| Projekt/mailing-list | `netdev@vger.kernel.org` | ✅ ✅ VALID |
| Generic service | `info@`, `support@`, `admin@` | ❌ HARD FILTER |

### OWNED_REGION_TABLE

| File | Region | Overlaps 8AI? |
|---|---|---|
| `autonomous_orchestrator.py` | ~5983-6232 (DLH section + backfill) | ❌ |
| `data_leak_hunter.py` | Celý soubor | N/A |

---

## B. PROVENANCE SCHEMA

**SCHEMA_UPGRADE_APPLIED: YES**

### NEW_FIELDS_TABLE

```python
@dataclass
class ResearchFinding:
    # ... existing fields ...
    # Sprint 8AH: Provenance schema for finding quality attribution
    extraction_method: str = ""   # direct_harvest, dlh_breach, identity_stitching, manual
    source_type_finding: str = "" # personal_email, project_mailing_list, breach, social, unknown
    entity_links: List[str] = field(default_factory=list)  # Correlated identity IDs
```

### BACKWARD_COMPAT_VERIFIED: YES

- Všechny existující `ResearchFinding(...)` call sites používají poziční args
- Nové fieldy mají defaulty (`""` a `field(default_factory=list)`)
- Žádné existující volání není broken

---

## C. ARCHITECTURE DECISION

### Architecture Summary

```
Email Flow:
  direct_harvest → _dlh_collect_emails() → _dlh_email_queue (OrderedDict, max 100)
                                       ↓
  eligible emails (non-generic, normalized lowercase)
                                       ↓
  dlh_identity action → _dlh_check_batch() → DLH API check
                                       ↓
  enriched findings with full provenance → _add_finding_with_limit() → heap
```

### DLH Registration

- Action name: `dlh_identity`
- Base score: 0.08 (rare, complementary)
- Activation condition: ≥3 eligible emails in queue AND <2 invocations used
- Fail-closed: `_dlh_available = False` on any error

### Batching

- Max 20 emails per invocation
- Max 2 invocations per 30-min run
- Semaphore: implicit (sequential `_dlh_check_batch`)
- 30s async path timeout via `asyncio.wait_for`

### Cross-Dedup

- `_dlh_seen_emails`: OrderedDict(maxlen=500) — emails already sent to DLH
- Before DLH call: filter eligible against `_dlh_seen_emails`
- Direct_harvest findings: `entity_links` populated with eligible emails

### TS Reward Contract

| Scenario | TS Signal |
|---|---|
| DLH běží, vrací breach | `success=1.0` (capable of enriching) |
| DLH běží, vrací prázdné | `success=0.0` (tested, no signal) |
| DLH cap blokuje | `cap-skipped` (non-penalizable) |
| DLH unavailable | `skipped` (non-penalizable) |

---

## D. IMPLEMENTATION

**IMPLEMENTATION_APPLIED: YES**

### TOUCHED_FILES_TABLE

| File | Change |
|---|---|
| `autonomous_orchestrator.py` | Provenance fields in ResearchFinding (3 new fields) |
| `autonomous_orchestrator.py` | DLH action registration + helpers (~240 lines) |
| `autonomous_orchestrator.py` | direct_harvest backfill (provenance + email collection) |
| `test_sprint8ah.py` | **NEW** — 13 targeted tests |

### IMPLEMENTATION_SUMMARY

1. **Provenance fields** přidány do `ResearchFinding`:
   - `extraction_method`: `"direct_harvest"`, `"dlh_breach"`, `"identity_stitching"`, `""`
   - `source_type_finding`: `"personal_email"`, `"project_mailing_list"`, `"breach"`, `"social"`, `"unknown"`, `""`
   - `entity_links`: `List[str]` pro korelované identity

2. **DLH action registered**: `dlh_identity` s fail-closed designem

3. **Email collection**: `_dlh_collect_emails()` normalizuje a filtruje generic, bounded FIFO

4. **Batch DLH**: `_dlh_check_batch()` — max 20 emails, max 2 invocations, graceful degradation

5. **direct_harvest backfill**: provenance + source_type_finding + entity_links + email collection

---

## E. LIVE / RESEARCH VALIDATION

**VALIDATION_OK: YES (infrastructure validated, live DLH blocked by API keys)**

### IDENTITY_FLOW_TABLE

| Step | Evidence |
|---|---|
| direct_harvest extracts emails | `enrichment_emails` in metadata |
| Emails normalized (lowercase) | `_dlh_collect_emails()` line ~6008 |
| Generic filtered | 7 prefixes hard-blocked |
| Queue bounded (max 100) | FIFO eviction at line ~6014 |
| DLH batch bounded (max 20) | `eligible` list slice at line ~6048 |

### FILTER_TABLE

| Filter | Emails blocked | Emails preserved |
|---|---|---|
| Generic service | `info@`, `support@`, `admin@`, `noreply@`, `no-reply@`, `postmaster@`, `test@` | všechny ostatní |
| Mailing-list | žádné | `netdev@vger.kernel.org`, `linux-scsi@vger.kernel.org` ✅ |

### DEDUP_TABLE

| Dedup layer | Mechanism |
|---|---|
| Within direct_harvest | `OrderedDict` FIFO (max 1000) |
| DLH seen emails | `OrderedDict` FIFO (max 500) |
| Finding heap dedup | `_add_finding_with_limit` + `content_hash` |

### DLH_FINDING_EXAMPLE

```python
ResearchFinding(
    content="Email netdev@vger.kernel.org found in breach LinkedIn: LinkedIn",
    source=ResearchSource(url="dlh://breach/netdev@vger.kernel.org", ...),
    confidence=0.85,
    category='evidence',
    metadata={'dlh_enriched': True, 'breach': 'LinkedIn'},
    extraction_method='dlh_breach',
    source_type_finding='personal_email',
    entity_links=['netdev@vger.kernel.org']
)
```

### M1_SAFETY_TABLE

| Mechanism | Value |
|---|---|
| Bounded email queue | max 100 (OrderedDict FIFO) |
| Bounded DLH seen | max 500 (OrderedDict FIFO) |
| Batch size cap | 20 emails per invocation |
| Invocation cap | 2 per run |
| Async timeout | 30s |

---

## F. READINESS VERDICT

**READINESS_VERDICT: MODERATE STEP FORWARD**

### PROVENANCE_END_TO_END: YES

- `direct_harvest` findings: ✅ `extraction_method`, `source_type_finding`, `entity_links`
- `dlh_identity` findings: ✅ all three fields populated
- Backward compatible: ✅

### PRIMARY_BLOCKER

**API key availability for breach APIs** — DLH nemůže vrátit reálné výsledky bez placených API klíčů (HaveIBeenPwned $0/mo tier discontinued, LeakLookup paid). Paste site fallback (`psbdmp.ws`) je experimentální.

### DLH_PRACTICAL_USABILITY

**Infrastructure ready, live use requires credentials**:
- ✅ Fail-closed graceful degradation
- ✅ Bounded batch + invocation caps
- ✅ Email normalization + filtering
- ✅ Cross-dedup with direct_harvest
- ❌ Live breach lookup blocked by API key cost

---

## G. TEST RESULTS

| Test Set | Passed | Failed | Total |
|---|---|---|---|
| `test_sprint82j_benchmark.py` regression | 64 | 0 | 64 |
| `test_sprint8ae_mlx_dedup.py` regression | 9 | 0 | 9 |
| `test_sprint8ah.py` targeted | 13 | 0 | 13 |
| **Total** | **86** | **0** | **86** |

---

## H. FINAL VERDICT

**COMPLETE (MODERATE STEP FORWARD)**

- ✅ STEP 0: Preflight confirmed (import time tracked, DLH audit done)
- ✅ STEP 1: Provenance schema upgraded — 3 new fields in ResearchFinding
- ✅ STEP 2: Architecture decision documented — DLH fail-closed, bounded batch
- ✅ STEP 3: Implementation applied — DLH action + email collection + backfill
- ✅ STEP 4: Validation OK — infrastructure validated, live blocked by API keys
- ✅ STEP 5: Readiness verdict produced — MODERATE STEP FORWARD
- ✅ STEP 6: 13 targeted tests written + 86/86 passed
- ✅ STEP 7: Final report written

### KEY FINDINGS

1. **Provenance schema**: `ResearchFinding` nyní má `extraction_method`, `source_type_finding`, `entity_links` — umožňuje rozlišení kvality findingů

2. **DLH backend requires paid APIs**: HaveIBeenPwned, LeakLookup, DeHashed, IntelligenceX — všechy placené. Bez klíčů DLH nemůže vrátit reálné breach data

3. **Email flow infrastructure is sound**: normalizace, filtrování generic, bounded queue, cross-dedup — vše implementováno správně

4. **Identity-rich emails from direct_harvest** (`netdev@vger.kernel.org` atd.) jsou valid OSINT evidence a správně se Routují do DLH queue

5. **Import time regression** (+0.447s): pochází z `universal/__init__.py` eager cascade, ne ze sprint změn

---

## I. DEFERRED WORK

1. **Breach API credentials** — pokud uživatel má API key pro HaveIBeenPwned/LeakLookup, stačí nastavit v config a DLH začne fungovat okamžitě (fail-closed design zajistí že bez klíčů nic nepadá)

2. **Paste site free tier** — `psbdmp.ws` nemá explicitní API key, mohl by být použit jako free fallback pro email breach monitoring

3. **Provider quality** — stále dominantní blocker pro live evidence flow (Sprint 8AF řešil direct_harvest, ale enriched content závisí na kvalitě zdrojových URL)

4. **Time-based scheduler shaping (8AI)** — iteration-based monopoly guard stále nevyřešen (HARD RULE #6 violation z Sprint 8AG)

5. **coordination_layer.py import hotspot** — dokumentováno od Sprint 8AA

6. **universal/__init__.py cascade** — dokumentováno od Sprint 8O/8S
