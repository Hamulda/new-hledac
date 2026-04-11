# Sprint 8VX §A: Export plane finish-up
# - ExportHandoff confirmed as primary handoff surface (wired in __main__.py:2343)
# - compat fallback documented with explicit removal conditions
# - No new framework, no new store API
"""
Sprint 8VI §A: EXPORT fáze — export_sprint() + _generate_next_sprint_seeds()
Sprint 8VJ §C: ExportHandoff | dict → typed handoff spotřeba
Sprint 8VX §A: Finish-up — removal conditions tightened, comments aligned with reality
Sprint F150I: product_value_summary — přenáší do exportu to, co runtime už ví:
  - accepted/stored reality z dedup status
  - reject breakdown (low-info / duplicate / fail-open)
  - circuit breaker state pokud je k dispozici
  - gnn_predictions signal
  - phase_durations timing truth
  - robustnější seed derivation (divný input → skip, ne pád)
Sprint F150J: Enhanced next-seed derivation driven by product_value_summary:
  - 4 seed categories: ioc_followup, query_suggestion, source_revisit, low_signal_recommendation
  - signal_quality → query direction (refine/broaden/narrow/new_approach)
  - reject_breakdown → query strategy (low_info_ratio → narrow scope)
  - cb_open_domains → source_revisit with backoff
  - depleted signal → retry_known_sources or new_approach
  - Bounded output: max 12 seeds total, sorted by priority
Sprint F150K: Next-action package — praktický follow-up balíček:
  - hypothesis_engine.suggest_next_queries() jako bounded seam (fail-soft, lazy load)
  - human-readable sprint_summary block (co found / co nevyšlo / co dělat dál)
  - priority-based next actions (max 10, deduped, signal-derived)
  - focus/expand recommendations derived from signal_quality
  - NO new persistence, NO new planner, NO new write-back path
"""

from __future__ import annotations

import json
import logging
import pathlib
from typing import TYPE_CHECKING, Any, Union

if TYPE_CHECKING:
    from hledac.universal.types import ExportHandoff

logger = logging.getLogger(__name__)


