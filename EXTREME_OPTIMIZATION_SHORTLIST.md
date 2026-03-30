# EXTREME OPTIMIZATION — IMPLEMENTATION SHORTLIST

**Source:** `EXTREME_OPTIMIZATION_AUDIT_M1_8GB.md`
**Scope:** `/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/**`
**Hardware:** MacBook Air M1 8GB

---

## 🚀 PHASE 1: IMPLEMENT IMMEDIATELY

### 1.1 orjson for Evidence Log

| Field | Value |
|-------|-------|
| **File** | `evidence_log.py` |
| **Function** | `EvidenceEvent.calculate_hash()` (line ~79), `EvidenceLog.append()` |
| **Why Worth It** | orjson is 5-10x faster than stdlib json. Evidence log serializes every event. Benefits compound over 1000+ events in long autonomous runs. |
| **Why Beats Alternatives** | Drop-in replacement, same API, already in requirements. No memory overhead. |
| **Benchmark** | Serialize 1000 events, measure time. Target: <50ms for 1000 events. |
| **Regression Risk** | orjson outputs bytes not str. Must ensure `orjson.dumps()` → `.decode()` where str expected. JSONL format must remain identical. |

**Change:**
```python
# Before:
import json
json_str = json.dumps(data, sort_keys=True, separators=(',', ':'))

# After:
import orjson
json_str = orjson.dumps(data, option=orjson.OPT_SORT_KEYS).decode('utf-8')
```

---

### 1.2 Pre-compile Regex in Graph RAG

| Field | Value |
|-------|-------|
| **File** | `knowledge/graph_rag.py` |
| **Function** | `_extract_entities_from_node()` (line ~1530) |
| **Why Worth It** | Regex compiled on every call to `_extract_entities_from_node()`. Called for every node in graph traversal. 30%+ speedup from pre-compilation. |
| **Why Beats Alternatives** | Module-level constant beats class-level, beats local compile. Zero runtime overhead. |
| **Benchmark** | Extract entities from 1000 nodes. Target: <100ms. |
| **Regression Risk** | LOW. Pattern must match same text. Test entity extraction output unchanged. |

**Change:**
```python
# Add at module top (around line 50):
_ENTITY_PATTERN = re.compile(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b')

# In function (line ~1540):
# import re  # REMOVE THIS
capitalized = _ENTITY_PATTERN.findall(content)
```

---

### 1.3 Remove Redundant verify_integrity Call

| Field | Value |
|-------|-------|
| **File** | `evidence_log.py` |
| **Function** | `EvidenceLog.append()` (line ~494) |
| **Why Worth It** | `verify_integrity()` calls `calculate_hash()` which does full `json.dumps()`. Called TWICE per event: once before append, once inside append. Eliminates double serialization. |
| **Why Beats Alternatives** | Alternative is cache hash — more complex. Simply remove the redundant call since hash was already verified before append. |
| **Benchmark** | Append 1000 events. Measure time. Target: 40% speedup. |
| **Regression Risk** | MEDIUM. Must verify hash chain integrity remains correct. Chain depends on `event.content_hash` which is set at event creation, not inside append. |

**Change:**
```python
# Line 493-499 in append():
# REMOVE THIS BLOCK:
# if not event.verify_integrity():
#     raise ValueError(
#         f"Event {event.event_id} has invalid content hash - possible tampering"
#     )

# Keep only: verify that run_id matches (line 488-492)
```

---

## 📊 PHASE 2: MEASUREMENT FIRST

### 2.1 Async Checkpoint Writes

| Field | Value |
|-------|-------|
| **File** | `autonomous_orchestrator.py` |
| **Function** | `_save_checkpoint()` or similar (around line 10939) |
| **Why Worth It** | Checkpoint saves block event loop. Async would keep decision loop responsive during crash-recovery writes. |
| **Why Beats Alternatives** | Alternative is reduce checkpoint frequency — hurts recoverability. Async is non-blocking. |
| **Benchmark** | Measure `time.time()` delta during checkpoint. Target: <10ms blocking. |
| **Regression Risk** | MEDIUM. Must preserve crash-safety. Must handle write failure gracefully. |

