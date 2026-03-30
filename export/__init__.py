# hledac/universal/export/__init__.py
"""Export namespace for Ghost Prime diagnostic outputs."""
from __future__ import annotations

from hledac.universal.export.jsonld_exporter import (
    normalize_export_input as normalize_export_input,
    render_jsonld,
    render_jsonld_str,
    render_jsonld_to_path,
)
from hledac.universal.export.markdown_reporter import (
    normalize_report_input,
    render_diagnostic_markdown,
    render_diagnostic_markdown_to_path,
)
from hledac.universal.export.stix_exporter import (
    render_stix_bundle,
    render_stix_bundle_json,
    render_stix_bundle_to_path,
)

__all__ = [
    # Shared
    "normalize_export_input",
    "normalize_report_input",
    # Markdown
    "render_diagnostic_markdown",
    "render_diagnostic_markdown_to_path",
    # JSON-LD
    "render_jsonld",
    "render_jsonld_str",
    "render_jsonld_to_path",
    # STIX
    "render_stix_bundle",
    "render_stix_bundle_json",
    "render_stix_bundle_to_path",
]
