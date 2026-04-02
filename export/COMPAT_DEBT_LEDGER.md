# Export Plane Compat Debt Ledger
# Sprint 8VI §A / Sprint 8VJ §C / Sprint 8VY §C
# Stav: 2026-04-02 — Entry #3 RESOLVED 8VY §C, #4 accepted

---

## Ledger Entry #1: `sprint_exporter` → `scheduler._ioc_graph` coupling

**Status: ✅ RESOLVED (Sprint 8VI) — SPRINT 8VX §B FINISH**

**Lokace:** `export/sprint_exporter.py:83-93`

**Popis:**
`sprint_exporter._generate_next_sprint_seeds()` volá `scheduler._ioc_graph.get_top_nodes_by_degree(n=5)`.
Toto předpokládá že `scheduler._ioc_graph` je DuckPGQGraph (quantum_pathfinder), ale:
- `SprintScheduler._ioc_graph` může být IOCGraph (Kuzu) v jiných execution path
- DuckPGQGraph je držen v `duckdb_store._ioc_graph` (SSOT dnes)
- `get_top_nodes_by_degree` je metoda DuckPGQGraph, ne IOCGraph

**Resolution (Sprint 8VI):**
- `export_sprint(scheduler, scorecard, sprint_id)` → `export_sprint(store, scorecard, sprint_id)`
- `scheduler` param REMOVED; data source = `scorecard["top_graph_nodes"]`
- COMPAT BRIDGE: pokud `top_graph_nodes` chybí v scorecard, fallback na `store._ioc_graph.get_top_nodes_by_degree(n=5)`

**Resolution (Sprint 8VX §B) — COMPLETE:**
- COMPAT BRIDGE přepnut z `store._ioc_graph.get_top_nodes_by_degree()` na `store.get_top_seed_nodes()`
- Store-facing seam — export consumer mluví se store API, ne graph internals
- Fail-soft chování zachováno

**Future owner:** `duckdb_store.get_top_seed_nodes()` — čisté store API bez graph internals

**Removal condition:** `duckdb_store.get_top_seed_nodes()` pokrývá všechny export use cases
NEBO `windup_engine.run_windup()` plní `scorecard["top_graph_nodes"]` ve všech pathách

---

## Ledger Entry #2: `export_sprint()` never wired to `__main__.py`

**Status: ✅ RESOLVED (Sprint 8VI)**

**Lokace:** `__main__.py:2411-2423`

**Popis:**
`export_sprint()` je definovaná, testovaná v `test_e2e_dry_run.py`, ale v produkčním `__main__.py:_run_sprint_mode()` se nikdy nevolá.
`lifecycle.request_export()` (line 2632) je called ale nemá žádného registered callback.

**Resolution (Sprint 8VI):**
- `export_sprint(store, scorecard, sprint_id)` wireován do `_print_scorecard_report()` na konci EXPORT fáze
- Volá se jako poslední krok před TEARDOWN
- Non-fatal: exception je catched a logged, nepropaguje se

**Future owner:** `__main__.py` — volání `export_sprint()` v EXPORT fázi

**Removal condition:** Až bude `export_sprint()` přesunuto do samostatného export module s lifecycle callbackem

---

## Ledger Entry #3: Inline `_render_sprint_report_markdown` dupe

**Status: ✅ RESOLVED (Sprint 8VJ §B) — Sprint 8VY §C PATH AUTHORITY FINISH**

**Lokace:**
- Old: `__main__.py:2136-2227` (inline, ~90 lines)
- New: `export/sprint_markdown_reporter.py` (canonical, pure)

**Popis:**
`__main__.py` měl hardcoded inline `_render_sprint_report_markdown()` funkci pro sprint markdown rendering.
Tato duplicita vznikla protože sprint markdown format nebyl přesunut do export plane spolu s diagnostic markdown reporterem.

**Resolution (Sprint 8VJ §B):**
- Pure rendering přesunuto do `export/sprint_markdown_reporter.py:render_sprint_markdown()`
- `__main__._render_sprint_report_markdown()` je nyní thin bridge (1-line delegation)

**Resolution (Sprint 8VY §C) — PATH AUTHORITY CLEANUP:**
- `_compute_sprint_report_path()` DELEGATES na `paths.get_sprint_report_path()` (canonical owner)
- Path computation (`~/.hledac/reports/{sprint_id}.md`) je nyní v `paths.py` — správce určen
- Shell (`__main__._export_markdown_report()`) provádí pouze orchestraci + zápis
- Sémantika cesty nikdy neměněna — pouze přesunuta na správného správce

