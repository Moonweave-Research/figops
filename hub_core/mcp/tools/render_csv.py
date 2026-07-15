from __future__ import annotations

import json
import shutil
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

import yaml

from hub_core.adapters import select_adapters
from hub_core.config_parser import validate_config
from hub_core.mcp import render_orchestration as render_helpers
from hub_core.mcp.tools.render_csv_args import (
    LEGEND_LAYOUT_PRESETS,  # noqa: F401
    _fill_between_required_columns,
    _normalized_annotation_args,
    _normalized_axis_limits_arg,
    _normalized_axis_scale_arg,
    _normalized_fill_between_args,
    _normalized_fit_options_arg,
    _normalized_guide_curve_args,
    _normalized_legend_layout_arg,
    _normalized_legend_options_arg,
    _normalized_point_label_options_arg,
    _normalized_secondary_y_arg,
    _normalized_series_style_args,
    _normalized_span_annotation_arg,  # noqa: F401
    _normalized_tick_style_arg,
    _reject_non_point_callout_args,  # noqa: F401
    _validated_plot_argument_compatibility,
)
from hub_core.mcp.tools.render_csv_multipanel_handler import render_csv_multipanel as _render_csv_multipanel_handler
from hub_core.mcp.tools.render_support import McpRenderToolSupportMixin
from hub_core.mcp.tools.render_validation import _optional_positive_int_arg
from hub_core.render_evidence import build_render_evidence
from hub_core.rendering import PLOT_TYPES
from themes.style_profiles import DEFAULT_PROFILE


