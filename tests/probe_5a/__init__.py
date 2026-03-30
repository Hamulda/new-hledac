"""
Sprint 5A: Checkpoint Restore + Export Sink + Finishable Sprint Path
======================================================================

Tests:
- checkpoint restore actually consumes _last_checkpoint
- restore is fail-open
- export hook creates minimal artifact
- export is idempotent
- windup → export → teardown path works
- AO canary passes

Run: pytest tests/probe_5a/ -q
"""
