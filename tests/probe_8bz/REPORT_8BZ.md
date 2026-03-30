# SPRINT 8BZ — BOOTSTRAP & ENTRYPOINT AUDIT REPORT

**Datum:** 2026-03-24
**Probe workspace:** `tests/probe_8bz/`

---

## EXECUTIVE SUMMARY

| Komponenta | Status | Detail |
|------------|--------|--------|
| `__main__.py` | ❌ **NEEXISTUJE** | Není entry point |
| `uvloop.install()` | ❌ **0 volání** | Nikdy není instalován |
| `thermal.py` v `utils/` | ❌ **NEEXISTUJE** | Samostatný thermal monitor není vytvořen |
| Cleanup handlers | ✅ `atexit` + signal | Registrovány v initialize() |
| Config loading | ✅ Env + dataclass | `UniversalConfig.from_env()` |

**Závěr:** `uvloop.install()` a thermal monitoring je třeba přidat do `initialize()` nebo vytvořit `__main__.py`.

---

## STEP 1 — ENTRY POINT ANALYSIS

### Console Scripts
```bash
$ grep -r "console_scripts\|entry_points" hledac/universal/ --include="*.toml"
# ŽÁDNÝ VÝSLEDEK
```

**`pyproject.toml` s console_scripts NEEXISTUJE.**

### `if __name__ == '__main__'`
V projektu existuje mnoho `if __name__ == '__main__'` bloků, ale **žádný není hlavní entry point orchestrátoru**:

| Soubor | Účel |
|--------|------|
| `utils/validation.py` | Test validace |
| `utils/execution_optimizer.py` | Benchmark |
| `security/self_healing.py` | Self-healing test |
| `run_comprehensive_tests.py` | Test runner |
| `benchmarks/run_sprint82j_benchmark.py` | Benchmark |
| `tests/*.py` | Různé testy |

**Žádný z nich není `autonomous_orchestrator.py`!**

### Způsob spuštění
Bez `__main__.py` a console_scripts se orchestrátor spouští **přímým importem**:
```python
from hledac.universal import AutonomousOrchestrator
orchestrator = AutonomousOrchestrator(config)
asyncio.run(orchestrator.initialize())
```

---

## STEP 2 — INITIALIZE() SEQUENCE (autonomous_orchestrator.py)

### Kompletní pořadí kroků v `async def initialize() -> bool`:

```
1.  MLX Metal memory limit (6GB)
    ├── mx.set_memory_limit(6 * 1024**3)
    └── var: hasattr guard pro mx.metal API

2.  Lazy module loading
    ├── Light moduly paralelně (transformers, pd)
    └── Heavy moduly sekvenčně (mlx_lm, torch)
    └── gc.collect() po všech importech

3.  Boot hygiene (Sprint 8AJ)
    ├── assert_ramdisk_alive()
    ├── FD baseline telemetry (nofile, rss_mb)
    ├── Count artifacts outside ramdisk
    ├── cleanup_stale_lmdb_locks()
    ├── cleanup_stale_sockets()
    └── atexit.register(_cleanup_fallback)
        └── cleanup_fallback_artifacts() on exit

4.  _initialize_coordinators()
    └── Vytváří fetch_coordinator, communication_layer, atd.

5.  _init_layers()
    └── Inicializuje LayerManager a všechny layery

6.  _memory_mgr.initialize()
7.  _brain_mgr.initialize()
8.  _security_mgr.initialize()
9.  _forensics_mgr.initialize()
10. _tool_mgr.initialize()
11. _research_mgr.initialize()

12. SourceBandit (Sprint 34)
    └── UCB1 bandit pro source selection

13. OSINTFrameworkRunner (Sprint 46)
    └── theHarvester, Sherlock, Maigret wrappers

14. DarknetConnector (Sprint 46)
    └── Tor/I2P support

15. VisionEncoder (Sprint 62)
    └── Multimodal ANE encoder

16. Fusion model (Sprint 62)
    └── MobileCLIPFusion nebo MambaFusion

17. DHT components (Sprint 62)
    ├── KeyManager
    ├── LocalGraphStore
    ├── KademliaNode
    └── SketchExchange

18. TotIntegrationLayer
    └──复杂度 analyzer + ToT wrapper
```

---

## STEP 3 — CONFIG LOADING