async def export_sprint(
    store: Any,
    handoff: Union["ExportHandoff", dict, None],  # type: ignore[name-defined]
    sprint_id: str | None = None,
) -> dict:
    """
    EXPORT fáze — JSON report, seed tasky pro příští sprint.

    Voláno z _print_scorecard_report() v __main__.py EXPORT fázi.
    Nikdy nevyhodí výjimku.

    Accepts typed ExportHandoff OR raw dict (backward compat via ensure_export_handoff).

    Součásti:
      1. JSON report do ~/.hledac/reports/{sprint_id}_report.json
         Canonical path owner: paths.get_sprint_json_report_path() (post-F500B)
      2. Seed tasky pro příští sprint z top IOC graph nodes
      3. Sprint F150I: product_value_summary — decisions有用的 pro další sprinty

    PRIMARY HANDOFF SURFACE (Sprint 8VX):
      - ExportHandoff.top_nodes — kanonický zdroj pro seed generation
      - ExportHandoff.scorecard — kanonický zdroj pro JSON report

    ACCEPTED COMPAT SEAM — store-facing fallback:
      - Pokud top_nodes prázdné (windup běžel ale neplnil ExportHandoff.top_nodes),
        zkusí store.get_top_seed_nodes(n=5) — store-facing seam (post-8VX).
      - REMOVAL CONDITION: ExportHandoff.top_nodes always populated in ALL windup paths.
      - Future owner: duckdb_store.get_top_seed_nodes() — already implemented, this
        fallback is the compat bridge pending windup engine producing typed ExportHandoff.
    """
    from hledac.universal.paths import get_sprint_json_report_path
    from hledac.universal.export.COMPAT_HANDOFF import ensure_export_handoff

    # Sprint 8VJ §C: Normalize ExportHandoff | dict | None → typed ExportHandoff
    # Maintains backward compat: dict input → from_windup() extraction
    eh = ensure_export_handoff(handoff, default_sprint_id=sprint_id or "unknown")

    # Resolve sprint_id — prefer from handoff (typed path)
    _sprint_id = eh.sprint_id if eh.sprint_id != "unknown" else (sprint_id or "unknown")

    # Sprint F500B §2: Canonical JSON report path via paths.py helper
    # (post-F500B: inline report_dir composition replaced by get_sprint_json_report_path)
    report_path = get_sprint_json_report_path(_sprint_id)

    # Sprint 8VZ §C: F10 runtime boundary wiring
    # sanitize_outbound() na JSON report boundary — content opouští systém
    boundary_content = _make_serializable(eh.scorecard)
    boundary_text = json.dumps(boundary_content, indent=2, default=str)

    # Pass through early privacy gate (outbound boundary)
    # Using security_coordinator sanitize_outbound seam
    try:
        from hledac.universal.coordinators.security_coordinator import UniversalSecurityCoordinator
        sec_coordinator = UniversalSecurityCoordinator(max_concurrent=2)
        await sec_coordinator.initialize()
        gate_result = await sec_coordinator.sanitize_outbound(boundary_text, force_fallback=True)
        sanitized_scorecard_raw = gate_result.get("sanitized", boundary_text)
        # Log audit metadata (non-blocking)
        if gate_result.get("pii_count"):
            logger.info("[EXPORT] sanitize_outbound: pii_count=%s, risk=%s",
                        gate_result.get("pii_count"), gate_result.get("risk_level", "unknown"))
    except Exception as e:
        # Fail-soft: fall back to DEGRADED SANITIZED-SAFE structure, NOT unsanitized original.
        # Sprint F500M §1 CRITICAL: boundary_text is UNSANITIZED — never return it.
        # Produces a bounded degraded report structure that is safe for export.
        logger.warning("[EXPORT] sanitize_outbound failed (non-fatal): %s", e)
        degraded = {
            "_sanitize_failure": True,
            "sprint_id": _sprint_id,
            "report": "sanitization_failed_degraded_export",
        }
        sanitized_scorecard_raw = json.dumps(degraded, default=str)

    # Sprint F150I §2: Build product_value_summary from all existing surfaces
    pvs = _build_product_value_summary(store, eh, _sprint_id)

    # 1. JSON report — write via canonical path (F10 boundary applied)
    # report_path already computed via get_sprint_json_report_path() above
    try:
        # Re-parse sanitized text back to JSON for writing
        try:
            sanitized_obj = json.loads(sanitized_scorecard_raw)
        except (json.JSONDecodeError, TypeError) as parse_err:
            # Sprint F500E §1: sanitize_outbound fallback_sanitize truncates to 10KB.
            # If content exceeded 10KB, sanitized string is truncated JSON → parse fails.
            # CRITICAL: do NOT fall back to original (unsanitized) content here — that
            # would be an export boundary correctness drift. Write sanitized prefix only.
            logger.warning(
                "[EXPORT] sanitize boundary parse failed (truncated JSON, size=%d): %s. "
                "Writing sanitized prefix only, NOT falling back to unsanitized content.",
                len(sanitized_scorecard_raw), parse_err
            )
            # Write what we have from sanitized — it's bounded and sanitized
            sanitized_obj = json.loads(sanitized_scorecard_raw[:5000]) if sanitized_scorecard_raw else {}
            if sanitized_obj is None:
                sanitized_obj = {}

        # Sprint F150I §3: Attach product_value_summary to JSON report (derived output)
        if isinstance(sanitized_obj, dict):
            sanitized_obj["product_value_summary"] = pvs
        elif isinstance(sanitized_obj, list):
            # Edge case: truncated JSON is a list — wrap in dict with pvs
            sanitized_obj = {"_truncated_content": sanitized_obj, "product_value_summary": pvs}

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(sanitized_obj, f, indent=2, default=str)
        logger.info(f"[EXPORT] JSON report → {report_path}")
    except Exception as e:
        logger.warning(f"[EXPORT] JSON write failed: {e}")
        report_path = None

    # 2. Seed tasky pro příští sprint — top_nodes z ExportHandoff (typed)
    # Post-8VZ: __main__._print_scorecard_report() sources top_nodes directly from
    # store.get_top_seed_nodes() and passes them to ExportHandoff(...) constructor.
    # Export does NOT access scheduler._ioc_graph — store-facing seam only.
    top_nodes = eh.top_nodes if eh.top_nodes else []

    # COMPAT BRIDGE: When top_nodes empty (e.g. windup path bypassed
    # _print_scorecard_report but export_sprint() still called directly),
    # fall back to store.get_top_seed_nodes() — store-facing seam.
    # Sprint 8VX §B: switched from store._ioc_graph.get_top_nodes_by_degree()
    # to store.get_top_seed_nodes() — no graph internals exposed.
    # Future owner: duckdb_store.get_top_seed_nodes()
    # REMOVAL CONDITION: ExportHandoff.top_nodes always populated in ALL windup paths
    if not top_nodes and store is not None:
        try:
            if hasattr(store, "get_top_seed_nodes"):
                top_nodes = store.get_top_seed_nodes(n=5)
        except Exception:
            pass

    # Sprint F500B §2 + F500D §3: seeds land alongside JSON report (colocation)
    # Primary: get_sprint_next_seeds_path() from paths.py (canonical)
    # Fallback: SPRINT_STORE_ROOT.parent/"reports" if report_path is None (write failed)
    # Sprint F150J: pvs drives enhanced seed derivation — signal_quality + reject_breakdown + cb state
    seeds_path = _generate_next_sprint_seeds(top_nodes, _sprint_id, report_path, pvs)

    # Sprint F150K: build sprint_summary for human use
    try:
        seeds_data = json.loads(seeds_path.read_text()) if seeds_path.exists() else []
        seeds_count = len(seeds_data) if isinstance(seeds_data, list) else 0
    except Exception:
        seeds_count = 0
    sprint_summary = _build_sprint_summary(pvs, seeds_count) if pvs else None

    return {
        "report_json": str(report_path) if report_path else "",
        "seeds_json": str(seeds_path),
        "product_value_summary": pvs,
        "sprint_summary": sprint_summary,
    }


