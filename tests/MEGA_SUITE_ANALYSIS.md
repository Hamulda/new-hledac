# AO Mega-Suite Structural Analysis
## test_autonomous_orchestrator.py — 22,154 lines, 291 test classes

---

## EXECUTIVE SUMMARY

| Category | Count | Run Time | Risk Level | Recommended |
|----------|-------|----------|-------------|-------------|
| **CANARY** | ~40 | <30s | Low | Every sprint |
| **PHASE_GATE** | ~180 | 5-15min | Medium | Per-sprint focused |
| **HEAVY** | ~50 | 15-60min | High | Manual only |
| **UNKNOWN** | ~21 | ? | ? | Inspection needed |

---

## CANARY-WORTHY Tests (Fast, Deterministic, Fully Mocked)

These tests are isolated, fast, and test seams without heavy I/O or model loading.

### Lifecycle & State (7 classes)
- `TestOrchestratorSmoke` — instantiation, basic research flow
- `TestCapabilitySystem` — registry creation, routing, unavailable capability handling
- `TestModelLifecycle` — single model constraint, phase transitions
- `TestReactRemoval` — ReAct code purging verification
- `TestSyncWrapperRejection` — event loop detection for sync wrappers
- `TestBudgetManager` — budget checks and limits
- `TestPersistentDedup` — cross-run deduplication

### Graph & Knowledge (8 classes)
- `TestGraphWiring` — graph ingest, multi-hop search with mocks
- `TestGraphIngestDedup` — content hash deduplication, edge dedup
- `TestEvidenceIds` — evidence ID chain integrity
- `TestContradictionDetection` — contested paths detection
- `TestTemporalMetadata` — ring buffer limits, first_seen/last_seen
- `TestTimelineAndDrift` — timeline buckets, drift detection
- `TestNarratives` — multi-narrative output with confidence

### Evidence & Trace (5 classes)
- `TestEvidenceTrace` — runs directory creation, JSONL format
- `TestEvidenceLogBasics` — sequence numbering, hash chain
- `TestCheckpointSaveLoad` — save/load with temp directory
- `TestCheckpointManifest` — manifest structure and completeness

### Concurrency & Control (4 classes)
- `TestConcurrencyControl` — semaphore creation, early stop logic
- `TestCollectorQueue` — queue operations, backpressure
- `TestActionRegistry` — action registration, scoring
- `TestPriorityHeap` — heap operations for action scheduling

### Capability Routing (3 classes)
- `TestCapabilityRouting` — routing decisions per capability
- `TestCapabilityPhaseGating` — phase-based capability enforcement
- `TestCapabilityFallback` — graceful degradation on unavailable

---

## PHASE-GATE-WORTHY Tests (Require Focused Sprint Context)

These tests are still relatively fast but require specific sprint context.

### Sprint 7A-7C Integration (6 classes)
- `TestSprint7AActivation` — truth validation, token bucket
- `TestSprint7BStructureClosure` — exception handling, adaptive yield
- `TestSprint7CFPSFix` — FPS metric extraction
- `TestSprint7DBenchmarkTruth` — benchmark determinism

### Sprint 8X Deep Investigation (12 classes)
- `TestSprint8XProbe` — probe integration
- `TestSprint8ANHygiene` — code hygiene checks
- `TestSprint8AQShadow` — shadow DTO performance
- `TestSprint8BJRuntime` — runtime safety audits

### Sprint 41-48 Heavy Components (35 classes)
- `TestDynamicBatching` — batch queue, aging, priority cap
- `TestPredictiveRSS` — EMA-based RSS prediction
- `TestLinUCBBandit` — contextual bandit implementation
- `TestLightpandaIntegration` — JS-heavy page detection
- `TestDeepForensics` — EXIF/GPS extraction, ELA analysis
- `TestLinkPrediction` — Adamic/Adar, LSH clustering
- `TestSessionManagement` — cookie injection, credential rotation
- `TestPaywallBypass` — paywall detection, archive fallback

### Sprint 50-60 ML Components (40 classes)
- `TestHNSWIndex` — HNSW build and search
- `TestHermesKVCache` — KV cache sharing
- `TestFlashRankReranker` — reranking quality
- `TestGLiNERNER` — named entity recognition
- `TestMPSAccelerated` — Metal performance shaders
- `TestGlobalScheduler` — priority queue, CPU affinity
- `TestANEEmbedder` — Apple Neural Engine acceleration
- `TestGNNPredictor` — graph neural network predictions
- `TestPagedAttention` — page-based KV cache
- `TestQMIXTrainer` — joint Q-learning training
- `TestPrefetchOracle` — prefetch prediction

---

## HEAVY / MANUAL-ONLY Tests (RAM/CPU/Time Intensive)

These tests load real models, make network calls, or run for extended periods.

