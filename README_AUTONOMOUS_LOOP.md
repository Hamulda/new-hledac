# Autonomous Loop Architecture

## Overview

Hermes-driven ReAct tool loop pro autonomní výzkum na M1 8GB.

Architektura implementuje iterativní cyklus myšlení a jednání (Reasoning + Acting) kde Hermes-3 LLM generuje strukturované plány, které orchestrátor provádí, sleduje výsledky a rozhoduje o dalších krocích.

## Architecture

### ReAct Loop

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           REACT LOOP                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐                 │
│   │  PLAN   │───▶│   ACT   │───▶│ OBSERVE │───▶│ DECIDE  │──┐             │
│   └─────────┘    └─────────┘    └─────────┘    └─────────┘  │             │
│        ▲                                                    │             │
│        │                                                    │             │
│        └────────────────────────────────────────────────────┘             │
│                              (repeat or break)                            │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────┐              │
│   │  SYNTHESIZE (final phase when stop conditions met)      │              │
│   └─────────────────────────────────────────────────────────┘              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Fáze smyčky

1. **PLAN** - Hermes analyzuje dotaz a generuje `ToolPlan` (JSON)
2. **ACT** - Orchestrátor validuje a spouští tooly sekvenčně
3. **OBSERVE** - Výsledky se ukládají do `EvidenceLog`
4. **DECIDE** - Hermes dostává shrnutou evidence, rozhoduje o pokračování
5. **SYNTHESIZE** - Finální syntéza všech zjištění do reportu

### Komponenty

| Komponenta | Soubor | Účel |
|------------|--------|------|
| **ReActOrchestrator** | `react/react_orchestrator.py` | Hlavní orchestrátor řídící smyčku |
| **ToolRegistry** | `tool_registry.py` | Registr nástrojů se schématy a cost modelem |
| **EvidenceLog** | `react/evidence_log.py` | Append-only log evidence |
| **ResearchContext** | `research_context.py` | Stav běhu výzkumu |
| **BudgetManager** | `budget_manager.py` | Stop conditions a rozpočty |
| **Hermes3Engine** | `brain/hermes3_engine.py` | LLM engine pro rozhodování |

### Data Flow

```
User Query
    │
    ▼
┌─────────────────┐
│  Hermes PLAN    │◄──────┐
│  Generate       │       │
│  ToolPlan       │       │
└────────┬────────┘       │
         │                │
         ▼                │
┌─────────────────┐       │
│  Validation     │       │
│  (Pydantic)     │       │
└────────┬────────┘       │
         │                │
         ▼                │
┌─────────────────┐       │
│  Tool Execution │       │
│  (ACT phase)    │       │
└────────┬────────┘       │
         │                │
         ▼                │
┌─────────────────┐       │
│  EvidenceLog    │───────┘
│  (append-only)  │  Evidence Summary
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Hermes DECIDE  │
│  Continue?      │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌───────┐  ┌──────────┐
│  Yes  │  │    No    │
│(loop) │  │(synthesize)
└───┬───┘  └────┬─────┘
    │           │
    └─────┐     │
          ▼     ▼
┌──────────────────────┐
│     SYNTHESIZE       │
│  Generate Report     │
└──────────────────────┘
```

## Tool Registry

### Definice toolu

```python
from pydantic import BaseModel, Field
from hledac.universal.tool_registry import Tool, CostModel, RateLimits, RiskLevel

# Definice schématu argumentů
class WebSearchArgs(BaseModel):
    query: str = Field(description="Vyhledávací dotaz")
    max_results: int = Field(default=10, ge=1, le=50)
    source: str = Field(default="google", pattern="^(google|bing|duckduckgo)$")

# Definice schématu návratové hodnoty
class WebSearchResult(BaseModel):
    urls: list[str]
    titles: list[str]
    snippets: list[str]
    total_found: int

# Registrace toolu
tool = Tool(
    name="web_search",
    description="Vyhledávání na webu pomocí vyhledávače",
    args_schema=WebSearchArgs,
    returns_schema=WebSearchResult,
    cost_model=CostModel(
        ram_mb_est=50,
        time_ms_est=2000,
        network=True,
        risk_level=RiskLevel.LOW
    ),
    rate_limits=RateLimits(
        max_calls_per_run=50,
        max_parallel=3
    ),
    handler=web_search_handler
)

registry = ToolRegistry()
registry.register(tool)
```

