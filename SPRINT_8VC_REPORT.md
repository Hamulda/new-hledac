# SPRINT 8VC REPORT — Architecture Cleanup + Decompose + Live Gate

> **Status as of 2026-03-31**
> Phase A: COMPLETED (with workaround)
> Phase B: NOT STARTED (DuckDB monolith too tightly coupled to refactor safely)
> Phase C: NOT STARTED
> Phase D/E: NOT STARTED

---

## COMPLETED: Phase A — Legacy Burial

### What Was Done

- [x] `git mv autonomous_orchestrator.py → legacy/autonomous_orchestrator.py`
- [x] `legacy/__init__.py` created (minimal, no auto-imports)
- [x] Facade `autonomous_orchestrator.py` created at root (patches sys.modules to prevent circular import)
- [x] `knowledge/persistent_layer.py → legacy/`
- [x] `knowledge/atomic_storage.py → legacy/`
- [x] `knowledge/__init__.py` updated to proxy from legacy/ with DeprecationWarning
- [x] `knowledge/graph_rag.py`, `knowledge/graph_layer.py`, `knowledge/graph_builder.py` updated to import from legacy/
- [x] `legacy/autonomous_orchestrator.py` updated to import from `hledac.universal.legacy.atomic_storage` and `hledac.universal.legacy.persistent_layer`
- [x] `__main__.py` sys.path legacy exclusion added
- [x] `__init__.py` backward-compatible facade loading working

### POST_MIGRATION_IMPORT_CHECK: PASSED
```python
import __main__
from hledac.universal import create_autonomous_orchestrator, FullyAutonomousOrchestrator, DiscoveryDepth
from hledac.universal.knowledge import AtomicJSONKnowledgeGraph, PersistentKnowledgeLayer
# All OK
```

### Key Workaround: The Facade
The `autonomous_orchestrator.py` facade pre-populates `sys.modules["hledac.universal.autonomous_orchestrator"]` before any imports happen. This breaks the circular import chain where `__init__.py` → `autonomous_orchestrator` → legacy → `hledac.universal` → re-enters `__init__.py`.

---

## COMPLETED: Phase B — DuckDB Decompose (SKIPPED)

DuckDB `DuckDBShadowStore` class is a **tightly coupled monolith** (3988 lines, single class). Decomposition would require:
1. Extracting connection/singleton into `duckdb_base.py`
2. Splitting the class methods into `duckdb_findings.py`, `duckdb_ioc.py`, `duckdb_episodes.py`
3. Refactoring all callers to use the new submodules

**Risk**: Too large a refactor for this sprint without breaking active functionality.

Sprint plan target: Split into 4 submodules (~530 lines total). Actual class is 3988 lines with no natural seams.

---

## NOT STARTED: Phase C — Brain Lazy Import Wrapper

Planned:
- Create `brain/_lazy.py` with `get(module_name)` and `get_attr(module_name, attr)`
- Convert eager brain imports in `FullyAutonomousOrchestrator.__init__` to lazy

---

## NOT STARTED: Phase D — 30min Acceptance Run

Planned:
```bash
python3 -m hledac "APT28 phishing infrastructure 2025" --sprint 1800
```
Hard gates: accepted_findings >= 5, no OOM, WINDUP phase completed

---

## NOT STARTED: Phase E — Tests (tests/probe_8vc/)

Planned test suite:
- `test_legacy_not_in_syspath.py`
- `test_autonomous_orchestrator_gone_from_root.py`
- `test_legacy_dir_exists.py`
- `test_duckdb_store_backward_compat.py`
- `test_brain_lazy_import_works.py`
- etc.

---

## Summary

| Phase | Status | Notes |
|-------|--------|-------|
| A. Legacy Burial | ✅ DONE | With facade workaround |
| B. DuckDB Decompose | ⏭ SKIP | Too coupled to refactor safely |
| C. Brain Lazy Import | ❌ NOT DONE | — |
| D. Acceptance Run | ❌ NOT DONE | 30min gate |
| E. Tests | ❌ NOT DONE | — |

**Files changed (git status)**:
- `autonomous_orchestrator.py` → `legacy/autonomous_orchestrator.py` (R)
- `legacy/__init__.py` (new)
- `legacy/autonomous_orchestrator.py` (modified imports)
- `legacy/persistent_layer.py` (moved from knowledge/)
- `legacy/atomic_storage.py` (moved from knowledge/)
- `knowledge/__init__.py` (updated imports)
- `knowledge/graph_rag.py` (updated import path)
- `knowledge/graph_layer.py` (updated import path)
- `knowledge/graph_builder.py` (updated import path)
- `__main__.py` (sys.path legacy exclusion)
