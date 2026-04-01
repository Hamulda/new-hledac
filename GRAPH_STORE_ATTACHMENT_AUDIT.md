# Graph Store Attachment Audit — Sprint 8TF

**Datum:** 2026-04-01
**Scope:** `knowledge/duckdb_store.py` — `_ioc_graph` attachment boundary
**Cíl:** Zabezpečit hranici kolem attached graph backendu, eliminovat tiché capability assumptions

---

## 1. Ptačí perspektiva — co je `_ioc_graph` problém

`DuckDBShadowStore` má attach point `inject_graph(graph)` určený původně pro `IOCGraph` (Kuzu, truth backend).
V runtime/windup_engine se však do téhož atributu injectuje `DuckPGQGraph` (DuckDB, donor/alternate backend).

```
inject_graph(IOCGraph)     → docstring říká "IOCGraph for graph ingest"
inject_graph(DuckPGQGraph)  → windup cpěje DuckPGQGraph jako "_ioc_graph"
```

Výsledek: `duckdb_store._ioc_graph` drží jeden ze dvou fyzicky různých backendů,
každý s jiným API a různými schopnostmi. Store nikdy nebyl truth owner — jen přijímal,
co mu bylo injectnuto. Bez explicitní capability kontroly hrozilo:

| Scénář | Riziko bez guardů |
|---|---|
| `duckdb_store._ioc_graph` je `DuckPGQGraph` | `.flush_buffers()` → `AttributeError` (tiché, schované v `except Exception: pass`) |
| `duckdb_store._ioc_graph` je `DuckPGQGraph` | `.buffer_ioc()` → voláno v `_graph_ingest_findings` bez efektu |
| `aclose()` při `DuckPGQGraph` | `flush_buffers()` guard preventivně chráněn, `close()` universálně dostupný |

---

## 2. Store Attachment Call-Site Matrix

| Call-site | Očekávaná capability | Možný backend | Safe/Unsafe | Silent/Explicit | Poznámka |
|---|---|---|---|---|---|
| `_graph_ingest_findings` volá `buffer_ioc()` | `buffer_ioc()` | IOCGraph (Kuzu) ✅, DuckPGQGraph ❌ | **Unsafe bez guardu** | Silent fail-open (tiché) | Opraveno: guard `graph_supports_buffered_writes()` |
| `_graph_ingest_findings` volá `buffer_observation()` | `buffer_observation()` | IOCGraph (Kuzu) ✅, DuckPGQGraph ❌ | **Unsafe bez guardu** | Silent fail-open | Opraveno: guard gating celou metodu |
| `_graph_ingest_findings` volá `flush_buffers()` | `flush_buffers()` | IOCGraph (Kuzu) ✅, DuckPGQGraph ❌ | **Unsafe bez guardu** | Silent fail-open | Opraveno: guard gating celou metodu |
| `aclose()` volá `flush_buffers()` | `flush_buffers()` | IOCGraph (Kuzu) ✅, DuckPGQGraph ❌ | Safe (except盲) | Explicitní guard | Opraveno: `callable(getattr(...))` guard |
| `aclose()` volá `close()` | `close()` | IOCGraph (Kuzu) ✅, DuckPGQGraph ✅ | Safe | Guard | Opraveno: `callable(getattr(...))` guard |
| `async_ingest_findings_batch` gating | `buffer_ioc+flush_buffers` | IOCGraph (Kuzu) ✅, DuckPGQGraph ❌ | **Unsafe bez guardu** | Silent (auto-fire) | Opraveno: `graph_supports_buffered_writes()` check |

---

## 3. Změněné soubory

| Soubor | Změna |
|---|---|
| `knowledge/duckdb_store.py` | Guardy + capability checkery + NON-AUTHORITATIVE docstringy |
| `tests/probe_8tf/test_graph_attachment_guards.py` | **NOVÝ** — 12 probe testů uzamykajících invarianty |
| `GRAPH_STORE_ATTACHMENT_AUDIT.md` | **NOVÝ** — tento dokument |
| `GRAPH_BACKEND_RECONCILIATION.md` | Sekce 8TF aktualizovaná |