**Co bylo přesunuto:**
- Všechny formatting helpery (`_render_research_metrics`, `_render_threat_actors`, `_render_top_findings`, `_render_source_leaderboard`, `_render_phase_timings`)
- Hlavní renderer `render_sprint_markdown()`
- Constants `_SYNTHESIS_ENGINE_LABELS`

**Co zůstává v shellu a proč:**
- `_compute_sprint_report_path()` — thin delegation seam (volá paths.get_sprint_report_path)
- `_export_markdown_report()` — orchestration + write only; ne měnit

**Canonical owner dnes:**
- Pure render: `export/sprint_markdown_reporter.py`
- Path computation: `paths.get_sprint_report_path()`
- Shell: orchestration + write only

**Removal condition:** NIKDY — shell bridge zůstává jako delegation seam; canonical renderer žije v export plane

---

## Ledger Entry #4: `_compat_scheduler` bridge in `__main__.py`

**Název:** `compat_scheduler_bridge`

**Lokace:** `__main__.py:2549`

**Popis:**
`_compat_scheduler = getattr(store_instance, "_ioc_graph", None) if store_instance else None`

Toto JE správná dnešní cesta — `store_instance._ioc_graph` drží DuckPGQGraph.
Ale toto je bridge protože budoucí cíl je: scheduler dostane store reference a nebude existovat žádný `scheduler._ioc_graph` přímý přístup.

**Future owner:** Scheduler dostane store inject a graf bude přístupný přes store API

**Removal condition:** SprintScheduler přestane mít `_ioc_graph` attribute a všechny graph operace půjdou přes `store`

---

## Ledger Entry #5: Typed ExportHandoff handoff spot (Sprint 8VJ §C)

**Status: ✅ RESOLVED 8VJ — Sprint 8VY §A producer convergence audit**

**Lokace:**
- `export/COMPAT_HANDOFF.py` — `ensure_export_handoff()` thin adapter
- `export/sprint_exporter.py` — `export_sprint(handoff: ExportHandoff | dict | None)` signatura
- `__main__.py:2340` — producer-side `ExportHandoff.from_windup(sprint_id, scorecard_data)` construction
- `types.py:1561` — `ExportHandoff.from_windup()` classmethod

**Popis:**
`export_sprint()` přijímá `ExportHandoff | dict | None` (backward compat zachováno).
Producer (`__main__`) vytváří `ExportHandoff` přes `ExportHandoff.from_windup()`.
`ensure_export_handoff()` normalizuje libovolný vstup na typed `ExportHandoff`.

**Canonical producer-side handoff truth (Sprint 8VY):**
`__main__._print_scorecard_report()` → `ExportHandoff.from_windup(sprint_id, scorecard_data)`
TOTO JE dnes canonical producer construction — ne __main__ → dict → ensure.

**Two chained compat seams remaining:**
  1. `windup_engine.run_windup()` → `scorecard["top_graph_nodes"]` dict (windup writes graph nodes)
  2. `scorecard["top_graph_nodes"]` → `ExportHandoff.top_nodes` (from_windup extraction)

**Removal conditions (Sprint 8VY §A — explicitní):**
  1. `from_windup(scorecard)` dict path → REMOVAL when windup_engine returns typed ExportHandoff directly
  2. `ensure_export_handoff(None)` → REMOVAL when __main__ always passes typed ExportHandoff (never None)
  3. `scorecard["top_graph_nodes"]` compat seam → REMOVAL when windup_engine fills `ExportHandoff.top_nodes` directly
  4. `store.get_top_seed_nodes()` fallback in `export_sprint()` → REMOVAL when `ExportHandoff.top_nodes` always populated

**Future owner:** Windup engine — až vrátí přímo `ExportHandoff`, `from_windup(scorecard)` se stane nepotřebným

**What this module is NOT (Sprint 8VY):**
  - NOT a new DTO system — `ExportHandoff` (types.py) is the only typed handoff
  - NOT growing — new features go to windup_engine or types.py, not here
  - NOT a producer factory — __main__ constructs via `from_windup()`, not via this module

---

## Ledger Entry #6: ghost_global entity export — direct graph spelunking removed

