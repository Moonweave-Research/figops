"""Small response-formatting helpers shared by CSV render handlers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def render_completion_summary(
    subject: str,
    *,
    status: str,
    geometry_verification: dict[str, Any],
) -> str:
    """Describe a completed render without obscuring unverified geometry."""

    if status == "ok":
        return f"Rendered {subject}."
    if geometry_verification.get("status") == "unverified":
        return f"Rendered {subject} without required geometry verification."
    return f"Rendered {subject} with preflight warnings."


def csv_render_success_envelope(
    renderer: Any,
    arguments: dict[str, Any],
    *,
    values: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the stable CSV render response from its completed render context."""

    return renderer._envelope(
        "figops.render_csv_graph",
        arguments,
        status=values["status"],
        summary=values["render_summary"],
        created_paths=values["created_paths"],
        artifact_resources=values["preview_references"]["artifact_resources"],
        preview_resources=values["preview_references"]["preview_resources"],
        warnings=(
            values["preflight_warnings"]
            + values["baseline_warnings"]
            + values["calculation_warnings"]
            + values["geometry_warnings"]
            + ([values["facet_promotion_warning"]] if values["facet_promotion_warning"] else [])
        ),
        manual_review_needed=values["manual_review_needed"],
        is_dry_run=False,
        job_id=values["job_id"],
        job_root=str(values["job_root"]),
        output_path=str(values["output_path"]),
        config_path=str(values["config_path"]),
        manifest_path=str(values["manifest_path"]),
        status_path=str(values["status_path"]),
        latest_dir=str(values["latest_dir"]),
        latest_alias=str(values["latest_dir"]),
        style_summary=values["manifest"]["style_summary"],
        visual_preflight_status=values["preflight"],
        geometry_diagnostics=values["geometry_diagnostics"],
        layout_report=values["layout_report"],
        failure_stage="",
        resolution_hint="",
        artifact_status=values["artifact_status"],
        baseline_comparison=values["baseline_comparison"],
        calculation_checks=values["calculation_checks"],
        statistical_claims=values["statistical_claims"],
        calculation_evidence=values["calculation_evidence"],
        descriptive_overlays=values["descriptive_overlays"],
        claim_candidates=values["claim_candidates"],
        label_transformations=values["authored_output"],
        mutation_ledger=values["authored_output"].get("mutation_ledger", []),
        evidence=values["manifest"]["evidence"],
    )
