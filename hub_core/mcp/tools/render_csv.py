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


def _normalized_axis_scale_arg(value: Any, *, field_name: str) -> str:
    scale = str(value or "linear").strip().lower()
    if scale not in {"linear", "log"}:
        raise ValueError(f"{field_name} must be 'linear' or 'log'.")
    return scale


def _normalized_span_annotation_arg(
    annotation: dict[str, Any],
    index: int,
    *,
    field: str,
    bounds: tuple[str, str],
) -> dict[str, Any]:
    span = annotation[field]
    lower_key, upper_key = bounds
    if not isinstance(span, dict) or lower_key not in span or upper_key not in span:
        raise ValueError(f"annotations[{index}].{field} must contain {lower_key} and {upper_key}.")
    item: dict[str, Any] = {field: {lower_key: span[lower_key], upper_key: span[upper_key]}}
    if annotation.get("text"):
        item["text"] = str(annotation["text"]).strip()
    if "color" in annotation:
        item["color"] = str(annotation.get("color") or "black")
    if "alpha" in annotation:
        item["alpha"] = annotation["alpha"]
    return item


def _normalized_series_style_args(value: Any) -> dict[str, dict[str, str]]:
    if value in (None, {}, []):
        return {}
    if not isinstance(value, dict):
        raise ValueError("series_styles must be an object keyed by series label.")
    allowed_keys = {
        "marker",
        "fill",
        "facecolor",
        "edgecolor",
        "markerfacecolor",
        "markeredgecolor",
        "linestyle",
        "hatch",
        "color",
        "alpha",
        "size",
        "linewidth",
        "zorder",
        "label",
    }
    normalized: dict[str, dict[str, str]] = {}
    for series_name, style in value.items():
        key = str(series_name).strip()
        if not key:
            raise ValueError("series_styles keys must be non-empty series labels.")
        if not isinstance(style, dict):
            raise ValueError(f"series_styles[{key!r}] must be an object.")
        item: dict[str, str] = {}
        for style_key, raw_style_value in style.items():
            if style_key not in allowed_keys:
                raise ValueError(
                    f"series_styles[{key!r}] has unsupported key {style_key!r}; "
                    f"supported keys: {', '.join(sorted(allowed_keys))}."
                )
            if raw_style_value is None:
                continue
            text = str(raw_style_value).strip()
            if text:
                item[style_key] = text
        if item:
            normalized[key] = item
    return normalized


def _normalized_guide_curve_args(value: Any) -> tuple[dict[str, Any], ...]:
    if value in (None, (), []):
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("guide_curves must be an array of objects.")
    normalized: list[dict[str, Any]] = []
    for index, overlay in enumerate(value):
        if not isinstance(overlay, dict):
            raise ValueError(f"guide_curves[{index}] must be an object.")
        item: dict[str, Any] = {}
        if overlay.get("points") is not None:
            points = overlay["points"]
            if not isinstance(points, (list, tuple)):
                raise ValueError(f"guide_curves[{index}].points must be an array.")
            item["points"] = list(points)
        else:
            if not isinstance(overlay.get("x"), (list, tuple)) or not isinstance(overlay.get("y"), (list, tuple)):
                raise ValueError(f"guide_curves[{index}] requires points or x/y arrays.")
            item["x"] = list(overlay["x"])
            item["y"] = list(overlay["y"])
        for key in ("color", "linestyle", "linewidth", "label", "zorder"):
            if key in overlay:
                item[key] = overlay[key]
        item.setdefault("color", "black")
        normalized.append(item)
    return tuple(normalized)