**Status: ✅ RESOLVED Sprint 8TF**

**Lokace:**
- Old: `__main__.py:2311-2333` — direct `store._ioc_graph.get_nodes()[:100]`
- New: `__main__.py` — `store.get_top_entities_for_ghost_global()`
- Store method: `knowledge/duckdb_store.py` — `get_top_entities_for_ghost_global(n=100)`

**Popis:**
`__main__.py:_print_scorecard_report()` obsahoval přímé graph spelunking pro ghost_global upsert:
```python
graph = store._ioc_graph
if graph is not None and hasattr(graph, "get_nodes"):
    nodes = graph.get_nodes()[:100]  # top 100  ← NIKDY NEEXISTOVALO
```
Metoda `get_nodes()` **neexistuje** na žádném graph backendu (IOCGraph ani DuckPGQGraph).
Kód vždy tiše failoval — ghost_global entity export byl vždy mrtvý.

**Resolution (Sprint 8TF):**
- Přímé graph spelunking **ODSTRANĚNO** z `__main__.py`
- **NOVÝ STORE SEAM:** `duckdb_store.get_top_entities_for_ghost_global(n=100)`
  - Read-only, fail-soft, vrací `list[tuple[str, str, float]]` — přesný shape pro `upsert_global_entities()`
  - Interně volá `_ioc_graph.get_top_nodes_by_degree(n=100)` — správná capability
  - DuckDBShadowStore zůstává **SIDE CAR**, není graph truth owner
- `__main__.py` nyní volá store seam místo graph internals

**STORE IS NOT GRAPH TRUTH OWNER:**
`get_top_entities_for_ghost_global()` je thin read-only adapter. Truth owner zůstává:
- `DuckPGQGraph.get_top_nodes_by_degree(n)` — jediný backend s touto capability

**Future owner:** IOCGraph — až bude mít `get_top_nodes_by_degree(n)` implementaci, helper zmizí

**Removal condition:** IOCGraph pokryje tuto capability a `duckdb_store.get_top_entities_for_ghost_global()` nebude potřeba

---

## Summary Table

| Entry | Debt | Severity | Status | Next Step |
|-------|------|----------|--------|-----------|
| #1 | `sprint_exporter` → `scheduler._ioc_graph` | HIGH | ✅ RESOLVED 8VI | `duckdb_store.get_top_seed_nodes()` |
| #2 | `export_sprint()` not wired | HIGH | ✅ RESOLVED 8VI | Lifecycle callback (future) |
| #3 | Inline `_render_sprint_report_markdown` dupe | MED | ✅ RESOLVED 8VJ §B | Canonical renderer in sprint_markdown_reporter.py |
| #4 | `_compat_scheduler` bridge | LOW | accepted | Store-first arch — sleduj SprintScheduler cutover |
| #5 | Typed ExportHandoff handoff spot | MED | ✅ RESOLVED 8VJ §C | Windup engine → ExportHandoff (future) |
| #6 | ghost_global direct graph spelunking | HIGH | ✅ RESOLVED 8TF | IOCGraph `get_top_nodes_by_degree()` (future) |

**Sprint 8VJ §B uzavřeno:** Entry #3 — sprint markdown rendering přesunuto do `export/sprint_markdown_reporter.py`. Shell zůstává thin bridge pro path computation a orchestration.

---

## Co je PLYŠE clean dnes

| Komponenta | Status | Poznámka |
|------------|--------|----------|
| `export/markdown_reporter.py` | ✅ READY | Pure function, side-effect-free |
| `export/jsonld_exporter.py` | ✅ READY | Pure function, side-effect-free |
| `export/stix_exporter.py` | ✅ READY | Pure function, side-effect-free |
| `export/__init__.py` | ✅ OK | Správně re-exportuje všechny public funkce |
| `export/sprint_exporter.py` | ✅ WIRED | `export_sprint(store, scorecard, sprint_id)` voláno z `_print_scorecard_report()` |

---

## Další krok po této fázi

**Fáze 3: Canonical seed export API**
1. Přidej `duckdb_store.get_top_seed_nodes(n=5)` — čisté store API pro top nodes
2. Odstraň COMPAT BRIDGE z `export_sprint()` (store._ioc_graph fallback)
3. Zvaž lifecycle callback pro export místo přímého volání v `_print_scorecard_report()`
