# Export Plane Compat Debt Ledger
# Sprint 8VI §A / Sprint 8VJ §C
# Stav: 2026-04-01 — Entry #1, #2 vyřešeny, #3 pending, #4 accepted

---

## Ledger Entry #1: `sprint_exporter` → `scheduler._ioc_graph` coupling

**Status: ✅ RESOLVED (Sprint 8VI)**

**Lokace:** `export/sprint_exporter.py:21`

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

**Future owner:** `duckdb_store.get_top_seed_nodes()` — čisté store API bez graph internals

**Removal condition:** `duckdb_store.get_top_nodes(n=5)` pokrývá všechny export use cases
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

**Status: ✅ RESOLVED (Sprint 8VJ §B)**

**Lokace:**
- Old: `__main__.py:2136-2227` (inline, ~90 lines)
- New: `export/sprint_markdown_reporter.py` (canonical, pure)

**Popis:**
`__main__.py` měl hardcoded inline `_render_sprint_report_markdown()` funkci pro sprint markdown rendering.
Tato duplicita vznikla protože sprint markdown format nebyl přesunut do export plane spolu s diagnostic markdown reporterem.

**Resolution (Sprint 8VJ §B):**
- Pure rendering přesunuto do `export/sprint_markdown_reporter.py:render_sprint_markdown()`
- `__main__._render_sprint_report_markdown()` je nyní thin bridge (1-line delegation)
- Path computation (`_compute_sprint_report_path`) zůstává v shellu — sémantika `~/.hledac/reports/{sprint_id}.md` nikdy neměněna
- File write (`_export_markdown_report`) zůstává v shellu — orchestrace zůstává tam kde je bezpečnější

**Co bylo přesunuto:**
- Všechny formatting helpery (`_render_research_metrics`, `_render_threat_actors`, `_render_top_findings`, `_render_source_leaderboard`, `_render_phase_timings`)
- Hlavní renderer `render_sprint_markdown()`
- Constants `_SYNTHESIS_ENGINE_LABELS`

**Co zůstává v shellu a proč:**
- `_compute_sprint_report_path()` — path computation; změna by nesla riziko driftu path sémantiky
- `_export_markdown_report()` — orchestration + write; bezpečnější neměnit

**Future owner:** `export/sprint_markdown_reporter.py` je canonical — další sprint markdown změny jdou tam

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

**Status: ✅ RESOLVED 8VJ**

**Lokace:**
- `export/COMPAT_HANDOFF.py` — `ensure_export_handoff()` adapter
- `export/sprint_exporter.py` — `export_sprint(handoff: ExportHandoff | dict | None)` signatura
- `__main__.py:2419` — producer-side `ExportHandoff.from_windup()` construction

**Popis:**
`export_sprint()` dosud přijímal raw `dict` (scorecard). Nově:
- Přijímá `ExportHandoff | dict | None` (backward compat zachováno)
- Producer (`__main__`) vytváří `ExportHandoff` přes `ExportHandoff.from_windup()`
- `ensure_export_handoff()` normalizuje libovolný vstup na typed `ExportHandoff`
- Path semantics beze změny — `scorecard["top_graph_nodes"]` zůstává compat seam

**CO ZŮSTÁVÁ DOČASNÉ:**
- `ExportHandoff.from_windup()` extrahuje z `scorecard["top_graph_nodes"]` — toto je dočasný seam
- Windup engine zatím nevrací přímo `ExportHandoff`

**Future owner:** Windup engine — až vrátí přímo `ExportHandoff`, adapter zmizí

**Removal condition:** Windup phase vrátí `ExportHandoff` místo `scorecard` dict

---

## Summary Table

| Entry | Debt | Severity | Status | Next Step |
|-------|------|----------|--------|-----------|
| #1 | `sprint_exporter` → `scheduler._ioc_graph` | HIGH | ✅ RESOLVED 8VI | `duckdb_store.get_top_seed_nodes()` |
| #2 | `export_sprint()` not wired | HIGH | ✅ RESOLVED 8VI | Lifecycle callback (future) |
| #3 | Inline `_render_sprint_report_markdown` dupe | MED | ✅ RESOLVED 8VJ §B | Canonical renderer in sprint_markdown_reporter.py |
| #4 | `_compat_scheduler` bridge | LOW | accepted | Store-first arch — sleduj SprintScheduler cutover |
| #5 | Typed ExportHandoff handoff spot | MED | ✅ RESOLVED 8VJ §C | Windup engine → ExportHandoff (future) |

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
