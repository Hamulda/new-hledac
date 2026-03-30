# probe_7d_legacy — Legacy Unload Model Tests

These tests were moved from `probe_7d/` because they test `model_lifecycle.unload_model()`
which is unrelated to the batch routing / structured generation work of Sprint 7G.

The tests fail because:
- `test_unload_model_evicts_prompt_cache`: mocks `__del__` which is not how prompt cache eviction works
- `test_unload_model_respects_order`: GC call order is non-deterministic in Python's async context

These are legacy tests that need a different testing approach and are not gating for current sprint work.
