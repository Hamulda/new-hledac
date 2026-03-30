"""
Deep Research Module for Hledac Universal Platform

Advanced research capabilities including:
- Path Discovery: Shadow Walker algorithm for hidden path prediction
- Link Rot Detection: Verify URL accessibility
- Content Extraction: Harvest structured data from HTML
"""

from __future__ import annotations

from .path_discovery import (
    ShadowWalkerAlgorithm,
    PathPatternAnalyzer,
    DatePathPattern,
    SequentialPathPattern,
    FilePathPattern,
)
from .utils import (
    LinkRotDetector,
    LinkCheckResult,
    Harvester,
    extract_dois,
    extract_dataset_ids,
    extract_emails,
    extract_phone_numbers,
    extract_social_media_links,
    extract_tables,
    clean_text,
    normalize,
)

__all__ = [
    # Path Discovery
    "ShadowWalkerAlgorithm",
    "PathPatternAnalyzer",
    "DatePathPattern",
    "SequentialPathPattern",
    "FilePathPattern",
    # Utils
    "LinkRotDetector",
    "LinkCheckResult",
    "Harvester",
    "extract_dois",
    "extract_dataset_ids",
    "extract_emails",
    "extract_phone_numbers",
    "extract_social_media_links",
    "extract_tables",
    "clean_text",
    "normalize",
]
