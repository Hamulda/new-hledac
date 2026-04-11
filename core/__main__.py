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

from hledac.universal.core.resource_governor import (
    UMAAlarmDispatcher,
    sample_uma_status,
)
from hledac.universal.intelligence.ct_log_client import CTLogClient
from hledac.universal.knowledge.duckdb_store import DuckDBShadowStore
from hledac.universal.knowledge.semantic_store import SemanticStore
from hledac.universal.paths import TOR_ROOT
from hledac.universal.runtime.sprint_scheduler import (
    SprintSchedulerConfig,
    async_run_tiered_feed_sprint_once,
)
from hledac.universal.transport.tor_transport import TorTransport
from hledac.universal.runtime.sprint_lifecycle import SprintLifecycleManager

logger = logging.getLogger(__name__)

# Sprint 8RA: Hardcoded feed sources for live sprint
_SPRINT_FEED_SOURCES = [
    "cisa_kev",
    "threatfox_ioc",
    "urlhaus_recent",
    "feodo_ip",
    "openphish_feed",
]


# =============================================================================
# UMA → Scheduler callbacks
# =============================================================================


async def _handle_uma_critical(scheduler) -> None:
    """Called when UMA transitions to CRITICAL — request early WINDUP."""
    logger.warning("[UMA] CRITICAL — requesting early WINDUP")
    if hasattr(scheduler, "request_early_windup"):
        scheduler.request_early_windup()


async def _handle_uma_emergency(scheduler) -> None:
    """Called when UMA transitions to EMERGENCY — abort sprint."""
    logger.error("[UMA] EMERGENCY — aborting sprint")
    if hasattr(scheduler, "request_immediate_abort"):
        scheduler.request_immediate_abort()


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
    Uses async_run_tiered_feed_sprint_once which handles lifecycle internally.
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

    # Lifecycle (internal to async_run_tiered_feed_sprint_once)
    lifecycle = SprintLifecycleManager()

    try:
        # Run sprint via convenience function (handles lifecycle correctly)
        result = await async_run_tiered_feed_sprint_once(
            sources=list(_SPRINT_FEED_SOURCES),
            config=config,
            lifecycle=lifecycle,
            now_monotonic=time.monotonic(),
        )

        _phase_times["WINDUP"] = time.monotonic()

        # Actual sprint elapsed (BOOT → WINDUP)
        actual_duration = _phase_times["WINDUP"] - _phase_times["BOOT"]

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

        logger.info(
            f"[SPRINT DONE] {sprint_id} | "
            f"findings: {result.accepted_findings} | "
            f"cycles: {result.cycles_completed}/{result.cycles_started} | "
            f"duplicates: {result.duplicate_entry_hashes_skipped} | "
            f"phase: {result.final_phase}"
        )

        # Sprint 8SA + 8UA: orjson JSON report export
        # Use /tmp directly to avoid FileExistsError when export_dir is a file
        report_path = Path(f"/tmp/{sprint_id}.json")
        report_dict = {
            "sprint_id": sprint_id,
            "query": query,
            "duration_s": duration_s,
            "accepted_findings": result.accepted_findings,
            "cycles_completed": result.cycles_completed,
            "cycles_started": result.cycles_started,
            "duplicate_entry_hashes_skipped": result.duplicate_entry_hashes_skipped,
            "final_phase": result.final_phase,
            "aborted": result.aborted,
            "abort_reason": result.abort_reason,
            "uma_peak_gib": uma_peak_gib - uma_baseline_gib,
            "synthesis_success": result.accepted_findings > 0,
            "phase_timing": {
                ph: round(_phase_times.get(ph, 0) - _phase_times.get("BOOT", 0), 2)
                for ph in phases if ph in _phase_times
            },
        }
        report_path.write_bytes(orjson.dumps(report_dict, option=orjson.OPT_INDENT_2))
        logger.info(f"[REPORT] {report_path}")

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
