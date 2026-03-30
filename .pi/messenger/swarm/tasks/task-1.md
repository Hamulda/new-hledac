# 🔎 Repo-wide Deep Audit (NO CHANGES) — Hledac / universal

# 🔎 Repo-wide Deep Audit (NO CHANGES) — Hledac / universal

## AUDIT SCOPE
- **Path:** /Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/**
- **Mode:** READ-ONLY (no code changes, no TODOs, no commits)
- **Standard:** Evidence-grade with file:line citations

## FOCUS AREAS

### A) Autonomous Loop Wiring Completeness
- Trace action registry → action implementations
- Identify wired vs orphan actions
- Map call graph: orchestrator → actions → dependencies

### B) Guardrails Audit
- Boundedness: Verify all loops have termination guarantees
- Lazy imports: Confirm no eager imports of heavy modules
- No toggles: Check for *_AVAILABLE flags replaced with capability probing
- Async blocking: Identify sync I/O in async contexts
- Cancellation hygiene: Verify proper task cancellation handling

### C) Performance & Memory (M1 8GB)
- Memory-heavy patterns (large imports, eager loading)
- MLX/Metal resource cleanup
- Context swap efficiency
- Garbage collection triggers

### D) Security & Privacy
- Secrets handling (env vars, config)
- Entropy sources (M1EntropySource usage)
- Stealth session integration
- Zero-logging compliance

### E) Dead Code & Redundancy Ledger
- Unused imports/modules
- Duplicate logic
- Orphaned files

### F) Tests/Observability Gaps
- Missing test coverage
- Metrics collection gaps
- Logging completeness

## OUTPUT FORMAT
Each specialist must deliver:
- Findings with file:line evidence
- Severity ratings (critical/high/medium/low)
- Remediation suggestions (NO implementation)

## RULES
- Read ONLY under hledac/universal/**
- Cite all findings as "path:line"
- No speculation — evidence-based only
- No code changes allowed