---

## 4. Patch/Implementace

### 4.1 `inject_graph()` — explicitní capability contract

```python
def inject_graph(self, graph: Any) -> None:
    """
    Inject a graph instance for IOC ingest on canonical findings.

    STORE IS NOT GRAPH TRUTH OWNER — the injected graph may be:
      - IOCGraph (Kuzu): truth backend, full capability
      - DuckPGQGraph (DuckDB): donor/alternate backend, limited capability

    Capability requirements for buffered writes (ACTIVE phase):
      - Requires: buffer_ioc(), buffer_observation(), flush_buffers()
      - IOCGraph has these. DuckPGQGraph does NOT.

    After inject, use get_graph_attachment_kind() to determine
    which backend was attached and check capabilities explicitly.
    """
    self._ioc_graph = graph
    self._graph_attachment_kind = graph.__class__.__name__ if graph is not None else None
```

### 4.2 `graph_supports_buffered_writes()` — compat seam

```python
def graph_supports_buffered_writes(self) -> bool:
    """
    NON-AUTHORITATIVE COMPAT CHECK: does attached graph support ACTIVE-phase
    buffered writes?

    Returns True only if attached graph has both:
      - buffer_ioc()
      - flush_buffers()

    IOCGraph (Kuzu): True — has full buffered write capability.
    DuckPGQGraph (DuckDB): False — has checkpoint() and add_ioc() only.

    Always check this before triggering background graph ingest,
    do not assume all injected graphs support buffered writes.
    """
    if self._ioc_graph is None:
        return False
    return (
        callable(getattr(self._ioc_graph, "buffer_ioc", None))
        and callable(getattr(self._ioc_graph, "flush_buffers", None))
    )
```

### 4.3 Background ingest gating — `async_ingest_findings_batch`

```python
# BEFORE (Sprint 8QA) — silent for DuckPGQGraph:
if results and any(r.get("lmdb_success") for r in results):
    self._graph_ingest_findings(findings)  # no capability check!

# AFTER (Sprint 8TF) — explicit guard:
if (
    results
    and any(r.get("lmdb_success") for r in results)
    and self.graph_supports_buffered_writes()  # explicit capability gate
):
    self._graph_ingest_findings(findings)  # only called when safe
```

### 4.4 `aclose()` teardown guards

```python
# BEFORE — DuckPGQGraph path: AttributeError schovaný v except盲:
if self._ioc_graph is not None:
    try:
        await self._ioc_graph.flush_buffers()   # DuckPGQGraph → AttributeError
        await self._ioc_graph.close()
    except Exception:
        pass

# AFTER — explicit callable guards:
if self._ioc_graph is not None:
    try:
        if callable(getattr(self._ioc_graph, "flush_buffers", None)):
            await self._ioc_graph.flush_buffers()
    except Exception:
        pass
    try:
        if callable(getattr(self._ioc_graph, "close", None)):
            await self._ioc_graph.close()
    except Exception:
        pass
```

---

## 5. Test/Probe Summary

```
tests/probe_8tf/test_graph_attachment_guards.py — 12 PASSED

test_graph_supports_buffered_writes_iocgraph_returns_true  → True for IOCGraph mock
test_graph_supports_buffered_writes_duckpgq_returns_false  → False for DuckPGQGraph mock
test_graph_supports_buffered_writes_none_returns_false     → False for None graph
test_inject_graph_sets_attachment_kind                     → class name recorded
test_get_graph_attachment_kind_none_when_no_graph         → None for no graph
test_graph_supports_buffered_writes_no_false_positives     → False for partial graph
test_inject_graph_accepts_none                            → clears state safely
test_aclose_no_flush_buffers_on_duckpgq                  → guard prevents call
test_aclose_flush_buffers_on_iocgraph                   → guard allows call
test_aclose_close_on_duckpgq                            → close() allowed
test_store_is_not_graph_truth_owner_note                  → docstring contract locked
test_graph_supports_buffered_writes_diagnostic_only        → compat seam docstring locked
```