### Cost model

```python
@dataclass
class CostModel:
    """Cost model for tool execution planning and resource management."""
    ram_mb_est: int = 100          # Odhadovaná RAM v MB
    time_ms_est: int = 1000        # Odhadovaný čas v ms
    network: bool = False          # Vyžaduje síť?
    risk_level: RiskLevel = RiskLevel.LOW  # Riziko pro sandboxing
```

Cost model se používá pro:
- Odhad resource potřeb před spuštěním
- Rozhodování o paralelizaci
- Hermes hinting pro efektivní plánování

### Rate limits

```python
@dataclass
class RateLimits:
    """Rate limiting configuration for tools."""
    max_calls_per_run: int = 100   # Max volání per běh
    max_parallel: int = 1          # Max paralelních běhů
```

## Evidence Log

### Struktura eventu

```python
@dataclass
class EvidenceEntry:
    """Jedna položka evidence z tool volání."""
    entry_id: str                  # Unikátní ID
    tool_name: str                 # Název toolu
    iteration: int                 # Číslo iterace
    evidence_type: EvidenceType    # Typ evidence
    content: str                   # Obsah
    source: Optional[str]          # Zdroj
    confidence: float              # Confidence 0-1
    timestamp: float               # Časová značka
    metadata: Dict[str, Any]       # Metadata
    related_entries: List[str]     # Související entry IDs
    answers_question: Optional[str]  # Odpověď na otázku
    supports_hypothesis: Optional[str]  # Podpora hypotézy
```

### Evidence types

```python
class EvidenceType(Enum):
    DOCUMENT = "document"                    # Dokument
    FACT = "fact"                           # Fakt
    HYPOTHESIS_CONFIRMED = "hypothesis_confirmed"  # Potvrzená hypotéza
    HYPOTHESIS_REJECTED = "hypothesis_rejected"    # Vyvrácená hypotéza
    ENTITY = "entity"                       # Entita
    RELATIONSHIP = "relationship"           # Vztah
    PATTERN = "pattern"                     # Pattern
    ANOMALY = "anomaly"                     # Anomálie
    INSIGHT = "insight"                     # Insight
```

### Append-only garantie

```python
class EvidenceLog:
    """Log evidence z ReAct smyčky - append-only."""

    def add_entry(self, entry: EvidenceEntry) -> None:
        """Přidá entry do logu - pouze append, nikdy modify."""
        self._entries.append(entry)
        self._entry_counter += 1

    def get_all_entries(self) -> List[EvidenceEntry]:
        """Vrátí všechny entries - read-only view."""
        return self._entries.copy()
```

### Replay mode

```python
# Replay pro debugging nebo obnovení stavu
log = EvidenceLog()
log.replay_from_entries(saved_entries)

# Export pro analýzu
json_export = log.export_to_json()
```

## Budget Manager

### Stop conditions

```python
class BudgetConfig(BaseModel):
    """Configuration for resource budgets."""
    max_iterations: int = 6        # Max iterací
    max_docs: int = 30             # Max dokumentů
    max_time_sec: int = 180        # Max čas v sekundách
    max_tool_calls: int = 60       # Max volání toolů
    min_confidence: float = 0.7    # Min confidence pro early stop
    stagnation_threshold: int = 2  # Iterace bez nových entit
```

### Stagnation detection

```python
class BudgetManager:
    """Detekuje stagnaci - když se N iterací nic nového neobjeví."""

    def check_stagnation(self, current_entities: int) -> bool:
        if current_entities <= self._state.last_entities_count:
            self._state.stagnation_counter += 1
        else:
            self._state.stagnation_counter = 0

        return self._state.stagnation_counter >= self._config.stagnation_threshold
```

