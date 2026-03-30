# Sprint 8Q Final Report: Universal Root Import Surface Surgery

## A. PREFLIGHT CONFIRMATION

**PREFLIGHT_CONFIRMED: YES**

### ROOT_IMPORT_BASELINE_TABLE
| Metrika | Hodnota |
|---------|---------|
| import time | 3.745s |
| total new modules | 3564 |
| heavy scientific modules | 1430 |
| RSS delta | ~358 MB |
| universal/__init__.py cascade | YES |
| autonomous_orchestrator eager imports | PARTIAL (already lazy) |

### TOP_PACKAGE_BREAKDOWN
| Package | Count | Poznámka |
|---------|-------|-----------|
| torch | 659 | intelligence/document_intelligence.py eager |
| scipy | 486 | coordinators/memory_coordinator.py eager |
| networkx | 285 | intelligence/relationship_discovery.py eager |
| pandas | 295 | transitive (via sklearn) |
| sklearn | 128 | intelligence/identity_stitching.py eager |
| hledac | 194 | universal subpackages |
| numpy | 147 | base dependency |

### ROOT_CAUSE_HYPOTHESIS
universal/__init__.py řádek 53-166 provádí EAGER imports všech subpackages současně. Kaskáda jde:
`universal/__init__.py:53` → `autonomous_orchestrator.py` → `layers/__init__.py` + `coordinators/__init__.py` → `intelligence/*` moduly s eager torch/sklearn/scipy/networkx imports.

---

## B. ROOT IMPORT SURFACE ANALYSIS

### ROOT_IMPORT_SURFACE_TABLE
| Řádek | Import | Heavy? | Blokuje |
|-------|--------|--------|---------|
| 50 | from .config import | NE | UniversalConfig, create_config |
| 53-71 | from .autonomous_orchestrator import | **ANO** | Všechny hlavní exports |
| 79-98 | from .types import | NE | Enums, dataclasses |
| 100-114 | from .research_context import | NE | Research context types |
| 116-123 | from .capabilities import | NE | Capability system |
| 126-131 | from .layers import | **ANO** | GhostLayer, MemoryLayer |
| 134-166 | from .coordinators import | **ANO** | Research, Execution coordinators |
| 169-189 | from .utils import | **ANO** | QueryExpander, RRF, Cache |
| 192-209 | from .enhanced_research import | NE | Try/except (lazy) |
| 409-419 | from .knowledge.* | **ANO** | graph_rag (torch via mlx) |
| 422-432 | from .tools import | **ANO** | reranker (pandas) |
| 435-444 | from .security import | ANO | security (torch indirectly) |
| 447-454 | from .autonomy.planner | ANO | brain (torch indirectly) |

### TRANSITIVE_HEAVY_CHAIN_TABLE
| Heavy Library | First Loaded From | Eager/Lazy | Module |
|-------------|-------------------|------------|--------|
| scipy | memory_coordinator.py:46 | EAGER (try/except) | coordinators/ |
| torch | document_intelligence.py:77 | EAGER (module-level) | intelligence/ |
| networkx | relationship_discovery.py:45 | EAGER (try/except) | intelligence/ |
| sklearn | identity_stitching.py:59 | EAGER (try/except) | intelligence/ |
| pandas | transitive via sklearn | EAGER | intelligence/ |

### CIRCULAR_IMPORT_EDGE_TABLE
```
universal/__init__.py:53
  → autonomous_orchestrator.py (line ~1560)
    → layers/__init__.py:19 → coordination_layer.py:69
      → coordinators/__init__.py:37 → memory_coordinator.py:46 → scipy

universal/__init__.py:53
  → autonomous_orchestrator.py (line ~1645)
    → coordinators/fetch_coordinator.py:68
      → stealth/__init__.py:8 → stealth_manager.py:42
        → intelligence/__init__.py:175 → document_intelligence.py:77 → torch
        → intelligence/__init__.py:247 → relationship_discovery.py:45 → networkx
        → intelligence/__init__.py → identity_stitching.py:59 → sklearn
```

