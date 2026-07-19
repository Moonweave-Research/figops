from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from hub_core.mcp.tools.render_csv_args import (
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
    _normalized_tick_style_arg,
)
from hub_core.rendering import PLOT_TYPES


def validate_multipanel_panel_specs(
    *,
    renderer: Any,
    panels_arg: list[Any],
    target_format: str,
    profile: str,
) -> dict[str, Any]:
    source_paths = []
    panel_specs = []
    contract_errors: list[str] = []
    calculation_checks = {"checks": [], "quality_passed": True, "manual_review_needed": False}
    panel_evidence_paths: list[tuple[str, ...]] = []
    all_evidence_paths: list[str] = []
    for index, panel in enumerate(panels_arg):
        if not isinstance(panel, dict):
            panel_evidence_paths.append(())
            continue
        try:
            paths = renderer._calculation_evidence_path_args(
                panel.get("calculation_evidence_path"),
                panel.get("calculation_evidence_paths"),
            )
        except ValueError as exc:
            contract_errors.append(f"panels[{index}]: {exc}")
            paths = ()
        panel_evidence_paths.append(paths)
        all_evidence_paths.extend(paths)
    try:
        verified_evidence_records = renderer._verified_calculation_evidence(None, all_evidence_paths)
    except ValueError as exc:
        contract_errors.append(str(exc))
        verified_evidence_records = []
    evidence_by_ref = {record["artifact_ref"]: record for record in verified_evidence_records}

    for index, panel in enumerate(panels_arg):
        if not isinstance(panel, dict):
            contract_errors.append(f"panels[{index}] must be an object.")
            continue
        try:
            from plotting.utils import normalize_label_map

            data_path = renderer._input_file_path(panel.get("data_path"))
            x_column = renderer._required_string(panel, "x_column")
            y_column = renderer._required_string(panel, "y_column")
            plot_type = str(panel.get("plot_type") or "scatter").strip().lower()
            x_scale = _normalized_axis_scale_arg(panel.get("x_scale"), field_name=f"panels[{index}].x_scale")
            y_scale = _normalized_axis_scale_arg(panel.get("y_scale"), field_name=f"panels[{index}].y_scale")
            secondary_y = _normalized_secondary_y_arg(panel.get("secondary_y"))
            legend_layout = _normalized_legend_layout_arg(
                panel.get("legend_layout"), field_name=f"panels[{index}].legend_layout"
            )
            legend_options = _normalized_legend_options_arg(
                panel.get("legend_options"), field_name=f"panels[{index}].legend_options"
            )
            axis_limits = _normalized_axis_limits_arg(
                panel.get("axis_limits"),
                field_name=f"panels[{index}].axis_limits",
                x_scale=x_scale,
                y_scale=y_scale,
            )
            tick_style = _normalized_tick_style_arg(panel.get("tick_style"), field_name=f"panels[{index}].tick_style")
            annotations = _normalized_annotation_args(panel.get("annotations"))
            series_styles = _normalized_series_style_args(panel.get("series_styles"))
            fit_options = _normalized_fit_options_arg(panel.get("fit_options"))
            guide_curves = _normalized_guide_curve_args(panel.get("guide_curves"))
            fill_between = _normalized_fill_between_args(panel.get("fill_between"))
            facet_column = str(panel.get("facet_column") or "").strip()
            series_column = str(panel.get("series_column") or "").strip()
            label_column = str(panel.get("label_column") or "").strip()
            label_map = normalize_label_map(panel.get("label_map"))
            label_transform = str(panel.get("label_transform") or "raw").strip().lower().replace("-", "_")
            if label_transform not in {"raw", "legacy_compress"}:
                raise ValueError("label_transform must be 'raw' or 'legacy_compress'")
            compliance_mode = str(panel.get("compliance_mode") or "validate").strip().lower()
            declutter_mode = str(panel.get("declutter_mode") or "none").strip().lower()
            if compliance_mode not in {"validate", "clamp"}:
                raise ValueError("compliance_mode must be 'validate' or 'clamp'")
            if declutter_mode not in {"none", "declutter"}:
                raise ValueError("declutter_mode must be 'none' or 'declutter'")
            point_label_options = _normalized_point_label_options_arg(
                panel.get("point_label_options"), field_name=f"panels[{index}].point_label_options"
            )
            yerr_column = str(panel.get("yerr_column") or "").strip()
            yerr_minus_column = str(panel.get("yerr_minus_column") or "").strip()
            yerr_cap_width = float(panel.get("yerr_cap_width", 3.0))
            fit_line = panel.get("fit_line", False)
            ci_band = panel.get("ci_band", False)
            significance_markers = renderer._normalized_significance_markers_arg(
                panel.get("significance_markers")
            )
            calculation_evidence = [
                evidence_by_ref[path]
                for path in panel_evidence_paths[index]
                if path in evidence_by_ref
            ]
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
        if secondary_y and plot_type not in {"line", "scatter", "xy"}:
            contract_errors.append(
                f"panels[{index}].secondary_y is only supported for plot_type 'line', 'scatter', or 'xy'."
            )
            continue
        if label_column and plot_type not in {"line", "scatter", "xy", "bar"}:
            contract_errors.append(
                f"panels[{index}].label_column is only supported for plot_type 'line', 'scatter', 'xy', or 'bar'."
            )
            continue
        if point_label_options and not label_column:
            contract_errors.append(f"panels[{index}].point_label_options requires label_column.")
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
        overlay_errors = renderer._statistical_overlay_arg_errors(
            plot_type=plot_type,
            fit_line=fit_line,
            ci_band=ci_band,
            fit_options=fit_options,
            significance_markers=significance_markers,
        )
        if overlay_errors:
            contract_errors.extend(f"panels[{index}]: {error}" for error in overlay_errors)
            continue
        if yerr_cap_width < 0:
            contract_errors.append(f"panels[{index}].yerr_cap_width must be non-negative.")
            continue

        semantic_checks = {}
        if yerr_column:
            semantic_checks = renderer._semantic_checks_with_bar_error_column(
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
            *([label_column] if label_column else []),
            *([str(point_label_options.get("priority_column"))] if point_label_options.get("priority_column") else []),
            *([str(point_label_options.get("skip_column"))] if point_label_options.get("skip_column") else []),
            *([yerr_column] if yerr_column else []),
            *([yerr_minus_column] if yerr_minus_column else []),
            *([secondary_y["column"]] if secondary_y else []),
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
                        label_column,
                        str(point_label_options.get("priority_column") or ""),
                        str(point_label_options.get("skip_column") or ""),
                        yerr_column,
                        yerr_minus_column,
                        secondary_y["column"] if secondary_y else "",
                    )
                    if column
                ),
            ),
        ]
        contract = renderer._validate_render_data_contract(
            data_path,
            required_columns=required_columns,
            semantic_checks=semantic_checks,
            axis_scales={
                x_column: x_scale,
                y_column: y_scale,
                **({secondary_y["column"]: secondary_y["scale"]} if secondary_y else {}),
            },
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
                "secondary_y": secondary_y,
                "z_column": str(panel.get("z_column") or "").strip(),
                "facet_column": facet_column,
                "series_column": series_column,
                "label_column": label_column,
                "label_map": label_map,
                "label_transform": label_transform,
                "compliance_mode": compliance_mode,
                "declutter_mode": declutter_mode,
                "point_label_options": point_label_options,
                "series_styles": series_styles,
                "x_scale": x_scale,
                "y_scale": y_scale,
                "legend_layout": legend_layout,
                "legend_options": legend_options,
                "axis_limits": axis_limits,
                "tick_style": tick_style,
                "annotations": annotations,
                "guide_curves": guide_curves,
                "fill_between": fill_between,
                "yerr_column": yerr_column,
                "yerr_minus_column": yerr_minus_column,
                "yerr_cap_width": yerr_cap_width,
                "fit_line": fit_line,
                "ci_band": ci_band,
                "fit_options": fit_options,
                "significance_markers": significance_markers,
                "verified_calculation_evidence": tuple(calculation_evidence),
                "title": str(panel.get("title") or ""),
                "x_axis_label": str(panel.get("x_axis_label") or x_column),
                "y_axis_label": str(panel.get("y_axis_label") or y_column),
                "target_format": target_format,
                "profile_name": profile,
            }
        )
    panel_calculation_evidence: list[tuple[dict[str, Any], ...]] = []
    claimed_ids: set[str] = set()
    statistical_claims: list[dict[str, Any]] = []
    claim_candidates: list[dict[str, Any]] = []
    for index, panel_spec in enumerate(panel_specs):
        panel_records = tuple(panel_spec.get("verified_calculation_evidence", ()))
        panel_calculation_evidence.append(panel_records)
        linkage_errors = renderer._statistical_claim_linkage_errors(
            panel_spec.get("significance_markers"),
            list(panel_records),
        )
        contract_errors.extend(f"panels[{index}]: {error}" for error in linkage_errors)
        for marker in panel_spec.get("significance_markers", ()):
            evidence_id = marker["calculation_evidence_id"]
            if evidence_id in claimed_ids:
                contract_errors.append(
                    f"panels[{index}]: calculation evidence {evidence_id!r} is claimed more than once "
                    "without panel scope."
                )
            claimed_ids.add(evidence_id)
            statistical_claims.append({"panel_index": index, **marker})
        annotation_claims = renderer._annotation_claim_evidence(
            panel_spec.get("annotations"),
            list(panel_records),
            claimed_ids=claimed_ids,
        )
        band_claims = renderer._fill_band_claim_evidence(panel_spec.get("fill_between"))
        contract_errors.extend(f"panels[{index}]: {error}" for error in annotation_claims["errors"])
        contract_errors.extend(f"panels[{index}]: {error}" for error in band_claims["errors"])
        statistical_claims.extend(
            {"panel_index": index, **claim} for claim in annotation_claims["claims"]
        )
        claim_candidates.extend(
            {"panel_index": index, **candidate}
            for candidate in [
                *annotation_claims["claim_candidates"],
                *band_claims["claim_candidates"],
            ]
        )
        panel_spec.pop("verified_calculation_evidence", None)
    return {
        "source_paths": source_paths,
        "panel_specs": panel_specs,
        "contract_errors": contract_errors,
        "calculation_checks": calculation_checks,
        "calculation_evidence": verified_evidence_records,
        "panel_calculation_evidence": panel_calculation_evidence,
        "statistical_claims": statistical_claims,
        "claim_candidates": claim_candidates,
    }