---

## 6. Odpovědi na klíčové otázky

### Kde store dělal tiché capability assumptions?

| Místo | Původní chování |
|---|---|
| `async_ingest_findings_batch` | Automaticky volal `_graph_ingest_findings` bez capability check — pro DuckPGQGraph to bylo tiché no-op |
| `aclose()` teardown | `flush_buffers()` na DuckPGQGraph → `AttributeError` schovaný v `except Exception: pass` — nevěděli jsme, že to selhalo |

### Jak jsou teď explicitně guardované?

- **Background ingest gating**: `graph_supports_buffered_writes()` check v `async_ingest_findings_batch` — DuckPGQGraph path už nikdy nezavolá `_graph_ingest_findings`
- **Teardown**: `callable(getattr(..., "flush_buffers", None))` guard — DuckPGQGraph nemá tuto metodu, takže se ani nezavolá
- **Capability discovery**: `get_graph_attachment_kind()` a `graph_supports_buffered_writes()` — consumer může zjistit, co je připojeno

### Jak bylo zabráněno tomu, aby store začal fungovat jako graph authority?

1. Žádná nová graph abstrakce, žádný GraphProtocol, žádný adapter layer
2. Helpers jsou označeny jako `NON-AUTHORITATIVE COMPAT CHECK` a `NON-AUTHORITATIVE DIAGNOSTIC`
3. `inject_graph()` docstring obsahuje `STORE IS NOT GRAPH TRUTH OWNER` — toto je zároveň dokumentace i kontrakt
4. Store nevolá žádné graph methody, které by nebyly guardované nebo explicitně otestované

### Co stále zůstává debt pro pozdější graph reconciliation?

| Debt | Detail |
|---|---|
| **DEBT-3** (Graph Backend Reconciliation) | Schizofrenie `duckdb_store._ioc_graph` — dva různé backendy, stejný atribut. Stále přítomno, ale teď aspoň explicitně označeno. Plné vyřešení vyžaduje graph cutover, který je mimo scope tohoto sprintu. |
| **`duckdb_store.flush_buffers()` na úrovni store** | Store nemá metodu `flush_buffers()` — pouze ji volá na attached graph v aclose. To je správně: store není graph authority. |
| **STIX degradace** | RESOLVED v Sprint 8TH — `_stix_status/reason/backend` na synthesis_runner instance |

---

## 7. Zero-Silent-Fallback Rule — uzamčeno

| Scénář | Před (silent) | Po (explicit) |
|---|---|---|
| DuckPGQGraph → background ingest | Tiché no-op, žádný log | `graph_supports_buffered_writes()` → False → žádné volání |
| DuckPGQGraph → aclose flush_buffers | AttributeError v except盲 | `callable()` guard → flush se nezavolá |
| Žádný graph attached | `buffer_ioc()` se nezavolá (None check) | Stejné + `graph_supports_buffered_writes()` → False |
| Partial graph (pouze buffer_ioc) | False negative | `graph_supports_buffered_writes()` → False (AND logika) |

---

## 8. Migration Blockers (pro plný graph cutover)

1. **DuckPGQGraph nemá `flush_buffers()`** — pokud by duckdb_store měl v budoucnu volat flush_buffers, musel by se přidat stub/buffer do DuckPGQGraph, nebo se změnit injektovaný backend
2. **`duckdb_store._ioc_graph` je obousměrný** — dnes tam jde IOCGraph i DuckPGQGraph v závislosti na lifecycle fázi. Rozpojení vyžaduje jasné rozhraní kdo co vlastní
3. **`synthesis_runner` dostává DuckPGQGraph** — STIX export je degradován (RESOLVED v 8TH), ale plná oprava vyžaduje správné injektování IOCGraph do synthesis_runner
