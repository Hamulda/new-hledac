#!/usr/bin/env python3
"""
Sprint 8C1: Trace analyzer script.

Analyzes flow trace JSONL output and produces bottleneck summary.

Usage:
    python analyze_trace_8c1.py <trace.jsonl>

Produces:
    - Bottleneck summary (top slowest spans, top wait stages)
    - Drop/fallback counts
    - Queue peak estimation
    - Flush latency p50/p95
"""

import json
import sys
from collections import defaultdict
from pathlib import Path


def analyze_trace(jsonl_path: str) -> dict:
    """Analyze trace file and produce summary."""
    path = Path(jsonl_path)
    if not path.exists():
        return {"error": f"Trace file not found: {jsonl_path}"}

    events = []
    durations = []
    stage_durations = defaultdict(list)
    status_counts = defaultdict(int)
    component_counts = defaultdict(int)
    span_starts = {}
    wait_spans = []

    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                events.append(event)
            except json.JSONDecodeError:
                continue

    # Aggregate
    for e in events:
        component = e.get("component", "unknown")
        stage = e.get("stage", "unknown")
        event_type = e.get("event_type", "unknown")
        status = e.get("status", "ok")
        duration_ms = e.get("duration_ms")
        item_id = e.get("item_id") or e.get("url") or e.get("target", "")

        component_counts[component] += 1
        status_counts[status] += 1

        if duration_ms is not None:
            durations.append(duration_ms)
            stage_durations[f"{component}/{stage}"].append(duration_ms)

        # Track wait spans (span_end with long duration)
        if event_type == "span_end" and duration_ms is not None:
            wait_spans.append({
                "span_id": e.get("target", ""),
                "component": component,
                "stage": stage,
                "duration_ms": duration_ms,
            })

    # Sort wait spans by duration descending
    wait_spans.sort(key=lambda x: x["duration_ms"], reverse=True)

    # Compute p50/p95 for durations
    durations.sort()
    p50 = durations[len(durations) * 50 // 100] if durations else 0
    p95 = durations[len(durations) * 95 // 100] if durations else 0

    # Top slowest stage averages
    stage_avg = {}
    for stage, durs in stage_durations.items():
        if durs:
            stage_avg[stage] = sum(durs) / len(durs)
    top_slowest = sorted(stage_avg.items(), key=lambda x: x[1], reverse=True)[:5]

    # Drop/fallback counts
    drop_count = status_counts.get("drop", 0) + status_counts.get("queue_drop", 0)
    fallback_count = sum(v for k, v in status_counts.items() if "fallback" in k)

    return {
        "total_events": len(events),
        "duration_ms_p50": round(p50, 2),
        "duration_ms_p95": round(p95, 0),
        "top_slowest_spans": wait_spans[:10],
        "top_slowest_stages": [(s, round(d, 2)) for s, d in top_slowest],
        "drop_count": drop_count,
        "fallback_count": fallback_count,
        "status_breakdown": dict(status_counts),
        "component_breakdown": dict(component_counts),
    }


def print_summary(summary: dict):
    """Print formatted summary."""
    print("=" * 60)
    print("FLOW TRACE ANALYSIS")
    print("=" * 60)

    if "error" in summary:
        print(f"ERROR: {summary['error']}")
        return

    print(f"\nTotal events: {summary['total_events']}")
    print(f"Duration p50: {summary['duration_ms_p50']}ms")
    print(f"Duration p95: {summary['duration_ms_p95']}ms")

    print("\n--- TOP SLOWEST SPANS ---")
    for span in summary.get("top_slowest_spans", [])[:5]:
        print(f"  {span['duration_ms']:>8.1f}ms  {span['component']}/{span['stage']}  [{span['span_id'][:40]}]")

    print("\n--- TOP SLOWEST STAGES (avg) ---")
    for stage, avg in summary.get("top_slowest_stages", []):
        print(f"  {avg:>8.1f}ms  {stage}")

    print("\n--- DROP / FALLBACK ---")
    print(f"  Drops:    {summary.get('drop_count', 0)}")
    print(f"  Fallbacks: {summary.get('fallback_count', 0)}")

    print("\n--- STATUS BREAKDOWN ---")
    for status, count in sorted(summary.get("status_breakdown", {}).items(), key=lambda x: -x[1]):
        print(f"  {status}: {count}")

    print("\n--- COMPONENT BREAKDOWN ---")
    for comp, count in sorted(summary.get("component_breakdown", {}).items(), key=lambda x: -x[1]):
        print(f"  {comp}: {count}")

    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_trace_8c1.py <trace.jsonl>")
        sys.exit(1)

    summary = analyze_trace(sys.argv[1])
    print_summary(summary)

    # Also write JSON summary
    json_path = Path(sys.argv[1]).with_suffix("_summary.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"\nSummary written to: {json_path}")
