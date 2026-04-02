# Graph Backend Reconciliation — Audit Report

**Datum:** 2026-04-01
**Scope:** `hledac/universal/`
**Režim:** ČISTĚ AUDITNÍ — žádný refactor, cutover ani nová interface

---

## 1. Graph Split — pohled z ptačí perspektivy

V codebase koexistují dva fyzicky oddělené graph backedny:

| Jméno | Backend | Schema | Role |
|---|---|---|---|
| `IOCGraph` | Kuzu (file-based) | IOC nodes + OBSERVED edges | Truth store — všechny IOC upserty jdou sem |
| `DuckPGQGraph` | DuckDB (SQL/PGQ) | ioc_nodes + ioc_edges | Analytics / donor backend — path queries, top-N, edge export |

Oběma se přistupuje přes atribut pojmenovaný `_ioc_graph`, ale na **různých objektech**:

```
scheduler._ioc_graph          → DuckPGQGraph (runtime, WARMUP)
duckdb_store._ioc_graph       → IOCGraph (Kuzu) nebo DuckPGQGraph (windup přepisuje)
```

Toto není multi-backend replicace — jde o dva různé systémy s různými schématy, různými capability a různými spotřebiteli.

---

## 2. Klíčová zjištění

### 2.1 duckdb_store._ioc_graph — dvojí role

`duckdb_store` (DuckDBShadowStore) má `inject_graph(graph)` určenou pro injektování **IOCGraph (Kuzu)**:

```python
# duckdb_store.py:537-544
def inject_graph(self, graph: Any) -> None:
    """Inject an IOCGraph instance for graph ingest on canonical findings."""
    self._ioc_graph = graph   # ← comment říká IOCGraph (Kuzu)
```

Avšak **windup_engine** do ní cpěje **DuckPGQGraph**:

```python
# windup_engine.py:183
ioc_graph=getattr(scheduler, "_ioc_graph", None),  # scheduler._ioc_graph = DuckPGQGraph
```

Výsledek: `duckdb_store._ioc_graph` po windupu drží **DuckPGQGraph**, ne IOCGraph.

### 2.2 duckdb_store._ioc_graph.flush_buffers() — DEBT

```python
# duckdb_store.py:2674-2677
if self._ioc_graph is not None:
    if callable(getattr(self._ioc_graph, "flush_buffers", None)):
        await self._ioc_graph.flush_buffers()
```

`DuckPGQGraph` **nemá** `flush_buffers()` — toto je metoda pouze IOCGraph. Tento kód je mrtvý kód pro DuckPGQGraph path.

### 2.3 DuckPGQGraph nemá `export_stix_bundle`

`synthesis_runner` volá:

```python
# synthesis_runner.py:986
export_fn = getattr(self._ioc_graph, "export_stix_bundle", None)
```

DuckPGQGraph tuto metodu **nemá**. IOCGraph ji má. DuckPGQGraph je předáván do synthesis_runner přes `inject_graph(scheduler._ioc_graph)` ve windup_engine.

### 2.4 duckdb_store._ioc_graph.get_top_graph_nodes() — CHYBÍ

`sprint_exporter` spoléhá na existenci `duckdb_store.get_top_graph_nodes()` (viz COMPAT_DEBT_LEDGER.md), ale tato metoda na `DuckDBShadowStore` **neexistuje**. Export bere top_graph_nodes z scorecard, kam je ukládá windup_engine přímo z `scheduler._ioc_graph.get_top_nodes_by_degree(n=10)`.

---

## 3. Capability Matrix

| Capability | IOCGraph (Kuzu) | DuckPGQGraph | Windup očekává | Export očekává | Scheduler očekává | Status |
|---|---|---|---|---|---|---|
| **upsert/write truth** | ✅ `upsert_ioc()`, `upsert_ioc_batch()` | ✅ `add_ioc()` | ✅ flush do DuckDB přes duckdb_store path | — | DuckPGQGraph `add_ioc()` | **SPLIT** — dva různé write API |
| **buffered ACTIVE writes** | ✅ `buffer_ioc()`, `buffer_observation()`, `_BUFFER_FLUSH_SIZE=500` | ❌ žádný buffer | ✅ volá `flush_buffers()` | — | IOCGraph buffer přes `duckdb_store.inject_graph()` → DuckPGQGraph nemá | **DEBT** — DuckPGQGraph nemá flush_buffers |
| **pivot/path queries** | ✅ `pivot()` — depth 1–2 | ✅ `find_connected()` — max_hops bound | — | — | `_pivot_ioc_graph` (IOCGraph) přes `inject_ioc_graph()` | IOCGraph pro pivot, DuckPGQGraph pro connected |
| **top nodes** | ❌ chybí úplně | ✅ `get_top_nodes_by_degree(n)` | ✅ volá `get_top_nodes_by_degree(n=10)` | ✅ čte z scorecard | DuckPGQGraph → write do scorecard | DuckPGQGraph je jediný zdroj |
| **ghost_global entities** | ❌ chybí | ✅ `get_top_nodes_by_degree(n=100)` | ✅ volá `get_top_nodes_by_degree(n=100)` | — | duckdb_store.get_top_entities_for_ghost_global() → DuckPGQGraph | Sprint 8TF: store seam removed direct graph spelunking |
| **graph stats** | ✅ `graph_stats()` → `{nodes, edges}` | ✅ `stats()` → `{nodes, edges, pgq_active}` | ✅ volá `stats()` | — | DuckPGQGraph | DuckPGQGraph je jediný zdroj |
| **edge export** | ❌ chybí | ✅ `export_edge_list()` | ✅ volá `export_edge_list()` | — | DuckPGQGraph → feed do GNN | DuckPGQGraph je jediný zdroj |
| **STIX export** | ✅ `export_stix_bundle()` | ❌ **chybí** | — | — | synthesis_runner používá `self._ioc_graph.export_stix_bundle` — dostává DuckPGQGraph → vrací None | **CRITICAL DEBT** |
| **checkpoint/recovery** | ✅ `close()` (Kuzu implicitní) | ✅ `checkpoint()` | ✅ volá `checkpoint()` | — | DuckPGQGraph | DuckPGQGraph je jediný zdroj |
| **GNN edge-list / analytics feed** | ❌ | ✅ `export_edge_list()` → GNN predictor | ✅ `export_edge_list()` | — | DuckPGQGraph → `gnn_predictor` přes synthesis_runner | DuckPGQGraph je jediný zdroj |

---

## 4. Vnitřní duplicity uvnitř IOCGraph

### 4.1 `upsert_ioc_batch` — DUPLICITA (TŘI definice)

V `knowledge/ioc_graph.py` existují **TŘI** definice `upsert_ioc_batch`:

**Definice 1** — řádky 427–450:
```python
async def upsert_ioc_batch(self, iocs: list[tuple[str, str, float]]) -> list[str]:
    if self._closed or self._conn is None or not iocs:
        return []
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        self._executor,
        self._upsert_ioc_batch_sync,
        iocs,
    )

def _upsert_ioc_batch_sync(self, iocs: list[tuple[str, str, float]]) -> list[str]:
    """Synchronous batch upsert — runs on _executor thread."""
    conn = self._conn
    assert conn is not None
    now = time.time()
    ids: list[str] = []
    for ioc_type, value, confidence in iocs:
        node_id = _make_ioc_id(ioc_type, value)
        ids.append(node_id)
        res = conn.execute(...)
        # MATCH → CREATE / SET pattern
```
Vrací `list[str]` — všechny node_id (existující i nové).