def _normalized_fill_between_args(value: Any) -> tuple[dict[str, Any], ...]:
    if value in (None, (), []):
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("fill_between must be an array of objects.")
    normalized: list[dict[str, Any]] = []
    for index, overlay in enumerate(value):
        if not isinstance(overlay, dict):
            raise ValueError(f"fill_between[{index}] must be an object.")
        item: dict[str, Any] = {}
        if overlay.get("points") is not None:
            points = overlay["points"]
            if not isinstance(points, (list, tuple)):
                raise ValueError(f"fill_between[{index}].points must be an array.")
            item["points"] = list(points)
        else:
            missing = [key for key in ("x_column", "y1_column", "y2_column") if not str(overlay.get(key) or "").strip()]
            if missing:
                raise ValueError(
                    f"fill_between[{index}] requires points or column field(s): {', '.join(missing)}."
                )
            item["x_column"] = str(overlay["x_column"]).strip()
            item["y1_column"] = str(overlay["y1_column"]).strip()
            item["y2_column"] = str(overlay["y2_column"]).strip()
        for key in ("color", "alpha", "label", "zorder"):
            if key in overlay:
                item[key] = overlay[key]
        item.setdefault("alpha", 0.2)
        normalized.append(item)
    return tuple(normalized)


def _fill_between_required_columns(
    fill_between: tuple[dict[str, Any], ...],
    *,
    existing: tuple[str, ...] = (),
) -> list[str]:
    seen = {str(column).strip() for column in existing if str(column or "").strip()}
    columns: list[str] = []
    for overlay in fill_between:
        for key in ("x_column", "y1_column", "y2_column"):
            column = str(overlay.get(key) or "").strip()
            if column and column not in seen:
                seen.add(column)
                columns.append(column)
    return columns


