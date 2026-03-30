# M1 8GB Optimization - Architecture Summary

## Overview
This document describes the M1 8GB optimizations applied to the FullyAutonomousOrchestrator.

## Hard Constraints
- **Memory limit**: 5.5GB (leaving headroom for macOS)
- **Models**: Only 3 models allowed (Hermes, ModernBERT, GLiNER)
- **Invariant**: NEVER more than 1 model loaded simultaneously
- **Import overhead**: Minimal - lazy loading only

## Runtime Call Summary

```
start
  ↓
initialize()
  ↓  - Create lightweight managers (no heavy models)
  ↓  - Initialize capability registry
  ↓  - Log available/unavailable capabilities
  ↓
research(query, depth)
  ↓
┌─────────────────────────────────────────┐
│  PHASE: BRAIN                           │
│  - Load Hermes                          │
│  - Release ModernBERT + GLiNER          │
│  - Analyze query                        │
│  - Determine required capabilities      │
└─────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────┐
│  PHASE: TOOLS                           │
│  - Release Hermes                       │
│  - Load ModernBERT/GLiNER on-demand     │
│  - Execute search tools                 │
│  - Release models after use             │
└─────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────┐
│  PHASE: SYNTHESIS                       │
│  - Load Hermes                          │
│  - Release ModernBERT + GLiNER          │
│  - Generate final report                │
└─────────────────────────────────────────┘
  ↓
CLEANUP
  - Release all models
  - gc.collect()
  - mx.clear_cache()
```

## New Components

### 1. Capability System (`capabilities.py`)

#### Capability Enum
```python
class Capability(Enum):
    GRAPH_RAG = "graph_rag"
    ENTITY_LINKING = "entity_linking"
    RERANKING = "reranking"
    STEALTH = "stealth"
    ...
```

#### CapabilityRegistry
- Tracks which capabilities are available and why
- On-demand loading via `await registry.load(capability)`
- Logs unavailable capabilities with reasons

#### CapabilityRouter
- Routes research requirements to required capabilities
- Considers: source types, depth, analysis, profile

#### ModelLifecycleManager
- Enforces hard phase invariants
- Ensures single-model constraint
- Handles cleanup between phases

### 2. On-Demand Initialization

**Before (eager loading):**
```python
async def initialize(self):
    self._exposed_service_hunter = ExposedServiceHunter()
    self._inference_engine = InferenceEngine()
    self._relationship_discovery = RelationshipDiscoveryEngine()
    # ... 20+ heavy modules
```

**After (on-demand):**
```python
async def initialize(self):
    # Only lightweight components
    self._agent_engine = AgentCoordinationEngine()
    self._optimizer = ResearchOptimizer()
    self._expander = QueryExpander()
    self._resilience = ResilientExecutionManager()

async def _ensure_module_loaded(self, capability: Capability):
    # Load heavy modules only when needed
```

### 3. Phase Model Lifecycle

```python
async def enforce_phase_models(self, phase_name: str):
    if phase_name == "BRAIN":
        await self._release_all_models()
        await self.registry.load(Capability.HERMES)
        self._active_models = {Capability.HERMES}
    elif phase_name == "TOOLS":
        await self._release_model(Capability.HERMES)
        # Models loaded on-demand by tools
    elif phase_name == "SYNTHESIS":
        await self._release_all_models()
        await self.registry.load(Capability.HERMES)
```

### 4. Evidence/Trace System

- Disk-backed JSONL logs in `runs/<run_id>.jsonl`
- RAM keeps only top-50 findings
- Remaining findings streamed to disk

### 5. Concurrency Control

- Global `asyncio.Semaphore(max_concurrency)` for network fetches
- Early-stop when ranking/score exceeds threshold and budgets met

## Removed Components

### ReAct Implementation
- Moved from `hledac/universal/react/` to `hledac/universal/legacy/react/`
- Removed imports from `autonomous_orchestrator.py`
- Removed exports from `__init__.py`

**Files moved to legacy:**
- `react/__init__.py`
- `react/react_orchestrator.py`
- `react/tool_plan.py`
- `react/evidence_log.py`

## Logging Format

```
[CAPABILITIES] enabled=X, unavailable=Y, loaded=Z
[CAPABILITIES] available: [hermes, modernbert, ...]
[CAPABILITIES] unavailable: [(dark_web, "Module not available"), ...]

[PHASE START] BRAIN
[MODEL] Before transition: active=[]
[MODEL LOAD] hermes
[MODEL] After transition: active=[hermes]
[PHASE END] BRAIN

[MODEL RELEASE] hermes
[MODEL] All models released, GC completed
```

## Testing

Run tests:
```bash
pytest hledac/universal/tests/test_autonomous_orchestrator.py -v
```

Test coverage:
- Smoke test: orchestrator initialization
- Capability gating: unavailable capabilities logged
- Model lifecycle: single-model constraint enforced
- Evidence trace: JSONL format
- Concurrency: semaphore and early-stop
- ReAct removal: verified

## Migration Guide

### For existing code using ReAct:
```python
# OLD (removed)
from hledac.universal import ReActOrchestrator

# NEW (use standard orchestrator)
from hledac.universal import FullyAutonomousOrchestrator
orchestrator = FullyAutonomousOrchestrator()
result = await orchestrator.research(query, depth)
```

### For adding new capabilities:
1. Add to `Capability` enum in `capabilities.py`
2. Register in `create_default_registry()`
3. Add to `CapabilityRouter.SOURCE_CAPABILITIES` or `DEPTH_CAPABILITIES`
4. Use `await _ensure_module_loaded(capability)` in research flow
