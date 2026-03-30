#!/usr/bin/env python3
"""
Sprint 8C3: Extended trace analyzer script.

Analyzes flow trace JSONL output and produces research-effectiveness
breadth, depth, quality/yield funnel, and anti-bot friction funnel metrics.

Usage:
    python analyze_trace_8c3.py <trace.jsonl>

Produces:
    - source_family_count / source_family_hhi
    - unindexed_source_hits, archive_hits, passive_hits
    - hidden_service_hits, decentralized_hits
    - challenge_issued_rate, challenge_solve_rate, challenge_loop_rate
    - fallback_rate
    - fetch_to_evidence_conversion_rate
    - avg_bytes_per_finding
    - top_bottleneck_stages, top_drop_reasons, top_fallback_reasons
"""

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set


def analyze_trace(jsonl_path: str) -> Dict[str, Any]:
    """Analyze trace file and produce research-effectiveness summary."""
    path = Path(jsonl_path)
    if not path.exists():
        return {"error": f"Trace file not found: {jsonl_path}"}

    events: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not events:
        return {"error": "No events found in trace file"}

    # =====================================================================
    # A) SOURCE FUNNEL AGGREGATION
    # =====================================================================
    source_family_counts: Dict[str, int] = defaultdict(int)
    source_accepted: Set[str] = set()
    source_dedup_dropped: Dict[str, int] = defaultdict(int)
    source_by_family: Dict[str, Set[str]] = defaultdict(set)

    # =====================================================================
    # B) CHALLENGE / ANTI-BOT FUNNEL
    # =====================================================================
    challenge_issued: int = 0
    challenge_passed: int = 0
    challenge_failed: int = 0
    challenge_loop: int = 0
    clearance_reused: int = 0

    # =====================================================================
    # C) EVIDENCE / QUALITY FUNNEL
    # =====================================================================
    evidence_emitted: int = 0
    evidence_corroborated: int = 0
    evidence_rejected_low_quality: int = 0
    evidence_flush_persisted: int = 0
    bytes_in_total: int = 0
    bytes_out_total: int = 0

    # =====================================================================
    # D) FETCH STATS
    # =====================================================================
    fetch_starts: int = 0
    fetch_ends: int = 0
    fetch_errors: int = 0
    fallback_after_403: int = 0
    fallback_after_429: int = 0
    provider_fallbacks: int = 0

    # =====================================================================
    # E) PERFORMANCE / QUEUE
    # =====================================================================
    queue_snapshots: List[Dict[str, Any]] = []
    periodic_snapshots: List[Dict[str, Any]] = []
    transport_mix: Dict[str, int] = defaultdict(int)

    # =====================================================================
    # F) STATUS / DROP TRACKING
    # =====================================================================
    status_counts: Dict[str, int] = defaultdict(int)
    stage_counts: Dict[str, int] = defaultdict(int)
    stage_durations: Dict[str, List[float]] = defaultdict(list)
    dedup_reasons: Dict[str, int] = defaultdict(int)
    fallback_reasons: Dict[str, int] = defaultdict(int)

    # =====================================================================
    # G) QUALITY TIERS
    # =====================================================================
    quality_tier_counts: Dict[str, int] = defaultdict(int)
    corroboration_keys: Dict[str, int] = defaultdict(int)

    # =====================================================================
    # H) HIDDEN SERVICE / SPECIAL SOURCE FLAGS
    # =====================================================================
    hidden_service_hits: int = 0
    archive_hits: int = 0
    passive_hits: int = 0
    unindexed_candidates: int = 0
    decentralized_hits: int = 0

    for e in events:
        component = e.get("component", "unknown")
        stage = e.get("stage", "unknown")
        event_type = e.get("event_type", "unknown")
        status = e.get("status", "ok")
        metadata = e.get("metadata", {})
        url = e.get("url", "")

        status_counts[status] += 1
        stage_counts[f"{component}/{stage}"] += 1

        duration_ms = e.get("duration_ms")
        if duration_ms is not None:
            stage_durations[f"{component}/{stage}"].append(duration_ms)

        # ---- Source funnel ----
        if event_type == "source_accepted":
            family = e.get("target", "unknown")
            source_family_counts[family] += 1
            if url:
                source_accepted.add(url)
                source_by_family[family].add(url)
            if metadata.get("is_hidden_service"):
                hidden_service_hits += 1
            if metadata.get("is_archive_hit"):
                archive_hits += 1
            if metadata.get("is_passive_hit"):
                passive_hits += 1
            if metadata.get("is_unindexed_candidate"):
                unindexed_candidates += 1
            if metadata.get("is_decentralized_hit"):
                decentralized_hits += 1
            if metadata.get("bytes_in"):
                bytes_in_total += int(metadata["bytes_in"])
            if metadata.get("bytes_out"):
                bytes_out_total += int(metadata["bytes_out"])

        elif event_type == "source_dedup_dropped":
            family = e.get("target", "unknown")
            source_dedup_dropped[family] += 1
            reason = metadata.get("dedup_reason", "unknown")
            dedup_reasons[reason] += 1

        # ---- Challenge funnel ----
        elif event_type == "challenge_issued":
            challenge_issued += 1
        elif event_type == "challenge_passed":
            challenge_passed += 1
        elif event_type == "challenge_failed":
            challenge_failed += 1
        elif event_type == "challenge_loop_detected":
            challenge_loop += 1
        elif event_type == "clearance_reused":
            clearance_reused += 1

        # ---- Evidence funnel ----
        elif event_type in ("evidence_emitted", "evidence_append_ext"):
            evidence_emitted += 1
            if metadata.get("evidence_quality_tier"):
                quality_tier_counts[metadata["evidence_quality_tier"]] += 1
        elif event_type == "evidence_corroborated":
            evidence_corroborated += 1
            key = metadata.get("corroboration_key", "")
            if key:
                corroboration_keys[key] += 1
        elif event_type == "evidence_rejected_low_quality":
            evidence_rejected_low_quality += 1
        elif event_type == "evidence_flush_persisted":
            evidence_flush_persisted += 1
            if metadata.get("bytes_written"):
                bytes_out_total += int(metadata["bytes_written"])

        # ---- Fetch funnel ----
        elif event_type == "fetch_start":
            fetch_starts += 1
        elif event_type == "fetch_end":
            fetch_ends += 1
            if status in ("error", "fail", "blocked"):
                fetch_errors += 1
        elif event_type == "fallback_after_403":
            fallback_after_403 += 1
        elif event_type == "fallback_after_429":
            fallback_after_429 += 1
        elif event_type == "provider_fallback":
            provider_fallbacks += 1
            reason = metadata.get("fallback_reason", "unknown")
            fallback_reasons[reason] += 1

        # ---- Snapshots ----
        elif event_type == "periodic_flow_snapshot":
            periodic_snapshots.append(metadata)
        elif event_type == "queue_snapshot":
            queue_snapshots.append(metadata)
        elif event_type == "transport_mix_snapshot":
            tc = metadata.get("transport_counts", {})
            for k, v in tc.items():
                transport_mix[k] += v

    # =====================================================================
    # COMPUTE DERIVED METRICS
    # =====================================================================

    total_sources = sum(source_family_counts.values())
    total_dedup = sum(source_dedup_dropped.values())
    total_fetch_attempts = fetch_starts or fetch_ends

    # Source HHI (Herfindahl index of source family distribution)
    def _compute_hhi(counter: Dict[str, int]) -> float:
        total = sum(counter.values())
        if total == 0:
            return 0.0
        return sum((v / total) ** 2 for v in counter.values())

    source_family_hhi = _compute_hhi(source_family_counts)

    # Challenge funnel rates
    total_challenges = challenge_issued
    challenge_issued_rate = challenge_issued / total_fetch_attempts if total_fetch_attempts else 0.0
    challenge_solve_rate = challenge_passed / total_challenges if total_challenges else 0.0
    challenge_loop_rate = challenge_loop / total_challenges if total_challenges else 0.0

    # Fallback rate
    total_fallbacks = fallback_after_403 + fallback_after_429 + provider_fallbacks
    fallback_rate = total_fallbacks / total_fetch_attempts if total_fetch_attempts else 0.0

    # Fetch-to-evidence conversion rate
    fetch_to_evidence_rate = evidence_emitted / total_fetch_attempts if total_fetch_attempts else 0.0

    # Avg bytes per finding
    avg_bytes_in = bytes_in_total / evidence_emitted if evidence_emitted else 0.0
    avg_bytes_out = bytes_out_total / evidence_emitted if evidence_emitted else 0.0

    # Top bottleneck stages (by average duration)
    stage_avg_dur = {
        k: sum(v) / len(v) if v else 0.0
        for k, v in stage_durations.items()
    }
    top_bottleneck_stages = sorted(stage_avg_dur.items(), key=lambda x: -x[1])[:5]

    # Top drop reasons
    top_dedup_reasons = sorted(dedup_reasons.items(), key=lambda x: -x[1])[:5]
    top_fallback_reasons = sorted(fallback_reasons.items(), key=lambda x: -x[1])[:5]

    # Top status drops
    drop_statuses = ["drop", "rejected", "blocked", "error", "loop"]
    top_drop_statuses = {
        k: v for k, v in sorted(status_counts.items(), key=lambda x: -x[1])
        if k in drop_statuses
    }

    # Periodics average
    avg_queue_depth = 0.0
    avg_frontier_size = 0.0
    avg_active_fetches = 0.0
    avg_rss_mb = 0.0
    if periodic_snapshots:
        avg_queue_depth = sum(p.get("queue_depth", 0) for p in periodic_snapshots) / len(periodic_snapshots)
        avg_frontier_size = sum(p.get("frontier_size", 0) for p in periodic_snapshots) / len(periodic_snapshots)
        avg_active_fetches = sum(p.get("active_fetches", 0) for p in periodic_snapshots) / len(periodic_snapshots)
        rss_vals = [p["rss_mb"] for p in periodic_snapshots if "rss_mb" in p]
        avg_rss_mb = sum(rss_vals) / len(rss_vals) if rss_vals else 0.0

    return {
        # Summary counts
        "total_events": len(events),
        "total_sources": total_sources,
        "total_dedup_drops": total_dedup,
        "total_fetch_attempts": total_fetch_attempts,
        "total_evidence_emitted": evidence_emitted,
        "total_evidence_corroborated": evidence_corroborated,
        "total_evidence_rejected": evidence_rejected_low_quality,

        # A) Source breadth
        "source_family_counts": dict(source_family_counts),
        "source_family_hhi": round(source_family_hhi, 4),
        "unique_sources_accepted": len(source_accepted),
        "source_dedup_drops_by_family": dict(source_dedup_dropped),

        # B) Hidden/unconventional source hits
        "unindexed_source_hits": unindexed_candidates,
        "archive_hits": archive_hits,
        "passive_hits": passive_hits,
        "hidden_service_hits": hidden_service_hits,
        "decentralized_hits": decentralized_hits,

        # C) Challenge / anti-bot funnel
        "challenge_issued": challenge_issued,
        "challenge_passed": challenge_passed,
        "challenge_failed": challenge_failed,
        "challenge_loop": challenge_loop,
        "clearance_reused": clearance_reused,
        "challenge_issued_rate": round(challenge_issued_rate, 4),
        "challenge_solve_rate": round(challenge_solve_rate, 4),
        "challenge_loop_rate": round(challenge_loop_rate, 4),

        # D) Fallback funnel
        "fallback_after_403": fallback_after_403,
        "fallback_after_429": fallback_after_429,
        "provider_fallbacks": provider_fallbacks,
        "fallback_rate": round(fallback_rate, 4),
        "top_fallback_reasons": top_fallback_reasons,

        # E) Quality / yield funnel
        "fetch_to_evidence_conversion_rate": round(fetch_to_evidence_rate, 4),
        "quality_tier_counts": dict(quality_tier_counts),
        "avg_bytes_in_per_finding": round(avg_bytes_in, 1),
        "avg_bytes_out_per_finding": round(avg_bytes_out, 1),

        # F) Bottlenecks
        "top_bottleneck_stages": [(s, round(d, 2)) for s, d in top_bottleneck_stages],
        "top_drop_reasons": top_dedup_reasons,
        "top_fallback_reasons_list": top_fallback_reasons,
        "top_drop_statuses": top_drop_statuses,

        # G) System health snapshots
        "periodic_snapshot_count": len(periodic_snapshots),
        "avg_queue_depth": round(avg_queue_depth, 2),
        "avg_frontier_size": round(avg_frontier_size, 2),
        "avg_active_fetches": round(avg_active_fetches, 2),
        "avg_rss_mb": round(avg_rss_mb, 1),
        "transport_mix": dict(transport_mix),

        # H) Status breakdown
        "status_breakdown": dict(status_counts),
        "stage_breakdown": dict(stage_counts),
    }