## Model Lifecycle (M1 8GB)

### 1-model-at-a-time

Na M1 8GB je kritické mít v paměti pouze jeden model najednou:

```python
class ReActOrchestrator:
    """M1-optimized orchestrator s 1-model-at-a-time policy."""

    async def _plan_phase(self, query: str, context: Dict) -> ToolPlan:
        # 1. Načti Hermes
        await self._load_hermes()

        # 2. Generuj plán
        plan = await self.hermes.generate_tool_plan(query, context)

        # 3. Uvolni Hermes (agresivní cleanup)
        await self._unload_hermes()

        return plan

    async def _act_phase(self, plan: ToolPlan) -> List[ToolResult]:
        # Tooly běží bez LLM - žádný model v paměti
        results = []
        for action in plan.actions:
            result = await self._execute_tool(action)
            results.append(result)
        return results
```

### Fáze a modely

| Fáze | Model | Účel | Memory |
|------|-------|------|--------|
| PLAN | Hermes-3 3B | Generování ToolPlan | ~2GB |
| ACT | Žádný | Spuštění toolů | ~0GB |
| OBSERVE | Žádný | Extrakce entit | ~0GB |
| DECIDE | Hermes-3 3B | Rozhodnutí o pokračování | ~2GB |
| SYNTHESIZE | Hermes-3 3B | Generování reportu | ~2GB |

### Memory cleanup

```python
import gc

class ReActOrchestrator:
    def _aggressive_cleanup(self):
        """Agresivní cleanup mezi fázemi."""
        # 1. Uvolni model
        if self._current_model:
            del self._current_model
            self._current_model = None

        # 2. Python GC
        gc.collect()

        # 3. MLX cache clear (pokud používáme MLX)
        try:
            import mlx.core as mx
            mx.clear_cache()
        except ImportError:
            pass

        logger.debug(f"Memory after cleanup: {self._get_memory_mb():.1f} MB")
```

## Example Run

### Log fází

```
================================================================================
🔬 ReAct Research Loop Starting
   Query: quantum cryptography 2024
================================================================================

--- Iteration 1/10 ---

[PHASE START] PLAN
[MODEL LOAD] hermes
[MODEL LOAD] hermes done (1.8s)
ToolPlan generated: 3 actions
  - web_search: "quantum cryptography 2024"
  - academic_search: "quantum cryptography post-quantum algorithms"
  - entity_extraction: (from results)
[MODEL RELEASE] hermes
[PHASE END] PLAN (2.1s)

[PHASE START] ACT
[TOOL] web_search: "quantum cryptography 2024"
[TOOL RESULT] 5 docs found
[EVIDENCE] event_id=ev_001, type=document, confidence=0.85

[TOOL] academic_search: "quantum cryptography post-quantum algorithms"
[TOOL RESULT] 3 papers found
[EVIDENCE] event_id=ev_002, type=document, confidence=0.92

[TOOL] entity_extraction
[EVIDENCE] event_id=ev_003, type=entity, entities=["NIST", "CRYSTALS-Kyber", "quantum supremacy"]
[PHASE END] ACT (4.5s)

[PHASE START] OBSERVE
Extracting entities from 8 documents...
New entities: ["NIST", "CRYSTALS-Kyber", "quantum supremacy", "IBM Quantum"]
[EVIDENCE] event_id=ev_004, type=insight, content="NIST standardized post-quantum algorithms in 2024"
[PHASE END] OBSERVE (0.3s)

[PHASE START] DECIDE
[MODEL LOAD] hermes
Evidence summary:
  - 8 documents collected
  - 4 new entities discovered
  - 1 key insight: NIST standardization
Continue: True
Next action: deep_research on CRYSTALS-Kyber
[MODEL RELEASE] hermes
[PHASE END] DECIDE (1.2s)

--- Iteration 2/10 ---

[PHASE START] PLAN
...

[PHASE START] SYNTHESIZE
[MODEL LOAD] hermes
Generating final report...
Report sections:
  1. Executive Summary
  2. NIST Standardization Timeline
  3. Key Algorithms (CRYSTALS-Kyber, CRYSTALS-Dilithium)
  4. Industry Adoption
  5. Future Outlook
  6. Sources (12 citations)
[MODEL RELEASE] hermes
[PHASE END] SYNTHESIZE (3.4s)

================================================================================
✅ ReAct Research Complete
   Iterations: 4
   Tool calls: 12
   Time: 45.2s
   Evidence count: 15
================================================================================
```

