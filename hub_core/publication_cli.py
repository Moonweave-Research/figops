"""CLI adapter for publication-readiness manifest evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from .publication_evidence import load_readiness_manifest
from .publication_readiness import (
    evaluate_publication_readiness,
    render_readiness_json,
    render_readiness_markdown,
)

ReadinessOutputFormat = Literal["json", "markdown"]
RENDER_JOB_REQUIRED_EVIDENCE = (
    "geometry_diagnostics",
    "visual_preflight_status",
    "layout_report",
)
_EXIT_CODES = {"needs_review": 0, "needs_revision": 2, "blocked": 1}


def evaluate_readiness_manifest(
    path: str | Path,
    *,
    output_format: ReadinessOutputFormat = "markdown",
) -> tuple[str, int]:
    """Load one render manifest and return its report text and process exit code."""
    evidence = load_readiness_manifest(path)
    report = evaluate_publication_readiness(
        evidence,
        project_id=evidence.get("project_id"),
        figure_id=evidence.get("figure_id"),
        required_evidence=RENDER_JOB_REQUIRED_EVIDENCE,
    )
    if output_format == "json":
        rendered = render_readiness_json(report)
    elif output_format == "markdown":
        rendered = render_readiness_markdown(report)
    else:
        raise ValueError(f"unsupported readiness output format: {output_format}")
    return rendered, _EXIT_CODES[report["readiness_status"]]
