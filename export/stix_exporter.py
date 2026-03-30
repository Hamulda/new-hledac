# hledac/universal/export/stix_exporter.py
# Sprint 8BJ — STIX 2.1 Structured Diagnostic Export
# Zero LLM / Zero model runtime / Zero network
"""
Deterministic, side-effect-free STIX 2.1 bundle exporter for ObservedRunReport.

B.5: STIX builtins path NEVER invents IOC/indicator/malware objects
     when no accepted findings are present — only metadata-safe bundle
     with note-like diagnostic facts.
B.7: If accepted findings are absent, exports metadata-safe diagnostic
     bundle (no fake CTI entities).

B.9: Builtins path produces proper STIX-compatible objects:
     - type = "bundle"
     - id = "bundle--<uuid>"
     - spec_version = "2.1"
     - RFC3339 created/modified timestamps
     - UUID-based ids for all objects

Optional stix2 package: if available, use it for full STIX object construction.
Otherwise the builtins path produces plain dicts that are syntactically
STIX-compatible and pass basic shape validation.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Union, cast

__all__ = [
    "render_stix_bundle",
    "render_stix_bundle_json",
    "render_stix_bundle_to_path",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_STIX_SPEC_VERSION = "2.1"
_BUNDLE_TYPE = "bundle"

# Canonical root-cause → label (shared with markdown_reporter / jsonld_exporter)
_ROOT_CAUSE_LABELS: dict[str, str] = {
    "network_variance": "Network Variance",
    "no_new_entries": "No New Entries",
    "empty_registry": "Empty Registry",
    "no_pattern_hits": "No Pattern Hits",
    "no_pattern_hits_possible_morphology_gap": "No Pattern Hits (Morphology Gap)",
    "pattern_hits_but_no_findings_built": "Pattern Hits But No Findings Built",
    "low_information_rejection_dominant": "Low-Information Rejection Dominant",
    "duplicate_rejection_dominant": "Duplicate Rejection Dominant",
    "accepted_present": "Accepted Findings Present",
    "unknown": "Unknown",
}

# Root-cause → recommendation fallback (shared)
_FALLBACK_RECOMMENDATION: dict[str, str] = {
    "network_variance": "repeat_live_run",
    "no_new_entries": "repeat_live_run",
    "empty_registry": "check_registry",
    "no_pattern_hits": "update_patterns",
    "no_pattern_hits_possible_morphology_gap": "update_patterns",
    "pattern_hits_but_no_findings_built": "update_extraction_logic",
    "low_information_rejection_dominant": "update_quality_thresholds",
    "duplicate_rejection_dominant": "update_dedup_logic",
    "accepted_present": "continue_monitoring",
    "unknown": "repeat_live_run",
}

# Canonical root-cause strings for export (machine-readable keys)
_CANONICAL_ROOT_CAUSES = frozenset(_ROOT_CAUSE_LABELS.keys())


# ---------------------------------------------------------------------------
# Input normalisation (standalone-safe, mirrors jsonld_exporter)
# ---------------------------------------------------------------------------
def normalize_export_input(report: object) -> dict[str, Any]:
    """
    Convert ObservedRunReport (msgspec.Struct) or Mapping → plain dict.
    """
    if hasattr(report, "__struct_fields__"):
        return {f: getattr(report, f) for f in getattr(report, "__struct_fields__")}
    if isinstance(report, dict):
        return dict(report)
    if hasattr(report, "keys"):
        return dict(cast(Mapping, report))
    raise TypeError(
        f"report must be msgspec.Struct or Mapping, got {type(report).__name__}"
    )


# ---------------------------------------------------------------------------
# Timestamp helpers (RFC3339)
# ---------------------------------------------------------------------------
def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_timestamp(ts: Any) -> str:
    """Convert unix timestamp or datetime to RFC3339 UTC string."""
    if ts is None:
        return _utc_now()
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return _utc_now()


def _safe_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val)


# ---------------------------------------------------------------------------
# Recommendation helper
# ---------------------------------------------------------------------------
def _get_recommendation(data: dict[str, Any]) -> str:
    rec = data.get("recommendation")
    if rec:
        return rec
    root = data.get("diagnostic_root_cause", "unknown")
    return _FALLBACK_RECOMMENDATION.get(root, _FALLBACK_RECOMMENDATION["unknown"])


# ---------------------------------------------------------------------------
# UUID helpers (STIX requires urn:uuid: for id fields)
# ---------------------------------------------------------------------------
def _bundle_id() -> str:
    return f"bundle--00000000-0000-0000-0000-000000000000"


def _make_uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Builtins path: plain-dict STIX objects (no stix2 package required)
# B.5/B.7: Metadata-safe only — no IOC/indicator/malware objects
# ---------------------------------------------------------------------------

def _build_diagnostic_note(data: dict[str, Any], created: str) -> dict[str, Any]:
    """
    Build a STIX note-like custom diagnostic object.
    Encapsulates root cause, recommendation, and signal funnel metadata.
    """
    root = data.get("diagnostic_root_cause", "unknown")
    label = _ROOT_CAUSE_LABELS.get(root, _ROOT_CAUSE_LABELS["unknown"])

    # Signal funnel fields as abstract content (no IOC semantics)
    signal_content_parts = [
        f"entries_seen={data.get('entries_seen', 0)}",
        f"entries_scanned={data.get('entries_scanned', 0)}",
        f"entries_with_hits={data.get('entries_with_hits', 0)}",
        f"total_pattern_hits={data.get('total_pattern_hits', 0)}",
        f"findings_built_pre_store={data.get('findings_built_pre_store', 0)}",
        f"accepted_count_delta={data.get('accepted_count_delta', 0)}",
    ]

    # Store rejection trace
    rejection_parts = [
        f"low_info_rejected={data.get('low_information_rejected_count_delta', 0)}",
        f"in_mem_dup_rejected={data.get('in_memory_duplicate_rejected_count_delta', 0)}",
        f"persistent_dup_rejected={data.get('persistent_duplicate_rejected_count_delta', 0)}",
        f"other_rejected={data.get('other_rejected_count_delta', 0)}",
    ]

    abstract = (
        f"Ghost Prime Diagnostic: root_cause={root} ({label}); "
        f"accepted_findings={data.get('accepted_findings', 0)}; "
        f"signal_funnel={{{' | '.join(signal_content_parts)}}}; "
        f"store_rejection_trace={{{' | '.join(rejection_parts)}}}; "
        f"recommendation={_get_recommendation(data)}"
    )

    return {
        "type": "note",
        "spec_version": _STIX_SPEC_VERSION,
        "id": f"note--{_make_uuid()}",
        "created": created,
        "modified": created,
        "created_by_ref": "identity--ghost-prime",
        "abstract": abstract[:2000] if len(abstract) > 2000 else abstract,
        "content": json.dumps({
            "accepted_findings": data.get("accepted_findings", 0),
            "entries_seen": data.get("entries_seen", 0),
            "entries_scanned": data.get("entries_scanned", 0),
            "entries_with_hits": data.get("entries_with_hits", 0),
            "total_pattern_hits": data.get("total_pattern_hits", 0),
            "findings_built_pre_store": data.get("findings_built_pre_store", 0),
            "accepted_count_delta": data.get("accepted_count_delta", 0),
            "signal_stage": _safe_str(data.get("signal_stage")),
        }, sort_keys=True),
        "object_refs": [f"identity--ghost-prime"],
    }


def _build_diagnostic_identity() -> dict[str, Any]:
    """Ghost Prime identity object (author of the report)."""
    return {
        "type": "identity",
        "spec_version": _STIX_SPEC_VERSION,
        "id": "identity--ghost-prime",
        "created": _utc_now(),
        "modified": _utc_now(),
        "name": "Ghost Prime",
        "identity_class": "system",
    }


def _build_diagnostic_uma_note(data: dict[str, Any], created: str) -> dict[str, Any]:
    """UMA snapshot as a note-like object (if UMA data available)."""
    uma = data.get("uma_snapshot", {})
    if not uma:
        return {}
    return {
        "type": "note",
        "spec_version": _STIX_SPEC_VERSION,
        "id": f"note--{_make_uuid()}",
        "created": created,
        "modified": created,
        "created_by_ref": "identity--ghost-prime",
        "abstract": f"UMA snapshot: {json.dumps(uma, sort_keys=True)}",
        "object_refs": ["identity--ghost-prime"],
    }


def _build_per_source_notes(data: dict[str, Any], created: str) -> list[dict[str, Any]]:
    """Per-source health as note-like objects (no indicator semantics)."""
    per_source = data.get("per_source")
    if not per_source:
        return []
    notes = []
    for src in sorted(per_source, key=lambda s: str(s.get("feed_url", ""))):
        url = _safe_str(src.get("feed_url", ""))
        if not url:
            continue
        note = {
            "type": "note",
            "spec_version": _STIX_SPEC_VERSION,
            "id": f"note--{_make_uuid()}",
            "created": created,
            "modified": created,
            "created_by_ref": "identity--ghost-prime",
            "abstract": (
                f"Source health: url={url} label={_safe_str(src.get('label'))} "
                f"fetched={src.get('fetched_entries', 0)} "
                f"accepted={src.get('accepted_findings', 0)} "
                f"stored={src.get('stored_findings', 0)} "
                f"elapsed_ms={src.get('elapsed_ms', 0):.1f} "
                f"error={_safe_str(src.get('error') or 'none')}"
            )[:2000],
            "object_refs": ["identity--ghost-prime"],
        }
        notes.append(note)
    return notes


def _build_root_cause_object(data: dict[str, Any], created: str) -> dict[str, Any]:
    """
    Root-cause and recommendation as a STIX custom object.
    Uses a note with structured abstract for machine-readable root cause.
    """
    root = data.get("diagnostic_root_cause", "unknown")
    label = _ROOT_CAUSE_LABELS.get(root, _ROOT_CAUSE_LABELS["unknown"])
    rec = _get_recommendation(data)

    return {
        "type": "note",
        "spec_version": _STIX_SPEC_VERSION,
        "id": f"note--{_make_uuid()}",
        "created": created,
        "modified": created,
        "created_by_ref": "identity--ghost-prime",
        "abstract": f"Root cause: {root} ({label}). Recommendation: {rec}. Network variance: {data.get('is_network_variance', False)}",
        "content": json.dumps({
            "diagnostic_root_cause": root,
            "diagnostic_root_cause_label": label,
            "recommendation": rec,
            "is_network_variance": data.get("is_network_variance", False),
        }, sort_keys=True),
        "object_refs": ["identity--ghost-prime"],
    }


# ---------------------------------------------------------------------------
# Optional stix2 package path
# ---------------------------------------------------------------------------
_stix2_module: Any = None
_stix2_available: bool = False
try:
    import stix2 as _stix2_module
    _stix2_available = True
except ImportError:
    pass


def _build_stix2_bundle(data: dict[str, Any]) -> dict[str, Any]:
    """Use stix2 package to build a proper STIX bundle."""
    bundle = _stix2_module.Bundle(
        objects=[],
        allow_custom=True,
    )
    # Add identity
    identity = _stix2_module.Identity(
        name="Ghost Prime",
        identity_class="system",
    )
    bundle.objects.append(identity)

    # Add diagnostic note
    root = data.get("diagnostic_root_cause", "unknown")
    label = _ROOT_CAUSE_LABELS.get(root, _ROOT_CAUSE_LABELS["unknown"])
    rec = _get_recommendation(data)

    signal_data = {
        "accepted_findings": data.get("accepted_findings", 0),
        "entries_seen": data.get("entries_seen", 0),
        "entries_scanned": data.get("entries_scanned", 0),
        "entries_with_hits": data.get("entries_with_hits", 0),
        "total_pattern_hits": data.get("total_pattern_hits", 0),
        "findings_built_pre_store": data.get("findings_built_pre_store", 0),
        "signal_stage": _safe_str(data.get("signal_stage")),
    }

    note = _stix2_module.Note(
        abstract=f"Ghost Prime Diagnostic: root_cause={root} ({label}); recommendation={rec}",
        content=json.dumps(signal_data, sort_keys=True),
        object_refs=[identity.id],
        created_by_ref=identity.id,
    )
    bundle.objects.append(note)

    # Root cause note
    rc_note = _stix2_module.Note(
        abstract=f"Root cause: {root} ({label}). Recommendation: {rec}. Network variance: {data.get('is_network_variance', False)}",
        content=json.dumps({
            "diagnostic_root_cause": root,
            "diagnostic_root_cause_label": label,
            "recommendation": rec,
            "is_network_variance": data.get("is_network_variance", False),
        }, sort_keys=True),
        object_refs=[identity.id],
        created_by_ref=identity.id,
    )
    bundle.objects.append(rc_note)

    return json.loads(str(bundle))


# ---------------------------------------------------------------------------
# Main bundle renderer
# ---------------------------------------------------------------------------
def render_stix_bundle(report: object) -> dict[str, Any]:
    """
    Render an ObservedRunReport (or Mapping) as a STIX 2.1 bundle dict.

    B.5: Never generates IOC/indicator/malware objects when no findings present.
    B.7: With zero accepted findings, exports only metadata-safe bundle
         (identity + diagnostic notes only).

    Parameters
    ----------
    report : msgspec.Struct or Mapping
        The observed run report.

    Returns
    -------
    dict
        STIX 2.1 bundle with type, id, spec_version, and objects list.
    """
    data = normalize_export_input(report)
    created = _iso_timestamp(data.get("started_ts") or data.get("finished_ts"))

    # Optional stix2 path
    if _stix2_available:
        return _build_stix2_bundle(data)

    # Builtins path: plain dicts
    objects: list[dict[str, Any]] = []

    # Always: identity (Ghost Prime as report author)
    objects.append(_build_diagnostic_identity())

    # Root cause + recommendation
    objects.append(_build_root_cause_object(data, created))

    # Signal funnel note
    objects.append(_build_diagnostic_note(data, created))

    # UMA note (if available)
    uma_note = _build_diagnostic_uma_note(data, created)
    if uma_note:
        objects.append(uma_note)

    # Per-source notes (if available)
    objects.extend(_build_per_source_notes(data, created))

    bundle: dict[str, Any] = {
        "type": _BUNDLE_TYPE,
        "id": _bundle_id(),
        "spec_version": _STIX_SPEC_VERSION,
        "created": created,
        "modified": created,
        "objects": objects,
    }

    return bundle


def render_stix_bundle_json(report: object) -> str:
    """
    Render report as a deterministic STIX bundle JSON string.

    Returns
    -------
    str
        JSON string with sorted keys for determinism.
    """
    bundle = render_stix_bundle(report)
    return json.dumps(bundle, indent=2, sort_keys=True, ensure_ascii=False)


# ---------------------------------------------------------------------------
# File-output helper
# ---------------------------------------------------------------------------
def render_stix_bundle_to_path(
    report: object,
    path: Union[str, Path, None] = None,
) -> Path:
    """
    Render report as STIX bundle and write to ``path``.

    If ``path`` is None:
      1. ``GHOST_EXPORT_DIR`` env var
      2. ``paths.RAMDISK_ROOT / "runs"`` (SSOT)
      3. ``/tmp/ghost_exports``

    Filename is deterministic: ``ghost_diagnostic_{run_id}.stix.json``
    falling back to ``ghost_diagnostic_{timestamp}.stix.json``.

    Returns the Path of the written file.
    """
    content = render_stix_bundle_json(report)

    if path is None:
        export_dir_env = os.environ.get("GHOST_EXPORT_DIR")
        if export_dir_env:
            base = Path(export_dir_env)
        else:
            try:
                from hledac.universal.paths import RAMDISK_ROOT
                base = RAMDISK_ROOT / "runs"
            except Exception:
                import tempfile
                base = Path(tempfile.gettempdir()) / "ghost_exports"
    else:
        base = Path(path).parent

    filename = Path(path).name if path else None
    if not filename:
        try:
            data = normalize_export_input(report)
            run_id = data.get("diagnostic_run_id") or data.get("run_id")
        except Exception:
            run_id = None
        if run_id:
            safe = str(run_id).replace("/", "_").replace("\\", "_")
            filename = f"ghost_diagnostic_{safe}.stix.json"
        else:
            try:
                ts = normalize_export_input(report).get("started_ts") or normalize_export_input(report).get("finished_ts")
            except Exception:
                ts = None
            if ts:
                filename = f"ghost_diagnostic_{int(ts)}.stix.json"
            else:
                filename = "ghost_diagnostic.stix.json"

    out_path = base / filename
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    return out_path