def prepare_multipanel_render_payload(
    *,
    panel_specs: list[dict[str, Any]],
    job_root: Path,
    output_path: Path,
    config_path: Path,
    arguments: dict[str, Any],
    rows: int,
    cols: int,
    target_format: str,
    profile: str,
    output_format: str,
    panel_height_mm: float,
    font_scale: float,
    layout_options: dict[str, Any],
    shared_legend: bool,
    shared_legend_options: dict[str, Any],
) -> dict[str, Any]:
    render_panels: list[dict[str, Any]] = []
    copied_data_paths: list[str] = []
    created_paths: list[str] = []
    for index, panel in enumerate(panel_specs):
        copied_path = job_root / "data" / f"panel_{index + 1}.csv"
        source_data_path = panel["source_data_path"]
        shutil.copy2(source_data_path, copied_path)
        copied_data_paths.append(str(copied_path))
        created_paths.append(str(copied_path))
        render_panel = {key: value for key, value in panel.items() if key != "source_data_path"}
        render_panels.append({"csv_path": str(copied_path), "output_path": "", **render_panel})

    render_payload = {
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
        "shared_legend": shared_legend,
        "shared_legend_options": shared_legend_options,
        **layout_options,
    }
    config_path.write_text(
        yaml.safe_dump(
            {
                "tool": "figops.render_csv_multipanel",
                "target_format": target_format,
                "profile": profile,
                "output_format": output_format,
                "layout_options": layout_options,
                "shared_legend": shared_legend,
                "shared_legend_options": shared_legend_options,
                "render_payload": render_payload,
                "panels": render_panels,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    created_paths.append(str(config_path))
    return {
        "render_payload": render_payload,
        "render_panels": render_panels,
        "copied_data_paths": copied_data_paths,
        "created_paths": created_paths,
    }
