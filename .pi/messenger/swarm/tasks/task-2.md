# 🔎 Repo-wide Deep Audit (NO CHANGES) — Hledac / universal (Round 2)

## AUDIT SPECIFICATION (VERBATIM)

### A) Wiring Completeness Audit
- Map all action handlers to their implementation functions
- Identify: wired / partial wiring / orphan actions
- Evidence: file:line references for each

### B) Guardrails Audit
- Boundedness: verify all loops have exit conditions
- Lazy imports: confirm no eager imports of heavy modules
- No toggles: ensure no runtime feature flags in hot paths
- Async blocking: find any sync I/O in async contexts
- Cancellation hygiene: check for cancelled tasks cleanup

### C) Performance & Memory (M1 8GB)
- Memory hotspots: any加载即吃的模块
- M1-specific: MLX/Metal usage, unified memory pressure
- Lazy loading gaps
- Garbage collection points

### D) Security & Privacy
- Secret handling (env vars, not hardcoded)
- Input sanitization
- Rate limiting presence
- Data exfiltration vectors

### E) Dead Code & Redundancy
- Unused imports/functions/classes
- Duplicate logic across modules
- TODO/FIXME that are stale

### F) Tests & Observability Gaps
- Missing test coverage areas
- Logging coverage
- Metrics/monitoring presence

### Scope
- Work ONLY inside: /Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/**
- ZERO code changes allowed
- Read-only commands only