### UniversalConfig.from_env()
```python
# V config.py (řádek 465-497)
HLEDAC_RESEARCH_MODE      # quick, standard, deep, extreme, autonomous
HLEDAC_MEMORY_LIMIT_MB    # float
HLEDAC_MAX_STEPS          # int
HLEDAC_LOG_LEVEL          # DEBUG, INFO, WARNING, ERROR
HLEDAC_M1_OPTIMIZED       # true/false
```

### UniversalConfig.for_mode()
```python
# V config.py (řádek 393-429)
QUICK       → max_steps=5, max_time=5min
STANDARD    → max_steps=20, max_time=30min
DEEP        → max_steps=50, max_time=120min
EXTREME     → max_steps=100, max_time=480min
AUTONOMOUS  → max_steps=200, max_time=1440min
```

### M1Presets (config.py řádek 36-56)
```python
MEMORY_LIMIT_MB = 5500.0
THERMAL_THRESHOLD_C = 85.0
HERMES_MODEL = "mlx-community/Hermes-3-Llama-3.2-3B-4bit"
MAX_CONCURRENT_AGENTS = 6
AGENT_TIMEOUT_SECONDS = 25.0
```

---

## STEP 4 — CLEANUP HANDLERS

### Atexit Handlers

| Handler | Registrován | Funkce |
|---------|-------------|--------|
| `_cleanup_fallback()` | `initialize()` řádek 11512 | `cleanup_fallback_artifacts()` |
| `_flush_iteration_trace()` | `_register_trace_atexit()` | Flush trace na exit |

```python
# initialize() řádek 11506-11512
if not RAMDISK_ACTIVE:
    import atexit
    def _cleanup_fallback():
        from hledac.universal.paths import cleanup_fallback_artifacts
        cleanup_fallback_artifacts()
    atexit.register(_cleanup_fallback)

# _register_trace_atexit() řádek 5106-5109
def _register_trace_atexit(self) -> None:
    atexit.register(self._flush_iteration_trace)
```

### Signal Handlers
```bash
# V run_comprehensive_tests.py (test runner)
signal.signal(signal.SIGINT, self._signal_handler)
signal.signal(signal.SIGTERM, self._signal_handler)
```
**V autonomous_orchestrator.py nejsou žádné signal handlery.**

---

## STEP 5 — UVLOOP STATUS

```bash
# grep -ri "uvloop" hledac/universal/ --include="*.py"
# VÝSLEDEK: 0 volání uvloop.install()
```

**`uvloop` je v dependencies** (`requirements.txt` nebo `pyproject.toml` uvloop), ale **nikdy není instalován**.

### Problém
Bez `uvloop.install()` běží na standardním `asyncio.SelectorEventLoop`, což je **2-3× pomalejší** než uvloop na macOS/Linux.

---

## STEP 6 — THERMAL MONITORING

### Current State
- `thermal_threshold_c = 85.0` definováno v `M1Presets` (config.py)
- **Žádný thermal monitor v kódu neexistuje**
- `enable_thermal_management: bool = True` v `UniversalConfig` (config.py řádek 284)

### Missing
- `utils/thermal.py` — **NEEXISTUJE**
- Žádná thermal check v `ResourceGovernor`
- Žádná thermal-aware akce v `initialize()`

---

## STEP 7 — RECOMMENDATIONS

### A. uvloop.install() — KAM PŘIDAT

**Option 1: Do initialize() (řádek 11419)**
```python
async def initialize(self) -> bool:
    """Inicializuje všechny komponenty."""
    # ⚡ UVLOOP MUST BE FIRST — before any async code
    try:
        import uvloop
        uvloop.install()
        logger.info("✅ uvloop installed")
    except ImportError:
        logger.warning("⚠️ uvloop not available, using default asyncio loop")

    # pak zbytek initialize...
```

**Option 2: Create `__main__.py` (DOPORUČENO)**
```python
# hledac/universal/__main__.py
if __name__ == "__main__":
    import uvloop
    uvloop.install()  # ⚡ MUST BE FIRST LINE

    import asyncio
    from hledac.universal import AutonomousOrchestrator
    from hledac.universal.config import UniversalConfig

    async def main():
        config = UniversalConfig.from_env()
        orch = AutonomousOrchestrator(config)
        await orch.initialize()
        # ... run research

    asyncio.run(main())
```

