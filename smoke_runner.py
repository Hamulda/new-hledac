"""
Smoke Runner - Lightweight network harness for testing
=====================================================

A minimal smoke test runner that uses the orchestrator (thin spine) + coordinators.
Strict budgets, produces bounded JSON summary, never logs raw text.

This module does nothing unless explicitly called.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Hard-coded tiny budgets (NOT user configurable)
MAX_URLS = 3
MAX_DEEP_READS = 1
MAX_SNAPSHOTS = 1
MAX_RUNTIME_SECS = 20


@dataclass
class SmokeConfig:
    """Smoke runner configuration with hard-coded tiny budgets."""
    max_urls: int = MAX_URLS
    max_deep_reads: int = MAX_DEEP_READS
    max_snapshots: int = MAX_SNAPSHOTS
    max_runtime_secs: int = MAX_RUNTIME_SECS


@dataclass
class SmokeRunResult:
    """Bounded smoke run result."""
    run_id: str
    query: str
    urls_fetched: int = 0
    evidence_count: int = 0
    ledger_events: List[Dict[str, Any]] = field(default_factory=list)
    tool_exec_events: List[Dict[str, Any]] = field(default_factory=list)
    metrics_snapshots: Dict[str, Any] = field(default_factory=dict)
    stop_reason: Optional[str] = None
    archive_escalations: int = 0
    resume_used: bool = False
    runtime_seconds: float = 0.0
    timestamp: str = ""


def run_smoke(
    query: str,
    seeds: List[str],
    run_id: Optional[str] = None,
    output_dir: Optional[str] = None,
    mock_network: bool = True,
) -> Dict[str, Any]:
    """
    Run a smoke test with strict budgets.

    Args:
        query: Research query
        seeds: Initial seed URLs
        run_id: Optional run ID (generated if not provided)
        output_dir: Optional output directory for run artifacts
        mock_network: If True, uses mocked network layer

    Returns:
        Bounded dict summary:
        {
            run_id, urls_fetched, evidence_count, ledger_events, tool_exec_events,
            metrics_snapshots, stop_reason, archive_escalations, resume_used
        }
    """
    if run_id is None:
        run_id = f"smoke_{uuid.uuid4().hex[:8]}"

    if output_dir is None:
        output_dir = os.path.join(os.getcwd(), ".omc", "smoke_runs", run_id)
    else:
        output_dir = os.path.join(output_dir, run_id)

    os.makedirs(output_dir, exist_ok=True)

    logger.info(f"Starting smoke run {run_id} with query: {query[:50]}...")

    result = asyncio.run(_run_smoke_async(
        query=query,
        seeds=seeds,
        run_id=run_id,
        output_dir=output_dir,
        mock_network=mock_network,
    ))

    summary_path = os.path.join(output_dir, "summary.json")
    with open(summary_path, "w") as f:
        json.dump(result, f, indent=2, default=str)

    logger.info(f"Smoke run {run_id} complete: {result.get('stop_reason')}")

    return result


async def _run_smoke_async(
    query: str,
    seeds: List[str],
    run_id: str,
    output_dir: str,
    mock_network: bool,
) -> Dict[str, Any]:
    config = SmokeConfig()
    start_time = time.time()

    result = {
        "run_id": run_id,
        "query": query,
        "urls_fetched": 0,
        "evidence_count": 0,
        "ledger_events": [],
        "tool_exec_events": [],
        "metrics_snapshots": {},
        "stop_reason": None,
        "archive_escalations": 0,
        "resume_used": False,
        "runtime_seconds": 0.0,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    try:
        from .autonomous_orchestrator import FullyAutonomousOrchestrator

        orchestrator = FullyAutonomousOrchestrator(
            research_query=query,
            max_urls=config.max_urls,
            max_depth=1,
            enable_stealth=True,
            enable_archives=True,
        )

        await orchestrator.initialize()

        for url in seeds[:config.max_urls]:
            await orchestrator.add_url_to_frontier(url)

        loop_count = 0
        max_loops = config.max_urls

        while loop_count < max_loops:
            elapsed = time.time() - start_time
            if elapsed >= config.max_runtime_secs:
                result["stop_reason"] = "runtime_budget_exceeded"
                break

            frontier = getattr(orchestrator, '_frontier', None)
            if frontier is None or len(frontier) == 0:
                result["stop_reason"] = "frontier_empty"
                break

            if mock_network:
                step_result = await _mock_fetch_step(orchestrator, loop_count)
            else:
                step_result = await _real_fetch_step(orchestrator)

            result["urls_fetched"] += step_result.get("urls_fetched", 0)
            result["evidence_count"] += step_result.get("evidence_count", 0)
            result["archive_escalations"] += step_result.get("archive_escalations", 0)

            events = step_result.get("ledger_events", [])
            result["ledger_events"].extend(events[:10 - len(result["ledger_events"])])

            tool_events = step_result.get("tool_exec_events", [])
            result["tool_exec_events"].extend(tool_events[:10 - len(result["tool_exec_events"])])

            loop_count += 1

            if result["urls_fetched"] >= config.max_urls:
                result["stop_reason"] = "max_urls_reached"
                break

        result["metrics_snapshots"] = _capture_metrics_snapshot(orchestrator)

    except Exception as e:
        logger.warning(f"Smoke run error: {e}")
        result["stop_reason"] = f"error: {str(e)[:50]}"

    finally:
        result["runtime_seconds"] = round(time.time() - start_time, 2)

    if result["ledger_events"]:
        ledger_path = os.path.join(output_dir, "ledger_events.jsonl")
        with open(ledger_path, "w") as f:
            for event in result["ledger_events"]:
                f.write(json.dumps(event) + "\n")

    if result["tool_exec_events"]:
        tool_path = os.path.join(output_dir, "tool_exec.jsonl")
        with open(tool_path, "w") as f:
            for event in result["tool_exec_events"]:
                f.write(json.dumps(event) + "\n")

    return result


async def _mock_fetch_step(orchestrator: Any, step_num: int) -> Dict[str, Any]:
    return {
        "urls_fetched": 1,
        "evidence_count": 1,
        "archive_escalations": 0,
        "ledger_events": [
            {
                "event_type": "url_fetched",
                "step": step_num,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        ],
        "tool_exec_events": [
            {
                "tool": "fetch",
                "step": step_num,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        ],
    }


async def _real_fetch_step(orchestrator: Any) -> Dict[str, Any]:
    return {
        "urls_fetched": 0,
        "evidence_count": 0,
        "archive_escalations": 0,
        "ledger_events": [],
        "tool_exec_events": [],
    }


def _capture_metrics_snapshot(orchestrator: Any) -> Dict[str, Any]:
    snapshot = {
        "frontier_size": 0,
        "evidence_stored": 0,
        "checkpoints_saved": 0,
    }

    try:
        frontier = getattr(orchestrator, '_frontier', None)
        if frontier is not None:
            snapshot["frontier_size"] = len(frontier)

        evidence_mgr = getattr(orchestrator, '_research_mgr', None)
        if evidence_mgr is not None:
            evidence_storage = getattr(evidence_mgr, '_evidence_packet_storage', None)
            if evidence_storage is not None:
                snapshot["evidence_stored"] = len(getattr(evidence_storage, '_packets', {}))

        checkpoint_mgr = getattr(orchestrator, '_checkpoint_manager', None)
        if checkpoint_mgr is not None:
            snapshot["checkpoints_saved"] = len(getattr(checkpoint_mgr, '_checkpoints', []))

    except Exception as e:
        logger.debug(f"Metrics snapshot error: {e}")

    return snapshot


def check_resume_eligibility(run_id: str, output_dir: Optional[str] = None) -> bool:
    if output_dir is None:
        output_dir = os.path.join(os.getcwd(), ".omc", "smoke_runs", run_id)
    else:
        output_dir = os.path.join(output_dir, run_id)

    summary_path = os.path.join(output_dir, "summary.json")

    if not os.path.exists(summary_path):
        return False

    try:
        with open(summary_path, "r") as f:
            summary = json.load(f)

        stop_reason = summary.get("stop_reason", "")
        return stop_reason in ("runtime_budget_exceeded", "frontier_empty")

    except Exception:
        return False