def _generate_next_sprint_seeds(
    top_nodes: list,
    sprint_id: str,
    report_path: pathlib.Path | None,
    pvs: dict[str, Any] | None = None,
) -> pathlib.Path:
    """
    Sprint F150J: Enhanced seed derivation driven by product_value_summary.

    4 seed categories derived from pvs:
      1. ioc_followup — top graph nodes (existing _type_aware_seeds logic)
      2. query_suggestion — based on signal_quality + reject_breakdown
      3. source_revisit — circuit-breaker open domains + depleted signal
      4. low_signal_recommendation — when sprint found almost nothing

    Bounded: max ~10 seeds total. No combinatorial explosion.

    Canonical next-seeds path (Sprint F500D):
      - Primary: get_sprint_next_seeds_path(sprint_id) z paths.py
      - Fallback: SPRINT_STORE_ROOT.parent/"reports" if report_path is None
    """
    from hledac.universal.paths import get_sprint_next_seeds_path, SPRINT_STORE_ROOT
    if report_path is not None:
        seeds_path = get_sprint_next_seeds_path(sprint_id)
    else:
        seeds_path = SPRINT_STORE_ROOT.parent / "reports" / f"{sprint_id}_next_seeds.json"
        seeds_path.parent.mkdir(parents=True, exist_ok=True)
    seeds: list[dict[str, Any]] = []

    try:
        # 1. IOC follow-up seeds from top_nodes (existing logic, now with reason tag)
        for node in top_nodes:
            try:
                if isinstance(node, dict):
                    ioc_value = str(node.get("value", "")) if node else ""
                    ioc_type = str(node.get("ioc_type", "unknown")) if node else "unknown"
                elif isinstance(node, (list, tuple)) and len(node) >= 2:
                    ioc_value = str(node[0]) if node[0] else ""
                    ioc_type = str(node[1]) if node[1] else "unknown"
                elif isinstance(node, (list, tuple)) and len(node) == 1:
                    ioc_value = str(node[0]) if node[0] else ""
                    ioc_type = "unknown"
                elif isinstance(node, str):
                    ioc_value = node
                    ioc_type = "unknown"
                elif isinstance(node, (int, float)):
                    ioc_value = str(node)
                    ioc_type = "unknown"
                else:
                    continue
            except Exception:
                continue

            if not ioc_value or len(ioc_value) < 3:
                continue

            node_seeds = _type_aware_seeds(ioc_value, ioc_type, reason="ioc_followup")
            seeds.extend(node_seeds)

        # 2. Sprint F150J: query_suggestion — derive next queries from sprint signal
        if pvs:
            query_seeds = _derive_query_seeds(pvs)
            seeds.extend(query_seeds)

        # 3. Sprint F150J: source_revisit — circuit breaker + depleted signal
        if pvs:
            revisit_seeds = _derive_source_revisit_seeds(pvs)
            seeds.extend(revisit_seeds)

        # 4. Sprint F150J: low_signal_recommendation — when sprint was nearly empty
        if pvs:
            low_signal_seeds = _derive_low_signal_seeds(pvs)
            seeds.extend(low_signal_seeds)

        # 5. Sprint F150K: hypothesis_engine.suggest_next_queries() seam
        if pvs:
            hyp_queries = _derive_hypothesis_queries(pvs, max_queries=2)
            seeds.extend(hyp_queries)

        # 6. Sprint F150K: focus/expand recommendations
        if pvs:
            focus_expand = _derive_focus_expand(pvs)
            seeds.extend(focus_expand)

        # Bounded output — keep total seed count manageable
        MAX_SEEDS = 15
        if len(seeds) > MAX_SEEDS:
            # Sort by priority descending, keep top N
            seeds.sort(key=lambda s: s.get("priority", 0.5), reverse=True)
            seeds = seeds[:MAX_SEEDS]

        seeds_path.write_text(json.dumps(seeds, indent=2, default=str))
        logger.info(f"[EXPORT] {len(seeds)} enhanced seeds ({', '.join(_seed_type_counts(seeds))}) → {seeds_path}")
    except Exception as e:
        logger.warning(f"[EXPORT] Enhanced seed generation failed: {e}")
        seeds_path.write_text(json.dumps([], indent=2))

    return seeds_path