**Definice 2** — řádky 651–707:
```python
async def upsert_ioc_batch(
    self, iocs: list[tuple[str, str, float]]
) -> list[str]:
    """Batch upsert of IOC nodes. ... Returns: List of node IDs created/updated."""
    if self._closed or self._conn is None or not iocs:
        return []
    loop = asyncio.get_running_loop()
    node_ids = [_make_ioc_id(t, v) for t, v, _ in iocs]
    now = time.time()
    try:
        return await loop.run_in_executor(
            self._executor,
            self._upsert_ioc_batch_sync,  # ← jiné jméno sync helperu
            node_ids,
            iocs,
            now,
        )
    except Exception as e:
        logging.warning(f"[IOCGraph] upsert_ioc_batch failed: {e}")
        return []

def _upsert_ioc_batch_sync(
    self,
    node_ids: list[str],
    iocs: list[tuple[str, str, float]],
    now: float,
) -> list[str]:
    """Synchronous batch upsert — runs on _executor thread."""
    conn = self._conn
    assert conn is not None
    created: list[str] = []
    for node_id, (ioc_type, value, confidence) in zip(node_ids, iocs):
        res = conn.execute(...)
        if not res.has_next():
            conn.execute("CREATE (:IOC {id: $id, ...})")
            created.append(node_id)  # ← vrací jen CREATED, ne všechny
        else:
            conn.execute("MATCH ... SET n.last_seen = $ts")
    return created  # ← vrací jen nově vytvořené!
```
Vrací `list[str]` — pouze **nově vytvořené** node_id.

**Definice 3** — volání z `flush_buffers` — řádky 177–178:
```python
if ioc_copy:
    ioc_ids = await self.upsert_ioc_batch(ioc_copy)  # ← volá Def 1 nebo Def 2? záleží na pořadí def
```

**PROBLÉM:** Definice 1 i Definice 2 jsou na stejné třídě. V Pythonu druhá definice přepíše první. `flush_buffers` volá `upsert_ioc_batch` — dostane verzi která vrací pouze `created` nodes, ne všechny. To je nekonzistentní s komentářem v `flush_buffers` ("Vrátí počet flushlých IOCs").

**AUDIT NOTE:** Toto je confusion-ready duplicated method. Obě async verze mají stejný název a podobný docstring, ale různou return value semantics. První definice (řádky 427–450) je **mrtvá** — nikdy není volána, protože druhá ji přepíše.

---

## 5. Nové / změněné soubory

| Soubor | Akce | Poznámka |
|---|---|---|
| `GRAPH_BACKEND_RECONCILIATION.md` | **NOVÝ** | Tento dokument |

Žádné jiné soubory nebyly změněny (auditně-čistý režim).

---

## 6. Graph Truth Owner, Analytics Provider, Donor Backend

| Role | Držitel | Backend |
|---|---|---|
| **Graph Truth Owner** | `IOCGraph` (Kuzu) | `knowledge/ioc_graph.py` — všechny IOC upserty v ACTIVE fázi jdou přes `buffer_ioc` / `flush_buffers` |
| **Graph Analytics Provider** | `DuckPGQGraph` | `graph/quantum_pathfinder.py` — `stats()`, `get_top_nodes_by_degree()`, `export_edge_list()` |
| **Donor / Alternate Backend** | `DuckPGQGraph` | Půjčuje své DuckDB-backed metody (`stats`, `top_nodes`, `edge_list`) scheduleru a windupu |

`synthesis_runner._ioc_graph` po windupu drží DuckPGQGraph (přes `inject_graph(scheduler._ioc_graph)`), takže STIX export je **degradován** na no-op.

---

## 7. Migration Blockers

1. **`duckdb_store.get_top_graph_nodes()` neexistuje** — COMPAT_DEBT_LEDGER.md řeší, ale zatím neimplementováno. Export bere top_nodes z scorecard, což je dočasné řešení.
2. **`duckdb_store._ioc_graph.flush_buffers()` je mrtvý kód** pro DuckPGQGraph path — DuckPGQGraph nemá flush_buffers. Pokud by se duckdb_store přepnul zpět na IOCGraph (Kuzu), musel by se inject_graph zavolat správně a flush_buffers by fungovalo.
3. **Dva různé write API** — `IOCGraph.upsert_ioc_batch()` vs `DuckPGQGraph.add_ioc()` — neexistuje žádná abstrakce. Každý consumer volá přímo.

---

## 8. Debt Sekce

### CRITICAL

**[DEBT-1] STIX export degradován**
`synthesis_runner` očekává `ioc_graph.export_stix_bundle()`, ale po windupu dostává DuckPGQGraph, který tuto metodu **nemá**. STIX context je tedy vždy prázdný seznam.
- Consumer: `synthesis_runner._build_stix_context()` (sprint_exporter → GNN context injection)
- Implicitní očekávání: truth store garantuje STIX export
- Skutečnost: truth store (IOCGraph) není nikdy předán do synthesis_runner pro STIX

### HIGH

**[DEBT-2] `upsert_ioc_batch` duplicitní definice — RESOLVED (Sprint 8TD)**
- **Původní stav:** Dvě async definice na stejné třídě s různou return value semantics. Python druhou přepíše první.
- **Akce:** Duplicitní definice (Def 1, ř. 427) odstraněna. Kanonická definice (Def 2, nyní jediná) formalizována s explicitní semantics block v docstringu.
- **Kanonická semantika (Sprint 8TD):** `upsert_ioc_batch(iocs)` vrací `list[str]` **pouze nově vytvořených** node IDs. Druhé volání se stejnými IOCs vrací `[]`. Idempotence garantována.
- **Uzamčení:** `tests/probe_8td/test_upsert_canonical_semantics.py` — 3 testy lockují CREATED-only semantics.
- **flush_buffers kontrakt:** `ioc_flushed` = počet newly created nodes (ne total buffered).
- **Ověření:** `grep -n "async def upsert_ioc_batch" knowledge/ioc_graph.py` → 1 výsledek

**[DEBT-3] `duckdb_store._ioc_graph` schizofrenie**
`inject_graph` injectuje IOCGraph (Kuzu) podle docstringu, ale windup_engine do nícpěí DuckPGQGraph. Výsledek závisí na pořadí volání.
- Consumer: `duckdb_store.flush_buffers()` — očekává `flush_buffers()` metodu, kterou DuckPGQGraph nemá

### MEDIUM

**[DEBT-4] `duckdb_store.get_top_graph_nodes()` chybí**
Export očekává store API, ale metoda není implementovaná. Windup obchází přes scorecard.
- COMPAT_DEBT_LEDGER.md již dokumentuje

**[DEBT-5] duckdb_store._ioc_graph.flush_buffers mrtvý kód**
`duckdb_store.py:2677` — pro DuckPGQGraph path je `flush_buffers` callable check false, takže await se nikdy neprovede. Pro IOCGraph path by to fungovalo, ale IOCGraph se do `duckdb_store._ioc_graph` už nedostává správně.