def print_summary(summary: Dict[str, Any]) -> None:
    """Print formatted research-effectiveness summary."""
    print("=" * 70)
    print("SPRINT 8C3 — FLOW TRACE RESEARCH-EFFECTIVENESS SUMMARY")
    print("=" * 70)

    if "error" in summary:
        print(f"ERROR: {summary['error']}")
        return

    print(f"\n--- OVERALL ---")
    print(f"  Total events:            {summary['total_events']}")
    print(f"  Total fetch attempts:    {summary['total_fetch_attempts']}")
    print(f"  Total sources accepted:  {summary['total_sources']}")
    print(f"  Unique sources:          {summary['unique_sources_accepted']}")
    print(f"  Evidence emitted:        {summary['total_evidence_emitted']}")

    print(f"\n--- A) SOURCE BREADTH (Research Breadth) ---")
    print(f"  source_family_hhi:       {summary['source_family_hhi']}")
    for fam, cnt in sorted(summary["source_family_counts"].items(), key=lambda x: -x[1]):
        print(f"    {fam}: {cnt}")
    print(f"  Unindexed hits:          {summary['unindexed_source_hits']}")
    print(f"  Archive hits:            {summary['archive_hits']}")
    print(f"  Passive hits:            {summary['passive_hits']}")
    print(f"  Hidden service hits:      {summary['hidden_service_hits']}")
    print(f"  Decentralized hits:      {summary['decentralized_hits']}")

    print(f"\n--- B) CHALLENGE FUNNEL (Anti-Bot Friction) ---")
    print(f"  Challenges issued:       {summary['challenge_issued']}")
    print(f"  Challenges passed:       {summary['challenge_passed']}")
    print(f"  Challenges failed:       {summary['challenge_failed']}")
    print(f"  Challenge loops:         {summary['challenge_loop']}")
    print(f"  Clearance reused:         {summary['clearance_reused']}")
    print(f"  challenge_issued_rate:   {summary['challenge_issued_rate']:.2%}")
    print(f"  challenge_solve_rate:   {summary['challenge_solve_rate']:.2%}")
    print(f"  challenge_loop_rate:     {summary['challenge_loop_rate']:.2%}")

    print(f"\n--- C) FALLBACK FUNNEL ---")
    print(f"  Fallback after 403:     {summary['fallback_after_403']}")
    print(f"  Fallback after 429:     {summary['fallback_after_429']}")
    print(f"  Provider fallbacks:      {summary['provider_fallbacks']}")
    print(f"  fallback_rate:           {summary['fallback_rate']:.2%}")
    print(f"  Top fallback reasons:")
    for reason, cnt in summary.get("top_fallback_reasons", [])[:3]:
        print(f"    {reason}: {cnt}")

    print(f"\n--- D) QUALITY / YIELD FUNNEL ---")
    print(f"  fetch_to_evidence_rate: {summary['fetch_to_evidence_conversion_rate']:.2%}")
    print(f"  Evidence corroborated: {summary['total_evidence_corroborated']}")
    print(f"  Evidence rejected:      {summary['total_evidence_rejected']}")
    print(f"  avg_bytes_in/finding:   {summary['avg_bytes_in_per_finding']:.1f}")
    print(f"  avg_bytes_out/finding:  {summary['avg_bytes_out_per_finding']:.1f}")
    print(f"  Quality tier counts:")
    for tier, cnt in sorted(summary["quality_tier_counts"].items(), key=lambda x: -x[1]):
        print(f"    {tier}: {cnt}")

    print(f"\n--- E) BOTTLENECKS ---")
    print(f"  Top slowest stages (avg ms):")
    for stage, dur in summary.get("top_bottleneck_stages", [])[:5]:
        print(f"    {dur:>8.1f}ms  {stage}")
    print(f"  Top drop reasons:")
    for reason, cnt in summary.get("top_drop_reasons", [])[:5]:
        print(f"    {reason}: {cnt}")

    print(f"\n--- F) SYSTEM HEALTH ---")
    print(f"  Periodic snapshots:      {summary['periodic_snapshot_count']}")
    print(f"  avg_queue_depth:        {summary['avg_queue_depth']:.2f}")
    print(f"  avg_frontier_size:      {summary['avg_frontier_size']:.2f}")
    print(f"  avg_active_fetches:     {summary['avg_active_fetches']:.2f}")
    print(f"  avg_rss_mb:             {summary['avg_rss_mb']:.1f}")
    print(f"  Transport mix:")
    for t, c in sorted(summary["transport_mix"].items(), key=lambda x: -x[1]):
        print(f"    {t}: {c}")

    print(f"\n--- G) STATUS BREAKDOWN ---")
    for status, cnt in sorted(summary["status_breakdown"].items(), key=lambda x: -x[1])[:10]:
        print(f"  {status}: {cnt}")

    print("=" * 70)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_trace_8c3.py <trace.jsonl>")
        sys.exit(1)

    summary = analyze_trace(sys.argv[1])
    print_summary(summary)

    # Also write JSON summary
    json_path = Path(sys.argv[1]).with_suffix("_8c3_summary.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"\nSummary written to: {json_path}")