---

### 2.2 Background Evidence Eviction

| Field | Value |
|-------|-------|
| **File** | `brain/inference_engine.py` |
| **Function** | `_evict_graph_node_if_needed()` (line ~656) |
| **Why Worth It** | Eviction triggered on new evidence add — can cause latency spike in hot path. Background task moves work out of critical path. |
| **Why Beats Alternatives** | Alternative is reduce eviction frequency — increases memory. Background task is non-blocking. |
| **Benchmark** | Long-run memory usage. Target: Stable <5GB over 1 hour. |
| **Regression Risk** | LOW. Periodic task, failsafe. |

---

### 2.3 Guard Hot-Path Logging

| Field | Value |
|-------|-------|
| **File** | `evidence_log.py`, `autonomous_orchestrator.py` |
| **Function** | Decision loop, evidence append |
| **Why Worth It** | 3255 logging calls throughout. Some in tight loops. Guards reduce overhead when DEBUG disabled. |
| **Why Beats Alternatives** | Alternative is remove logging — hurts observability. Guards preserve debug capability. |
| **Benchmark** | Profile decision loop with logger.disabled=True vs False. |
| **Regression Risk** | LOW. Only affects debug output. |

---

## 🔬 PHASE 3: APPLE-SILICON EXPERIMENTS (Later)

### 3.1 Complete CoreML Embedder

| Field | Value |
|-------|-------|
| **File** | `knowledge/rag_engine.py` |
| **Function** | Embedding generation (line ~695) |
| **Why Worth It** | Neural Engine uses <1W vs GPU 10W. ANE embeddings = zero-power inference. |
| **Why Beats Alternatives** | Alternative is MLX on GPU — higher power. ANE is purpose-built for this. |
| **Benchmark** | Embed 1000 sentences. Target: <500ms, <1W power. Compare quality to MLX. |
| **Regression Risk** | MEDIUM. CoreML export may differ from PyTorch/MLX. Quality validation required. |

---

### 3.2 Verify MLX Similarity Paths

| Field | Value |
|-------|-------|
| **File** | `knowledge/lancedb_store.py` |
| **Function** | Similarity computation (line ~77-90) |
| **Why Worth It** | MLX on GPU should be faster than CPU numpy. Need to verify GPU actually used. |
| **Why Beats Alternatives** | Alternative is stay on CPU — slower. MLX is native Apple Silicon. |
| **Benchmark** | Query similarity 1000 vectors. Target: GPU time <10% of CPU time. |
| **Regression Risk** | LOW. Verify GPU used, fall back to numpy if not. |

---

### 3.3 MPS Graph Expansion

| Field | Value |
|-------|-------|
| **File** | `utils/mps_graph.py` |
| **Function** | Linear algebra ops |
| **Why Worth It** | MPS Graph compiles ops into single GPU kernel. Faster than individual MPS calls. |
| **Why Beats Alternatives** | Alternative is use MLX — higher level, may not cover all ops. MPS Graph is lower-level optimization. |
| **Benchmark** | Matrix operations. Target: 20% speedup vs individual MPS calls. |
| **Regression Risk** | LOW. Experimental but isolated to utils. |

---

## ❌ REJECTED FOR NOW

| Item | Why Rejected |
|------|--------------|
| Parallel scorer execution | O(1) dict lookups, parallelism overhead > benefit |
| Replace numpy with MLX wholesale | MLX transfer overhead > numpy for small ops |
| Aggressive prefetching | Memory pressure risk on 8GB |
| Full GPU offload | Memory constraints |
| Natural Language framework NER | Not proven better, HIGH risk |
| Structure map prefetch queue | Marginal benefit, memory risk |

---

## VALIDATION CHECKLIST

Before marking Phase 1 complete:
- [ ] orjson: 1000 events serialize in <50ms
- [ ] orjson: JSONL output byte-identical to stdlib json
- [ ] regex: 1000 node entity extraction <100ms
- [ ] regex: Output identical to inline version
- [ ] verify_integrity: 1000 events append 40%+ faster
- [ ] verify_integrity: Hash chain integrity test passes