---

## 9. Co se NESMÍ refaktorovat před scheduler cutoverem

1. **NEMĚNIT** `scheduler._ioc_graph` setter logic — windup_engine, sprint_lifecycle a sprint_scheduler spoléhají na to, že `scheduler._ioc_graph` je DuckPGQGraph
2. **NEMĚNIT** pořadí `inject_graph` vs `runner.inject_graph` — windup_engine závisí na konkrétním pořadí
3. **NEMĚNIT** capability `DuckPGQGraph.stats()` / `DuckPGQGraph.get_top_nodes_by_degree()` / `DuckPGQGraph.export_edge_list()` — windup_engine a scorecard je přímo konzumují
4. **NEMĚNIT** `IOCGraph.export_stix_bundle()` — synthesis_runner používá `getattr(..., "export_stix_bundle", None)` fallback, takže chybějící metoda je dnes bezpečná, ale CUTOVER by to mohl změnit
5. **NEROZPOJOVAT** `duckdb_store._ioc_graph` path — dokud `duckdb_store.flush_buffers()` závisí na `flush_buffers()` metodě, nemůže `duckdb_store._ioc_graph` být bezpečně DuckPGQGraph (kromě toho, že dnes je)
6. **NEODSTRAŇOVAT** `duckdb_store.get_top_graph_nodes()` absenci — dokud export bere z scorecard, není to akutní, ale cutover scheduleru by to měl řešit

---

## 10. Shrnutí — kdo je kdo

| Otázka | Odpověď |
|---|---|
| **Graph Truth Owner dnes** | `IOCGraph` (Kuzu) — `knowledge/ioc_graph.py` — všechny IOC upserty v ACTIVE |
| **Analytics/Export Provider** | `DuckPGQGraph` — `graph/quantum_pathfinder.py` — `stats()`, `get_top_nodes_by_degree()`, `export_edge_list()` |
| **Donor/Alternate Backend** | `DuckPGQGraph` — půjčuje SQL/PGQ-backed analytics metodu scheduleru a windupu |
| **Kdo produkuje STIX** | `IOCGraph.export_stix_bundle()` — ale synthesis_runner dostává DuckPGQGraph → **degradováno na no-op** |
| **Kdo produkuje top_graph_nodes pro scorecard** | `DuckPGQGraph.get_top_nodes_by_degree(n=10)` v windup_engine |
| **Co se NESMÍ refaktorovat** | Viz sekce 9 — scheduler cutover je limitovaný existujícími implicitními contracty mezi duckdb_store, windup_engine a synthesis_runner |

---

## 11. Sprint 8TH — STIX Structured Degradation (2026-04-01)

### Co bylo silent mismatch

`_build_stix_context()` v `synthesis_runner.py` vracel `""` (prázdný string) ve třech případech degradace:

1. `_ioc_graph is None`
2. `getattr(ioc_graph, "export_stix_bundle", None)` vrátí `None` (DuckPGQGraph nemá tuto metodu)
3. Výjimka při volání

Ve všech třech případech volající dostal prázdný string bez jakéhokoliv vysvětlení. To je **tichá degradace** — caller neví proč STIX context chybí.

### Co je teď explicitně guardované

`_build_stix_context()` je nyní `async` (protože `IOCGraph.export_stix_bundle()` je async) a nastavuje tři instance atributy **před** returnem v každé větví:

| Atribut | Možné hodnoty | Kdy se nastavuje |
|---|---|---|
| `_stix_status` | `"available"` \| `"unavailable"` \| `"error"` | Vždy, v každé větvi |
| `_stix_reason` | Textový důvod | Vždy, v každé větvi |
| `_stix_backend` | Název třídy backendu | Když je `_ioc_graph` nenulový |

Příklad pro DuckPGQGraph:
```
_stix_status = "unavailable"
_stix_reason = "backend 'DuckPGQGraph' lacks export_stix_bundle — DuckPGQGraph donor cannot serve STIX"
_stix_backend = "DuckPGQGraph"
```

### Změněné soubory

| Soubor | Změna |
|---|---|
| `brain/synthesis_runner.py` | `_build_stix_context` → `async`, přidány `_stix_status/reason/backend` do `__slots__` a `__init__` |
| `tests/probe_8th/test_stix_degradation_not_silent.py` | **NOVÝ** — 4 probe testy uzamykající invarianty |

### Testy uzamykající invarianty

```
tests/probe_8th/test_stix_degradation_not_silent.py
  test_duckpgq_graph_lacks_export_stix_bundle     → DuckPGQGraph → status="unavailable", reason names backend ✓
  test_ioc_graph_has_export_stix_bundle           → IOCGraph s IOCs → status="available" ✓
  test_none_graph_sets_unavailable                 → None graph → status="unavailable" s důvodem ✓
  test_ioc_graph_no_nodes_available_empty         → IOCGraph prázdný → status="available", reason obsahuje "empty" ✓
```

### Co bylo schválně NEděláno

1. **Nevytvořen nový DTO/framework** — použity existující instance atributy (`_stix_status/reason/backend`)
2. **Nepřidána nová graph abstrakce** — žádný GraphProtocol, router ani adapter
3. **Nezměněn IOCGraph ani DuckPGQGraph** — jen consumer-side `_build_stix_context`
4. **Není to log-only** — structured state na instanci je hmatatelný a auditovatelný
5. **Není to "one backend to rule them all"**

### Truth vs Donor capability — uzamčeno

| Capability | Truth Owner | Donor Backend | Status |
|---|---|---|---|
| `export_stix_bundle` | IOCGraph (Kuzu) ✅ | DuckPGQGraph ❌ | **UZNAMČENO** — DuckPGQGraph negarantuje STIX; tichá degradace odstraněna |
| `get_top_nodes_by_degree` | DuckPGQGraph ✅ | — | DuckPGQGraph je jediný zdroj, žádná tichá degradace |
| `export_edge_list` | DuckPGQGraph ✅ | — | DuckPGQGraph je jediný zdroj, žádná tichá degradace |
| `stats()` | DuckPGQGraph ✅ | — | DuckPGQGraph je jediný zdroj, žádná tichá degradace |

### Debt sekce — aktualizace

**[DEBT-1] STIX export degradován → RESOLVED (Sprint 8TH)**
- Původní stav: `_build_stix_context()` vrací `""` bez explanation pro DuckPGQGraph path
- Akce: `_build_stix_context` → `async`, přidány `_stix_status/reason/backend` instance atributy
- Kanonická semantika: žádné tiché `""` — vždy existuje structured state v atributech instance
- Uzamčení: `tests/probe_8th/test_stix_degradation_not_silent.py` — 4 testy
- **Poznámka:** `_stix_status` je "unavailable" pro DuckPGQGraph — toto JE očekávané chování, ne bug. DuckPGQGraph donor nemá STIX capability. Truth store (IOCGraph) je třeba injectovat správně v production path.

---

## 12. Sprint 8TF — DuckDB Store Graph Attachment Audit (2026-04-01)

### Co bylo silent mismatch

`duckdb_store._ioc_graph` byl přijímán jako "graph backend" bez jakýchkoliv guardů.
Dva problémy:

1. **`async_ingest_findings_batch`** — automaticky volal `_graph_ingest_findings` bez capability check.
   Pro DuckPGQGraph (který nemá `buffer_ioc`/`flush_buffers`) to bylo tiché no-op.
2. **`aclose()` teardown** — volal `flush_buffers()` na `DuckPGQGraph` → `AttributeError` schovaný
   v `except Exception: pass`. Nevěděli jsme, že flush vůbec neproběhl.

### Co je teď explicitně guardované

| Scénář | Guard |
|---|---|
| Background ingest trigger | `graph_supports_buffered_writes()` — AND logika, DuckPGQGraph → False → nikdy nezavolá `_graph_ingest_findings` |
| `aclose()` flush_buffers | `callable(getattr(g, "flush_buffers", None))` — DuckPGQGraph nemá → nezavolá se |
| `aclose()` close | `callable(getattr(g, "close", None))` — oba backendy mají → zavolá se |

### Přidané helpers (NON-AUTHORITATIVE, DIAGNOSTIC ONLY)

- `inject_graph()` — nyní nastavuje `_graph_attachment_kind` (class name), docstring obsahuje `STORE IS NOT GRAPH TRUTH OWNER`
- `get_graph_attachment_kind()` — vrací class name attached backendu nebo None
- `graph_supports_buffered_writes()` — True pouze když `buffer_ioc` AND `flush_buffers` jsou přítomny

### Změněné soubory

| Soubor | Změna |
|---|---|
| `knowledge/duckdb_store.py` | 3 nové metody, 2 guardy v aclose, 1 guard v async_ingest_findings_batch |
| `tests/probe_8tf/test_graph_attachment_guards.py` | **NOVÝ** — 12 probe testů |
| `GRAPH_STORE_ATTACHMENT_AUDIT.md` | **NOVÝ** — detailní audit s call-site maticí |

### Testy uzamykající invarianty

```
tests/probe_8tf/test_graph_attachment_guards.py — 12 PASSED
  IOCGraph mock → supports buffered writes = True
  DuckPGQGraph mock → supports buffered writes = False
  None graph → supports buffered writes = False
  inject_graph sets _graph_attachment_kind
  get_graph_attachment_kind = None when no graph
  Partial graph (buffer_ioc only) → False
  inject_graph(None) clears state
  aclose: flush_buffers guard safe for DuckPGQGraph
  aclose: flush_buffers guard allows call on IOCGraph
  aclose: close guard allows call on DuckPGQGraph
  inject_graph docstring: "STORE IS NOT GRAPH TRUTH OWNER"
  graph_supports_buffered_writes: "NON-AUTHORITATIVE COMPAT CHECK"
```

### Co bylo schválně NEděláno

1. **Žádný GraphProtocol/interface** — jen diagnostické helpers
2. **Žádný nový graph abstraction layer**
3. **Žádná změna v IOCGraph ani DuckPGQGraph**
4. **Žádné generické graph API na store** — store nepřidává metody jako `flush_graph_buffers`
5. **Žádný tichý fallback** — každá větev má explicitní guard

### Debt sekce — aktualizace

**[DEBT-3] `duckdb_store._ioc_graph` schizofrenie → PARTIALLY MITIGATED**
- Původní stav: `inject_graph` acceptuje cokoliv bez capability contract
- Akce: Přidány `graph_supports_buffered_writes()` + `get_graph_attachment_kind()` + explicitní guardy
- **Stále přetrvává**: `duckdb_store._ioc_graph` stále drží DuckPGQGraph po windupu — to je mimo scope tohoto sprintu
- Uzamčení: `tests/probe_8tf/test_graph_attachment_guards.py` — 12 testů

---

## 13. Sprint 8VL — Synthesis Lifecycle Gate Truth Cleanup (2026-04-02)

### Co bylo silent mismatch

`_is_windup_allowed()` v `synthesis_runner.py` používal jako primární truth:
```python
# utils.sprint_lifecycle — COMPAT SHIM, not lifecycle authority
from ..utils.sprint_lifecycle import SprintLifecycleManager
manager = SprintLifecycleManager.get_instance()  # singleton z utils
return manager.is_windup_phase()
```

Ale canonical lifecycle truth je `runtime/sprint_lifecycle.SprintLifecycleManager` (dataclass, bez singletonu).
Utils verze je **compat shim** — 85% orchestration residue, 15% compat aliases.

Windup engine volá `synthesize_findings(force_synthesis=True)` — force flag bypassuje gate,
ale internal diagnostics stále preferovaly utils singleton.

### Co je teď explicitně řešeno

**1. Lifecycle gate truth priority (structured, auditable):**

| Priority | Path | Source label |
|---|---|---|
| 1 | Injected `_lifecycle_adapter` (windup_engine → scheduler._lc_adapter) | `"runtime"` |
| 2 | Direct runtime SprintLifecycleManager check | `"runtime"` |
| 3 | utils SprintLifecycleManager.get_instance() | `"compat"` |
| — | žádná dostupná | `"unavailable"` |

**2. Structured state in SynthesisRunner:**
- `_lifecycle_gate_source`: `"runtime"` | `"compat"` | `"unavailable"` | `"forced"`
- `_lifecycle_gate_mode`: `"windup"` | `"forced"` | `"blocked"`
- `_lifecycle_adapter`: injected `_LifecycleAdapter` instance or None

**3. windup_engine injectuje lifecycle adapter:**
```python
# windup_engine.py:136-140
runner = SynthesisRunner(ModelLifecycle())
if hasattr(scheduler, "_ioc_graph") and scheduler._ioc_graph is not None:
    runner.inject_graph(scheduler._ioc_graph)
# Sprint 8VL: Inject lifecycle adapter — PREFERRED truth path for windup gate
if hasattr(scheduler, "_lc_adapter") and scheduler._lc_adapter is not None:
    runner.inject_lifecycle_adapter(scheduler._lc_adapter)
```

**4. New method `inject_lifecycle_adapter()` in SynthesisRunner:**
```python
def inject_lifecycle_adapter(self, adapter: Any) -> None:
    """
    SPRINT 8VL: Inject runtime lifecycle adapter for windup gate.
    windup_engine passes scheduler._lc_adapter (runtime _LifecycleAdapter wrapping
    the canonical SprintLifecycleManager). This is the PREFERRED truth path.
    """
    self._lifecycle_adapter = adapter
```

### Graph capability consumption v synthesis/windup — status

| Capability | Path | Status |
|---|---|---|
| STIX export | `_build_stix_context()` → IOCGraph only | ✅ Explicitní degradation s `_stix_status/reason/backend` (Sprint 8TH) |
| GraphRAG `find_connections()` | `GraphRAGOrchestrator` → persistent layer | ✅ Graceful no-op pokud nedostupný |
| `stats()` / `get_top_nodes_by_degree()` | DuckPGQGraph only | ✅ Jediný zdroj, žádná tichá degradace |
| `export_edge_list()` | DuckPGQGraph only → GNN | ✅ Jediný zdroj, žádná tichá degradace |
| `flush_buffers()` | IOCGraph only | ✅ Guard: `callable(getattr(g, "flush_buffers", None))` |
| Buffered writes | IOCGraph only | ✅ Guard: `graph_supports_buffered_writes()` (Sprint 8TF) |

