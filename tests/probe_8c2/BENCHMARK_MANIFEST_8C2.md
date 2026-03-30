# Research Benchmark Manifest 8C2

## Purpose
Research-Effectiveness benchmark suite for Hledac OSINT orchestrator.
Computes top-level research scorecards from benchmark/evidence data.

---

## Source of Truth Files

| File | Role |
|------|------|
| `benchmarks/research_effectiveness.py` | Score aggregation helpers: 5 scorecards, HHI, canonical normalization |
| `tests/probe_8c2/test_research_effectiveness.py` | Schema consistency, determinism, unavailable paths, regression guards |
| `tests/probe_8c2/results/example_research_scorecard.json` | Example scorecard output |

---

## Top-Level Scorecards

### ResearchBreadthIndex
- **Dimensions**: source_family_count, source_family_hhi, unique_domains, unique_tlds, unique_content_types, unique_source_hosts
- **Score formula**: composite of family diversity + domain coverage + content diversity
- **Status**: READY / UNAVAILABLE_WITH_REASON

### ResearchDepthIndex
- **Dimensions**: unindexed_source_hits, archive_resurrection_hits, passive_source_hits, hidden_service_hits, max_frontier_depth
- **Score formula**: archive/ct/onion/prf coverage weighted
- **Status**: READY / UNAVAILABLE_WITH_REASON

### ResearchQualityIndex
- **Dimensions**: high_conf_findings_per_minute, novel_findings_per_100_sources, corroborated_findings_ratio, single_source_claim_ratio
- **Score formula**: confidence × novelty × corroboration
- **Status**: READY / UNAVAILABLE_WITH_REASON

### ResearchFrictionIndex
- **Dimensions**: challenge_issued_rate, challenge_solve_rate, fallback_rate_after_403/429, wayback_fallback_rate
- **Score formula**: friction weighted inversely (lower friction = higher score)
- **Status**: READY / UNAVAILABLE_WITH_REASON

### DeepResearchPowerScore
- **Formula**: breadth×0.25 + depth×0.30 + quality×0.30 + (100−friction)×0.15
- **Tiers**: excellent (≥80), good (≥60), average (≥40), poor (≥20), minimal (<20)
- **Status**: READY / UNAVAILABLE_WITH_REASON

---

## Canonical Normalizations

| Concept | Values |
|---------|--------|
| source_family | certificate_transparency, archive, commoncrawl, darknet, search, iot, dns, threat, other |
| acquisition_mode | passive, archive, hidden_service, certificate_transparency, commoncrawl, deep_crawl, direct |
| confidence_bucket | high (≥0.9), medium (≥0.7), low (≥0.4), unknown |
| severity | critical, high, medium, low, unknown |

---

## Command Matrix

### Run tests
```bash
pytest tests/probe_8c2/ -v --tb=short
```

### Generate scorecard from benchmark files
```bash
python benchmarks/research_effectiveness.py benchmark_results/benchmark_*.json
```

### Combine and score
```bash
python -c "
import json, sys
sys.path.insert(0, '.')
from benchmarks.research_effectiveness import compute_all_scorecards, generate_scorecard_markdown
sc = compute_all_scorecards('benchmark_results/benchmark_*.json')
print(generate_scorecard_markdown(sc))
"
```

---

## Status Classification

| Scorecard | Status | Reason |
|----------|--------|--------|
| ResearchBreadthIndex | READY | Computable from acquisition counters |
| ResearchDepthIndex | READY | Computable from acquisition counters |
| ResearchQualityIndex | PARTIAL | quality_score=0 when findings data unavailable |
| ResearchFrictionIndex | READY | Computable from acquisition counters |
| DeepResearchPowerScore | READY | Composite of above |

---

## Availability Rules

- All functions **fail-open**: missing data → UNAVAILABLE_WITH_REASON, never hard fail
- All functions **offline-ready**: no network calls, no external dependencies beyond stdlib
- All functions **deterministic-friendly**: same input → same output

---

## Probe Tests Coverage

- Schema consistency: all 5 scorecards have required fields
- Deterministic aggregation: HHI, scorecard computation stable across runs
- Unavailable-path: empty/partial data handled gracefully
- No-network: no network calls in any function
- Stable output: same input → same output (hashable fixtures)
- No boot regression: no torch, no duckdb imports
- Example output: `tests/probe_8c2/results/example_research_scorecard.json`