### Evidence Events

```json
{
  "event_id": "ev_001",
  "type": "document",
  "tool": "web_search",
  "iteration": 1,
  "content": "NIST announces first post-quantum cryptography standards...",
  "source": "https://www.nist.gov/news-events/news/2024/08/...",
  "confidence": 0.85,
  "timestamp": 1707830400.0
}
```

```json
{
  "event_id": "ev_003",
  "type": "entity",
  "tool": "entity_extraction",
  "iteration": 1,
  "content": "CRYSTALS-Kyber",
  "entity_type": "technology",
  "related_to": ["NIST", "post-quantum cryptography"],
  "confidence": 0.95,
  "timestamp": 1707830405.0
}
```

```json
{
  "event_id": "ev_007",
  "type": "hypothesis_confirmed",
  "tool": "academic_search",
  "iteration": 2,
  "content": "CRYSTALS-Kyber is secure against known quantum attacks",
  "hypothesis": "CRYSTALS-Kyber quantum security",
  "supporting_evidence": ["ev_002", "ev_004"],
  "confidence": 0.88,
  "timestamp": 1707830420.0
}
```

### Final Synthesis

```python
{
    "query": "quantum cryptography 2024",
    "report": {
        "title": "Post-Quantum Cryptography: NIST Standards and Industry Impact 2024",
        "sections": [
            {
                "heading": "Executive Summary",
                "content": "In August 2024, NIST released the first three post-quantum cryptography standards..."
            },
            {
                "heading": "NIST Standardization Timeline",
                "content": "The standardization process began in 2016..."
            }
        ],
        "sources": [
            {"url": "https://www.nist.gov/...", "title": "NIST PQC Standards", "confidence": 0.95},
            {"url": "https://arxiv.org/...", "title": "CRYSTALS-Kyber Security Analysis", "confidence": 0.92}
        ],
        "confidence_score": 0.89
    },
    "statistics": {
        "iterations": 4,
        "tool_calls": 12,
        "documents_found": 15,
        "entities_discovered": 8,
        "hypotheses_confirmed": 3,
        "execution_time": 45.2
    }
}
```

## Usage

### Basic Usage

```python
import asyncio
from hledac.universal import ReActOrchestrator
from hledac.universal.brain.hermes3_engine import Hermes3Engine

async def main():
    # Initialize Hermes
    hermes = Hermes3Engine()
    await hermes.initialize()

    # Create orchestrator
    orchestrator = ReActOrchestrator(
        hermes_engine=hermes,
        max_memory_mb=5500  # M1 8GB limit
    )

    # Run research
    result = await orchestrator.research(
        query="quantum cryptography 2024",
        max_iterations=10
    )

    print(f"Report: {result['result']['report']}")
    print(f"Iterations: {result['iterations']}")
    print(f"Time: {result['execution_time']:.2f}s")

if __name__ == "__main__":
    asyncio.run(main())
```

### With Custom Tool Adapters

```python
from hledac.universal.react import ReActOrchestrator

# Register custom tools
orchestrator.register_tool_adapter(
    "web_search",
    lambda args: my_custom_search(args["query"], args.get("max_results", 10))
)

orchestrator.register_tool_adapter(
    "academic_search",
    lambda args: search_arxiv(args["query"])
)
```

### With Budget Constraints