**Truth-store-only:** `export_stix_bundle()`, `buffer_ioc()`, `flush_buffers()`
**Donor/analytics-only:** `stats()`, `get_top_nodes_by_degree()`, `export_edge_list()`
**DuckPGQGraph jako donor:** negarantuje truth-store capabilities — structured degradation labeled

### Debt sekce — aktualizace

**[DEBT-1] STIX export degradován → RESOLVED (Sprint 8TH)**

**[DEBT-6] Synthesis lifecycle gate utils-singleton drift → RESOLVED (Sprint 8VL)**
- Původní stav: `_is_windup_allowed()` preferoval utils singleton jako primary truth
- Akce: 3-path priority (runtime adapter → runtime direct → utils compat), structured state attributes
- Kanonická semantika: žádná tichá volba — vždy existuje `_lifecycle_gate_source` label
- Uzamčení: `tests/probe_8vl/test_lifecycle_gate_truth.py` — probe testy

### Změněné soubory

| Soubor | Změna |
|---|---|
| `brain/synthesis_runner.py` | `__slots__` + `__init__` přidány `_lifecycle_gate_*`; nová `_is_windup_allowed` 3-path logika; nová `inject_lifecycle_adapter()` |
| `runtime/windup_engine.py` | Injektuje `scheduler._lc_adapter` do runneru |
| `GRAPH_BACKEND_RECONCILIATION.md` | Sekce 13 — Sprint 8VL výsledky |
| `tests/probe_8vl/test_lifecycle_gate_truth.py` | **NOVÝ** — probe testy |

### Co bylo schválně NEděláno

1. **Žádný nový lifecycle framework** — použit existující `_LifecycleAdapter` + `SprintLifecycleManager`
2. **Žádný nový graph framework** — žádný GraphProtocol, adapter layer
3. **Nepřidána nová lifecycle autorita** — runtime manager zůstává kanonický, utils zůstává compat shim
4. **Žádné nové background tasky** — lifecycle adapter je synchroní read-only wrapper
5. **Žádné nové cross-plane DTO** — structured state jsou instance attributes na SynthesisRunner
6. **Nepřepisoval jsem `__main__.py` lifecycle creation** — ten zůstává v režii dalšího sprintu

---

## 14. Sprint 8VQ — STIX Truth-Store-Only Capability Path (2026-04-02)

### Co bylo silent mismatch

`synthesis_runner._build_stix_context()` používal jako jedinou graph source `_ioc_graph`.
V produkčním kódu `_run_sprint_mode`:
- `store._ioc_graph` byl vždy **None** (duckdb_store.inject_graph se nikdy nevolal)
- `scheduler._ioc_graph` byl DuckPGQGraph (analytics/donor, nemá `export_stix_bundle`)
- **IOCGraph (Kuzu truth-store) se do consumer path NEDOSTAL**

Výsledek: `_build_stix_context()` vždy skončil na `unavailable` pro DuckPGQGraph, i když IOCGraph truth-store existoval odděleně.

### Co je teď explicitně řešeno

**1. Dedicated STIX graph slot v duckdb_store:**
```python
# knowledge/duckdb_store.py
self._stix_graph: Any = None  # INDEPENDENT of _ioc_graph (analytics)

def inject_stix_graph(self, graph: Any) -> None:
    """TRUTH-STORE ONLY: pouze IOCGraph (Kuzu) sem patří."""

def get_stix_graph(self) -> Any:
    """Returns injected truth-store STIX graph or None."""
```

**2. Dedicated STIX graph slot v synthesis_runner:**
```python
# brain/synthesis_runner.py __slots__
"_stix_graph"  # NEW

def inject_stix_graph(self, graph: Any) -> None:
    """TRUTH-STORE ONLY: priorita 1 pro STIX context."""
```

**3. `_build_stix_context()` — dvě priority:**
```python
# Priority 1: _stix_graph (truth-store STIX)
if self._stix_graph is not None:
    # použij truth-store IOCGraph

# Priority 2: _ioc_graph (analytics/donor fallback)
if self._ioc_graph is not None:
    # DuckPGQGraph → unavailable (nemá export_stix_bundle)
```

**4. Production wire v `__main__._run_sprint_mode`:**
```python
# Sprint 8VQ: Create IOCGraph truth-store for STIX capability.
# Vytváří se v WINDUP bloku (po ACTIVE fázi) a injektuje do store.
if store_instance is not None:
    from .knowledge.ioc_graph import IOCGraph
    ioc_graph = IOCGraph()
    await ioc_graph.initialize()
    store_instance.inject_stix_graph(ioc_graph)
```

**5. `_windup_synthesis()` — STIX priority seam:**
```python
# Priority 1: store.get_stix_graph() → runner.inject_stix_graph()
# Priority 2: store._ioc_graph → runner.inject_graph() (analytics, no STIX)
```

### Změněné soubory

| Soubor | Změna |
|---|---|
| `knowledge/duckdb_store.py` | `_stix_graph` slot, `inject_stix_graph()`, `get_stix_graph()` |
| `brain/synthesis_runner.py` | `_stix_graph` v `__slots__` + `__init__`, `inject_stix_graph()`, Priority 1 path v `_build_stix_context()` |
| `__main__.py` | WINDUP block: IOCGraph creation + `inject_stix_graph()`, `_windup_synthesis()`: STIX priority wire |
| `tests/probe_8th/test_stix_degradation_not_silent.py` | Aktualizovány testy pro Priority 1/2 path |
| `GRAPH_BACKEND_RECONCILIATION.md` | Sekce 14 — Sprint 8VQ výsledky |

### Graph consumer truth matrix (aktualizovaná)

| Consumer | Graph source | Backend | STIX capable |
|---|---|---|---|
| `_run_sprint_mode` WINDUP block | `IOCGraph()` nový | Kuzu | ✅ |
| `store.inject_stix_graph()` | IOCGraph (truth) | Kuzu | ✅ |
| `runner.inject_stix_graph()` | Priority 1 | Kuzu | ✅ |
| `_run_sprint_mode` compat | `scheduler._ioc_graph` | DuckPGQGraph | ❌ |
| `runner.inject_graph()` | Priority 2 fallback | DuckPGQGraph | ❌ (unavailable label) |
| `duckdb_store._ioc_graph` | (mimo scope) | DuckPGQGraph | ❌ |

### Co bylo schválně NEděláno

1. **Žádný nový graph framework** — pouze dedicated STIX slot, ne GraphProtocol
2. **Žádná změna DuckPGQGraph** — zůstává analytics/donor, není STIX owner
3. **Žádná změna IOCGraph** — truth-store zůstává Kuzu-only
4. **Žádná změna `duckdb_store._ioc_graph`** — ten zůstává analytics path
5. **Nepřepisoval jsem windup_engine** — ten zůstává na `scheduler._ioc_graph` (DuckPGQGraph)
6. **Žádná změna scheduler cutover** — IOCGraph v ACTIVE fázi zůstává pro pozdější sprint

### Debt sekce — aktualizace

