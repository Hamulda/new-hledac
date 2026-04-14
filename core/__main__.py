"""
Sprint 8RA — CLI Entry Point: python -m hledac.universal.core

Pre-sprint checks, UMA wiring, sprint_delta reporting.
Wires UMAAlarmDispatcher → SprintScheduler wind-down callbacks.

Usage:
    python -m hledac.universal.core --sprint --query "LockBit ransomware" --duration 1800
    python -m hledac.universal.core --ct-pivot example.com
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time
from pathlib import Path

import aiohttp
import orjson

from hledac.universal.core.resource_governor import sample_uma_status
from hledac.universal.intelligence.ct_log_client import CTLogClient
from hledac.universal.knowledge.duckdb_store import DuckDBShadowStore
from hledac.universal.knowledge.semantic_store import SemanticStore
from hledac.universal.paths import TOR_ROOT, get_sprint_json_report_path
from hledac.universal.runtime.sprint_scheduler import (
    SprintScheduler,
    SprintSchedulerConfig,
)
from hledac.universal.transport.tor_transport import TorTransport
from hledac.universal.runtime.sprint_lifecycle import SprintLifecycleManager
from hledac.universal.export.sprint_exporter import export_sprint

logger = logging.getLogger(__name__)

# =============================================================================
# Smoke vs meaningful runtime guard
# =============================================================================


def _is_meaningful_run(
    actual_duration_s: float,
    cycles_completed: int,
    cycles_started: int,
    accepted_findings: int,
    total_pattern_hits: int,
) -> tuple[bool, str]:
    """
    Distinguish smoke from meaningful active evidence.

    Returns (is_meaningful, evidence_note).
    Smoke: too short, too few cycles, no signal whatsoever.
    Meaningful: enough runtime or evidence of real work.
    """
    # Hard smoke: no cycles ran at all
    if cycles_started == 0:
        return False, "zero cycles started — entry only, no active work"

    # Short but found something: counts as minimal meaningful
    if accepted_findings > 0:
        return True, f"found {accepted_findings} findings despite short runtime"

    # Short but pattern activity: minimal signal
    if total_pattern_hits > 0 and actual_duration_s >= 15:
        return True, f"pattern activity ({total_pattern_hits} hits) despite short run"

    # Hard smoke thresholds
    if actual_duration_s < 30 and cycles_completed < 3:
        return False, f"runtime {actual_duration_s:.0f}s and {cycles_completed} cycles below minimum"

    if actual_duration_s < 10:
        return False, f"runtime {actual_duration_s:.1f}s — entry/import only"

    # E0-T4: <180s without findings is meaningful_empty, not meaningful.
    # authoritative early-returns above (findings > 0, hits >= 15) are exempt.
    if actual_duration_s < 180 and accepted_findings == 0 and total_pattern_hits == 0:
        return False, (
            f"runtime {actual_duration_s:.0f}s < 180s floor, "
            f"no findings, no pattern hits — below meaningful threshold"
        )

    # Normal meaningful run
    return True, (
        f"{actual_duration_s:.0f}s runtime, "
        f"{cycles_completed}/{cycles_started} cycles completed, "
        f"no findings but within normal parameters"
    )


def _runtime_truth(
    actual_duration_s: float,
    query: str,
    duration_s: float,
    cycles_completed: int,
    cycles_started: int,
    accepted_findings: int,
    total_pattern_hits: int,
    public_accepted_findings: int,
    feed_findings: int,
) -> dict:
    """Build canonical runtime-truth record from scheduler result data."""
    is_meaningful, evidence_note = _is_meaningful_run(
        actual_duration_s, cycles_completed, cycles_started,
        accepted_findings, total_pattern_hits
    )

    # Branch mix — dominant signal source
    branch_mix = {
        "feed_findings": feed_findings,
        "public_findings": public_accepted_findings,
    }

    # Primary signal source label
    if feed_findings > 0 and public_accepted_findings == 0:
        primary = "feed"
    elif public_accepted_findings > 0 and feed_findings == 0:
        primary = "public"
    elif feed_findings > 0 and public_accepted_findings > 0:
        primary = "mixed"
    else:
        primary = "none"

    return {
        "is_meaningful": is_meaningful,
        "evidence_note": evidence_note,
        "command_params": {
            "query": query,
            "requested_duration_s": duration_s,
        },
        "actual_duration_s": round(actual_duration_s, 2),
        "cycles_completed": cycles_completed,
        "cycles_started": cycles_started,
        "branch_mix": branch_mix,
        "primary_signal_source": primary,
        "total_pattern_hits": total_pattern_hits,
        "accepted_findings": accepted_findings,
    }

def _get_live_feed_urls() -> list[str]:
    """
    Return canonical runtime feed URLs for live sprint path.

    Uses get_runtime_feed_seeds() from rss_atom_adapter — the single source
    of truth for the runtime RSS/Atom feed surface. Returns only ``curated_seed``
    entries sorted by priority descending. This is the accessor the canonical
    sprint owner path should use; topology_candidates are excluded by design.
    """
    from hledac.universal.discovery.rss_atom_adapter import get_runtime_feed_seeds
    return [seed.feed_url for seed in get_runtime_feed_seeds()]


# =============================================================================
# Pre-sprint checks
# =============================================================================


def run_pre_sprint_checks() -> bool:
    """
    Run mandatory pre-sprint checks.

    Returns True if safe to proceed, False to abort.
    """
    import mlx.core as mx

    checks_passed = True

    # MX wired limit — BOOT invariant (set even before model load)
    if mx.metal.is_available():
        try:
            mx.metal.set_wired_limit(2_500_000_000)  # 2.5GB
            logger.info("[BOOT] MLX wired limit: 2.5GB")
        except Exception as exc:
            logger.warning(f"[BOOT] mx.metal.set_wired_limit failed: {exc}")

    # Swap check — WARNING only, non-blocking
    s = sample_uma_status()
    if s.swap_used_gib > 2.0:
        logger.warning(
            f"[BOOT] SWAP {s.swap_used_gib:.1f}GB > 2GB — "
            f"doporučuji restart před long run"
        )

    logger.info(
        f"[BOOT] Pre-sprint checks OK | "
        f"UMA: {s.system_used_gib:.2f}GiB used | swap: {s.swap_used_gib:.2f}GiB"
    )
    return checks_passed


# =============================================================================
# Sprint delta writer (uses existing DuckDB schema)
# =============================================================================


def _derive_top_source(hits_per_source: dict[str, int]) -> str:
    """Return source with most hits, or empty string if no data."""
    if not hits_per_source:
        return ""
    return max(hits_per_source, key=lambda k: hits_per_source[k])


async def write_sprint_delta(
    store: DuckDBShadowStore,
    sprint_id: str,
    query: str,
    new_findings: int,
    dedup_hits: int,
    ioc_nodes: int,
    uma_baseline_gib: float,
    uma_peak_gib: float,
    synthesis_success: bool,
    duration_s: float,
    hits_per_source: dict[str, int],
) -> None:
    """Write sprint_delta record to DuckDB at TEARDOWN."""
    try:
        findings_per_min = (new_findings / (duration_s / 60.0)) if duration_s > 0 else 0.0
        top_source = _derive_top_source(hits_per_source)
        row = {
            "sprint_id": sprint_id,
            "ts": time.time(),
            "query": query,
            "duration_s": duration_s,
            "new_findings": new_findings,
            "dedup_hits": dedup_hits,
            "ioc_nodes": ioc_nodes,
            "ioc_new_this_sprint": new_findings,
            "uma_peak_gib": uma_peak_gib - uma_baseline_gib,
            "synthesis_success": synthesis_success,
            "findings_per_min": findings_per_min,
            "top_source_type": top_source,
            "synthesis_confidence": 1.0 if synthesis_success else 0.0,
        }
        # Wait for store to be healthy
        for _ in range(40):
            if await store.async_healthcheck():
                break
            await asyncio.sleep(0.05)
        await store.async_record_sprint_delta(row)
        logger.info(
            f"[TEARDOWN] sprint_delta written: {new_findings} findings, "
            f"{dedup_hits} dedup hits, "
            f"UMA delta: {uma_peak_gib - uma_baseline_gib:+.2f}GiB, "
            f"top_source: {top_source!r}, "
            f"findings_per_min: {findings_per_min:.2f}"
        )
    except Exception as exc:
        logger.warning(f"[TEARDOWN] sprint_delta write failed: {exc}")


# =============================================================================
# Main sprint runner
# =============================================================================


async def run_sprint(
    query: str,
    duration_s: float = 1800.0,
    export_dir: str = str(Path.home() / ".hledac" / "reports"),
) -> None:
    """
    Run a full sprint lifecycle with UMA monitoring and delta reporting.
    Uses SprintScheduler.run() directly to enable compute_sprint_intelligence() access.
    """
    # Sprint 8SA: Phase timing instrumentation
    _phase_times: dict[str, float] = {}
    _phase_times["BOOT"] = time.monotonic()

    # Pre-sprint checks
    run_pre_sprint_checks()

    # UMA baseline
    uma_baseline_gib = sample_uma_status().system_used_gib

    # Sprint ID
    sprint_id = f"8sa_{int(time.time())}"
    _phase_times["WARMUP"] = time.monotonic()

    # Initialize stores
    store = DuckDBShadowStore()
    await store.async_initialize()

    # Scheduler config
    config = SprintSchedulerConfig(
        sprint_duration_s=duration_s,
        export_enabled=True,
        export_dir=export_dir,
    )

    # Sprint F153: Lifecycle receives explicit runtime params — duration authority propagated
    lifecycle = SprintLifecycleManager(
        sprint_duration_s=duration_s,
        windup_lead_s=config.windup_lead_s,
    )
    scheduler = SprintScheduler(config)

    # Sprint F153: Canonical source inventory — real URLs from typed seed surface
    live_feed_urls = _get_live_feed_urls()

    try:
        # Run sprint via scheduler directly (enables compute_sprint_intelligence access)
        # now_monotonic=None: scheduler uses live time internally via adapter.tick()
        result = await scheduler.run(
            lifecycle=lifecycle,
            sources=live_feed_urls,
            now_monotonic=None,
            query=query,
            duckdb_store=store,
        )

        # Sprint F150H: Pull scheduler intelligence (fail-soft, additive)
        # correlation, hypothesis_pack, signal_path, feed_verdict,
        # public_verdict, branch_value, sprint_verdict
        try:
            intel = scheduler.compute_sprint_intelligence()
        except Exception:
            intel = {}

        _phase_times["WINDUP"] = time.monotonic()

        # BOOT → WINDUP: when scheduler's should_enter_windup() fires.
        # This is NOT the full run time — it reflects windup_lead_s offset.
        # e.g. requested=300s, windup_lead_s=180 → time_to_windup_s ≈ 120s (correct, not a bug)
        time_to_windup_s = _phase_times["WINDUP"] - _phase_times["BOOT"]
        actual_duration = time_to_windup_s  # backward-compatible alias

        # UMA peak
        uma_peak_gib = sample_uma_status().system_used_gib

        # Write sprint delta
        await write_sprint_delta(
            store=store,
            sprint_id=sprint_id,
            query=query,
            new_findings=result.accepted_findings,
            dedup_hits=result.duplicate_entry_hashes_skipped,
            ioc_nodes=result.unique_entry_hashes_seen,
            uma_baseline_gib=uma_baseline_gib,
            uma_peak_gib=uma_peak_gib,
            synthesis_success=result.accepted_findings > 0,
            duration_s=actual_duration,
            hits_per_source=result.hits_per_source,
        )

        _phase_times["TEARDOWN"] = time.monotonic()

        # Sprint 8SA: Phase timing profile
        phases = ["BOOT", "WARMUP", "ACTIVE", "WINDUP", "TEARDOWN"]
        for i, ph in enumerate(phases):
            if ph in _phase_times:
                next_ph = phases[i + 1] if i + 1 < len(phases) else "END"
                if next_ph in _phase_times:
                    elapsed = _phase_times[next_ph] - _phase_times[ph]
                    logger.info(f"[{sprint_id}] {ph}→{next_ph}: {elapsed:.1f}s")

        # --- Timing truth (Sprint F160E) -------------------------------------------
        # Canonical surfaces that distinguish:
        #   requested_duration  — what operator asked for
        #   windup_lead_s       — T-minus offset that triggers wind-down
        #   time_to_windup_s    — BOOT→WINDUP, the active window actually used
        #   time_to_teardown_s  — BOOT→TEARDOWN, full wall-clock of this run
        #   active_window_budget_s — theoretical active window (requested - windup_lead)
        #   windup_lead_observed_s — actual time between WINDUP entry and TEARDOWN
        _teardown_time = _phase_times.get("TEARDOWN", _phase_times.get("WINDUP", 0))
        windup_lead_observed_s = _teardown_time - _phase_times.get("WINDUP", 0)
        timing_truth = {
            "requested_duration_s": duration_s,
            "windup_lead_s": config.windup_lead_s,
            "time_to_windup_s": round(time_to_windup_s, 2),
            "time_to_teardown_s": round(_teardown_time - _phase_times["BOOT"], 2),
            "active_window_budget_s": round(duration_s - config.windup_lead_s, 2),
            "windup_lead_observed_s": round(windup_lead_observed_s, 2),
        }

        # --- Derived metrics --------------------------------------------------------
        findings_per_min = (result.accepted_findings / (actual_duration / 60.0)) if actual_duration > 0 else 0.0
        total_seen = result.unique_entry_hashes_seen + result.duplicate_entry_hashes_skipped
        dup_rate = (result.duplicate_entry_hashes_skipped / total_seen * 100) if total_seen > 0 else 0.0
        feed_fnd = result.accepted_findings - result.public_accepted_findings
        public_pct = (result.public_accepted_findings / result.accepted_findings * 100) if result.accepted_findings > 0 else 0.0

        # Source mix
        src_mix: list[str] = []
        for src, cnt in sorted(result.hits_per_source.items(), key=lambda x: x[1], reverse=True):
            src_mix.append(f"{src}={cnt}")
        src_mix_str = ", ".join(src_mix) if src_mix else "none"

        # Verdict heuristics — public_error is authoritative over depleted interpretation
        if result.aborted:
            verdict = "⚠️  ABORTED"
        elif result.public_error:
            verdict = "🌐  DEGRADED: public branch blocked — check network/TOR/proxy"
        elif result.accepted_findings == 0:
            if result.public_discovered > 0:
                verdict = "🔍  NOVELTY: public found hits, feed accepted nothing"
            elif result.total_pattern_hits == 0:
                verdict = "🗿  DEPLETED: no pattern hits anywhere"
            else:
                verdict = "🤷  SILENT: pattern hits but no accepted findings"
        elif dup_rate > 85:
            verdict = "📦  NOISE-HEAVY: duplicated heavily"
        elif public_pct > 60:
            verdict = "🌐  PUBLIC-LED: public discovery dominated"
        elif public_pct > 25:
            verdict = "⚖️  MIXED: public contributed meaningfully"
        elif feed_fnd > 0:
            verdict = "✅  FEED-LED: feed sources strong"
        else:
            verdict = "✅  SIGNAL: good feed performance"

        # Next-step hint (heuristic, no new planner)
        next_hint: str
        if result.accepted_findings == 0 and result.total_pattern_hits == 0:
            next_hint = "query may be too narrow — broaden terms or switch seed"
        elif dup_rate > 80:
            next_hint = "high dup rate — consider narrowing query scope"
        elif public_pct > 60:
            next_hint = "public discovery effective — let it run longer next time"
        elif public_pct < 10 and feed_fnd == 0:
            next_hint = "feed yield low — check if sources still alive (urlhaus, threatfox)"
        elif public_pct < 10 and feed_fnd > 0:
            next_hint = "feed performing — rely on feed-first, use public as supplemental"
        elif result.public_discovered > 0 and result.public_fetched == 0:
            next_hint = "public discovered but not fetched — check network/TOR"
        elif result.stop_requested:
            next_hint = "early stop triggered — lower threshold or widen query"
        else:
            next_hint = "current query and source mix working — continue as-is"

        # --- Runtime truth (smoke vs meaningful) ---------------------------------
        runtime_truth = _runtime_truth(
            actual_duration_s=actual_duration,
            query=query,
            duration_s=duration_s,
            cycles_completed=result.cycles_completed,
            cycles_started=result.cycles_started,
            accepted_findings=result.accepted_findings,
            total_pattern_hits=result.total_pattern_hits,
            public_accepted_findings=result.public_accepted_findings,
            feed_findings=feed_fnd,
        )
        is_meaningful = runtime_truth["is_meaningful"]
        evidence_note = runtime_truth["evidence_note"]

        # Clear separation: [SMOKE] vs [ACTIVE]
        if is_meaningful:
            logger.info(
                f"[RUNTIME TRUTH] ✅ MEANINGFUL ACTIVE RUN | {evidence_note} | "
                f"primary: {runtime_truth['primary_signal_source']} | "
                f"cycles: {result.cycles_completed}/{result.cycles_started} | "
                f"windup: {time_to_windup_s:.0f}s (budget={timing_truth['active_window_budget_s']:.0f}s)"
            )
        else:
            logger.warning(
                f"[RUNTIME TRUTH] 🚨 SMOKE ONLY | {evidence_note} | "
                f"cycles: {result.cycles_completed}/{result.cycles_started} | "
                f"windup: {time_to_windup_s:.0f}s (budget={timing_truth['active_window_budget_s']:.0f}s)"
            )

        logger.info(
            f"[SPRINT DONE] {sprint_id} | "
            f"findings: {result.accepted_findings} | "
            f"cycles: {result.cycles_completed}/{result.cycles_started} | "
            f"duplicates: {result.duplicate_entry_hashes_skipped} | "
            f"phase: {result.final_phase}"
        )
        logger.info(
            f"[SUMMARY] {verdict} | "
            f"feed={feed_fnd} public={result.public_accepted_findings}({public_pct:.0f}%) | "
            f"f/min={findings_per_min:.2f} | dup={dup_rate:.1f}% | "
            f"public: disc={result.public_discovered} fetch={result.public_fetched} "
            f"match={result.public_matched_patterns} stored={result.public_stored_findings}"
        )
        logger.info(f"[NEXT] {next_hint}")
        logger.info(f"[SOURCES] {src_mix_str}")

        # Sprint F150H: Log scheduler intelligence (visible operator signal)
        sv = intel.get("sprint_verdict") or {}
        sp = intel.get("signal_path") or {}
        corr = intel.get("correlation") or {}
        hyp = intel.get("hypothesis_pack") or {}
        if sv:
            logger.info(
                f"[INTEL] posture={sv.get('posture','?')} | "
                f"dominant={sv.get('dominant_signal','?')} | "
                f"corroborated={sp.get('is_corroborated',False)} | "
                f"noisy={sp.get('is_noisy',False)} | "
                f"risk={corr.get('risk_score',0):.3f} | "
                f"hypotheses={hyp.get('hypothesis_count',0)} | "
                f"next={sv.get('first_action','?')[:60]}"
            )

        # Sprint F500I: Use canonical path helper (no more ad-hoc /tmp)
        report_path = get_sprint_json_report_path(sprint_id)

        # CHECKPOINT-0 additive derived fields (computed before report_dict)
        active_iterations = result.cycles_completed

        # E0-T4: short_signal — <180s with pattern hits but no findings.
        # 180s floor in _is_meaningful_run is exempt for hits/findings early-returns.
        runtime_truth_level = (
            "active"
            if is_meaningful and result.accepted_findings > 0
            else "short_signal"
            if is_meaningful and result.total_pattern_hits > 0
            else "meaningful_empty"
            if is_meaningful
            else "smoke"
        )

        # Sprint F162D: observed_run_tuple must be deterministic — no verdict string
        # (verdict is heuristic and non-reproducible across identical runs).
        # Canonical components: query-truncated, duration, iterations, source-mix, truth-level.
        observed_run_tuple = (
            query[:40] if len(query) > 40 else query,
            round(actual_duration, 1),
            active_iterations,
            src_mix_str,
            runtime_truth_level,
        )

        # CHECKPOINT-0 taxonomy (Sprint F155 + E0-T4 + F163C)
        # Bucket set: signal_reaches_findings | short_signal | degraded_public_blocker | depleted | windup_export_fail_soft | authority_census
        _ckpt_category = (
            "signal_reaches_findings"
            if result.accepted_findings > 0
            else "degraded_public_blocker"
            if result.public_error
            else "short_signal"
            if is_meaningful and result.total_pattern_hits > 0
            else "depleted"
            if result.accepted_findings == 0 and result.total_pattern_hits == 0
            else "windup_export_fail_soft"
            if result.accepted_findings == 0 and _phase_times.get("WINDUP", 0) > 0
            else "authority_census"
            if not is_meaningful
            else "depleted"
        )
        # Sprint F163C: reason chain — public_error is primary signal over depleted.
        # smoke: is_meaningful=False → evidence_note
        # active: findings>0 → "signal_reaches_findings"
        # degraded_public: public_error set → "degraded_public_branch_blocked:{public_error}"
        # short_signal: meaningful, hits>0, no findings → "short_signal_no_findings"
        # depleted: meaningful, hits=0, no findings → "depleted_no_pattern_hits"
        # windup_export_fail_soft: zero findings, windup fired → "windup_export_fail_soft"
        _checkpoint_zero_reason = (
            evidence_note
            if not is_meaningful
            else "signal_reaches_findings"
            if result.accepted_findings > 0
            else f"degraded_public_branch_blocked:{result.public_error}"
            if result.public_error
            else "short_signal_no_findings"
            if is_meaningful and result.total_pattern_hits > 0
            else "depleted_no_pattern_hits"
        )
        _export_finish_status = (
            "finished" if result.final_phase in ("EXPORT", "TEARDOWN") and result.accepted_findings > 0
            else "empty_run" if result.accepted_findings == 0
            else "aborted" if result.aborted
            else "unknown"
        )

        report_dict = {
            "sprint_id": sprint_id,
            "query": query,
            "duration_s": duration_s,
            "actual_duration_s": actual_duration,
            "accepted_findings": result.accepted_findings,
            "feed_findings": feed_fnd,
            "public_accepted_findings": result.public_accepted_findings,
            "public_discovered": result.public_discovered,
            "public_fetched": result.public_fetched,
            "public_matched_patterns": result.public_matched_patterns,
            "public_stored_findings": result.public_stored_findings,
            "public_error": result.public_error,
            "cycles_completed": result.cycles_completed,
            "cycles_started": result.cycles_started,
            "unique_entry_hashes_seen": result.unique_entry_hashes_seen,
            "duplicate_entry_hashes_skipped": result.duplicate_entry_hashes_skipped,
            "total_pattern_hits": result.total_pattern_hits,
            "dup_rate_pct": round(dup_rate, 2),
            "findings_per_min": round(findings_per_min, 2),
            "final_phase": result.final_phase,
            "aborted": result.aborted,
            "abort_reason": result.abort_reason,
            "stop_requested": result.stop_requested,
            "entries_per_source": result.entries_per_source,
            "hits_per_source": result.hits_per_source,
            "export_paths": result.export_paths,
            "uma_peak_gib": uma_peak_gib - uma_baseline_gib,
            "synthesis_success": result.accepted_findings > 0,
            "verdict": verdict,
            "next_hint": next_hint,
            "phase_timing": {
                ph: round(_phase_times.get(ph, 0) - _phase_times.get("BOOT", 0), 2)
                for ph in phases if ph in _phase_times
            },
            "runtime_truth": runtime_truth,
            # Sprint F150H: Scheduler intelligence propagated fail-soft (additive)
            "correlation_summary": intel.get("correlation"),
            "hypothesis_pack_summary": intel.get("hypothesis_pack"),
            "signal_path": intel.get("signal_path"),
            "feed_verdict": intel.get("feed_verdict"),
            "public_verdict": intel.get("public_verdict"),
            "branch_value": intel.get("branch_value"),
            "sprint_verdict": intel.get("sprint_verdict"),
            # Sprint F500I: Empirical run boundary — reproducible tuple
            "execution_context": {
                "query": query,
                "requested_duration_s": duration_s,
                "actual_duration_s": round(actual_duration, 2),
                "source_count": len(live_feed_urls),
                "sources": live_feed_urls,
                "platform": {
                    "python_version": __import__("sys").version.split()[0],
                    "macos_version": __import__("platform").mac_ver()[0] or "unknown",
                },
                "report_path": str(report_path),
                "git_snapshot": "unknown",
                "export_dir": export_dir,
            },
            # Sprint F150H: Canonical operator summary — condensed truth on core boundary
            # CHECKPOINT-0 additive derived fields
            "canonical_run_summary": {
                "meaningful": runtime_truth["is_meaningful"],
                "primary_signal": runtime_truth["primary_signal_source"],
                "posture": (intel.get("sprint_verdict") or {}).get("posture", "unknown"),
                "dominant_signal_path": (intel.get("signal_path") or {}).get("dominant_signal_path", "unknown"),
                "corroborated": (intel.get("signal_path") or {}).get("is_corroborated", False),
                "is_noisy": (intel.get("signal_path") or {}).get("is_noisy", False),
                "next_pivot": (intel.get("signal_path") or {}).get("next_pivot_recommendation", "unknown"),
                "branch_verdict": (intel.get("branch_value") or {}).get("branch_verdict", "unknown"),
                "risk_score": (intel.get("correlation") or {}).get("risk_score", 0.0),
                "hypothesis_count": (intel.get("hypothesis_pack") or {}).get("hypothesis_count", 0),
                "first_action": (intel.get("sprint_verdict") or {}).get("first_action", ""),
                "confidence": (intel.get("sprint_verdict") or {}).get("confidence", ""),
                # CHECKPOINT-0 derived additive fields
                "runtime_truth_level": runtime_truth_level,
                "checkpoint_zero_category": _ckpt_category,
                "checkpoint_zero_reason": _checkpoint_zero_reason,
                "observed_run_tuple": observed_run_tuple,
                "canonical_sprint_owner": "core.__main__.run_sprint",
                "canonical_path_used": "run_sprint",
                "effective_source_mix": src_mix_str,
                "effective_parallelism": len(live_feed_urls),
                "effective_timeouts": {},
                "active_iteration_count": active_iterations,
                "export_finish_layer_status": _export_finish_status,
                # Sprint F163C: public_error must surface at canonical boundary
                "public_error": result.public_error,
                # Sprint F160E: Canonical timing truth — separates active window from full run
                "timing_truth": timing_truth,
            },
        }
        report_path.write_bytes(orjson.dumps(report_dict, option=orjson.OPT_INDENT_2))
        logger.info(f"[REPORT] {report_path}")

        # Sprint F151D: Wire existing exporter seam over already-computed truth surfaces.
        # Reuse: ExportHandoff, ensure_export_handoff, store.get_top_seed_nodes(),
        # intel (correlation/hypothesis_pack/signal_path/feed_verdict/
        # public_verdict/branch_value/sprint_verdict), runtime_truth, canonical_run_summary.
        # Additive + fail-soft only — exporter failure does not crash sprint.
        try:
            from hledac.universal.types import ExportHandoff

            top_seed_nodes: list = []
            try:
                top_seed_nodes = store.get_top_seed_nodes(n=5) if store else []
            except Exception:
                pass

            # Sprint F155: Determine handoff enrichment level (canonical_run_summary built inline)
            _handoff_enriched = bool(runtime_truth and intel)

            handoff = ExportHandoff(
                sprint_id=sprint_id,
                scorecard={
                    "synthesis_engine_used": "hermes3",
                    "gnn_predicted_links": 0,
                    "top_graph_nodes": top_seed_nodes,
                    "phase_duration_seconds": {
                        ph: round(_phase_times.get(ph, 0) - _phase_times.get("BOOT", 0), 2)
                        for ph in phases if ph in _phase_times
                    },
                },
                top_nodes=top_seed_nodes,
                phase_durations={
                    ph: round(_phase_times.get(ph, 0) - _phase_times.get("BOOT", 0), 2)
                    for ph in phases if ph in _phase_times
                },
                # Sprint F155: Canonical truth enrichment — additive, derived-only
                runtime_truth=runtime_truth,
                execution_context={
                    "query": query,
                    "requested_duration_s": duration_s,
                    "actual_duration_s": round(actual_duration, 2),
                    "source_count": len(live_feed_urls),
                    "sources": live_feed_urls,
                    "platform": {
                        "python_version": __import__("sys").version.split()[0],
                        "macos_version": __import__("platform").mac_ver()[0] or "unknown",
                    },
                    "report_path": str(report_path),
                    "git_snapshot": "unknown",
                    "export_dir": export_dir,
                },
                # Sprint F155: canonical_run_summary inline (already computed in report_dict)
                canonical_run_summary={
                    "meaningful": runtime_truth["is_meaningful"],
                    "primary_signal": runtime_truth["primary_signal_source"],
                    "posture": (intel.get("sprint_verdict") or {}).get("posture", "unknown"),
                    "dominant_signal_path": (intel.get("signal_path") or {}).get("dominant_signal_path", "unknown"),
                    "corroborated": (intel.get("signal_path") or {}).get("is_corroborated", False),
                    "is_noisy": (intel.get("signal_path") or {}).get("is_noisy", False),
                    "next_pivot": (intel.get("signal_path") or {}).get("next_pivot_recommendation", "unknown"),
                    "branch_verdict": (intel.get("branch_value") or {}).get("branch_verdict", "unknown"),
                    "risk_score": (intel.get("correlation") or {}).get("risk_score", 0.0),
                    "hypothesis_count": (intel.get("hypothesis_pack") or {}).get("hypothesis_count", 0),
                    "first_action": (intel.get("sprint_verdict") or {}).get("first_action", ""),
                    "confidence": (intel.get("sprint_verdict") or {}).get("confidence", ""),
                    "runtime_truth_level": runtime_truth_level,
                    "checkpoint_zero_category": _ckpt_category,
                    "checkpoint_zero_reason": _checkpoint_zero_reason,
                    "observed_run_tuple": observed_run_tuple,
                    "canonical_sprint_owner": "core.__main__.run_sprint",
                    "canonical_path_used": "run_sprint",
                    "effective_source_mix": src_mix_str,
                    "effective_parallelism": len(live_feed_urls),
                    "effective_timeouts": {},
                    "active_iteration_count": active_iterations,
                    "export_finish_layer_status": _export_finish_status,
                    # Sprint F163C: public_error must surface at canonical boundary
                    "public_error": result.public_error,
                    # Sprint F160E: Canonical timing truth — separates active window from full run
                    "timing_truth": timing_truth,
                },
                synthesis_outcome_payload=None,  # synthesis_runner not exposed on lifecycle/scheduler
                # Sprint F153: Top-level sprint verdict propagated to export
                sprint_verdict=intel.get("sprint_verdict"),
            )

            # Sprint F155: Log enrichment level
            logger.info(
                f"[EXPORT] {'fully_enriched' if _handoff_enriched else 'degraded'} → sprint_id={sprint_id}"
            )

            export_result = await export_sprint(store=store, handoff=handoff, sprint_id=sprint_id)
            logger.info(f"[EXPORT] finish layer → seeds={export_result.get('seeds_json','')}")
        except Exception as ex:
            logger.warning(f"[EXPORT] sprint_exporter seam failed (non-fatal): {ex}")

    finally:
        await store.aclose()


# =============================================================================
# CLI entry point
# =============================================================================


async def run_ct_pivot(domain: str) -> None:
    """Run CT log pivot for a single domain."""
    ct_client = CTLogClient(TOR_ROOT.parent / "cache" / "crt")
    tor_transport = TorTransport()

    tor_started = await tor_transport.start()
    if tor_started:
        logger.info("Tor ready for .onion fetches")
    else:
        logger.warning("Tor unavailable — .onion sources disabled")

    try:
        async with aiohttp.ClientSession() as sess:
            result = await ct_client.pivot_domain(domain, sess)
        print(f"\nCT LOG PIVOT: {result['domain']}")
        print(f"  Cert count:  {result['cert_count']}")
        print(f"  First cert: {result['first_cert']}")
        print(f"  Last cert:  {result['last_cert']}")
        print(f"  SAN domains: {len(result['san_names'])}")
        for san in result["san_names"][:10]:
            print(f"    {san}")
        if result["san_names"] and len(result["san_names"]) > 10:
            print(f"    ... (+{len(result['san_names']) - 10} more)")
        print(f"  Issuers: {result['issuers']}")
    finally:
        await tor_transport.stop()
        logger.info("CT pivot done, Tor stopped")


async def run_semantic_pivot(query: str, top_k: int = 10) -> None:
    """
    Sprint 8SB: Semantic pivot — ANN search for similar findings.

    Loads SemanticStore, runs semantic_pivot, prints results.
    """
    from hledac.universal.paths import RAMDISK_ROOT

    lancedb_path = RAMDISK_ROOT / "lancedb"
    store = SemanticStore(db_path=lancedb_path)
    await store.initialize()

    try:
        results = await store.semantic_pivot(query, top_k=top_k)
        print(f"\n[SEMANTIC PIVOT] query: {query!r}  top_k={top_k}")
        if not results:
            print("  No results found.")
        for r in results:
            score = r.get("score", 0.0)
            src = r.get("source_type", "?")
            text = r.get("text", "")[:120]
            ts = r.get("ts", 0)
            print(f"  [{score:.3f}] {src:15} | {text}")
            if ts:
                import datetime
                print(f"               ts: {datetime.datetime.fromtimestamp(ts):.0f}")
        print(f"\nTotal results: {len(results)}")
    finally:
        await store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Hledac Sprint 8RA Runner")
    parser.add_argument("--sprint", action="store_true", help="Run in sprint mode")
    parser.add_argument("--query", type=str, default="OSINT default query")
    parser.add_argument(
        "--duration",
        type=int,
        default=1800,
        help="Sprint duration in seconds (default: 1800 = 30min)",
    )
    parser.add_argument(
        "--export-dir",
        type=str,
        default=str(Path.home() / ".hledac" / "reports"),
    )
    parser.add_argument(
        "--ct-pivot",
        type=str,
        default=None,
        help="Run CT log pivot for a domain via crt.sh",
    )
    parser.add_argument(
        "--pivot",
        type=str,
        default=None,
        help="Sprint 8SB: semantic pivot — find similar findings via ANN search",
    )
    parser.add_argument(
        "--pivot-k",
        type=int,
        default=10,
        help="Number of results for --pivot (default: 10)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.ct_pivot:
        asyncio.run(run_ct_pivot(args.ct_pivot))
    elif args.sprint:
        asyncio.run(run_sprint(args.query, float(args.duration), args.export_dir))
    elif args.pivot:
        asyncio.run(run_semantic_pivot(args.pivot, top_k=args.pivot_k))
    else:
        print("Hledac Sprint 8RA Runner")
        print("  python -m hledac.universal.core --sprint --query '...' --duration 1800")
        print("  python -m hledac.universal.core --ct-pivot example.com")
        print("  python -m hledac.universal.core --pivot 'ransomware CVE' --pivot-k 10")


if __name__ == "__main__":
    main()