class McpRenderCsvMixin(McpRenderToolSupportMixin):
    """CSV-graph rendering MCP tool handlers."""

    def render_csv_graph(self, arguments: dict[str, Any]) -> dict[str, Any]:
        guarded = self._authorize_write_tool("figops.render_csv_graph", arguments)
        if guarded is not None:
            return guarded
        dry_run = bool(arguments.get("dry_run", False))
        overwrite = bool(arguments.get("overwrite", False))
        job_id = self._render_job_id(arguments.get("job_id"))
        self._activate_runtime_root_for_runtime_access()
        job_root = self._mcp_jobs_root() / job_id
        try:
            from plotting.utils import normalize_label_map

            data_path = self._input_file_path(arguments.get("data_path"))
            x_column = self._required_string(arguments, "x_column")
            y_column = self._required_string(arguments, "y_column")
            z_column = str(arguments.get("z_column") or "").strip()
            facet_column = str(arguments.get("facet_column") or "").strip()
            series_column = str(arguments.get("series_column") or "").strip()
            label_column = str(arguments.get("label_column") or "").strip()
            label_map = normalize_label_map(arguments.get("label_map"))
            label_transform = str(arguments.get("label_transform") or "raw").strip().lower().replace("-", "_")
            if label_transform not in {"raw", "legacy_compress"}:
                raise ValueError("label_transform must be 'raw' or 'legacy_compress'.")
            compliance_mode = str(arguments.get("compliance_mode") or "validate").strip().lower()
            declutter_mode = str(arguments.get("declutter_mode") or "none").strip().lower()
            if compliance_mode not in {"validate", "clamp"}:
                raise ValueError("compliance_mode must be 'validate' or 'clamp'.")
            if declutter_mode not in {"none", "declutter"}:
                raise ValueError("declutter_mode must be 'none' or 'declutter'.")
            calculation_evidence = self._verified_calculation_evidence(
                arguments.get("calculation_evidence_path"),
                arguments.get("calculation_evidence_paths"),
            )
        except ValueError as exc:
            return self._csv_render_error(
                arguments,
                summary="Render request has invalid CSV input settings.",
                errors=[str(exc)],
                is_dry_run=dry_run,
                failure_stage="CONTRACT",
                resolution_hint="Fix data_path and CSV column inputs before rendering.",
            )
        plot_type = str(arguments.get("plot_type") or "scatter").strip().lower()
        target_format = str(arguments.get("target_format") or "nature").strip().lower()
        profile = str(arguments.get("profile") or DEFAULT_PROFILE).strip() or DEFAULT_PROFILE
        output_format = str(arguments.get("output_format") or "png").strip().lower().lstrip(".")
        facet_scales = str(arguments.get("facet_scales") or "fixed").strip().lower()
        fit_line = arguments.get("fit_line", False)
        ci_band = arguments.get("ci_band", False)
        descriptive_overlays = (
            [{"kind": "linear_fit", "algorithm": "ordinary_least_squares", "descriptive_only": True}]
            if fit_line
            else []
        )
        try:
            significance_markers = self._normalized_significance_markers_arg(
                arguments.get("significance_markers")
            )
        except ValueError as exc:
            return self._csv_render_error(
                arguments,
                summary="Render request has invalid statistical overlay settings.",
                errors=[str(exc)],
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Provide closed, evidence-linked significance marker objects.",
            )
        aggregate = str(arguments.get("aggregate") or "").strip().lower()
        raw_annotate_values = arguments.get("annotate_values", False)
        raw_bar_error_column = arguments.get("bar_error_column", "")
        raw_yerr_column = arguments.get("yerr_column", "")
        raw_yerr_minus_column = arguments.get("yerr_minus_column", "")
        raw_yerr_cap_width = arguments.get("yerr_cap_width")
        raw_facet_ncols = arguments.get("facet_ncols")
        raw_facet_nrows = arguments.get("facet_nrows")
        try:
            category_order = self._order_arg(arguments.get("category_order"), "category_order", allow_numbers=True)
            facet_order = self._order_arg(arguments.get("facet_order"), "facet_order", allow_numbers=False)
            facet_ncols = _optional_positive_int_arg(raw_facet_ncols, "facet_ncols")
            facet_nrows = _optional_positive_int_arg(raw_facet_nrows, "facet_nrows")
            x_scale = _normalized_axis_scale_arg(arguments.get("x_scale"), field_name="x_scale")
            y_scale = _normalized_axis_scale_arg(arguments.get("y_scale"), field_name="y_scale")
            secondary_y = _normalized_secondary_y_arg(arguments.get("secondary_y"))
            legend_layout = _normalized_legend_layout_arg(arguments.get("legend_layout"), field_name="legend_layout")
            legend_options = _normalized_legend_options_arg(
                arguments.get("legend_options"), field_name="legend_options"
            )
            axis_limits = _normalized_axis_limits_arg(
                arguments.get("axis_limits"), field_name="axis_limits", x_scale=x_scale, y_scale=y_scale
            )
            tick_style = _normalized_tick_style_arg(arguments.get("tick_style"), field_name="tick_style")
            point_label_options = _normalized_point_label_options_arg(
                arguments.get("point_label_options"), field_name="point_label_options"
            )
            annotations = _normalized_annotation_args(arguments.get("annotations"))
            series_styles = _normalized_series_style_args(arguments.get("series_styles"))
            fit_options = _normalized_fit_options_arg(arguments.get("fit_options"))
            guide_curves = _normalized_guide_curve_args(arguments.get("guide_curves"))
            fill_between = _normalized_fill_between_args(arguments.get("fill_between"))
        except ValueError as exc:
            return self._csv_render_error(
                arguments,
                summary="Render request has invalid plot argument settings.",
                errors=[str(exc)],
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint=(
                    "Provide valid ordering, facet sizing, axis-scale, annotation, and series style arguments."
                ),
            )
        compatibility = _validated_plot_argument_compatibility(
            plot_type=plot_type,
            raw_annotate_values=raw_annotate_values,
            raw_bar_error_column=raw_bar_error_column,
            raw_yerr_column=raw_yerr_column,
            raw_yerr_minus_column=raw_yerr_minus_column,
            raw_yerr_cap_width=raw_yerr_cap_width,
            series_column=series_column,
            label_column=label_column,
            point_label_options=point_label_options,
            guide_curves=guide_curves,
            fill_between=fill_between,
        )
        annotate_values = compatibility["annotate_values"]
        bar_error_column = compatibility["bar_error_column"]
        yerr_column = compatibility["yerr_column"]
        yerr_minus_column = compatibility["yerr_minus_column"]
        yerr_cap_width = compatibility["yerr_cap_width"]
        render_arg_errors = compatibility["errors"]
        if secondary_y and plot_type not in {"line", "scatter", "xy"}:
            render_arg_errors.append("secondary_y is only supported for plot_type 'line', 'scatter', or 'xy'.")
        if render_arg_errors:
            return self._csv_render_error(
                arguments,
                summary="Render request has invalid plot argument settings.",
                errors=render_arg_errors,
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Use annotate_values only with heatmap and bar_error_column only with bar plots.",
            )
        raw_semantic_checks = arguments.get("semantic_checks", {})
        semantic_checks = {} if raw_semantic_checks is None else raw_semantic_checks
        if plot_type not in PLOT_TYPES:
            return self._csv_render_error(
                arguments,
                summary="Render request has invalid plot settings.",
                errors=[f"Invalid plot_type '{plot_type}'. Supported: {', '.join(sorted(PLOT_TYPES))}."],
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Use a supported plot_type.",
            )
        category_order_errors = self._category_order_arg_errors(plot_type=plot_type, category_order=category_order)
        if category_order_errors:
            return self._csv_render_error(
                arguments,
                summary="Render request has invalid category ordering settings.",
                errors=category_order_errors,
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Use category_order only with plot types that support categorical x ordering.",
            )
        overlay_errors = self._statistical_overlay_arg_errors(
            plot_type=plot_type,
            fit_line=fit_line,
            ci_band=ci_band,
            fit_options=fit_options,
            significance_markers=significance_markers,
        )
        if overlay_errors:
            return self._csv_render_error(
                arguments,
                summary="Render request has invalid statistical overlay settings.",
                errors=overlay_errors,
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Use fit_line, ci_band, and significance_markers only with line, scatter, or xy plots.",
            )
        aggregate_errors = self._bar_aggregate_arg_errors(plot_type=plot_type, aggregate=aggregate)
        if aggregate_errors:
            return self._csv_render_error(
                arguments,
                summary="Render request has invalid bar aggregation settings.",
                errors=aggregate_errors,
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Use aggregate='mean' or aggregate='median' only with plot_type 'bar'.",
            )
        if plot_type == "heatmap" and not z_column:
            return self._csv_render_error(
                arguments,
                summary="Render request has invalid plot settings.",
                errors=["plot_type 'heatmap' requires a z_column."],
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Provide z_column for heatmap plot_type.",
            )
        if plot_type == "facet" and not facet_column:
            return self._csv_render_error(
                arguments,
                summary="Render request has invalid plot settings.",
                errors=["plot_type 'facet' requires a facet_column."],
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Provide facet_column for facet plot_type.",
            )
        if facet_scales not in {"fixed", "free"}:
            return self._csv_render_error(
                arguments,
                summary="Render request has invalid facet settings.",
                errors=["facet_scales must be 'fixed' or 'free'."],
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Use facet_scales='fixed' for shared axes or facet_scales='free' for independent axes.",
            )
        style_errors = self._render_style_errors(target_format, output_format, profile)
        if style_errors:
            return self._csv_render_error(
                arguments,
                summary="Render request has invalid style settings.",
                errors=style_errors,
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Use a supported target_format, output_format, and profile.",
            )
        if not isinstance(semantic_checks, dict):
            return self._csv_render_error(
                arguments,
                summary="Render request has invalid data contract settings.",
                errors=["semantic_checks must be an object."],
                is_dry_run=dry_run,
                failure_stage="CONTRACT",
                resolution_hint="Provide semantic_checks as an object keyed by CSV column.",
            )
        if bar_error_column or yerr_column:
            try:
                semantic_checks = self._semantic_checks_with_bar_error_column(
                    semantic_checks,
                    y_column=y_column,
                    bar_error_column=bar_error_column or yerr_column,
                )
            except ValueError as exc:
                return self._csv_render_error(
                    arguments,
                    summary="Render request has conflicting bar error column settings.",
                    errors=[str(exc)],
                    is_dry_run=dry_run,
                    failure_stage="CONFIG",
                    resolution_hint="Remove the conflicting semantic_checks entry or align it with bar_error_column.",
                )
        config = self._render_project_config(
            target_format=target_format,
            profile=profile,
            output_format=output_format,
            x_column=x_column,
            y_column=y_column,
            z_column=z_column,
            facet_column=facet_column,
            series_column=series_column,
            semantic_checks=semantic_checks,
            extra_required_columns=_fill_between_required_columns(
                fill_between,
                existing=tuple(
                    column
                    for column in (
                        x_column,
                        y_column,
                        z_column,
                        facet_column,
                        series_column,
                        secondary_y["column"] if secondary_y else "",
                        label_column,
                        str(point_label_options.get("priority_column") or ""),
                        str(point_label_options.get("skip_column") or ""),
                    )
                    if column
                ),
            ),
        )
        config_errors = validate_config(config)
        if config_errors:
            return self._csv_render_error(
                arguments,
                summary="Render request has invalid project config settings.",
                errors=config_errors,
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Fix the generated render project_config settings.",
            )
        prefetcher = select_adapters(config).prefetcher
        with redirect_stdout(sys.stderr):
            prefetcher.ensure_local([str(data_path)])
        contract_result = self._validate_render_data_contract(
            data_path,
            required_columns=[
                x_column,
                y_column,
                *([z_column] if z_column else []),
                *([facet_column] if facet_column else []),
                *([series_column] if series_column else []),
                *([secondary_y["column"]] if secondary_y else []),
                *([label_column] if label_column else []),
                *(
                    [str(point_label_options.get("priority_column"))]
                    if point_label_options.get("priority_column")
                    else []
                ),
                *([str(point_label_options.get("skip_column"))] if point_label_options.get("skip_column") else []),
                *([yerr_column] if yerr_column else []),
                *([yerr_minus_column] if yerr_minus_column else []),
                *_fill_between_required_columns(
                    fill_between,
                    existing=tuple(
                        column
                        for column in (
                            x_column,
                            y_column,
                            z_column,
                            facet_column,
                            series_column,
                            secondary_y["column"] if secondary_y else "",
                            label_column,
                            yerr_column,
                            yerr_minus_column,
                            str(point_label_options.get("priority_column") or ""),
                            str(point_label_options.get("skip_column") or ""),
                        )
                        if column
                    ),
                ),
                *[str(key) for key in semantic_checks],
            ],
            semantic_checks=semantic_checks,
            axis_scales={
                x_column: x_scale,
                y_column: y_scale,
                **({secondary_y["column"]: secondary_y["scale"]} if secondary_y else {}),
            },
        )
        contract_errors = contract_result["errors"]
        calculation_checks = contract_result["calculation_checks"]
        claim_linkage_errors = self._statistical_claim_linkage_errors(significance_markers, calculation_evidence)
        annotation_claims = self._annotation_claim_evidence(
            annotations,
            calculation_evidence,
            claimed_ids={marker["calculation_evidence_id"] for marker in significance_markers},
        )
        band_claims = self._fill_band_claim_evidence(fill_between)
        claim_linkage_errors.extend(annotation_claims["errors"])
        claim_linkage_errors.extend(band_claims["errors"])
        if claim_linkage_errors:
            return self._csv_render_error(
                arguments,
                summary="Statistical claim evidence linkage failed.",
                errors=claim_linkage_errors,
                is_dry_run=dry_run,
                failure_stage="CONTRACT",
                resolution_hint=(
                    "Cite an independently produced calculation evidence artifact "
                    "and its verified SHA-256."
                ),
                calculation_checks=calculation_checks,
            )
        statistical_claims = [*significance_markers, *annotation_claims["claims"]]
        claim_candidates = [*annotation_claims["claim_candidates"], *band_claims["claim_candidates"]]
        if contract_errors:
            return self._csv_render_error(
                arguments,
                summary="Render data contract validation failed.",
                errors=contract_errors,
                is_dry_run=dry_run,
                failure_stage="CONTRACT",
                resolution_hint="Fix the CSV data contract, data_path, columns, or semantic_checks.",
                calculation_checks=calculation_checks,
            )
        if dry_run:
            calculation_warnings = self._calculation_warnings(calculation_checks)
            manual_review_needed = bool(calculation_checks.get("manual_review_needed")) or bool(claim_candidates)
            return self._envelope(
                "figops.render_csv_graph",
                arguments,
                status="warning" if manual_review_needed else "ok",
                summary=(
                    "Render request validated with calculation warnings in dry-run mode; no files were created."
                    if manual_review_needed
                    else "Render request validated in dry-run mode; no files were created."
                ),
                warnings=calculation_warnings,
                manual_review_needed=manual_review_needed,
                is_dry_run=True,
                job_id=job_id,
                job_root=str(job_root),
                output_path=str(job_root / "results" / "figures" / f"graph.{output_format}"),
                config_path=str(job_root / "project_config.yaml"),
                manifest_path=str(job_root / "manifest.json"),
                style_summary={"target_format": target_format, "profile": profile, "output_format": output_format},
                visual_preflight_status={"passed": None, "checks": [], "warnings": ["dry_run"]},
                failure_stage="",
                resolution_hint="",
                artifact_status="validated",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
                calculation_checks=calculation_checks,
                statistical_claims=statistical_claims,
                claim_candidates=claim_candidates,
                geometry_diagnostics=render_helpers._geometry_stub("dry_run"),
                layout_report=render_helpers._layout_report_from_geometry(render_helpers._geometry_stub("dry_run")),
            )
        self._activate_runtime_root_for_runtime_access()
        job_root = self._mcp_jobs_root() / job_id
        if job_root.exists() and not overwrite:
            return self._csv_render_error(
                arguments,
                summary="Render job already exists.",
                errors=[f"Render job already exists: {self._runtime_uri(job_root)}. Set overwrite=true to replace it."],
                is_dry_run=False,
                job_id=job_id,
                job_root=str(job_root),
                failure_stage="EXPORT",
                resolution_hint="Set overwrite=true to replace the existing MCP render job.",
            )
        if job_root.exists() and overwrite:
            symlink = render_helpers._first_symlink_component(job_root)
            if symlink is not None:
                return self._csv_render_error(
                    arguments,
                    summary="Render job path is not safe to overwrite.",
                    errors=[f"Runtime job path includes a symlinked component: {symlink}"],
                    is_dry_run=False,
                    job_id=job_id,
                    job_root=str(job_root),
                    failure_stage="EXPORT",
                    resolution_hint="Choose a new job_id or remove the symlinked runtime path manually.",
                )
            shutil.rmtree(job_root)
        job_data_path = job_root / "data" / "input.csv"
        output_path = job_root / "results" / "figures" / f"graph.{output_format}"
        config_path = job_root / "project_config.yaml"
        manifest_path = job_root / "manifest.json"
        status_path = job_root / "status.json"
        latest_dir = self.runtime_root / "_latest" / "mcp_render"
        created_paths: list[str] = []
        unsafe_path = (
            render_helpers._first_symlink_component(job_root)
            or render_helpers._first_symlink_component(latest_dir)
        )
        if unsafe_path is not None:
            return self._csv_render_error(
                arguments,
                summary="Render runtime path is not safe to write.",
                errors=[f"Runtime write path includes a symlinked component: {unsafe_path}"],
                is_dry_run=False,
                job_id=job_id,
                job_root=str(job_root),
                failure_stage="EXPORT",
                resolution_hint="Choose a different job_id/runtime root or remove the symlinked runtime path manually.",
            )
        try:
            job_data_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(data_path, job_data_path)
            created_paths.append(str(job_data_path))
            config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
            created_paths.append(str(config_path))
            with self._geometry_diagnostics_env(job_root):
                render_spec_payload = {
                        "csv_path": str(job_data_path),
                        "output_path": str(output_path),
                        "plot_type": plot_type,
                        "x_column": x_column,
                        "y_column": y_column,
                        "z_column": z_column,
                        "facet_column": facet_column,
                        "series_column": series_column,
                        "label_column": label_column,
                        "label_map": label_map,
                        "label_transform": label_transform,
                        "compliance_mode": compliance_mode,
                        "declutter_mode": declutter_mode,
                        "point_label_options": point_label_options,
                        "series_styles": series_styles,
                        "secondary_y": secondary_y,
                        "x_scale": x_scale,
                        "y_scale": y_scale,
                        "legend_layout": legend_layout,
                        "legend_options": legend_options,
                        "axis_limits": axis_limits,
                        "tick_style": tick_style,
                        "annotations": annotations,
                        "guide_curves": guide_curves,
                        "fill_between": fill_between,
                        "facet_scales": facet_scales,
                        "facet_ncols": facet_ncols,
                        "facet_nrows": facet_nrows,
                        "category_order": category_order,
                        "facet_order": facet_order,
                        "aggregate": aggregate,
                        "annotate_values": annotate_values,
                        "yerr_column": bar_error_column or yerr_column,
                        "yerr_minus_column": yerr_minus_column,
                        "yerr_cap_width": yerr_cap_width,
                        "fit_line": fit_line,
                        "ci_band": ci_band,
                        "fit_options": fit_options,
                        "significance_markers": significance_markers,
                        "title": str(arguments.get("title") or ""),
                        "x_axis_label": str(arguments.get("x_axis_label") or x_column),
                        "y_axis_label": str(arguments.get("y_axis_label") or y_column),
                        "target_format": target_format,
                        "profile_name": profile,
                    }
                if calculation_evidence:
                    self._run_render_bridge_figure(
                        render_spec_payload,
                        verified_calculation_evidence=tuple(calculation_evidence),
                    )
                else:
                    self._run_render_bridge_figure(render_spec_payload)
            geometry_diagnostics = render_helpers._read_geometry_sidecar(job_root)
            authored_output_path = job_root / "authored_output.json"
            authored_output = (
                json.loads(authored_output_path.read_text(encoding="utf-8"))
                if authored_output_path.is_file()
                else {"mode": "raw", "mappings": [], "collisions": [], "mutation_ledger": []}
            )
            geometry_warnings = render_helpers._geometry_warnings(geometry_diagnostics)
            layout_report = render_helpers._layout_report_from_geometry(geometry_diagnostics)
            figures = self._rendered_figure_artifacts(output_path)
            preview_artifacts = render_helpers._build_preview_artifacts(
                job_root=job_root,
                output_path=output_path,
                figures=figures,
            )
            preview_references = render_helpers._preview_resource_references(job_id, preview_artifacts)
            created_paths.extend(str(figure["path"]) for figure in figures)
            preflight = self._visual_preflight_with_geometry_overlaps(output_path, target_format, geometry_diagnostics)
            preflight_warnings = self._preflight_warnings(preflight)
            baseline_comparison = self._baseline_comparison(output_path, arguments.get("baseline_path"))
            baseline_warnings = self._baseline_warnings(baseline_comparison)
            calculation_warnings = self._calculation_warnings(calculation_checks)
            provenance = self._mcp_render_provenance(
                job_id=job_id,
                source_data_path=data_path,
                copied_data_path=job_data_path,
                config_path=config_path,
                output_path=output_path,
                target_format=target_format,
                profile=profile,
                output_format=output_format,
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
            manual_review_needed = (
                not bool(preflight.get("passed"))
                or bool(preflight_warnings)
                or (baseline_comparison["checked"] and not baseline_comparison["matched"])
                or bool(calculation_checks.get("manual_review_needed"))
                or geometry_diagnostics.get("passed") is False
                or bool(claim_candidates)
            )
            status = "warning" if manual_review_needed else "ok"
            artifact_status = self._artifact_status(preflight, baseline_comparison)
            created_paths.extend([str(manifest_path), str(status_path)])
            manifest = render_helpers._build_manifest(
                job_id=job_id,
                job_root=job_root,
                config_path=config_path,
                status_path=status_path,
                latest_dir=latest_dir,
                figures=figures,
                created_paths=created_paths,
                style_summary={
                    "target_format": target_format,
                    "profile": profile,
                    "output_format": output_format,
                },
                visual_preflight_status=preflight,
                geometry_diagnostics=geometry_diagnostics,
                layout_report=layout_report,
                artifact_status=artifact_status,
                baseline_comparison=baseline_comparison,
                manual_review_needed=manual_review_needed,
                provenance=provenance,
                data_contract={"schema_version": "data_contract_summary/1", "passed": True},
                source_data_path=str(data_path),
                copied_data_path=str(job_data_path),
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
                producer_kind="mcp-csv-render",
                producer_version=self._read_version(),
                baseline_reference_sha256=(
                    self._file_sha256(Path(baseline_comparison["baseline_path"]))
                    if baseline_comparison.get("checked")
                    and isinstance(baseline_comparison.get("baseline_path"), str)
                    and Path(baseline_comparison["baseline_path"]).is_file()
                    else None
                ),
                resolved_policy={
                    "id": f"journal-{target_format}",
                    "version": "1",
                    "source": "render-style-selection",
                    "parameters": {
                        "target_format": target_format,
                        "profile": profile,
                        "compliance_mode": compliance_mode,
                        "declutter_mode": declutter_mode,
                    },
                },
            )
            status_payload = self._render_status_payload(
                job_id=job_id,
                status=status,
                summary="Rendered CSV graph." if status == "ok" else "Rendered CSV graph with preflight warnings.",
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
            failure_stage = "TIMEOUT" if "timed out" in str(exc).lower() else "PLOT"
            resolution_hint = (
                "Increase the render timeout or simplify the figure."
                if failure_stage == "TIMEOUT"
                else "Inspect the render engine error and graph input settings."
            )
            if job_root.exists():
                baseline_comparison = self._baseline_comparison(None, arguments.get("baseline_path"))
                created_paths = self._write_render_failure_artifacts(
                    job_id=job_id,
                    job_root=job_root,
                    source_data_path=data_path,
                    copied_data_path=job_data_path,
                    config_path=config_path,
                    output_path=output_path,
                    manifest_path=manifest_path,
                    status_path=status_path,
                    latest_dir=latest_dir,
                    created_paths=created_paths,
                    failure_stage=failure_stage,
                    resolution_hint=resolution_hint,
                    baseline_comparison=baseline_comparison,
                )
            else:
                baseline_comparison = self._baseline_comparison(None, arguments.get("baseline_path"))
            return self._csv_render_error(
                arguments,
                summary="Render execution failed.",
                errors=[str(exc)],
                is_dry_run=False,
                created_paths=created_paths,
                job_id=job_id,
                job_root=str(job_root),
                manifest_path=str(manifest_path) if job_root.exists() else "",
                status_path=str(status_path) if job_root.exists() else "",
                latest_dir=str(latest_dir) if job_root.exists() else "",
                latest_alias=str(latest_dir) if job_root.exists() else "",
                failure_stage=failure_stage,
                resolution_hint=resolution_hint,
                geometry_diagnostics=render_helpers._geometry_stub("render_execution_failed"),
                layout_report=render_helpers._layout_report_from_geometry(
                    render_helpers._geometry_stub("render_execution_failed"),
                    failure_stage=failure_stage,
                ),
            )
        return self._envelope(
            "figops.render_csv_graph",
            arguments,
            status=status,
            summary="Rendered CSV graph." if status == "ok" else "Rendered CSV graph with preflight warnings.",
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
            statistical_claims=statistical_claims,
            calculation_evidence=calculation_evidence,
            descriptive_overlays=descriptive_overlays,
            claim_candidates=claim_candidates,
            label_transformations=authored_output,
            mutation_ledger=authored_output.get("mutation_ledger", []),
            evidence=manifest["evidence"],
        )

    def render_csv_multipanel(self, arguments: dict[str, Any]) -> dict[str, Any]:
        guarded = self._authorize_write_tool("figops.render_csv_multipanel", arguments)
        if guarded is not None:
            return guarded
        return _render_csv_multipanel_handler(self, arguments)