**[DEBT-1] STIX export degradován → RESOLVED (Sprint 8VQ)**
- Původní stav: `_build_stix_context()` měl jedinou path přes `_ioc_graph`, který byl vždy DuckPGQGraph v production
- Akce: Sprint 8VQ přidává dedicated `_stix_graph` slot s Priority 1 path
- Kanonická semantika: `_stix_graph` (truth) → `_ioc_graph` (analytics fallback) → unavailable
- Uzamčení: `tests/probe_8th/test_stix_degradation_not_silent.py` — 4 testy vč. Priority 1/2 invariantů

**[DEBT-3] duckdb_store._ioc_graph schizofrenie → PARTIALLY MITIGATED (Sprint 8VQ)**
- Nový `_stix_graph` slot je INDEPENDENT of `_ioc_graph` — oddělené concernsy
- `inject_stix_graph` TRUTH-STORE ONLY contract — DuckPGQGraph sem nepatří
- Stále přetrvává: `duckdb_store._ioc_graph` je stále DuckPGQGraph path


---

## 14. Sprint 8VQ — STIX Truth-Store-Only Capability Path (2026-04-02)

### Co bylo silent mismatch

`synthesis_runner._build_stix_context()` používal jako jedinou graph source `_ioc_graph`.
V produkčním kódu `_run_sprint_mode`:
- `store._ioc_graph` byl vždy **None** (duckdb_store.inject_graph se nikdy nevolal)
- `scheduler._ioc_graph` byl DuckPGQGraph (analytics/donor, nemá `export_stix_bundle`)
- **IOCGraph (Kuzu truth-store) se do consumer path NEDOSTAL**

Výsledek: `_build_stix_context()` vždy skončil na `unavailable` pro DuckPGQGraph, i když IOCGraph truth-store existoval odděleně.

### Co je teď explicitně řešeno

**1. Dedicated STIX graph slot v duckdb_store:**
```python
# knowledge/duckdb_store.py
self._stix_graph: Any = None  # INDEPENDENT of _ioc_graph (analytics)

def inject_stix_graph(self, graph: Any) -> None:
    """TRUTH-STORE ONLY: pouze IOCGraph (Kuzu) sem patří."""

def get_stix_graph(self) -> Any:
    """Returns injected truth-store STIX graph or None."""
```

**2. Dedicated STIX graph slot v synthesis_runner:**
```python
# brain/synthesis_runner.py __slots__
"_stix_graph"  # NEW

def inject_stix_graph(self, graph: Any) -> None:
    """TRUTH-STORE ONLY: priorita 1 pro STIX context."""
```

**3. `_build_stix_context()` — dvě priority:**
```python
# Priority 1: _stix_graph (truth-store STIX)
if self._stix_graph is not None:
    # použij truth-store IOCGraph

# Priority 2: _ioc_graph (analytics/donor fallback)
if self._ioc_graph is not None:
    # DuckPGQGraph → unavailable (nemá export_stix_bundle)
```

**4. Production wire v `__main__._run_sprint_mode`:**
```python
# Sprint 8VQ: Create IOCGraph truth-store for STIX capability.
if store_instance is not None:
    from .knowledge.ioc_graph import IOCGraph
    ioc_graph = IOCGraph()
    await ioc_graph.initialize()
    store_instance.inject_stix_graph(ioc_graph)
```

### Změněné soubory

| Soubor | Změna |
|---|---|
| `knowledge/duckdb_store.py` | `_stix_graph` slot, `inject_stix_graph()`, `get_stix_graph()` |
| `brain/synthesis_runner.py` | `_stix_graph` v `__slots__` + `__init__`, `inject_stix_graph()`, Priority 1 path v `_build_stix_context()` |
| `__main__.py` | WINDUP block: IOCGraph creation + `inject_stix_graph()`, `_windup_synthesis()`: STIX priority wire |
| `tests/probe_8th/test_stix_degradation_not_silent.py` | Aktualizovány testy pro Priority 1/2 path |
| `GRAPH_BACKEND_RECONCILIATION.md` | Sekce 14 — Sprint 8VQ výsledky |

### Graph consumer truth matrix (aktualizovaná)

| Consumer | Graph source | Backend | STIX capable |
|---|---|---|---|
| `_run_sprint_mode` WINDUP block | `IOCGraph()` nový | Kuzu | ✅ |
| `store.inject_stix_graph()` | IOCGraph (truth) | Kuzu | ✅ |
| `runner.inject_stix_graph()` | Priority 1 | Kuzu | ✅ |
| `_run_sprint_mode` compat | `scheduler._ioc_graph` | DuckPGQGraph | ❌ |
| `runner.inject_graph()` | Priority 2 fallback | DuckPGQGraph | ❌ (unavailable label) |

### Co bylo schválně NEděláno

1. **Žádný nový graph framework** — pouze dedicated STIX slot, ne GraphProtocol
2. **Žádná změna DuckPGQGraph** — zůstává analytics/donor, není STIX owner
3. **Žádná změna IOCGraph** — truth-store zůstává Kuzu-only
4. **Žádná změna `duckdb_store._ioc_graph`** — ten zůstává analytics path
5. **Nepřepisoval jsem windup_engine** — ten zůstává na `scheduler._ioc_graph` (DuckPGQGraph)
6. **Žádná změna scheduler cutover** — IOCGraph v ACTIVE fázi zůstává pro pozdější sprint

### Debt sekce — aktualizace

**[DEBT-1] STIX export degradován → RESOLVED (Sprint 8VQ)**
- Původní stav: `_build_stix_context()` měl jedinou path přes `_ioc_graph`, který byl vždy DuckPGQGraph v production
- Akce: Sprint 8VQ přidává dedicated `_stix_graph` slot s Priority 1 path
- Kanonická semantika: `_stix_graph` (truth) → `_ioc_graph` (analytics fallback) → unavailable
- Uzamčení: `tests/probe_8th/test_stix_degradation_not_silent.py` — 4 testy vč. Priority 1/2 invariantů

**[DEBT-3] duckdb_store._ioc_graph schizofrenie → PARTIALLY MITIGATED (Sprint 8VQ)**
- Nový `_stix_graph` slot je INDEPENDENT of `_ioc_graph` — oddělené concernsy
- `inject_stix_graph` TRUTH-STORE ONLY contract — DuckPGQGraph sem nepatří
- Stále přetrvává: `duckdb_store._ioc_graph` je stále DuckPGQGraph path

---

## 15. Sprint 8WA — Truth-Write Graph Attachment Role Split (2026-04-02)

### Co bylo silent mismatch

`_graph_ingest_findings()` používala `self._ioc_graph` pro ACTIVE-phase buffered writes.
V produkčním kódu po windupu `_ioc_graph` drží DuckPGQGraph (analytics/donor backend),
který **nemá** `buffer_ioc`/`flush_buffers`. Výsledkem byl tichý no-op pro DuckPGQGraph path,
protože volání `buffer_ioc` na objektu bez této metody by bylo `AttributeError`.

Navíc trigger `async_ingest_findings_batch` volal `graph_supports_buffered_writes()` na
analytics `_ioc_graph` slotu — špatný slot pro pravdu o buffered-write schopnosti.

### Co je teď explicitně řešeno