### B. Thermal Monitor — KAM PŘIDAT

**Option 1: Samostatný `utils/thermal.py`**
```python
# utils/thermal.py
import asyncio
import logging
import psutil

logger = logging.getLogger(__name__)

class ThermalMonitor:
    def __init__(self, threshold_c: float = 85.0, interval: float = 5.0):
        self.threshold_c = threshold_c
        self.interval = interval
        self._running = False

    async def start(self):
        """Start background thermal monitoring."""
        self._running = True
        while self._running:
            temp = self._read_thermal()
            if temp > self.threshold_c:
                logger.warning(f"🔥 Thermal threshold exceeded: {temp}°C")
                # Trigger throttling
                await self._trigger_throttle()
            await asyncio.sleep(self.interval)

    def stop(self):
        self._running = False

    def _read_thermal(self) -> float:
        # macOS: thermal from powermetrics or IOKit
        # Linux: /sys/class/thermal/thermal_zone0/temp
        return 0.0  # placeholder

    async def _trigger_throttle(self):
        # Notify ResourceGovernor to throttle
        pass
```

**Option 2: Integrace do ResourceGovernor**
```python
# V autonomous_orchestrator.py initialize()
# Po _memory_mgr.initialize()
try:
    from .utils.thermal import ThermalMonitor
    self._thermal_monitor = ThermalMonitor(
        threshold_c=self.config.memory.thermal_threshold_c,
        interval=5.0
    )
    asyncio.create_task(self._thermal_monitor.start())
    logger.info("✅ ThermalMonitor started")
except ImportError:
    logger.warning("⚠️ ThermalMonitor not available")
```

### C. Inject Points Summary

| Komponenta | Inject Point | Akce |
|------------|--------------|------|
| uvloop | `initialize()` řádek 11419 | Přidat `uvloop.install()` na začátek |
| Thermal | `initialize()` po řádku 11530 | Přidat `ThermalMonitor` background task |
| Cleanup | `_register_trace_atexit()` | Už existuje ✅ |
| Boot hygiene | `_cleanup_fallback()` | Už existuje ✅ |

---

## STEP 8 — BOOT SEQUENCE MAP

```
┌─────────────────────────────────────────────────────────────┐
│  ENTRY POINT (brak __main__.py)                            │
│  ↓                                                          │
│  User imports and calls:                                    │
│  asyncio.run(orchestrator.initialize())                     │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  async initialize()                                         │
│  1. MLX Metal memory limit (6GB)          [line 11421]     │
│  2. Lazy module loading (parallel/seq)    [line 11435]     │
│  3. gc.collect()                          [line 11452]     │
│  4. Boot hygiene (LMDB/socket cleanup)   [line 11457]     │
│     ⚠️ atexit.register(_cleanup_fallback)                  │
│  5. _initialize_coordinators()            [line 11522]     │
│  6. _init_layers()                        [line 11525]     │
│  7. _memory_mgr.initialize()              [line 11530]     │
│  8. _brain_mgr.initialize()               [line 11531]     │
│  9. _security_mgr.initialize()            [line 11532]     │
│  10. _forensics_mgr.initialize()          [line 11534]     │
│  11. _tool_mgr.initialize()               [line 11535]     │
│  12. _research_mgr.initialize()           [line 11536]     │
│  13. SourceBandit                         [line 11539]     │
│  14. OSINTFrameworkRunner                 [line 11547]     │
│  15. DarknetConnector                     [line 11554]     │
│  16. VisionEncoder                        [line 11562]     │
│  17. Fusion model                         [line 11573]     │
│  18. DHT components                       [line 11585]     │
│  19. TotIntegrationLayer                  [line 11609]     │
│  20. _register_trace_atexit()             [line 13864]     │
└─────────────────────────────────────────────────────────────┘
```

---

## FINAL DELTA

| Akce | Soubor | Řádek | Priorita |
|------|--------|-------|----------|
| Přidat `uvloop.install()` | `autonomous_orchestrator.py` | 11419 | 🔴 HIGH |
| Vytvořit `utils/thermal.py` | `utils/thermal.py` | — | 🔴 HIGH |
| Integrvat ThermalMonitor | `autonomous_orchestrator.py` | 11537 | 🟡 MEDIUM |
| Vytvořit `__main__.py` | `__main__.py` | — | 🟢 LOW (best practice) |
