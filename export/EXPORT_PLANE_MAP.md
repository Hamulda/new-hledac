# Export Plane Map
# Sprint 8VJ §B
# Stav: 2026-04-01

---

## Dva exportní plány

### 1. Diagnostics Plane ✅ READY (pure, stateless)

**Moduly:** `markdown_reporter.py`, `jsonld_exporter.py`, `stix_exporter.py`

| Vlastnost | Hodnota |
|-----------|---------|
| Typ | Pure function, side-effect-free |
| Vstup | `ObservedRunReport` (msgspec.Struct) nebo `Mapping` |
| Výstup | Deterministic string/dict |
| Závislost na scheduler | None |
| Závislost na store | None |
| Voláno z `__main__.py` | ❌ NOT WIRED |
| Vystupní path | `paths.RAMDISK_ROOT / "runs"` |

**Hlavní funkce:**
- `render_diagnostic_markdown(report)` → `str`
- `render_diagnostic_markdown_to_path(report, path=None)` → `Path`
- `render_jsonld(report)` → `dict`
- `render_jsonld_to_path(report, path=None)` → `Path`
- `render_stix_bundle(report)` → `dict`
- `render_stix_bundle_to_path(report, path=None)` → `Path`

---

### 2. Sprint Export / Next-Sprint Handoff Plane ✅ WIRED

**Modul:** `sprint_exporter.py`

| Vlastnost | Hodnota |
|-----------|---------|
| Typ | Async function, side-effect-full (writes files) |
| Vstup | `store`, `ExportHandoff | dict`, `sprint_id` |
| Výstup | `{"report_json": path, "seeds_json": path}` |
| Závislost na scheduler | ✅ None — data z ExportHandoff.top_nodes |
| Závislost na store | Fallback graph access only |
| Voláno z `__main__.py` | ✅ WIRED — voláno z `_print_scorecard_report()` |
| Test coverage | ✅ `test_e2e_dry_run.py` |

**Komponenty:**
- `export_sprint(store, handoff, sprint_id)` — hlavní async export
- `_generate_next_sprint_seeds(top_nodes, sprint_id, output_dir)` — seed tasky pro příští sprint
- `_make_serializable(obj)` — utilita

---

### 3. Sprint Markdown Renderer Plane ✅ DELEGATED

**Modul:** `sprint_markdown_reporter.py` (Sprint 8VJ §B — new)

| Vlastnost | Hodnota |
|-----------|---------|
| Typ | Pure function, side-effect-free |
| Vstup | `report`, `scorecard: dict`, `sprint_id: str` |
| Výstup | Deterministic markdown `str` |
| Závislost na scheduler | None |
| Závislost na store | None |
| Voláno z `__main__.py` | ✅ DELEGATED — `__main__._render_sprint_report_markdown()` volá canonical |
| Vystupní path | Shell concern — `~/.hledac/reports/{sprint_id}.md` |

**Hlavní funkce:**
- `render_sprint_markdown(report, scorecard, sprint_id)` → `str`

**Canonical renderer:** `export/sprint_markdown_reporter.py`
**Shell delegace:** `__main__._render_sprint_report_markdown()` — thin bridge

---

## Path Authority

| Use | Authority | Status |
|-----|-----------|--------|
| Diagnostic export output | `paths.RAMDISK_ROOT / "runs"` | ✅ SSOT v markdown_reporter |
| Sprint report (markdown) | `~/.hledac/reports/{sprint_id}.md` | ✅ Shell — path computation + write v __main__.py |
| Sprint report JSON | `~/.hledac/reports/{sprint_id}_report.json` | ✅ sprint_exporter.py |
| Sprint next-seeds JSON | `~/.hledac/reports/{sprint_id}_next_seeds.json` | ✅ sprint_exporter.py |

---

## Entry Points in `__main__.py`

```
WINDUP
  └─ _windup_synthesis() → report
  └─ _print_scorecard_report() → scorecard_data
       ├─ store.upsert_scorecard() ✅
       ├─ store.upsert_episode() ✅
       ├─ _export_markdown_report() ✅ DELEGATED → render_sprint_markdown()
       │    ├─ path computation (shell) ✅
       │    └─ file write (shell) ✅
       ├─ export_sprint(store, handoff) ✅ WIRED
       └─ store._ioc_graph.get_nodes() ✅ (správná cesta)
```

---

## Compat Handoffs (debt ledger entries)

viz `COMPAT_DEBT_LEDGER.md`

| Entry | Debt | Severity | Status |
|-------|------|----------|--------|
| #1 | `sprint_exporter` → `scheduler._ioc_graph` | HIGH | ✅ RESOLVED 8VI |
| #2 | `export_sprint()` not wired | HIGH | ✅ RESOLVED 8VI |
| #3 | Inline `_render_sprint_report_markdown` dupe | MED | ✅ RESOLVED 8VJ §B |
| #4 | `_compat_scheduler` bridge | LOW | accepted |
| #5 | Typed ExportHandoff handoff spot | MED | ✅ RESOLVED 8VJ §C |

---

## Co je clean dnes

| Komponenta | Status |
|------------|--------|
| `export/__init__.py` | ✅ Správně re-exportuje |
| `export/markdown_reporter.py` | ✅ READY — pure, side-effect-free |
| `export/jsonld_exporter.py` | ✅ READY — pure, side-effect-free |
| `export/stix_exporter.py` | ✅ READY — pure, side-effect-free |
| `export/sprint_markdown_reporter.py` | ✅ NEW — canonical sprint markdown renderer |
| `export/sprint_exporter.py` | ✅ WIRED — JSON + seeds export |
| `paths.py` RAMDISK_ROOT/RAMDISK_ACTIVE | ✅ Path authority SSOT |

---

## Další krok (Fáze 3)

1. Přidej `duckdb_store.get_top_seed_nodes(n=5)` — čisté store API pro top nodes
2. Odstraň COMPAT BRIDGE z `export_sprint()` (store._ioc_graph fallback)
3. Zvaž lifecycle callback pro export místo přímého volání v `_print_scorecard_report()`
