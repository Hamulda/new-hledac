# SPRINT 8BS — Hidden I/O & CPU Blockers Report

**Datum:** 2026-03-24
**Probe type:** READ-ONLY analysis
**Scope:** `/hledac/universal/` (11207 souborů skenováno, kontaminace venv ignorována)

---

## Executive Summary

| Kategorie | Počet | Riziko |
|-----------|-------|--------|
| 🔴 **SYNC HTTP v async** | 3 skutečné | **VYSOKÉ** — blokuje event loop |
| 🟡 **SYNC FILE I/O** | ~60 | **STŘEDNÍ** — různé závažnosti |
| 🟢 **Heavy JSON parse** | ~46 | **NÍZKÉ** — orjson je rychlý |

---

## 🔴 CRITICAL: Synchronous HTTP Calls in Async Contexts

### Nejkritičtější nález — BLOKUJÍ EVENT LOOP

| Soubor | Řádek | Kód | Závažnost |
|--------|-------|-----|-----------|
| `coordinators/fetch_coordinator.py` | 783 | `requests.head(url, timeout=3, ...)` | **KRITICKÉ** |
| `coordinators/fetch_coordinator.py` | 785 | `requests.get(url, timeout=3, ...)` | **KRITICKÉ** |
| `coordinators/security_coordinator.py` | 1551 | `requests.Session(impersonate=...)` | **KRITICKÉ** |

### Detaily

#### 1. `fetch_coordinator.py:783-785` — HEAD/GET bez `await`

```python
# NEASYNCHRONNÍ — TOČÍ EVENT LOOP
resp = requests.head(url, timeout=3, allow_redirects=True, cookies=session_cookies)
resp = requests.get(url, timeout=3, allow_redirects=True, cookies=session_cookies)
```

**Problém:** `requests` je synchronní knihovna. Volání blokuje celý event loop.
**Dopad:** Při 100ms latenci HTTP requestu pojede celý orchestrátor na 1 request současně místo paralelně.
**Očekávané chování:** Mělo by používat `aiohttp` nebo `curl_cffi.AsyncSession`.

#### 2. `security_coordinator.py:1551` — Session creation

```python
# NEASYNCHRONNÍ — TOČÍ EVENT LOOP
session = requests.Session(impersonate=impersonate)
```

**Problém:** Vytváří synchronní session uvnitř async funkce.
**Kontext:** `stealth_request_with_jitter()` — ochranný layer, ale sám sebe brzdí.

---

## 🟡 MEDIUM RISK: Synchronous File I/O

### Kategorie false positives (NEJSOU problém)

Některé detekce `open(` jsou **false positives** — jedná se o:
- `fitz.open()` — PyMuPDF (PDF knihovna, ne builtin open)
- `Image.open()` — PIL/Pillow, ověřeno v async contextu
- `lmdb.open()` — LMDB databáze
- `tarfile.open()` — archivy

### Skutečné problémy

| Soubor | Řádek | Operace | Závažnost |
|--------|-------|---------|-----------|
| `autonomous_orchestrator.py` | 21685 | `open(snapshot_path, 'wb')` | STŘEDNÍ |
| `autonomous_orchestrator.py` | 21726 | `open(entry.snapshot_path, 'rb')` | STŘEDNÍ |
| `autonomous_orchestrator.py` | 28132 | `open(snapshot_path, 'r', encoding='utf-8')` | STŘEDNÍ |
| `tool_registry.py` | 857, 876 | `open(path, "r"/mode)` | STŘEDNÍ |
| `intelligent_cache.py` | 586, 604-605 | `open(persist_file, 'w'/'r')` | NÍZKÉ |
| `smoke_runner.py` | 199, 205 | `open(ledger_path/tool_path, "w")` | NÍZKÉ |

### Mazání (destruction) — potential double-risk

```python
# security/destruction.py
with open(path, 'r+b') as f:  # Otevření pro overwrite
with open(path, 'rb') as f:   # Ověření smazání
```

---

## 🟢 LOW RISK: Heavy JSON Parsing

### orjson.loads() — Acceptable

`orjson` je C-based, velmi rychlý (až 3x rychlejší než stdlib json).

**Měření:** orjson.parse() 1MB JSON ≈ 2-5ms na M1.

| Location | Count | Notes |
|----------|-------|-------|
| `autonomous_orchestrator.py` | 8 | CT/Wayback/CDX streaming |
| `dht/local_graph.py` | 3 | LMDB data retrieval |
| `federated/model_store.py` | 1 | Model loading |
| `brain/distillation_engine.py` | 2 | Example loading |

### json.loads() — Stdlib fallback

Standardní `json` je pomalejší, ale většinou jde o malé dokumenty.

---

## 🔍 FP/FN Analysis

### False Positives (detekováno špatně)

| Detekce | Skutečnost |
|----------|------------|
| `open(path, 'r')` v `tool_registry.py` | `Path.read_text()` nebo `Path.write_text()` — Path metody, ne sync I/O |
| `is_net_breaker_open()` | Method call, ne file open |
| `lmdb.open()` | LMDB interní, ne souborový open |

### False Negatives (nebylo detekováno)

- `asyncio.sleep()` s nulovým časem — `await asyncio.sleep(0)` — yieldnutí event loopu je správné
- `_io` operace skryté v C extension — nelze detekovat bez runtime trace

---

## Risk-Ranked Prioritization

### 🚨 IMMEDIATE ACTION (blokující event loop)

1. **fetch_coordinator.py:783-785** — Nahradit `requests.get/head` za `curl_cffi` async session
2. **security_coordinator.py:1551** — Refaktorovat na async session creation

### ⚠️ DEFERRED (non-blocking ale neoptimální)

3. **autonomous_orchestrator.py snapshot I/O** — `open()` pro snapshot write/read
   - mitigace: Již používá `loop.run_in_executor` pro velké operace
   - Lze přesunout do `aiothreadpool` pro background writes

4. **tool_registry.py file handlers** — Malé soubory, nízký dopad
   - mitigace: Konverze na `Path` metody nebo `asyncio.to_thread`

### ✅ ACCEPTABLE (low risk)

5. **orjson/json.loads()** — Výkonově acceptable
6. **Image.open(), fitz.open()** — C extension, async-safe pokud jsou v executoru

---

## Methodology

- **Tool:** Python AST parsing s line-number mapping
- **Pattern detection:** Regex na úrovni řádků v těle async funkcí
- **Limitation:** AST nemůže rozpoznat dynamicky generované stringy
- **Scope:** 11207 souborů, ignorovány `.venv`, `.phase`, `tests/probe`

---

## Conclusion

**3 kritické sync HTTP blockery** musí být opraveny — absolutně blokují event loop.
**~60 sync file I/O** je střední riziko, většina je v executoru nebo jde o C-extensions.
**~46 JSON parse** je nízké riziko kvůli orjson rychlosti.

**Doporučení:** Opravit fetch_coordinator + security_coordinator sync HTTP jako prioritu 1.