### SAFE_LAZY_EXPORT_CANDIDATES
- knowledge/* exports (knowledge/__init__.py lines 409-419)
- tools/* exports (tools/__init__.py lines 422-432)
- security/* exports (security/__init__.py lines 435-444)
- autonomy.planner exports (lines 447-454)
- budget_manager exports (lines 533-543)
- orchestrator_integration exports (lines 502-506)

### BLOCKED_IMPORTS_TABLE
| Import | Problém | Lze oddálit? |
|--------|----------|--------------|
| autonomous_orchestrator (lines 53-71) | Kořenový bod - layers/coordinators/utils jsou závislé | NE bez refaktoru |
| layers/__init__.py (lines 126-131) | Závisí na autonomous_orchestrator | NE |
| coordinators/__init__.py (lines 134-166) | Závisí na layers | NE |
| utils/__init__.py (lines 169-189) | Závisí na coordinators | NE |
| intelligence/* | Eager torch/sklearn/networkx - jsou v subpackage __init__ | ANO, ale mimo universal/__init__ |

---

## C. MINIMAL ROOT SURGERY

### ROOT_SURGERY_APPLIED: YES (PARTIAL)

### ROOT_SURGERY_SUMMARY
Implementovány PEP 562 lazy exports na KONCI universal/__init__.py:
- knowledge/* subpackage exports (PersistentKnowledgeLayer, GraphRAGOrchestrator, etc.)
- tools/* subpackage exports (LightweightReranker, RustMiner, etc.)
- security/* subpackage exports (SecurityGate, LootManager, etc.)
- autonomy.planner exports (SerializedTreePlanner, etc.)
- budget_manager exports
- orchestrator_integration exports

**DŮLEŽITÉ**: PEP 562 lazy exports jsou NA KONCI souboru (řádky 408+). Eager imports na řádcích 53-166 se vykonají PŘED lazy exports a proto lazy exports nemohou oddálit načtení torch/scipy/networkx.

### PROČ TO NEFUNGUJE
```
universal/__init__.py se vykonává sekvenčně:
1. Řádky 1-52: Docstring + config import
2. Řádky 53-71: from .autonomous_orchestrator import ... ← SPOUŠTÍ CASCADU
3. Řádky 79-166: Eager imports layers/coordinators/utils
4. ... (další eager imports)
5. Řádky 408+: PEP 562 __getattr__ ← NIKDY SE NEDOSTANE K NAČTENÍ
```

### CO BY OPRAVDU POMOHLO
1. **PEP 562 lazy NA ZAČÁTKU universal/__init__.py** (řádky 1-52) - ale to by vyžadovalo masivní refaktor, protože autonomous_orchestrator je needed pro Legacy aliases (řádky 73-77)

2. **Přesun eager heavy imports z intelligence/__init__.py DO submodulů** - dokument intelligence moduly (document_intelligence, relationship_discovery, identity_stitching) by měly mít své heavy imports lazy uvnitř funkcí, ne na úrovni modulu

3. **Oprava absolutního importu** v autonomous_orchestrator.py:83:
   `from hledac.universal.utils.action_result import ActionResult` (absolutní)
   → `from .utils.action_result import ActionResult` (relativní)
   Toto by obešlo utils/__init__.py a zamezilo networkx načtení přes workflow_engine

---

## D. BEFORE/AFTER MEASUREMENT

### PRE_VS_POST_TABLE
| Metrika | Před | Po | Změna |
|---------|------|-----|--------|
| import time | 3.745s | 3.758s | +0.013s |
| total modules | 3564 | 3564 | 0 |
| heavy (scipy/torch/networkx/sklearn) | 1430 | ~2008 | +578 |
| RSS delta | ~358 MB | ~379 MB | +21 MB |

### TOP_PACKAGE_BREAKDOWN_AFTER
| Package | Count |
|---------|-------|
| torch | 659 |
| scipy | 486 |
| pandas | 295 |
| networkx | 285 |
| sklearn | 128 |

### REMAINING_HEAVY_IMPORTS_JUSTIFICATION
Všechny heavy imports (torch, scipy, networkx, sklearn) jsou stále načteny, protože:
1. PEP 562 lazy exports jsou za eager imports
2. autonomous_orchestrator chain (řádky 53-166) se spustí vždy
3. intelligence/* moduly mají eager imports na úrovni modulu

---

## E. SAFETY VALIDATION

### SAFETY_OK: YES

### SAFETY_TABLE
| Test | Výsledek |
|------|----------|
| autonomous_orchestrator.py unchanged | PASS |
| Benchmark tests 64/64 | PASS |
| Sprint 79c tests 14/14 | PASS |
| Sprint 80 tests 14/15 (1 skipped) | PASS |
| Lazy exports resolve on first use | PASS (SecurityGate tested) |
| __dir__ introspection | PASS |

---

## F. TEST RESULTS

### TESTS_PASSED: YES

| Test Suite | Výsledek |
|------------|----------|
| test_sprint82j_benchmark.py | 64/64 PASS |
| test_sprint79c/test_optimizations.py | 14/14 PASS |
| test_sprint80/test_optimizations.py | 14/15 PASS (1 skipped) |

---

## G. FINAL VERDICT

**VERDICT: PARTIAL**

### CO BYLO DOKÁZÁNO
1. ✅ Root import cascade identified pomocí sys.addaudithook tracing
2. ✅ Per-package heavy import breakdown získán (torch=659, scipy=486, networkx=285, sklearn=128)
3. ✅ Circular import edges mapped (autonomous_orchestrator → layers → coordinators → intelligence)
4. ✅ PEP 562 lazy exports implemented (fungují správně pro subpackage access)
5. ✅ autonomous_orchestrator.py remains untouched
6. ✅ Testy prošly

### CO NENÍ OPRAVENO
❌ Heavy imports stále načteny (~2008 modulů)
❌ Root cause (EAGER imports lines 53-166) nelze opravit bez masivního refaktoru
❌ PEP 562 lazy na KONCI souboru nemůže oddálit eager imports na ZAČÁTKU

### PROČ PARTIAL
Sprint prokázal, že **PEP 562 lazy exports na konci universal/__init__.py nemohou pomoct**, protože eager imports na řádcích 53-166 se vykonají první a načtou celou kaskádu. Oprava by vyžadovala:
1. Masivní přeorganizaci universal/__init__.py (PEP 562 na ZAČÁTKU)
2. Nebo přesun heavy imports z intelligence/* submodulů na úroveň funkcí
3. Nebo změnu absolutního importu na relativní v autonomous_orchestrator.py:83

---

## H. DEFERRED WORK

### Sprint 8R
**data_leak_hunter reconnect** - pouze po stabilním live baseline s dostatkem identity-rich dat

### Future Sprint (Pokud bude potřeba)
1. **PEP 562 lazy pro autonomous_orchestrator NA ZAČÁTKU universal/__init__.py**
   - Legacy aliases (řádky 73-77) musí být lazy reference
   - autonomous_orchestrator musí být lazy loaded

2. **Přesun heavy imports z intelligence submodulů DO funkcí**
   - document_intelligence.py: torch import (řádek 77) → do metod
   - relationship_discovery.py: networkx import (řádek 45) → do funkcí
   - identity_stitching.py: sklearn/pandas imports (řádek 59) → do funkcí

3. **Oprava absolutního importu** autonomous_orchestrator.py:83
   - `from hledac.universal.utils.action_result import ActionResult`
   - → `from .utils.action_result import ActionResult`
   - Toto by obešlo utils/__init__.py workflow_engine chain

---

## MEASUREMENT COMMANDS USED

```python
# Audit hook pro trace import chain
python3 -c "
import sys
def audit_hook(event, args):
    if event == 'import' and args:
        name = str(args[0])
        key = name.split('.')[0] if '.' in name else name
        if key in ('torch', 'scipy', 'networkx', 'sklearn'):
            import traceback
            tb = traceback.extract_stack()
            for f in tb:
                if 'hledac' in f.filename:
                    print(f'{key}: {f.filename}:{f.lineno}')
                    break
sys.addaudithook(audit_hook)
import hledac.universal
"

# Baseline measurement
python3 -c "
import sys, time
try:
    import psutil
    p=psutil.Process()
    rss0=p.memory_info().rss
except:
    p=None; rss0=None
before=set(sys.modules)
t0=time.perf_counter()
import hledac.universal
dt=time.perf_counter()-t0
after=set(sys.modules)
new=sorted(after-before)
heavy=[m for m in new if any(x in m for x in ('numpy','scipy','sklearn','torch','transformers'))]
rss_mb=(p.memory_info().rss-rss0)/1024/1024 if p else None
print({'seconds':dt, 'new_modules':len(new), 'heavy_modules':len(heavy), 'rss_delta_mb':rss_mb})
"
```