**Tři dedicated graph slots v DuckDBShadowStore:**

| Slot | Účel | Kanonický backend | Capability |
|---|---|---|---|
| `_truth_write_graph` | ACTIVE-phase buffered IOC writes | IOCGraph (Kuzu) | `buffer_ioc`, `buffer_observation`, `flush_buffers` |
| `_ioc_graph` | Analytics/donor — top-n, degree, edge export | DuckPGQGraph | `get_top_nodes_by_degree`, `stats`, `export_edge_list` |
| `_stix_graph` | STIX synthesis context | IOCGraph (Kuzu) | `export_stix_bundle` |

**Dedicated truth-write seam:**

```python
# knowledge/duckdb_store.py
self._truth_write_graph: Any = None  # Sprint 8WA: NEW slot

def inject_truth_write_graph(self, graph: Any) -> None:
    """TRUTH-WRITE ONLY: pouze IOCGraph (Kuzu) sem patří."""

def get_truth_write_graph(self) -> Any:
    """Returns injected truth-write graph or None."""

def truth_write_graph_supports_buffered_writes(self) -> bool:
    """True pouze když _truth_write_graph má buffer_ioc AND flush_buffers."""
```

**_graph_ingest_findings — dedicated truth-write path:**

```python
# Sprint 8WA: používá _truth_write_graph, ne analytics _ioc_graph
if self._truth_write_graph is None:
    return  # early exit pro prázdný slot

async def _run():
    for finding in findings:
        await self._truth_write_graph.buffer_ioc(ioc_type, value, 1.0)
        await self._truth_write_graph.buffer_observation(...)
```

**async_ingest_findings_batch trigger — dedicated capability check:**

```python
# Sprint 8WA: truth_write_graph_supports_buffered_writes() místo graph_supports_buffered_writes()
if results and any(r.get("lmdb_success") for r in results) and self.truth_write_graph_supports_buffered_writes():
    self._graph_ingest_findings(findings)
```

**aclose — dva oddělené teardowny:**

```python
# Sprint 8WA: truth-write graph (IOCGraph) — flush + close
if self._truth_write_graph is not None:
    if callable(getattr(self._truth_write_graph, "flush_buffers", None)):
        await self._truth_write_graph.flush_buffers()
    if callable(getattr(self._truth_write_graph, "close", None)):
        await self._truth_write_graph.close()

# analytics/donor graph (DuckPGQGraph) — close only
if self._ioc_graph is not None:
    if callable(getattr(self._ioc_graph, "close", None)):
        await self._ioc_graph.close()
```

### Graph attachment role matrix (aktualizovaná)

| Consumer | Graph slot | Backend | Buffered writes | STIX | Analytics |
|---|---|---|---|---|---|
| `_graph_ingest_findings` | `_truth_write_graph` | IOCGraph (Kuzu) | ✅ | — | — |
| `flush_buffers()` trigger | `_truth_write_graph` | IOCGraph (Kuzu) | ✅ | — | — |
| `aclose()` teardown | `_truth_write_graph` | IOCGraph (Kuzu) | ✅ flush+close | — | — |
| `aclose()` teardown | `_ioc_graph` | DuckPGQGraph | ❌ | — | ✅ close only |
| `get_top_entities_for_ghost_global()` | `_ioc_graph` | DuckPGQGraph | ❌ | — | ✅ |
| `get_top_seed_nodes()` | `_ioc_graph` | DuckPGQGraph | ❌ | — | ✅ |
| `_build_stix_context()` Priority 1 | `_stix_graph` | IOCGraph (Kuzu) | — | ✅ | — |
| `_build_stix_context()` Priority 2 | `_ioc_graph` | DuckPGQGraph | — | ❌ (unavailable) | ✅ |

### Změněné soubory

| Soubor | Změna |
|---|---|
| `knowledge/duckdb_store.py` | `_truth_write_graph` slot, `inject_truth_write_graph()`, `get_truth_write_graph()`, `truth_write_graph_supports_buffered_writes()`, `_graph_ingest_findings` používá `_truth_write_graph`, trigger v `async_ingest_findings_batch`, aclose má dva oddělené teardowny |
| `tests/probe_8wa/test_truth_write_graph_slot.py` | **NOVÝ** — 19 probe testů |
| `GRAPH_BACKEND_RECONCILIATION.md` | Sekce 15 — Sprint 8WA výsledky |

### Co bylo schválně NEděláno

1. **Žádný nový graph framework** — pouze dedicated slot, ne GraphProtocol
2. **Žádná změna DuckPGQGraph** — zůstává analytics/donor
3. **Žádná změna IOCGraph** — truth-store zůstává Kuzu-only
4. **Nepřidán generic `get_graph()`** — každý slot má explicitní účel
5. **`get_top_seed_nodes()` a `get_top_entities_for_ghost_global()` zůstaly na analytics path** — nemigrovaly na truth-write
6. **Žádný nový produkční soubor**

### Debt sekce — aktualizace

**[DEBT-3] duckdb_store._ioc_graph schizofrenie → RESOLVED (Sprint 8WA)**
- Původní stav: `_graph_ingest_findings` používala špatný slot (`_ioc_graph`) pro buffered writes
- Akce: Sprint 8WA přidává dedicated `_truth_write_graph` slot pro ACTIVE-phase writes
- Kanonická semantika: `_truth_write_graph` (truth) → `_ioc_graph` (analytics/donor)
- Uzamčení: `tests/probe_8wa/test_truth_write_graph_slot.py` — 19 testů

**[DEBT-5] duckdb_store._ioc_graph.flush_buffers mrtvý kód → RESOLVED (Sprint 8WA)**
- Původní stav: `aclose()` volal `flush_buffers()` na `_ioc_graph` — pro DuckPGQGraph to byl mrtvý kód
- Akce: `aclose()` nyní volá `flush_buffers()` na `_truth_write_graph`, `close()` na obou
- Kanonická semantika: `_truth_write_graph` → flush+close, `_ioc_graph` → close only
- Uzamčení: `test_aclose_flushes_truth_write_graph`, `test_aclose_closes_analytics_graph_separately`

---

## 16. Attachment Role Cleanup Summary — Three-Slot Architecture

### Proč není "attachment role cleanup" graph unification

Graph unification by znamenalo sloučit tři různé graph backendy do jedné autority.
Sprint 8WA nedělá nic takového — pouze **explicitně odděluje tři existující sloty**,
každý s jasně definovanou rolí:

1. **Truth-write slot** (`_truth_write_graph`): Kuzu-backed IOCGraph pro ACTIVE-phase buffered writes
2. **Analytics/donor slot** (`_ioc_graph`): DuckDB-backed DuckPGQGraph pro top-n, degree, edge export
3. **STIX synthesis slot** (`_stix_graph`): Kuzu-backed IOCGraph pro STIX bundle export

Toto je **role cleanup, ne capability merger**. Každý slot má svůj backend a svou sadu capability.
Žádný nový generic abstraction layer nevznikl.

### Graph attachment role matrix — finální stav

