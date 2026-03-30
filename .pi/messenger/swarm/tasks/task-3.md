# 🔎 MEGA AUDIT v2 (READ-ONLY) — Wiring + Perf + Dead-code + Guardrails (universal)

## MEGA AUDIT SPEC (VERBATIM)

Role: Jsi senior maintainer + perf/memory auditor pro projekt Hledac.
Cíl: Udělej "repo-wide wiring + perf + dead-code + guardrails" audit. ŽÁDNÉ změny souborů.

### A) Wiring Completeness
- Find entrypoint in autonomous_orchestrator.py: research(), _initialize_actions(), _register_action(), _analyze_state(), _decide_next_action(), _execute_action(), _process_result()
- Build "Wiring Truth Table": action → scorer → handler → components → evidence events → gates
- Verify: scorer is O(1), handler is async-safe, background tasks have lifecycle
- Find orphaned/partial components in coordinators/*, intelligence/*, brain/*, knowledge/*, tools/*

### B) Guardrails + Security
- Boundedness: verify loops have exit conditions
- Lazy imports: confirm no eager heavy imports
- No toggles: no runtime feature flags in hot paths
- Async blocking: find sync I/O in async contexts
- Cancellation hygiene: check cleanup on cancelled tasks
- Security: EvidenceLog PII, DNS rebinding, darkweb fallbacks

### C) Performance & M1 8GB
- Import-time analysis with python -X importtime
- Memory hotspots: unbounded structures, cache policies
- Event-loop hazards: sync I/O in async, CPU heavy without to_thread
- Resource gating: _memory_pressure_ok() consistency

### D) Dead Code & Redundancy
- Unused imports, unreferenced functions/classes
- Backup/bak files
- Duplicate logic → single source of truth

### E) Test Gaps
- Critical M1-specific branches without coverage
- Specific missing tests + determinism strategy

Scope: /Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal/**
