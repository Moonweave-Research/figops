from __future__ import annotations

import shutil
import sys
from contextlib import redirect_stdout
from typing import Any

import yaml

from hub_core.adapters import select_adapters
from hub_core.config_parser import validate_config
from hub_core.mcp import render_orchestration as render_helpers
from hub_core.mcp.tools.render_support import McpRenderToolSupportMixin
from hub_core.mcp.tools.render_validation import _optional_positive_int_arg
from hub_core.rendering import PLOT_TYPES
from themes.style_profiles import DEFAULT_PROFILE


class McpRenderCsvMixin(McpRenderToolSupportMixin):
    """CSV-graph rendering MCP tool handlers."""

    def _csv_render_error(
        self,
        arguments: dict[str, Any],
        *,
        summary: str,
        errors: list[str],
        failure_stage: str,
        resolution_hint: str,
        is_dry_run: bool | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        geometry_diagnostics = extra.pop(
            "geometry_diagnostics",
            render_helpers._geometry_stub("no figure"),
        )
        layout_report = extra.pop(
            "layout_report",
            render_helpers._layout_report_from_geometry(geometry_diagnostics),
        )
        return self._envelope(
            "figops.render_csv_graph",
            arguments,
            status="error",
            summary=summary,
            errors=errors,
            manual_review_needed=True,
            is_dry_run=False if is_dry_run is None else is_dry_run,
            artifact_status="failed",
            baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
            geometry_diagnostics=geometry_diagnostics,
            layout_report=layout_report,
            failure_stage=failure_stage,
            resolution_hint=resolution_hint,
            **extra,
        )

    def render_csv_graph(self, arguments: dict[str, Any]) -> dict[str, Any]:
        dry_run = bool(arguments.get("dry_run", False))
        overwrite = bool(arguments.get("overwrite", False))
        job_id = self._render_job_id(arguments.get("job_id"))
        self._activate_runtime_root_for_runtime_access()
        job_root = self._mcp_jobs_root() / job_id
        try:
            data_path = self._input_file_path(arguments.get("data_path"))
            x_column = self._required_string(arguments, "x_column")
            y_column = self._required_string(arguments, "y_column")
            z_column = str(arguments.get("z_column") or "").strip()
            facet_column = str(arguments.get("facet_column") or "").strip()
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
        significance_markers = arguments.get("significance_markers", ())
        aggregate = str(arguments.get("aggregate") or "").strip().lower()
        raw_annotate_values = arguments.get("annotate_values", False)
        raw_bar_error_column = arguments.get("bar_error_column", "")
        raw_facet_ncols = arguments.get("facet_ncols")
        raw_facet_nrows = arguments.get("facet_nrows")
        try:
            category_order = self._order_arg(arguments.get("category_order"), "category_order", allow_numbers=True)
            facet_order = self._order_arg(arguments.get("facet_order"), "facet_order", allow_numbers=False)
            facet_ncols = _optional_positive_int_arg(raw_facet_ncols, "facet_ncols")
            facet_nrows = _optional_positive_int_arg(raw_facet_nrows, "facet_nrows")
        except ValueError as exc:
            return self._csv_render_error(
                arguments,
                summary="Render request has invalid facet/category layout settings.",
                errors=[str(exc)],
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint=(
                    "Provide category_order/facet_order arrays and positive integer facet_ncols/facet_nrows."
                ),
            )
        annotate_values = raw_annotate_values
        bar_error_column = ""
        render_arg_errors: list[str] = []
        if not isinstance(annotate_values, bool):
            render_arg_errors.append("annotate_values must be a boolean.")
            annotate_values = False
        elif annotate_values and plot_type != "heatmap":
            render_arg_errors.append("annotate_values is only supported for plot_type 'heatmap'.")
        if raw_bar_error_column is not None and raw_bar_error_column != "":
            if not isinstance(raw_bar_error_column, str):
                render_arg_errors.append("bar_error_column must be a string.")
            else:
                bar_error_column = raw_bar_error_column.strip()
                if not bar_error_column:
                    render_arg_errors.append("bar_error_column must be a non-empty string when provided.")
                elif plot_type != "bar":
                    render_arg_errors.append("bar_error_column is only supported for plot_type 'bar'.")
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
        if bar_error_column:
            try:
                semantic_checks = self._semantic_checks_with_bar_error_column(
                    semantic_checks,
                    y_column=y_column,
                    bar_error_column=bar_error_column,
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
            semantic_checks=semantic_checks,
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
                *[str(key) for key in semantic_checks],
            ],
            semantic_checks=semantic_checks,
        )
        contract_errors = contract_result["errors"]
        calculation_checks = contract_result["calculation_checks"]
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
            manual_review_needed = bool(calculation_checks.get("manual_review_needed"))
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
            shutil.rmtree(job_root)
        job_data_path = job_root / "data" / "input.csv"
        output_path = job_root / "results" / "figures" / f"graph.{output_format}"
        config_path = job_root / "project_config.yaml"
        manifest_path = job_root / "manifest.json"
        status_path = job_root / "status.json"
        latest_dir = self.runtime_root / "_latest" / "mcp_render"
        created_paths: list[str] = []
        try:
            job_data_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(data_path, job_data_path)
            created_paths.append(str(job_data_path))
            config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
            created_paths.append(str(config_path))
            with self._geometry_diagnostics_env(job_root):
                self._run_render_bridge_figure(
                    {
                        "csv_path": str(job_data_path),
                        "output_path": str(output_path),
                        "plot_type": plot_type,
                        "x_column": x_column,
                        "y_column": y_column,
                        "z_column": z_column,
                        "facet_column": facet_column,
                        "facet_scales": facet_scales,
                        "facet_ncols": facet_ncols,
                        "facet_nrows": facet_nrows,
                        "category_order": category_order,
                        "facet_order": facet_order,
                        "aggregate": aggregate,
                        "annotate_values": annotate_values,
                        "yerr_column": bar_error_column,
                        "fit_line": fit_line,
                        "ci_band": ci_band,
                        "significance_markers": significance_markers,
                        "title": str(arguments.get("title") or "FigOps MCP render"),
                        "x_axis_label": str(arguments.get("x_axis_label") or x_column),
                        "y_axis_label": str(arguments.get("y_axis_label") or y_column),
                        "target_format": target_format,
                        "profile_name": profile,
                    }
                )
            geometry_diagnostics = render_helpers._read_geometry_sidecar(job_root)
            geometry_warnings = render_helpers._geometry_warnings(geometry_diagnostics)
            layout_report = render_helpers._layout_report_from_geometry(geometry_diagnostics)
            figures = self._rendered_figure_artifacts(output_path)
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
            manual_review_needed = (
                not bool(preflight.get("passed"))
                or bool(preflight_warnings)
                or (baseline_comparison["checked"] and not baseline_comparison["matched"])
                or bool(calculation_checks.get("manual_review_needed"))
                or geometry_diagnostics.get("passed") is False
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
                source_data_path=str(data_path),
                copied_data_path=str(job_data_path),
                calculation_checks=calculation_checks,
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
            artifact_resources=[f"file://{figure['path']}" for figure in manifest["figures"]],
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
        )