| Role | Slot | Backend |Write | Read | STIX |
|---|---|---|---|---|---|
| **Truth-write** | `_truth_write_graph` | IOCGraph (Kuzu) | `buffer_ioc`, `flush_buffers` | — | — |
| **Analytics/donor** | `_ioc_graph` | DuckPGQGraph | `add_ioc` | `get_top_nodes_by_degree`, `stats`, `export_edge_list` | — |
| **STIX synthesis** | `_stix_graph` | IOCGraph (Kuzu) | — | — | `export_stix_bundle` |

### Co zůstává pro F7

1. **IOCGraph v ACTIVE fázi** — truth-write graph je vytvořen v `__main__._run_sprint_mode` WINDUP bloku,
   ale **v ACTIVE bloku se nevytváří a neinjectuje** do `_truth_write_graph`. ACTIVE fáze stále
   nemá IOCGraph pro buffered writes.
2. **DuckDBShadowStore není graph owner** — store zůstává sidecar. Graph attachment seams
   jsou consumer-facing adapters, ne authority shift.
3. **`get_top_graph_nodes()` chybí** — stále není implementovaná na store, export bere z scorecard.

---

## 17. Sprint 8VY — Shell Boundary Cleanup: Private Graph Slot Access Removed (2026-04-02)

### 1. Ptačí perspektiva: Proč je to shell boundary cleanup, ne graph rewrite

V products kódu `__main__._run_sprint_mode()` a `_windup_synthesis()` existovaly **přímé přístupy na store private sloty**:

```python
# __main__.py — COMPAT LAYER (8VI §A) — PŘÍMÝ PRIVATE-SLOT ACCESS
_compat_scheduler = getattr(store_instance, "_ioc_graph", None)  # ← private slot
if _compat_scheduler is not None:
    gs = _compat_scheduler.stats()                                # ← direct method call na private slotu
    connected = _compat_scheduler.find_connected(first_ioc, ...)  # ← direct method call na private slotu

# _windup_synthesis() — FALLBACK PŘÍMÝ PRIVATE-SLOT ACCESS
elif hasattr(store, "_ioc_graph") and store._ioc_graph is not None:  # ← private slot
    runner.inject_graph(store._ioc_graph)                           # ← direct private slot access
```

Toto **nejsou graph rewrite, unification ani nové frameworky**. Je to čistě **nahrazení direct shell accessu
s pevně danými private názvy slotů úzkými read-only seam metodami** na store objektu.

Proč to není graph rewrite:
- Počet graph slotů se nemění (3 slots: `_truth_write_graph`, `_ioc_graph`, `_stix_graph`)
- Žádný graph backend se nemění (IOCGraph, DuckPGQGraph)
- Žádný nový GraphProtocol nevzniká
- Store se nestává graph authority
- Semantika volání zůstává stejná — pouze shell access je přesměrován přes seam

### 2. Graph Shell-Boundary Matrix

| Consumer | Přístup | Slot | Seam Metoda | Semantika |
|---|---|---|---|---|
| `_run_sprint_mode` stats logging | `getattr(store, "_ioc_graph").stats()` | `_ioc_graph` | `store.get_graph_stats()` | fail-open → `{}` |
| `_run_sprint_mode` connected logging | `getattr(store, "_ioc_graph").find_connected()` | `_ioc_graph` | `store.get_connected_iocs()` | fail-open → `[]` |
| `_windup_synthesis` Priority 2 | `elif store._ioc_graph: runner.inject_graph()` | `_ioc_graph` | `store.get_analytics_graph_for_synthesis()` | explicit None check |
| Sprint 8VQ STIX Priority 1 | `store.get_stix_graph()` | `_stix_graph` | — | beze změny |
| Sprint 8TF seed nodes | `store.get_top_seed_nodes()` | `_ioc_graph` | — | beze změny |
| Sprint 8TF ghost_global | `store.get_top_entities_for_ghost_global()` | `_ioc_graph` | — | beze změny |

**Změněné řádky:**
- `__main__.py:2548-2562` — COMPAT LAYER block odstraněn, nahrazen seam voláními
- `__main__.py:2655-2658` — `elif hasattr(store, "_ioc_graph")` odstraněn, nahrazen `get_analytics_graph_for_synthesis()`

### 3. Seznam změněných souborů

| Soubor | Změna |
|---|---|
| `knowledge/duckdb_store.py` | 3 nové seam metody: `get_graph_stats()`, `get_connected_iocs()`, `get_analytics_graph_for_synthesis()` |
| `__main__.py` | Odstraněn COMPAT LAYER (8VI §A) přímý přístup na `_ioc_graph`, nahrazen seam voláními |
| `GRAPH_BACKEND_RECONCILIATION.md` | Sekce 17 — dokumentace shell boundary cleanup |

### 4. Co bylo odstraněno z live shell-private graph access

**Z `__main__._run_sprint_mode()` (řádky 2548-2562):**
```python
# REMOVED:
_compat_scheduler = getattr(store_instance, "_ioc_graph", None) if store_instance else None
if _compat_scheduler is not None:
    gs = _compat_scheduler.stats()
    ...
    connected = _compat_scheduler.find_connected(first_ioc, max_hops=2)
```

**Z `_windup_synthesis()` (řádky 2655-2658):**
```python
# REMOVED:
elif hasattr(store, "_ioc_graph") and store._ioc_graph is not None:
    runner.inject_graph(store._ioc_graph)
```

### 5. Jaké nové store-facing seams vznikly

| Seam | Účel | Návrat | Fail-open |
|---|---|---|---|
| `get_graph_stats()` | Náhrada `store._ioc_graph.stats()` | `dict {nodes, edges, pgq_active}` nebo `{}` | ✅ |
| `get_connected_iocs(ioc, max_hops)` | Náhrada `store._ioc_graph.find_connected()` | `list` nebo `[]` | ✅ |
| `get_analytics_graph_for_synthesis()` | Náhrada `store._ioc_graph` fallback v `_windup_synthesis()` | graph backend nebo `None` | ✅ explicitní None |

Všechny seams jsou:
- **Fail-open**: žádný hard fail pokud graph není dostupný
- **Read-only**: žádná write operace
- **Consumer-specific**: úzce zaměřené na konkrétní use case
- **Non-authoritative**: store仍然是 sidecar, ne graph authority

### 6. Proč store stále není graph authority

Store má seams, které **pouze delegují** na attached graph backend:
- `get_graph_stats()` → volá `DuckPGQGraph.stats()` (ne store)
- `get_connected_iocs()` → volá `DuckPGQGraph.find_connected()` (ne store)
- `get_analytics_graph_for_synthesis()` → vrací `_ioc_graph` reference (ne store data)

Store **nezná** graph schema, neimplementuje graph logiku, a neukládá graph data.
Je to stále sidecar adapter — pouze s explicitnějším, auditable rozhraním.

### 7. Co zůstává pro další F7 kroky

1. **IOCGraph v ACTIVE fázi** — viz sekce 16 / F7 krok 1
2. **`get_top_graph_nodes()`** — stále chybí na store, export bere z scorecard
3. **Shell boundary pro `DuckPGQGraph` specifická volání** — pokud nějaké existují v other modules (ne v __main__.py scope tohoto sprintu)
4. **ACTUAL sprint scheduler cutover** — COMPAT LAYER comment říká "when SprintScheduler becomes canonical" — toto je oddělený sprint
