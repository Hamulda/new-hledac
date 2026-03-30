"""
Checkpoint utilities with bounded serialization.

Provides helpers for safe checkpoint serialization with:
- Host penalties bounding
- Size limits enforcement
"""

import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Constants for bounding
MAX_CHECKPOINT_BYTES = 512 * 1024  # 512KB max checkpoint size
MAX_HOST_PENALTIES = 512  # Max number of host penalties to keep
MAX_HOST_LEN = 256  # Max length for host string


def _bound_host_penalties(obj: Dict[str, Any]) -> Dict[str, Any]:
    """
    Bound host_penalties dict to MAX_HOST_PENALTIES entries.
    Keeps top-K highest penalties.

    This is called BEFORE the first json.dumps to ensure bounding
    happens even in the main serialization path.
    """
    hp = obj.get("host_penalties")
    if not isinstance(hp, dict):
        return obj
    if len(hp) <= MAX_HOST_PENALTIES:
        return obj

    # Convert to list of (penalty, host) tuples
    items = []
    for k, v in hp.items():
        try:
            host = str(k)[:MAX_HOST_LEN]
            pen = float(v)
            if pen < 0.0:
                pen = 0.0
            items.append((pen, host))
        except (ValueError, TypeError):
            continue

    # Sort by penalty descending, keep top K
    items.sort(key=lambda t: t[0], reverse=True)
    bounded = {host: pen for pen, host in items[:MAX_HOST_PENALTIES]}

    logger.debug(f"Bounded host_penalties from {len(hp)} to {len(bounded)} entries")
    return {**obj, "host_penalties": bounded}


def bounded_json_dumps(obj: Dict[str, Any], max_bytes: int = MAX_CHECKPOINT_BYTES) -> str:
    """
    Serialize to JSON with host_penalties bounding.
    Bounding happens BEFORE first json.dumps call.
    """
    # Shallow copy to avoid mutating the input dict
    obj = {**obj}

    # Bound host_penalties first
    obj = _bound_host_penalties(obj)

    # First serialization attempt
    data = json.dumps(obj)
    if len(data.encode('utf-8')) <= max_bytes:
        return data

    # If still too large, try shrinking other fields
    logger.warning(f"Checkpoint still too large after bounding, attempting further truncation")

    # Try removing lower priority fields
    if "debug_info" in obj:
        del obj["debug_info"]
        data = json.dumps(obj)
        if len(data.encode('utf-8')) <= max_bytes:
            return data

    # Last resort: truncate results
    if "results" in obj and isinstance(obj["results"], list):
        while len(obj["results"]) > 10 and len(json.dumps(obj).encode('utf-8')) > max_bytes:
            obj["results"] = obj["results"][:-5]

    return json.dumps(obj)