### E2E Integration (8 classes)
- `TestE2EPipeline` — full research pipeline (mocked external calls)
- `TestAutonomousLoop` — continuous loop with real scheduling
- `TestDeepDiveResearch` — multi-hop recursion with RAM safety

### Model Loading (15 classes)
- `TestHermesModelLoad` — MLX model loading/unloading
- `TestModernBERTEmbed` — embedding generation
- `TestGLiNERExtraction` — real NER extraction
- `TestFlashRankScore` — real reranking

### Network Tests (12 classes)
- `TestDeepReadHTTP` — real HTTP fetching
- `TestTorConnection` — Tor circuit handling
- `TestSearxngSearch` — real searxng queries
- `TestAcademicSearch` — ArXiv API calls

### Stress / Chaos (10 classes)
- `TestMemoryPressure` — aggressive memory eviction
- `TestThermalThrottling` — thermal limit handling
- `TestChaosInjection` — fault injection
- `TestConcurrentLoad` — parallel action execution

### Benchmark Tests (5 classes)
- `TestBenchmarkFPS` — FPS measurement runs
- `TestBenchmarkMemory` — memory profiling
- `TestBenchmarkAccuracy` — accuracy evaluation

---

## STRUCTURAL CATEGORIZATION BY LINE RANGE

### Lines 1-2000: Core Lifecycle + Evidence (CANARY)
- TestOrchestratorSmoke
- TestCapabilitySystem
- TestModelLifecycle
- TestEvidenceTrace
- TestConcurrencyControl
- TestReactRemoval
- TestGraphWiring

### Lines 2000-5000: Graph + Dedup (CANARY)
- TestGraphIngestDedup
- TestEdgeDedup
- TestPersistentDedup
- TestEvidenceIds
- TestContradictionDetection
- TestTemporalMetadata

### Lines 5000-8000: Synthesis + Budget (PHASE_GATE)
- TestSynthesisManager
- TestBudgetManager
- TestCollectorQueue
- TestActionRegistry
- TestPriorityHeap

### Lines 8000-12000: Deep Features (PHASE_GATE)
- TestDeepRead
- TestTemporalArchaeologist
- TestURLFrontier
- TestHostPenaltyTracker
- TestRotatingBloomFilter

### Lines 12000-16000: ML Components (PHASE_GATE/HEAVY)
- TestHNSWIndex
- TestPagedAttention
- TestKnowledgeLayer
- TestRAGEngine
- TestGNNPredictor

### Lines 16000-20000: Advanced Features (HEAVY)
- TestQMIXTrainer
- TestPrefetchOracle
- TestHTNPlanner
- TestAdaptiveCostModel
- TestDeepExplainer

### Lines 20000-22154: Sprint-Specific (MIXED)
- TestSprint7A* - Sprint 7A activation
- TestSprint7B* - Sprint 7B structure
- TestSprint7C* - Sprint 7C FPS fix
- TestSprint5G* - Sprint 5G collector
- TestSprint6F* - Sprint 6F FPS root-cause

---

## RECOMMENDED GATES

### After Every Sprint Change
```bash
# 1. Probe gate (instant)
pytest tests/probe_*/ -m probe_gate -q

# 2. AO Canary (5-10s)
pytest tests/test_ao_canary.py -q

# 3. Phase gate (10-60s per sprint)
pytest tests/test_sprint*.py::TestSprintN* -q
```

### Before Major Release
```bash
# Full sprint suite (15-30 min)
pytest tests/test_sprint*.py -q

# Selected heavy tests
pytest tests/test_e2e_pipeline.py -q
```

### NEVER as Default Gate
```bash
# The mega-suite - 22k lines, 291 classes, 10+ minutes
pytest tests/test_autonomous_orchestrator.py -q  # DON'T
```

---

## MARKER RECOMMENDATIONS

To implement proper gate markers, add to `conftest.py`:

```python
def pytest_configure(config):
    config.addinivalue_line("markers", "canary: Fast canary tests")
    config.addinivalue_line("markers", "phase_gate: Per-sprint focused tests")
    config.addinivalue_line("markers", "heavy: RAM/time intensive tests")
    config.addinivalue_line("markers", "manual: Manual verification only")
```

Then add markers to test classes in mega-suite:
```python
@pytest.mark.canary
class TestOrchestratorSmoke:
    ...

@pytest.mark.heavy
class TestHermesModelLoad:
    ...
```

---

## FILE REFERENCES

- **Mega Suite**: `tests/test_autonomous_orchestrator.py` (22,154 lines)
- **Canary Layer**: `tests/test_ao_canary.py` (NEW)
- **Phase Gates**: `tests/PHASE_GATES.py` (NEW)
- **Sprint Files**: `tests/test_sprint*.py` (80+ files)
- **Probe Files**: `tests/probe_*/` (probe smoke tests)
