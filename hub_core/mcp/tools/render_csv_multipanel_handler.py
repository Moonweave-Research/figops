"""MCP multipanel CSV-render tool envelope.

The public mixin delegates here with its renderer instance so all established
runtime-root, envelope, and monkeypatch behaviour remains on that instance.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

from hub_core.adapters import select_adapters
from hub_core.mcp import render_orchestration as render_helpers
from hub_core.mcp.tools.render_csv_args import _normalized_multipanel_render_settings
from hub_core.mcp.tools.render_csv_multipanel import prepare_multipanel_render_payload, validate_multipanel_panel_specs
from hub_core.render_evidence import build_render_evidence
from themes.style_profiles import DEFAULT_PROFILE


def render_csv_multipanel(renderer: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    """Render a CSV multipanel figure through the supplied tool mixin instance."""
    guarded = renderer._authorize_write_tool("figops.render_csv_multipanel", arguments)
    if guarded is not None:
        return guarded
    dry_run = bool(arguments.get("dry_run", False))
    overwrite = bool(arguments.get("overwrite", False))
    job_id = renderer._render_job_id(arguments.get("job_id"))
    renderer._activate_runtime_root_for_runtime_access()
    job_root = renderer._mcp_jobs_root() / job_id
    target_format = str(arguments.get("target_format") or "nature").strip().lower()
    profile = str(arguments.get("profile") or DEFAULT_PROFILE).strip() or DEFAULT_PROFILE
    output_format = str(arguments.get("output_format") or "png").strip().lower().lstrip(".")
    panels_arg = arguments.get("panels")
    try:
        settings = _normalized_multipanel_render_settings(
            arguments,
            panel_count=len(panels_arg) if isinstance(panels_arg, list) else 0,
        )
    except (TypeError, ValueError) as exc:
        return renderer._csv_render_error(
            arguments,
            summary="Multipanel render request has invalid layout settings.",
            errors=[str(exc) or "rows, cols, panel_height_mm, font_scale, and layout_options must be valid."],
            is_dry_run=dry_run,
            failure_stage="CONFIG",
            resolution_hint="Provide numeric multipanel layout settings.",
            tool_name="figops.render_csv_multipanel",
        )
    rows = settings["rows"]
    cols = settings["cols"]
    panel_height_mm = settings["panel_height_mm"]
    font_scale = settings["font_scale"]
    layout_options = settings["layout_options"]
    shared_legend = settings["shared_legend"]
    shared_legend_options = settings["shared_legend_options"]

    if shared_legend_options and not shared_legend:
        return renderer._csv_render_error(
            arguments,
            summary="Multipanel render request has invalid shared legend settings.",
            errors=["shared_legend_options requires shared_legend=true."],
            is_dry_run=dry_run,
            failure_stage="CONFIG",
            resolution_hint="Set shared_legend=true or remove shared_legend_options.",
            tool_name="figops.render_csv_multipanel",
        )
    if not isinstance(panels_arg, list) or not panels_arg:
        return renderer._csv_render_error(
            arguments,
            summary="Multipanel render request has invalid panel settings.",
            errors=["panels must be a non-empty array."],
            is_dry_run=dry_run,
            failure_stage="CONFIG",
            resolution_hint="Provide one or more CSV panel objects.",
            tool_name="figops.render_csv_multipanel",
        )
    if rows < 1 or cols < 1:
        return renderer._csv_render_error(
            arguments,
            summary="Multipanel render request has invalid layout settings.",
            errors=["rows and cols must be positive integers."],
            is_dry_run=dry_run,
            failure_stage="CONFIG",
            resolution_hint="Use positive rows and cols.",
            tool_name="figops.render_csv_multipanel",
        )
    if rows * cols < len(panels_arg):
        return renderer._csv_render_error(
            arguments,
            summary="Multipanel render request has too many panels for the grid.",
            errors=[f"rows * cols must fit {len(panels_arg)} panel(s); got {rows} * {cols}."],
            is_dry_run=dry_run,
            failure_stage="CONFIG",
            resolution_hint="Increase rows or cols, or remove panels.",
            tool_name="figops.render_csv_multipanel",
        )
    if panel_height_mm <= 0 or font_scale <= 0:
        return renderer._csv_render_error(
            arguments,
            summary="Multipanel render request has invalid layout settings.",
            errors=["panel_height_mm and font_scale must be positive."],
            is_dry_run=dry_run,
            failure_stage="CONFIG",
            resolution_hint="Use positive panel_height_mm and font_scale.",
            tool_name="figops.render_csv_multipanel",
        )
    style_errors = renderer._render_style_errors(target_format, output_format, profile)
    if style_errors:
        return renderer._csv_render_error(
            arguments,
            summary="Multipanel render request has invalid style settings.",
            errors=style_errors,
            is_dry_run=dry_run,
            failure_stage="CONFIG",
            resolution_hint="Use a supported target_format, output_format, and profile.",
            tool_name="figops.render_csv_multipanel",
        )

    panel_validation = validate_multipanel_panel_specs(
        renderer=renderer,
        panels_arg=panels_arg,
        target_format=target_format,
        profile=profile,
    )
    source_paths = panel_validation["source_paths"]
    panel_specs = panel_validation["panel_specs"]
    contract_errors = panel_validation["contract_errors"]
    calculation_checks = panel_validation["calculation_checks"]
    calculation_evidence = panel_validation["calculation_evidence"]
    panel_calculation_evidence = panel_validation["panel_calculation_evidence"]
    statistical_claims = panel_validation["statistical_claims"]
    claim_candidates = panel_validation["claim_candidates"]
    if contract_errors:
        return renderer._csv_render_error(
            arguments,
            summary="Multipanel render request failed validation.",
            errors=contract_errors,
            is_dry_run=dry_run,
            failure_stage="CONTRACT",
            resolution_hint="Fix panel CSV paths, columns, plot types, scales, or error-bar inputs.",
            tool_name="figops.render_csv_multipanel",
        )
    if dry_run:
        dry_manual_review = bool(calculation_checks.get("manual_review_needed")) or bool(claim_candidates)
        return renderer._envelope(
            "figops.render_csv_multipanel",
            arguments,
            status="warning" if dry_manual_review else "ok",
            summary="Multipanel CSV render dry run passed.",
            warnings=renderer._calculation_warnings(calculation_checks),
            manual_review_needed=dry_manual_review,
            is_dry_run=True,
            calculation_checks=calculation_checks,
            statistical_claims=statistical_claims,
            claim_candidates=claim_candidates,
        )
    if job_root.exists() and not overwrite:
        return renderer._csv_render_error(
            arguments,
            summary="Render job already exists.",
            errors=[f"Render job already exists: {renderer._runtime_uri(job_root)}. Set overwrite=true to replace it."],
            is_dry_run=False,
            failure_stage="CONFIG",
            resolution_hint="Use a unique job_id or set overwrite=true.",
            tool_name="figops.render_csv_multipanel",
        )
    if job_root.exists() and overwrite:
        symlink = render_helpers._first_symlink_component(job_root)
        if symlink is not None:
            return renderer._csv_render_error(
                arguments,
                summary="Render job path is not safe to overwrite.",
                errors=[f"Runtime job path includes a symlinked component: {symlink}"],
                is_dry_run=False,
                failure_stage="EXPORT",
                resolution_hint="Choose a new job_id or remove the symlinked runtime path manually.",
                tool_name="figops.render_csv_multipanel",
            )
        shutil.rmtree(job_root)

    output_path = job_root / "outputs" / f"multipanel.{output_format}"
    config_path = job_root / "config" / "multipanel.yaml"
    manifest_path = job_root / "manifest.json"
    status_path = job_root / "status.json"
    latest_dir = renderer.runtime_root / "_latest" / "mcp_render"
    created_paths: list[str] = []
    unsafe_path = (
        render_helpers._first_symlink_component(job_root)
        or render_helpers._first_symlink_component(latest_dir)
    )
    if unsafe_path is not None:
        return renderer._csv_render_error(
            arguments,
            summary="Multipanel render runtime path is not safe to write.",
            errors=[f"Runtime write path includes a symlinked component: {unsafe_path}"],
            is_dry_run=False,
            failure_stage="EXPORT",
            resolution_hint="Choose a different job_id/runtime root or remove the symlinked runtime path manually.",
            tool_name="figops.render_csv_multipanel",
        )
    try:
        job_root.mkdir(parents=True, exist_ok=True)
        (job_root / "data").mkdir(parents=True, exist_ok=True)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        prefetch_config = renderer._render_project_config(
            target_format=target_format,
            profile=profile,
            output_format=output_format,
            x_column=panel_specs[0]["x_column"],
            y_column=panel_specs[0]["y_column"],
            z_column="",
            facet_column="",
            series_column="",
            semantic_checks={},
        )
        with redirect_stdout(sys.stderr):
            select_adapters(prefetch_config).prefetcher.ensure_local([str(path) for path in source_paths])

        prepared = prepare_multipanel_render_payload(
            panel_specs=panel_specs,
            job_root=job_root,
            output_path=output_path,
            config_path=config_path,
            arguments=arguments,
            rows=rows,
            cols=cols,
            target_format=target_format,
            profile=profile,
            output_format=output_format,
            panel_height_mm=panel_height_mm,
            font_scale=font_scale,
            layout_options=layout_options,
            shared_legend=shared_legend,
            shared_legend_options=shared_legend_options,
        )
        render_payload = prepared["render_payload"]
        copied_data_paths = prepared["copied_data_paths"]
        created_paths.extend(prepared["created_paths"])
        with renderer._geometry_diagnostics_env(job_root):
            if any(panel_calculation_evidence):
                renderer._run_render_multipanel_figure(
                    render_payload,
                    verified_calculation_evidence=tuple(panel_calculation_evidence),
                )
            else:
                renderer._run_render_multipanel_figure(render_payload)
        geometry_diagnostics = render_helpers._read_geometry_sidecar(job_root)
        authored_output_path = job_root / "authored_output.json"
        authored_output = (
            json.loads(authored_output_path.read_text(encoding="utf-8"))
            if authored_output_path.is_file()
            else {"mode": "raw", "mappings": [], "collisions": [], "mutation_ledger": []}
        )
        descriptive_overlays = [
            {
                "panel_index": index,
                "kind": "linear_fit",
                "algorithm": "ordinary_least_squares",
                "descriptive_only": True,
            }
            for index, panel in enumerate(panel_specs)
            if panel.get("fit_line")
        ]
        geometry_warnings = render_helpers._geometry_warnings(geometry_diagnostics)
        layout_report = render_helpers._layout_report_from_geometry(geometry_diagnostics)
        figures = renderer._rendered_figure_artifacts(output_path)
        preview_artifacts = render_helpers._build_preview_artifacts(
            job_root=job_root,
            output_path=output_path,
            figures=figures,
        )
        preview_references = render_helpers._preview_resource_references(job_id, preview_artifacts)
        created_paths.extend(str(figure["path"]) for figure in figures)
        preflight = renderer._visual_preflight_with_geometry_overlaps(output_path, target_format, geometry_diagnostics)
        preflight_warnings = renderer._preflight_warnings(preflight)
        baseline_comparison = renderer._baseline_comparison(output_path, arguments.get("baseline_path"))
        baseline_warnings = renderer._baseline_warnings(baseline_comparison)
        calculation_warnings = renderer._calculation_warnings(calculation_checks)
        manual_review_needed = (
            not bool(preflight.get("passed"))
            or bool(preflight_warnings)
            or (baseline_comparison["checked"] and not baseline_comparison["matched"])
            or bool(calculation_checks.get("manual_review_needed"))
            or geometry_diagnostics.get("passed") is False
            or bool(claim_candidates)
        )
        status = "warning" if manual_review_needed else "ok"
        artifact_status = renderer._artifact_status(preflight, baseline_comparison)
        provenance = renderer._mcp_render_provenance(
            job_id=job_id,
            source_data_path=source_paths[0],
            copied_data_path=Path(copied_data_paths[0]),
            config_path=config_path,
            output_path=output_path,
            target_format=target_format,
            profile=profile,
            output_format=output_format,
        )
        source_hashes = [renderer._file_sha256(path) for path in source_paths]
        copied_hashes = [renderer._file_sha256(Path(path)) for path in copied_data_paths]
        provenance.update(
            {
                "renderer": "plotting.bridge_renderer.render_multipanel_figure",
                "renderer_surface": "figops.render_csv_multipanel",
                "input_sha256": hashlib.sha256(
                    json.dumps(source_hashes, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                ).hexdigest(),
                "source_data_sha256": hashlib.sha256(
                    json.dumps(source_hashes, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                ).hexdigest(),
                "copied_data_sha256": hashlib.sha256(
                    json.dumps(copied_hashes, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                ).hexdigest(),
                "source_data_paths": [str(path) for path in source_paths],
                "copied_data_paths": copied_data_paths,
            }
        )
        if calculation_evidence:
            provenance["calculation_evidence_refs"] = [
                {
                    "artifact_ref": item["artifact_ref"],
                    "sha256": item["analysis_artifact_sha256"],
                    "evidence_id": item["evidence_id"],
                }
                for item in calculation_evidence
            ]
        created_paths.extend([str(manifest_path), str(status_path)])
        manifest = render_helpers._build_manifest(
            job_id=job_id,
            job_root=job_root,
            config_path=config_path,
            status_path=status_path,
            latest_dir=latest_dir,
            figures=figures,
            created_paths=created_paths,
            style_summary={"target_format": target_format, "profile": profile, "output_format": output_format},
            visual_preflight_status=preflight,
            geometry_diagnostics=geometry_diagnostics,
            layout_report=layout_report,
            artifact_status=artifact_status,
            baseline_comparison=baseline_comparison,
            manual_review_needed=manual_review_needed,
            provenance=provenance,
            data_contract={"schema_version": "data_contract_summary/1", "passed": True},
            calculation_checks=calculation_checks,
            statistical_claims=statistical_claims,
            calculation_evidence=calculation_evidence,
            descriptive_overlays=descriptive_overlays,
            claim_candidates=claim_candidates,
            label_transformations=authored_output,
            mutation_ledger=authored_output.get("mutation_ledger", []),
            preview_artifacts=preview_artifacts,
        )
        manifest["evidence"] = build_render_evidence(
            manifest,
            job_root=job_root,
            producer_kind="mcp-csv-multipanel-render",
            producer_version=renderer._read_version(),
            baseline_reference_sha256=(
                renderer._file_sha256(Path(baseline_comparison["baseline_path"]))
                if baseline_comparison.get("checked")
                and isinstance(baseline_comparison.get("baseline_path"), str)
                and Path(baseline_comparison["baseline_path"]).is_file()
                else None
            ),
        )
        status_payload = renderer._render_status_payload(
            job_id=job_id,
            status=status,
            summary="Rendered CSV multipanel." if status == "ok" else "Rendered CSV multipanel with warnings.",
            manifest_path=manifest_path,
            output_path=output_path,
            artifact_status=artifact_status,
            manual_review_needed=manual_review_needed,
            failure_stage="",
            resolution_hint="",
        )
        status_payload["calculation_checks"] = calculation_checks
        status_payload["provenance"] = provenance
        status_payload["layout_report"] = layout_report
        status_payload["statistical_claims"] = statistical_claims
        status_payload["calculation_evidence"] = calculation_evidence
        status_payload["descriptive_overlays"] = descriptive_overlays
        status_payload["claim_candidates"] = claim_candidates
        status_payload["label_transformations"] = authored_output
        render_helpers._write_manifest_and_status(manifest, manifest_path, status_payload, status_path, latest_dir)
    except Exception as exc:
        return renderer._csv_render_error(
            arguments,
            summary="Multipanel render execution failed.",
            errors=[str(exc)],
            is_dry_run=False,
            created_paths=created_paths,
            job_id=job_id,
            job_root=str(job_root),
            failure_stage="PLOT",
            resolution_hint="Inspect the render engine error and multipanel input settings.",
            tool_name="figops.render_csv_multipanel",
        )
    return renderer._envelope(
        "figops.render_csv_multipanel",
        arguments,
        status=status,
        summary="Rendered CSV multipanel." if status == "ok" else "Rendered CSV multipanel with warnings.",
        created_paths=created_paths,
        artifact_resources=preview_references["artifact_resources"],
        preview_resources=preview_references["preview_resources"],
        warnings=preflight_warnings + baseline_warnings + calculation_warnings + geometry_warnings,
        manual_review_needed=manual_review_needed,
        is_dry_run=False,
        job_id=job_id,
        job_root=str(job_root),
        output_path=str(output_path),
        config_path=str(config_path),
        manifest_path=str(manifest_path),
        status_path=str(status_path),
        latest_dir=str(latest_dir),
        latest_alias=str(latest_dir),
        style_summary=manifest["style_summary"],
        visual_preflight_status=preflight,
        geometry_diagnostics=geometry_diagnostics,
        layout_report=layout_report,
        failure_stage="",
        resolution_hint="",
        artifact_status=artifact_status,
        baseline_comparison=baseline_comparison,
        calculation_checks=calculation_checks,
        provenance=provenance,
        statistical_claims=statistical_claims,
        calculation_evidence=calculation_evidence,
        descriptive_overlays=descriptive_overlays,
        claim_candidates=claim_candidates,
        label_transformations=authored_output,
        mutation_ledger=authored_output.get("mutation_ledger", []),
        evidence=manifest["evidence"],
    )
