"""
Sprint 8AW: Diagnostic Live Run V2 + End-to-End Signal/Store Trace

Test suite:
  D.1   test_observed_report_includes_pre_store_signal_fields
  D.2   test_observed_report_includes_store_rejection_delta_fields
  D.3   test_diagnose_end_to_end_live_run_no_pattern_hits
  D.4   test_diagnose_end_to_end_live_run_no_pattern_hits_possible_morphology_gap
  D.5   test_diagnose_end_to_end_live_run_pattern_hits_but_no_findings
  D.6   test_diagnose_end_to_end_live_run_low_information_dominant
  D.7   test_diagnose_end_to_end_live_run_duplicate_dominant
  D.8   test_diagnose_end_to_end_live_run_accepted_present
  D.9   test_completed_sources_zero_and_entries_zero_is_network_variance_not_regression
  D.10  test_completed_sources_positive_and_entries_zero_is_no_new_entries
  D.11  test_before_snapshot_resets_ingest_reason_counters_when_surface_exists
  D.12  test_compare_observed_run_to_baseline_handles_zero_completed_without_exception
  D.13  test_probe_8as_still_green
  D.14  test_probe_8at_still_green
  D.15  test_probe_8au_still_green
  D.16  test_probe_8av_still_green
  D.17  test_probe_8aq_still_green_or_env_blocker_na
  D.18  test_probe_8ar_still_green_or_env_blocker_na
  D.19  test_ao_canary_still_green

Benchmarks:
  E.1   1000x diagnose_end_to_end_live_run(): <300ms total
  E.2   1000x compare_observed_run_to_baseline() with normal input: <300ms total
  E.3   1000x compare_observed_run_to_baseline() with degenerate input: <300ms total
  E.4   20x mocked observed run composition with 8AU + 8AV fields: no task leak
"""

# conftest.py — shared fixtures and configuration for Sprint 8AW probe tests
import pytest  # noqa: F401  (used by pytest markers in test file)