```python
from hledac.universal.budget_manager import BudgetConfig, BudgetManager

budget = BudgetConfig(
    max_iterations=6,
    max_docs=30,
    max_time_sec=180,
    min_confidence=0.7
)

result = await orchestrator.research(
    query="quantum cryptography 2024",
    budget=budget
)
```

## Configuration

### BudgetConfig

```python
from hledac.universal.budget_manager import BudgetConfig

config = BudgetConfig(
    max_iterations=6,           # Max iterací smyčky
    max_docs=30,                # Max dokumentů ke zpracování
    max_time_sec=180,           # Max čas běhu
    max_tool_calls=60,          # Max volání toolů
    min_confidence=0.7,         # Min confidence pro early stop
    stagnation_threshold=2      # Iterace bez nových entit
)
```

### ToolRegistry

```python
from hledac.universal.tool_registry import ToolRegistry, Tool, CostModel

registry = ToolRegistry()

# Register with cost model
registry.register(Tool(
    name="web_search",
    description="Web search",
    args_schema=WebSearchArgs,
    returns_schema=WebSearchResult,
    cost_model=CostModel(
        ram_mb_est=50,
        time_ms_est=2000,
        network=True,
        risk_level=RiskLevel.LOW
    ),
    handler=search_handler
))
```

### ReActOrchestrator

```python
from hledac.universal.react import ReActOrchestrator

orchestrator = ReActOrchestrator(
    hermes_engine=hermes,           # Hermes3Engine instance
    tool_registry=registry,          # Optional custom registry
    max_memory_mb=5500              # M1 8GB memory limit
)
```

## API Reference

### ReActOrchestrator

```python
class ReActOrchestrator:
    def __init__(
        self,
        hermes_engine: Any,
        tool_registry: Optional[ToolRegistry] = None,
        max_memory_mb: float = 5500
    )

    async def research(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        max_iterations: int = 10
    ) -> Dict[str, Any]

    def register_tool_adapter(
        self,
        tool_name: str,
        adapter: Callable
    ) -> None
```

### EvidenceLog

```python
class EvidenceLog:
    def add_entry(self, entry: EvidenceEntry) -> None
    def get_all_entries(self) -> List[EvidenceEntry]
    def get_summary(self) -> EvidenceSummary
    def next_iteration(self) -> None
    def clear(self) -> None
    def export_to_json(self) -> str
    def replay_from_entries(self, entries: List[EvidenceEntry]) -> None
```

### BudgetManager

```python
class BudgetManager:
    def __init__(self, config: BudgetConfig)
    def check_limits(self, evidence_count: int) -> BudgetStatus
    def check_stagnation(self, current_entities: int) -> bool
    def get_status(self) -> BudgetStatus
    def record_tool_call(self) -> None
    def update_confidence(self, confidence: float) -> None
```

## M1 8GB Optimization Tips

1. **Vždy používej 1-model-at-a-time** - Nikdy nenačítej více modelů současně
2. **Agresivní GC** - Volej `gc.collect()` mezi fázemi
3. **MLX cache clear** - Používej `mx.clear_cache()` po uvolnění modelu
4. **Monitoruj memory** - Loguj memory usage pro debugging
5. **Limituj iterace** - Používej rozumné limity pro rychlý feedback

## Troubleshooting

### Out of Memory

```python
# Snížit memory limit
orchestrator = ReActOrchestrator(
    hermes_engine=hermes,
    max_memory_mb=4500  # Nižší limit
)

# Zkrátit max iterací
result = await orchestrator.research(
    query="...",
    max_iterations=5  # Méně iterací
)
```

### Stagnation Detection

```python
# Upravit threshold
budget = BudgetConfig(
    stagnation_threshold=3  # Více iterací před detekcí
)
```

### Tool Failures

```python
# Implementovat fallback v tool adapteru
def web_search_with_fallback(args):
    try:
        return primary_search(args)
    except Exception:
        return fallback_search(args)

orchestrator.register_tool_adapter("web_search", web_search_with_fallback)
```