def _normalized_annotation_args(value: Any) -> tuple[dict[str, Any], ...]:
    if value in (None, (), []):
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("annotations must be an array of objects.")
    normalized: list[dict[str, Any]] = []
    for index, annotation in enumerate(value):
        if not isinstance(annotation, dict):
            raise ValueError(f"annotations[{index}] must be an object.")
        if annotation.get("region") is not None:
            region = annotation["region"]
            if not isinstance(region, dict) or any(key not in region for key in ("xmin", "xmax", "ymin", "ymax")):
                raise ValueError(f"annotations[{index}].region must contain xmin, xmax, ymin, ymax.")
            region_item: dict[str, Any] = {"region": {key: region[key] for key in ("xmin", "xmax", "ymin", "ymax")}}
            if annotation.get("text"):
                region_item["text"] = str(annotation["text"]).strip()
            if "color" in annotation:
                region_item["color"] = str(annotation.get("color") or "black")
            if "alpha" in annotation:
                region_item["alpha"] = annotation["alpha"]
            normalized.append(region_item)
            continue
        if annotation.get("hspan") is not None:
            normalized.append(
                _normalized_span_annotation_arg(annotation, index, field="hspan", bounds=("ymin", "ymax"))
            )
            continue
        if annotation.get("vspan") is not None:
            normalized.append(
                _normalized_span_annotation_arg(annotation, index, field="vspan", bounds=("xmin", "xmax"))
            )
            continue
        missing = [key for key in ("x", "y") if key not in annotation]
        if missing:
            raise ValueError(f"annotations[{index}] missing required field(s): {', '.join(missing)}.")
        item = {
            "x": annotation["x"],
            "y": annotation["y"],
            "text": str(annotation.get("text") or "").strip(),
        }
        arrow_to = annotation.get("arrow_to")
        if not item["text"] and arrow_to is None:
            raise ValueError(f"annotations[{index}] text must be non-empty unless arrow_to is provided.")
        if "color" in annotation:
            item["color"] = str(annotation.get("color") or "black")
        if arrow_to is not None:
            if not isinstance(arrow_to, dict) or "x" not in arrow_to or "y" not in arrow_to:
                raise ValueError(f"annotations[{index}].arrow_to must contain x and y.")
            item["arrow_to"] = {"x": arrow_to["x"], "y": arrow_to["y"]}
        if "arrowstyle" in annotation:
            item["arrowstyle"] = str(annotation.get("arrowstyle") or "->").strip() or "->"
        if annotation.get("connectionstyle"):
            item["connectionstyle"] = str(annotation["connectionstyle"]).strip()
        normalized.append(item)
    return tuple(normalized)



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
        tool_name: str = "figops.render_csv_graph",
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
            tool_name,
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
            series_column = str(arguments.get("series_column") or "").strip()
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
            annotations = _normalized_annotation_args(arguments.get("annotations"))
            series_styles = _normalized_series_style_args(arguments.get("series_styles"))
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
        annotate_values = raw_annotate_values
        bar_error_column = ""
        yerr_column = ""
        yerr_minus_column = ""
        yerr_cap_width = 3.0
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
        for raw_error_column, field_name in (
            (raw_yerr_column, "yerr_column"),
            (raw_yerr_minus_column, "yerr_minus_column"),
        ):
            if raw_error_column is None or raw_error_column == "":
                continue
            if not isinstance(raw_error_column, str):
                render_arg_errors.append(f"{field_name} must be a string.")
                continue
            stripped_error_column = raw_error_column.strip()
            if not stripped_error_column:
                render_arg_errors.append(f"{field_name} must be a non-empty string when provided.")
                continue
            if plot_type not in {"line", "scatter", "xy"}:
                render_arg_errors.append(f"{field_name} is only supported for plot_type 'line', 'scatter', or 'xy'.")
                continue
            if field_name == "yerr_column":
                yerr_column = stripped_error_column
            else:
                yerr_minus_column = stripped_error_column
        if raw_yerr_cap_width is not None:
            try:
                yerr_cap_width = float(raw_yerr_cap_width)
            except (TypeError, ValueError):
                render_arg_errors.append("yerr_cap_width must be numeric.")
            else:
                if yerr_cap_width < 0:
                    render_arg_errors.append("yerr_cap_width must be non-negative.")
        if yerr_column and bar_error_column:
            render_arg_errors.append("Use yerr_column for line/scatter/xy or bar_error_column for bar, not both.")
        if series_column and plot_type not in {"line", "scatter", "xy"}:
            render_arg_errors.append("series_column is only supported for plot_type 'line', 'scatter', or 'xy'.")
        if (guide_curves or fill_between) and plot_type not in {"line", "scatter", "xy"}:
            render_arg_errors.append(
                "guide_curves and fill_between are only supported for plot_type 'line', 'scatter', or 'xy'."
            )
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
                    column for column in (x_column, y_column, z_column, facet_column, series_column) if column
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
                            yerr_column,
                            yerr_minus_column,
                        )
                        if column
                    ),
                ),
                *[str(key) for key in semantic_checks],
            ],
            semantic_checks=semantic_checks,
            axis_scales={x_column: x_scale, y_column: y_scale},
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
                        "series_column": series_column,
                        "series_styles": series_styles,
                        "x_scale": x_scale,
                        "y_scale": y_scale,
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

    def render_csv_multipanel(self, arguments: dict[str, Any]) -> dict[str, Any]:
        dry_run = bool(arguments.get("dry_run", False))
        overwrite = bool(arguments.get("overwrite", False))
        job_id = self._render_job_id(arguments.get("job_id"))
        self._activate_runtime_root_for_runtime_access()
        job_root = self._mcp_jobs_root() / job_id
        target_format = str(arguments.get("target_format") or "nature").strip().lower()
        profile = str(arguments.get("profile") or DEFAULT_PROFILE).strip() or DEFAULT_PROFILE
        output_format = str(arguments.get("output_format") or "png").strip().lower().lstrip(".")
        panels_arg = arguments.get("panels")
        try:
            rows = int(arguments.get("rows") or 1)
            cols = int(arguments.get("cols") or (len(panels_arg) if isinstance(panels_arg, list) else 1))
            panel_height_mm = float(arguments.get("panel_height_mm") or 65.0)
            font_scale = float(arguments.get("font_scale") or 1.0)
        except (TypeError, ValueError):
            return self._csv_render_error(
                arguments,
                summary="Multipanel render request has invalid layout settings.",
                errors=["rows, cols, panel_height_mm, and font_scale must be numeric."],
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Provide numeric multipanel layout settings.",
                tool_name="figops.render_csv_multipanel",
            )

        if not isinstance(panels_arg, list) or not panels_arg:
            return self._csv_render_error(
                arguments,
                summary="Multipanel render request has invalid panel settings.",
                errors=["panels must be a non-empty array."],
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Provide one or more CSV panel objects.",
                tool_name="figops.render_csv_multipanel",
            )
        if rows < 1 or cols < 1:
            return self._csv_render_error(
                arguments,
                summary="Multipanel render request has invalid layout settings.",
                errors=["rows and cols must be positive integers."],
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Use positive rows and cols.",
                tool_name="figops.render_csv_multipanel",
            )
        if rows * cols < len(panels_arg):
            return self._csv_render_error(
                arguments,
                summary="Multipanel render request has too many panels for the grid.",
                errors=[f"rows * cols must fit {len(panels_arg)} panel(s); got {rows} * {cols}."],
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Increase rows or cols, or remove panels.",
                tool_name="figops.render_csv_multipanel",
            )
        if panel_height_mm <= 0 or font_scale <= 0:
            return self._csv_render_error(
                arguments,
                summary="Multipanel render request has invalid layout settings.",
                errors=["panel_height_mm and font_scale must be positive."],
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Use positive panel_height_mm and font_scale.",
                tool_name="figops.render_csv_multipanel",
            )
        style_errors = self._render_style_errors(target_format, output_format, profile)
        if style_errors:
            return self._csv_render_error(
                arguments,
                summary="Multipanel render request has invalid style settings.",
                errors=style_errors,
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Use a supported target_format, output_format, and profile.",
                tool_name="figops.render_csv_multipanel",
            )

        source_paths = []
        panel_specs = []
        contract_errors: list[str] = []
        calculation_checks = {"checks": [], "quality_passed": True, "manual_review_needed": False}
        for index, panel in enumerate(panels_arg):
            if not isinstance(panel, dict):
                contract_errors.append(f"panels[{index}] must be an object.")
                continue
            try:
                data_path = self._input_file_path(panel.get("data_path"))
                x_column = self._required_string(panel, "x_column")
                y_column = self._required_string(panel, "y_column")
                plot_type = str(panel.get("plot_type") or "scatter").strip().lower()
                x_scale = _normalized_axis_scale_arg(panel.get("x_scale"), field_name=f"panels[{index}].x_scale")
                y_scale = _normalized_axis_scale_arg(panel.get("y_scale"), field_name=f"panels[{index}].y_scale")
                annotations = _normalized_annotation_args(panel.get("annotations"))
                series_styles = _normalized_series_style_args(panel.get("series_styles"))
                guide_curves = _normalized_guide_curve_args(panel.get("guide_curves"))
                fill_between = _normalized_fill_between_args(panel.get("fill_between"))
                facet_column = str(panel.get("facet_column") or "").strip()
                series_column = str(panel.get("series_column") or "").strip()
                yerr_column = str(panel.get("yerr_column") or "").strip()
                yerr_minus_column = str(panel.get("yerr_minus_column") or "").strip()
                yerr_cap_width = float(panel.get("yerr_cap_width", 3.0))
            except (TypeError, ValueError) as exc:
                contract_errors.append(f"panels[{index}]: {exc}")
                continue
            if plot_type not in PLOT_TYPES:
                contract_errors.append(f"panels[{index}].plot_type {plot_type!r} is not supported.")
                continue
            if plot_type == "facet" and not facet_column:
                contract_errors.append(f"panels[{index}] plot_type 'facet' requires facet_column.")
                continue
            if plot_type == "heatmap" and not str(panel.get("z_column") or "").strip():
                contract_errors.append(f"panels[{index}] plot_type 'heatmap' requires z_column.")
                continue
            if series_column and plot_type not in {"line", "scatter", "xy"}:
                contract_errors.append(
                    f"panels[{index}].series_column is only supported for plot_type 'line', 'scatter', or 'xy'."
                )
                continue
            if (yerr_column or yerr_minus_column) and plot_type not in {"line", "scatter", "xy"}:
                contract_errors.append(
                    f"panels[{index}] yerr columns are only supported for plot_type 'line', 'scatter', or 'xy'."
                )
                continue
            if (guide_curves or fill_between) and plot_type not in {"line", "scatter", "xy"}:
                contract_errors.append(
                    f"panels[{index}] guide_curves and fill_between are only supported for plot_type "
                    "'line', 'scatter', or 'xy'."
                )
                continue
            if yerr_cap_width < 0:
                contract_errors.append(f"panels[{index}].yerr_cap_width must be non-negative.")
                continue

            semantic_checks = {}
            if yerr_column:
                semantic_checks = self._semantic_checks_with_bar_error_column(
                    semantic_checks,
                    y_column=y_column,
                    bar_error_column=yerr_column,
                )
            required_columns = [
                x_column,
                y_column,
                *([str(panel.get("z_column") or "").strip()] if plot_type == "heatmap" else []),
                *([facet_column] if facet_column else []),
                *([series_column] if series_column else []),
                *([yerr_column] if yerr_column else []),
                *([yerr_minus_column] if yerr_minus_column else []),
                *_fill_between_required_columns(
                    fill_between,
                    existing=tuple(
                        column
                        for column in (
                            x_column,
                            y_column,
                            str(panel.get("z_column") or "").strip() if plot_type == "heatmap" else "",
                            facet_column,
                            series_column,
                            yerr_column,
                            yerr_minus_column,
                        )
                        if column
                    ),
                ),
            ]
            contract = self._validate_render_data_contract(
                data_path,
                required_columns=required_columns,
                semantic_checks=semantic_checks,
                axis_scales={x_column: x_scale, y_column: y_scale},
            )
            if contract["errors"]:
                contract_errors.extend(f"panels[{index}]: {error}" for error in contract["errors"])
            calculation_checks["checks"].extend(contract["calculation_checks"].get("checks", []))
            calculation_checks["quality_passed"] = (
                calculation_checks["quality_passed"] and contract["calculation_checks"].get("quality_passed", True)
            )
            calculation_checks["manual_review_needed"] = (
                calculation_checks["manual_review_needed"]
                or contract["calculation_checks"].get("manual_review_needed", False)
            )
            source_paths.append(data_path)
            panel_specs.append(
                {
                    "source_data_path": data_path,
                    "plot_type": plot_type,
                    "x_column": x_column,
                    "y_column": y_column,
                    "z_column": str(panel.get("z_column") or "").strip(),
                    "facet_column": facet_column,
                    "series_column": series_column,
                    "series_styles": series_styles,
                    "x_scale": x_scale,
                    "y_scale": y_scale,
                    "annotations": annotations,
                    "guide_curves": guide_curves,
                    "fill_between": fill_between,
                    "yerr_column": yerr_column,
                    "yerr_minus_column": yerr_minus_column,
                    "yerr_cap_width": yerr_cap_width,
                    "title": str(panel.get("title") or ""),
                    "x_axis_label": str(panel.get("x_axis_label") or x_column),
                    "y_axis_label": str(panel.get("y_axis_label") or y_column),
                    "target_format": target_format,
                    "profile_name": profile,
                }
            )
        if contract_errors:
            return self._csv_render_error(
                arguments,
                summary="Multipanel render request failed validation.",
                errors=contract_errors,
                is_dry_run=dry_run,
                failure_stage="CONTRACT",
                resolution_hint="Fix panel CSV paths, columns, plot types, scales, or error-bar inputs.",
                tool_name="figops.render_csv_multipanel",
            )
        if dry_run:
            return self._envelope(
                "figops.render_csv_multipanel",
                arguments,
                status="ok",
                summary="Multipanel CSV render dry run passed.",
                warnings=self._calculation_warnings(calculation_checks),
                manual_review_needed=bool(calculation_checks.get("manual_review_needed")),
                is_dry_run=True,
                calculation_checks=calculation_checks,
            )
        if job_root.exists() and not overwrite:
            return self._csv_render_error(
                arguments,
                summary="Render job already exists.",
                errors=[f"Render job already exists: {self._runtime_uri(job_root)}. Set overwrite=true to replace it."],
                is_dry_run=False,
                failure_stage="CONFIG",
                resolution_hint="Use a unique job_id or set overwrite=true.",
                tool_name="figops.render_csv_multipanel",
            )

        output_path = job_root / "outputs" / f"multipanel.{output_format}"
        config_path = job_root / "config" / "multipanel.yaml"
        manifest_path = job_root / "manifest.json"
        status_path = job_root / "status.json"
        latest_dir = self.runtime_root / "_latest" / "mcp_render"
        created_paths: list[str] = []
        try:
            job_root.mkdir(parents=True, exist_ok=True)
            (job_root / "data").mkdir(parents=True, exist_ok=True)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.parent.mkdir(parents=True, exist_ok=True)
            prefetch_config = self._render_project_config(
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

            render_panels = []
            copied_data_paths = []
            for index, panel in enumerate(panel_specs):
                copied_path = job_root / "data" / f"panel_{index + 1}.csv"
                shutil.copy2(panel.pop("source_data_path"), copied_path)
                copied_data_paths.append(str(copied_path))
                created_paths.append(str(copied_path))
                render_panels.append({"csv_path": str(copied_path), "output_path": "", **panel})
            config_path.write_text(
                yaml.safe_dump(
                    {
                        "tool": "figops.render_csv_multipanel",
                        "target_format": target_format,
                        "profile": profile,
                        "output_format": output_format,
                        "panels": render_panels,
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            created_paths.append(str(config_path))
            with self._geometry_diagnostics_env(job_root):
                self._run_render_multipanel_figure(
                    {
                        "panels": render_panels,
                        "output_path": str(output_path),
                        "rows": rows,
                        "cols": cols,
                        "target_format": target_format,
                        "column_width": str(arguments.get("column_width") or "double"),
                        "panel_height_mm": panel_height_mm,
                        "panel_labels": bool(arguments.get("panel_labels", True)),
                        "font_scale": font_scale,
                        "profile_name": profile,
                        "compose_mode": str(arguments.get("compose_mode") or "draft"),
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
            manual_review_needed = (
                not bool(preflight.get("passed"))
                or bool(preflight_warnings)
                or (baseline_comparison["checked"] and not baseline_comparison["matched"])
                or bool(calculation_checks.get("manual_review_needed"))
                or geometry_diagnostics.get("passed") is False
            )
            status = "warning" if manual_review_needed else "ok"
            artifact_status = self._artifact_status(preflight, baseline_comparison)
            provenance = {
                "job_id": job_id,
                "renderer": "plotting.bridge_renderer.render_multipanel_figure",
                "renderer_surface": "figops.render_csv_multipanel",
                "mcp_surface_version": self._read_version(),
                "hub_git_commit": self._git_commit(),
                "source_data_paths": [str(path) for path in source_paths],
                "copied_data_paths": copied_data_paths,
                "output_sha256": self._file_sha256(output_path) if output_path.is_file() else "",
            }
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
                calculation_checks=calculation_checks,
            )
            status_payload = self._render_status_payload(
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
            render_helpers._write_manifest_and_status(manifest, manifest_path, status_payload, status_path, latest_dir)
        except Exception as exc:
            return self._csv_render_error(
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
        return self._envelope(
            "figops.render_csv_multipanel",
            arguments,
            status=status,
            summary="Rendered CSV multipanel." if status == "ok" else "Rendered CSV multipanel with warnings.",
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
            provenance=provenance,
        )