def _seed_type_counts(seeds: list[dict[str, Any]]) -> dict[str, int]:
    """Count seeds by their seed_type."""
    counts: dict[str, int] = {}
    for s in seeds:
        t = s.get("task_type", "unknown")
        counts[t] = counts.get(t, 0) + 1
    return counts


def _derive_query_seeds(pvs: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Sprint F150J: query_suggestion — derive next query seeds from sprint signal.

    Reads: signal_quality, reject_breakdown, accepted, ioc_density.

    Logic:
      - high_density + accepted > 0 → suggest more of the same queries (query refinement)
      - medium_density → suggest broadening scope
      - low_density / slow_novelty → suggest different query strategy
      - depleted → no query seeds (already tried hard, switch approach)
    """
    signal = pvs.get("signal_quality", "unknown")
    accepted = pvs.get("accepted", 0)
    ioc_density = pvs.get("ioc_density", 0.0)
    findings_per_minute = pvs.get("findings_per_minute", 0.0)
    reject_breakdown = pvs.get("reject_breakdown") or {}

    seeds: list[dict[str, Any]] = []

    # Low-information rejection ratio — if most rejects were low-info, queries may be too broad
    total_rejected = pvs.get("total_rejected", 0)
    low_info_rejected = reject_breakdown.get("low_information", 0)
    low_info_ratio = low_info_rejected / total_rejected if total_rejected > 0 else 0.0

    if signal == "high_density":
        # Good sprint: suggest refining current query approach
        seeds.append({
            "task_type": "query_suggestion",
            "suggested_action": "refine",
            "priority": 0.75,
            "reason": f"signal=high_density/accepted={accepted}/ioc_density={ioc_density:.2f}",
        })
    elif signal == "medium_density":
        if low_info_ratio > 0.5:
            # Many low-info rejects → queries are too broad, suggest narrowing
            seeds.append({
                "task_type": "query_suggestion",
                "suggested_action": "narrow_scope",
                "priority": 0.70,
                "reason": f"low_info_ratio={low_info_ratio:.2f}/broad_queries",
            })
        else:
            # Mixed signal → suggest broadening
            seeds.append({
                "task_type": "query_suggestion",
                "suggested_action": "broaden",
                "priority": 0.65,
                "reason": f"signal=medium_density/ioc_density={ioc_density:.2f}",
            })
    elif signal == "slow_novelty":
        # Few findings but they exist — suggest faster queries or different sources
        seeds.append({
            "task_type": "query_suggestion",
            "suggested_action": "accelerate",
            "priority": 0.60,
            "reason": f"signal=slow_novelty/fpm={findings_per_minute:.2f}",
        })
    elif signal == "depleted":
        # Exhausted this query space — suggest fundamentally different queries
        seeds.append({
            "task_type": "query_suggestion",
            "suggested_action": "new_approach",
            "priority": 0.80,
            "reason": "signal=depleted/exhausted_query_space",
        })

    return seeds[:3]  # Hard cap: max 3 query suggestions


def _derive_source_revisit_seeds(pvs: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Sprint F150J: source_revisit — domains/hosts that need re-visiting.

    Reads: cb_open_domains (circuit breaker open domains), signal_quality.

    Logic:
      - cb_open_domains → retry with longer backoff
      - depleted signal → revisit domains that previously timed out
    """
    seeds: list[dict[str, Any]] = []
    cb_open: list[str] = pvs.get("cb_open_domains") or []
    signal = pvs.get("signal_quality", "unknown")

    if cb_open:
        for domain in cb_open[:3]:  # Max 3 domains from circuit breaker
            seeds.append({
                "task_type": "source_revisit",
                "value": domain,
                "priority": 0.55,
                "reason": "circuit_breaker_open",
                "backoff_seconds": 3600,  # 1h backoff recommendation
            })
    elif signal == "depleted":
        # No cb state but depleted — suggest retrying known sources with backoff
        seeds.append({
            "task_type": "source_revisit",
            "suggested_action": "retry_known_sources",
            "priority": 0.50,
            "reason": "signal=depleted/retry_after_backoff",
        })

    return seeds[:3]


def _derive_low_signal_seeds(pvs: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Sprint F150J: low_signal_recommendation — when sprint found almost nothing.

    Reads: accepted, total_rejected, findings_per_minute.

    Trigger: accepted <= 2 AND findings_per_minute < 0.5.

    Generates practical starting points for next sprint instead of
    continuing with same approach that yielded near-zero results.
    """
    accepted = pvs.get("accepted", 0)
    findings_per_minute = pvs.get("findings_per_minute", 0.0)
    total_rejected = pvs.get("total_rejected", 0)

    seeds: list[dict[str, Any]] = []

    if accepted <= 2 and findings_per_minute < 0.5 and total_rejected > 0:
        # Sprint was nearly empty — offer practical restart suggestions
        seeds.append({
            "task_type": "low_signal_recommendation",
            "suggested_action": "start_fresh",
            "priority": 0.70,
            "reason": f"accepted={accepted}/fpm={findings_per_minute:.2f}/near_empty_sprint",
        })
        # If dedup was effective but we still found nothing, sources may be exhausted
        if pvs.get("dedup_effective"):
            seeds.append({
                "task_type": "low_signal_recommendation",
                "suggested_action": "new_seed_sources",
                "priority": 0.65,
                "reason": "dedup_effective_but_depleted/switch_sources",
            })

    return seeds[:2]  # Hard cap: max 2 low-signal recommendations


def _type_aware_seeds(value: str, ioc_type: str, reason: str = "top_graph_node") -> list[dict[str, Any]]:
    """
    Sprint F500G §H2: Type-aware seed generation.

    Truthful mapping — generates seeds JEN kde typu odpovídá task_type.

    | ioc_type  | rdap_lookup | domain_to_ct | dht_infohash_lookup |
    |-----------|-------------|--------------|---------------------|
    | domain    | YES         | YES          | NO                  |
    | ip        | YES         | NO           | NO                  |
    | url       | YES         | NO           | NO                  |
    | infohash  | NO          | NO           | YES                 |
    | onion     | NO          | NO           | CONDITIONAL         |
    | cve       | NO          | NO           | NO                  |
    | md5/sha*  | NO          | NO           | NO                  |
    | unknown   | NO          | NO           | NO                  |

    Truthful skip: CVE, hash, unknown — žádné seed tasky, není co generovat.
    Willing to SKIP: není false-positive seed generation.
    """
    # Normalize ioc_type lowercase for matching
    t = ioc_type.lower()

    if t == "domain":
        return [
            {
                "task_type": "rdap_lookup",
                "value": value,
                "priority": 0.85,
                "reason": f"{reason}/{ioc_type}",
            },
            {
                "task_type": "domain_to_ct",
                "value": value,
                "priority": 0.80,
                "reason": f"{reason}/{ioc_type}",
            },
        ]
    elif t in ("ip", "ipv4", "ipv6"):
        return [
            {
                "task_type": "rdap_lookup",
                "value": value,
                "priority": 0.85,
                "reason": f"{reason}/{ioc_type}",
            },
        ]
    elif t == "url":
        # URL has host component — RDAP lookup makes sense
        # domain_to_ct makes NO sense (URL is not a domain)
        return [
            {
                "task_type": "rdap_lookup",
                "value": value,
                "priority": 0.80,
                "reason": f"{reason}/{ioc_type}",
            },
        ]
    elif t == "infohash":
        return [
            {
                "task_type": "dht_infohash_lookup",
                "value": value,
                "priority": 0.90,
                "reason": f"{reason}/{ioc_type}",
            },
        ]
    elif t == "onion":
        # Onion is not a DNS domain — no domain_to_ct
        # DHT lookup is marginally relevant (some Tor research uses DHT)
        # but skip entirely to be safe — no strong signal
        return []
    elif t in ("cve", "md5", "sha1", "sha256", "sha512", "sha384",
               "md6", "ripemd160", "unknown", "email", "phone",
               "ipv4_addr", "ipv6_addr", "mac_addr", "btc", "eth",
               "xmpp", "jabber"):
        # Truthful skip — these types have no meaningful follow-up seed
        # CVE: vuln ID not a network observable
        # Hashes: not domains, not infohashes, not IPs
        # Unknown: no valid seeds possible
        return []
    else:
        # Catch-all for any other type not explicitly handled:
        # generate NO seeds — better to skip than to generate falsy task
        return []


def _build_product_value_summary(
    store: Any,
    eh: "ExportHandoff",  # type: ignore[name-defined]
    sprint_id: str,
) -> dict[str, Any]:
    """
    Sprint F150I §1: product_value_summary — agreguje truth surfaces do jednoho
    rozhodovacího balíčku pro další sprinty.

    ZDROJE (existující surfaces, žádné nové):
      1. eh.scorecard — windup output (findings_per_minute, ioc_density,
         semantic_novelty, accepted_findings, peak_rss_mb, phase_timings)
      2. store.get_dedup_runtime_status() — accepted vs rejected by reason
         (Sprint 8AV extended: low-info / in-memory-dup / persistent-dup / fail-open)
      3. eh.scorecard["cb_open_domains"] — circuit breaker state
      4. eh.gnn_predictions — ML model signal (0 pokud nepoužit)
      5. eh.phase_durations — timing truth

    DEGRADED MODE: pokud store není dostupný, pole jsou None — není to chyba,
    je to expected degraded state pro standalone/test scénáře.

    JE TO DERIVED OUTPUT, NE NOVÝ TRUTH STORE:
      - Žádné nové write API
      - Žádné nové history mechanismy
      - Pouze čte z existujících surfaces a skládá je dohromady
    """
    scorecard = eh.scorecard if eh.scorecard else {}

    # 1. Základní scorecard facts
    # Sprint F150I §1: all numeric fields use isinstance guards to prevent
    # TypeError when scorecard contains MagicMock or other non-numeric values
    def _num(val, default):
        return val if isinstance(val, (int, float)) else default
    def _n(key, default):
        return _num(scorecard.get(key, default), default)
    accepted = _n("accepted_findings", 0) or _n("accepted_findings_count", 0)
    findings_per_minute = _n("findings_per_minute", 0.0)
    ioc_density = _n("ioc_density", 0.0)
    peak_rss_mb = scorecard.get("peak_rss_mb", None)
    if peak_rss_mb is not None and not isinstance(peak_rss_mb, (int, float)):
        peak_rss_mb = None
    phase_timings = scorecard.get("phase_duration_seconds", {}) or {}

    # 2. Dedup status — Sprint 8AV extended ingest outcome counters
    dedup_status: dict[str, Any] | None = None
    if store is not None:
        try:
            if hasattr(store, "get_dedup_runtime_status"):
                raw = store.get_dedup_runtime_status()
                # Sprint F150I §6: guard against MagicMock / non-dict returns
                if isinstance(raw, dict):
                    dedup_status = raw
        except Exception:
            pass

    if dedup_status:
        accepted = dedup_status.get("accepted_count", accepted)
        reject_breakdown = {
            "low_information": dedup_status.get("low_information_rejected_count", 0),
            "in_memory_duplicate": dedup_status.get("in_memory_duplicate_rejected_count", 0),
            "persistent_duplicate": dedup_status.get("persistent_duplicate_rejected_count", 0),
            "fail_open": dedup_status.get("other_rejected_count", 0),
        }
        total_rejected = sum(reject_breakdown.values())
        dedup_effective = dedup_status.get("persistent_dedup_enabled", False)
        dedup_lmdb_path = dedup_status.get("dedup_lmdb_path", "")
        hot_cache = {
            "size": dedup_status.get("hot_cache_size", 0),
            "capacity": dedup_status.get("hot_cache_capacity", 0),
        }
    else:
        reject_breakdown = None
        total_rejected = None
        dedup_effective = None
        dedup_lmdb_path = None
        hot_cache = None

    # 3. Circuit breaker state
    cb_open_domains = scorecard.get("cb_open_domains", []) or []

    # 4. GNN predictions
    gnn_predictions = eh.gnn_predictions if eh.gnn_predictions else 0

    # 5. Synthesis engine
    synthesis_engine = eh.synthesis_engine if eh.synthesis_engine else (
        scorecard.get("synthesis_engine_used", "unknown") or "unknown"
    )

    # Sprint F150I §4: Build signal_quality — condensed quality verdict
    # Pro další sprint: je tenhle sprint dobrý seed source?
    if accepted > 0 and findings_per_minute > 0:
        # Good signal: we found things and did it efficiently
        if ioc_density >= 0.5:
            signal_quality = "high_density"
        elif ioc_density >= 0.2:
            signal_quality = "medium_density"
        else:
            signal_quality = "low_density"
    elif accepted > 0 and findings_per_minute == 0:
        signal_quality = "slow_novelty"
    elif accepted == 0 and dedup_status:
        signal_quality = "depleted"
    else:
        signal_quality = "unknown"

    summary: dict[str, Any] = {
        "sprint_id": sprint_id,
        # Accepted reality
        "accepted": accepted,
        # Reject breakdown (Sprint 8AV extended dedup status)
        "reject_breakdown": reject_breakdown,
        "total_rejected": total_rejected,
        # Dedup infrastructure state
        "dedup_effective": dedup_effective,
        "dedup_lmdb_path": dedup_lmdb_path,
        "hot_cache": hot_cache,
        # Circuit breaker
        "cb_open_domains": cb_open_domains,
        # ML signal
        "gnn_predictions": gnn_predictions,
        # Synthesis engine
        "synthesis_engine": synthesis_engine,
        # Scorecard basics
        "findings_per_minute": findings_per_minute,
        "ioc_density": ioc_density,
        "peak_rss_mb": peak_rss_mb,
        # Phase timings
        "phase_durations": phase_timings if phase_timings else None,
        # Decision signal for next sprint
        "signal_quality": signal_quality,
    }

    # Remove None fields for cleaner output (keep 0 as valid)
    return {k: v for k, v in summary.items() if v is not None}


def _derive_hypothesis_queries(
    pvs: dict[str, Any],
    max_queries: int = 3,
) -> list[dict[str, Any]]:
    """
    Sprint F150K: Lazy hypothesis_engine.suggest_next_queries() seam.

    Bounded helper — only used to enrich query_followup seeds.
    Fails soft: if hypothesis_engine not available or call fails, returns [].
    Never blocks on MLX model loading.

    Args:
        pvs: product_value_summary (provides findings context)
        max_queries: hard cap on returned queries (default 3)

    Returns:
        List of query dicts with keys: query, rationale, type
    """
    try:
        from hledac.universal.brain.hypothesis_engine import HypothesisEngine
    except ImportError:
        return []

    try:
        # Lightweight instance — no inference engine, no MLX
        engine = HypothesisEngine(
            inference_engine=None,
            max_hypotheses=20,
            enable_adversarial_verification=False,
        )
    except Exception:
        return []

    # Build findings string from pvs signal
    findings: list[str] = []
    signal = pvs.get("signal_quality", "unknown")

    if signal == "high_density":
        accepted = pvs.get("accepted", 0)
        ioc_density = pvs.get("ioc_density", 0.0)
        findings.append(f"high_value_findings: {accepted} entities at density {ioc_density:.2f}")
    elif signal == "medium_density":
        findings.append(f"mixed_results: investigate_correlations")
    elif signal == "slow_novelty":
        findings.append(f"slow_but_real: verify_and_expand")
    elif signal == "depleted":
        findings.append(f"exhausted_space: new_approach_needed")

    # Dedup status context
    dedup = pvs.get("reject_breakdown")
    if dedup:
        low_info = dedup.get("low_information", 0)
        total = pvs.get("total_rejected", 1)
        if total > 0 and low_info / total > 0.5:
            findings.append(f"low_info_rejects: narrow_scope_recommended")

    try:
        queries = engine.suggest_next_queries(
            findings=findings,
            context={"known_iocs": set()},
            max_queries=max_queries,
        )
        # Convert to export format
        result = []
        for q in queries[:max_queries]:
            result.append({
                "task_type": "query_suggestion",
                "suggested_action": q.get("type", "entity_expansion"),
                "value": q.get("query", ""),
                "priority": 0.60,
                "reason": q.get("rationale", "hypothesis_engine_suggestion"),
            })
        return result
    except Exception:
        return []


def _derive_focus_expand(pvs: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Sprint F150K: Focus/expand recommendations based on sprint signal.

    Derived purely from pvs signal_quality — no new data sources.
    Returns max 2 recommendations (one focus, one expand if both apply).

    Args:
        pvs: product_value_summary

    Returns:
        List of recommendation dicts with keys: task_type, suggested_action, priority, reason
    """
    signal = pvs.get("signal_quality", "unknown")
    accepted = pvs.get("accepted", 0)
    ioc_density = pvs.get("ioc_density", 0.0)
    dedup_effective = pvs.get("dedup_effective", False)

    recs: list[dict[str, Any]] = []

    if signal == "high_density":
        # Good results — focus on what works
        recs.append({
            "task_type": "focus_recommendation",
            "suggested_action": "focus_on_high_density",
            "priority": 0.80,
            "reason": f"signal=high_density/accepted={accepted}/ioc_density={ioc_density:.2f}",
        })
        recs.append({
            "task_type": "expand_recommendation",
            "suggested_action": "expand_sources",
            "priority": 0.70,
            "reason": "high_density_means_room_to_broaden",
        })
    elif signal == "medium_density":
        recs.append({
            "task_type": "focus_recommendation",
            "suggested_action": "narrow_scope",
            "priority": 0.75,
            "reason": "medium_density_mixed_signal_narrow_focus",
        })
    elif signal == "slow_novelty":
        recs.append({
            "task_type": "focus_recommendation",
            "suggested_action": "accelerate_existing",
            "priority": 0.65,
            "reason": "slow_novelty_means_queries_work_just_slow",
        })
        recs.append({
            "task_type": "expand_recommendation",
            "suggested_action": "new_timing_strategy",
            "priority": 0.60,
            "reason": "temporal_patterns_may_unlock_findings",
        })
    elif signal == "depleted":
        recs.append({
            "task_type": "focus_recommendation",
            "suggested_action": "abandon_current_approach",
            "priority": 0.85,
            "reason": "depleted_signal_switch_approach",
        })
        if dedup_effective:
            recs.append({
                "task_type": "expand_recommendation",
                "suggested_action": "completely_new_sources",
                "priority": 0.75,
                "reason": "dedup_effective_sources_exhausted",
            })

    return recs[:2]


def _build_sprint_summary(pvs: dict[str, Any], seeds_count: int) -> dict[str, Any]:
    """
    Sprint F150K: Human-readable sprint_summary block.

    DERIVED ONLY — reads from pvs, no new data sources.
    NO write-back. NO new persistence.

    Structure:
      - what_found: co sprint našel (high-level)
      - what_didnt_work: co nevyšlo (reject breakdown, depleted signal)
      - what_to_do_next: co dělat dál (top priority action)
      - priority_reason: proč tohle je priorita (derived from signal)

    Args:
        pvs: product_value_summary
        seeds_count: počet vygenerovaných seeds (pro kontext)

    Returns:
        sprint_summary dict
    """
    signal = pvs.get("signal_quality", "unknown")
    accepted = pvs.get("accepted", 0)
    total_rejected = pvs.get("total_rejected", 0)
    dedup_effective = pvs.get("dedup_effective", False)
    cb_open = pvs.get("cb_open_domains", [])
    ioc_density = pvs.get("ioc_density", 0.0)
    findings_per_minute = pvs.get("findings_per_minute", 0.0)
    dedup = pvs.get("reject_breakdown")

    # --- what_found ---
    if signal == "high_density":
        what_found = f"dobrý sprint: {accepted} accept IOCs při density {ioc_density:.2f}"
    elif signal == "medium_density":
        what_found = f"smíšený sprint: {accepted} accept IOCs, ioc_density={ioc_density:.2f}"
    elif signal == "slow_novelty":
        what_found = f"pomalý aleexistující signál: {accepted} finds, {findings_per_minute:.2f} fpm"
    elif signal == "depleted":
        what_found = "sprint nic nepřinesl — vyčerpaný prostor nebo špatné zdroje"
    else:
        what_found = f"nedefinovaný stav: accepted={accepted}"

    # --- what_didnt_work ---
    didnt_work: list[str] = []
    if total_rejected > 0 and dedup:
        low_info = dedup.get("low_information", 0)
        in_mem = dedup.get("in_memory_duplicate", 0)
        persistent = dedup.get("persistent_duplicate", 0)
        if low_info > 0:
            ratio = low_info / total_rejected
            didnt_work.append(f"low_info rejects: {ratio:.0%} (příliš široké dotazy)")
        if in_mem > 0:
            didnt_work.append(f"in-memory duplikáty: {in_mem} (příliš mnoho podobných výsledků)")
        if persistent > 0 and not dedup_effective:
            didnt_work.append("persistent duplikáty ale dedup nepomohl")
    if signal == "depleted":
        didnt_work.append("signál vyčerpaný — žádné nové IOCs")
    if cb_open:
        didnt_work.append(f"circuit breaker open: {len(cb_open)} domains")

    if not didnt_work:
        didnt_work.append("nic podstatného — sprint byl čistý")

    # --- what_to_do_next (top priority) ---
    if signal == "high_density":
        next_action = "rozšířit úspěšné dotazy o nové zdroje"
        priority_reason = f"{accepted} kvalitních nálezů = prostor expandovat"
    elif signal == "medium_density":
        next_action = "zúžit scope dotazů"
        priority_reason = "příliš mnoho low-info rejectů"
    elif signal == "slow_novelty":
        next_action = "urychlit stávající přístup (rychlejší zdroje)"
        priority_reason = "signál existuje ale je pomalý"
    elif signal == "depleted":
        next_action = "úplně nový přístup — nové seed zdroje"
        priority_reason = "vyčerpaný prostor — continuation nepomůže"
    else:
        next_action = "zjistit více o stavu sprintu"
        priority_reason = "nedefinovaný stav"

    return {
        "what_found": what_found,
        "what_didnt_work": didnt_work,
        "what_to_do_next": next_action,
        "priority_reason": priority_reason,
        "seeds_generated": seeds_count,
        "signal_derived": signal,
    }


def _make_serializable(obj: Any) -> Any:
    """Rekurzivně převede objekt na JSON-serializovatelný dict."""
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_serializable(v) for v in obj]
    if hasattr(obj, "__dict__"):
        return _make_serializable(obj.__dict__)
    return str(obj)
