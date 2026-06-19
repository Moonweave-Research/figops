from __future__ import annotations

import json
import shutil
import sys
from contextlib import redirect_stdout
from typing import Any

import yaml

from hub_core.adapters import select_adapters
from hub_core.config_parser import validate_config
from hub_core.mcp import render_orchestration as render_helpers
from hub_core.mcp.tools.render_support import McpRenderToolSupportMixin
from hub_core.rendering import PLOT_TYPES
from themes.style_profiles import DEFAULT_PROFILE

_STATISTICAL_OVERLAY_PLOT_TYPES = {"line", "scatter", "xy"}
_BAR_AGGREGATE_METHODS = {"mean", "median"}


class McpRenderToolsMixin(McpRenderToolSupportMixin):
    """Graph rendering MCP tool handlers."""
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
            return self._envelope(
                "graphhub.render_csv_graph",
                arguments,
                status="error",
                summary="Render request has invalid CSV input settings.",
                errors=[str(exc)],
                manual_review_needed=True,
                is_dry_run=dry_run,
                failure_stage="CONTRACT",
                resolution_hint="Fix data_path and CSV column inputs before rendering.",
                artifact_status="failed",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
                geometry_diagnostics=render_helpers._geometry_stub("no figure"),
                layout_report=render_helpers._layout_report_from_geometry(render_helpers._geometry_stub("no figure")),
            )
        plot_type = str(arguments.get("plot_type") or "scatter").strip().lower()
        target_format = str(arguments.get("target_format") or "nature").strip().lower()
        profile = str(arguments.get("profile") or DEFAULT_PROFILE).strip() or DEFAULT_PROFILE
        output_format = str(arguments.get("output_format") or "png").strip().lower().lstrip(".")
        fit_line = arguments.get("fit_line", False)
        ci_band = arguments.get("ci_band", False)
        significance_markers = arguments.get("significance_markers", ())
        aggregate = str(arguments.get("aggregate") or "").strip().lower()
        raw_semantic_checks = arguments.get("semantic_checks", {})
        semantic_checks = {} if raw_semantic_checks is None else raw_semantic_checks
        if plot_type not in PLOT_TYPES:
            return self._envelope(
                "graphhub.render_csv_graph",
                arguments,
                status="error",
                summary="Render request has invalid plot settings.",
                errors=[
                    f"Invalid plot_type '{plot_type}'. Supported: {', '.join(sorted(PLOT_TYPES))}."
                ],
                manual_review_needed=True,
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Use a supported plot_type.",
                artifact_status="failed",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
                geometry_diagnostics=render_helpers._geometry_stub("no figure"),
                layout_report=render_helpers._layout_report_from_geometry(render_helpers._geometry_stub("no figure")),
            )
        overlay_errors = self._statistical_overlay_arg_errors(
            plot_type=plot_type,
            fit_line=fit_line,
            ci_band=ci_band,
            significance_markers=significance_markers,
        )
        if overlay_errors:
            return self._envelope(
                "graphhub.render_csv_graph",
                arguments,
                status="error",
                summary="Render request has invalid statistical overlay settings.",
                errors=overlay_errors,
                manual_review_needed=True,
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Use fit_line, ci_band, and significance_markers only with line, scatter, or xy plots.",
                artifact_status="failed",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
                geometry_diagnostics=render_helpers._geometry_stub("no figure"),
                layout_report=render_helpers._layout_report_from_geometry(render_helpers._geometry_stub("no figure")),
            )
        aggregate_errors = self._bar_aggregate_arg_errors(plot_type=plot_type, aggregate=aggregate)
        if aggregate_errors:
            return self._envelope(
                "graphhub.render_csv_graph",
                arguments,
                status="error",
                summary="Render request has invalid bar aggregation settings.",
                errors=aggregate_errors,
                manual_review_needed=True,
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Use aggregate='mean' or aggregate='median' only with plot_type 'bar'.",
                artifact_status="failed",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
                geometry_diagnostics=render_helpers._geometry_stub("no figure"),
                layout_report=render_helpers._layout_report_from_geometry(render_helpers._geometry_stub("no figure")),
            )
        if plot_type == "heatmap" and not z_column:
            return self._envelope(
                "graphhub.render_csv_graph",
                arguments,
                status="error",
                summary="Render request has invalid plot settings.",
                errors=["plot_type 'heatmap' requires a z_column."],
                manual_review_needed=True,
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Provide z_column for heatmap plot_type.",
                artifact_status="failed",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
                geometry_diagnostics=render_helpers._geometry_stub("no figure"),
                layout_report=render_helpers._layout_report_from_geometry(render_helpers._geometry_stub("no figure")),
            )
        if plot_type == "facet" and not facet_column:
            return self._envelope(
                "graphhub.render_csv_graph",
                arguments,
                status="error",
                summary="Render request has invalid plot settings.",
                errors=["plot_type 'facet' requires a facet_column."],
                manual_review_needed=True,
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Provide facet_column for facet plot_type.",
                artifact_status="failed",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
                geometry_diagnostics=render_helpers._geometry_stub("no figure"),
                layout_report=render_helpers._layout_report_from_geometry(render_helpers._geometry_stub("no figure")),
            )
        style_errors = self._render_style_errors(target_format, output_format, profile)
        if style_errors:
            return self._envelope(
                "graphhub.render_csv_graph",
                arguments,
                status="error",
                summary="Render request has invalid style settings.",
                errors=style_errors,
                manual_review_needed=True,
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Use a supported target_format, output_format, and profile.",
                artifact_status="failed",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
                geometry_diagnostics=render_helpers._geometry_stub("no figure"),
                layout_report=render_helpers._layout_report_from_geometry(render_helpers._geometry_stub("no figure")),
            )
        if not isinstance(semantic_checks, dict):
            return self._envelope(
                "graphhub.render_csv_graph",
                arguments,
                status="error",
                summary="Render request has invalid data contract settings.",
                errors=["semantic_checks must be an object."],
                manual_review_needed=True,
                is_dry_run=dry_run,
                failure_stage="CONTRACT",
                resolution_hint="Provide semantic_checks as an object keyed by CSV column.",
                artifact_status="failed",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
                geometry_diagnostics=render_helpers._geometry_stub("no figure"),
                layout_report=render_helpers._layout_report_from_geometry(render_helpers._geometry_stub("no figure")),
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
            return self._envelope(
                "graphhub.render_csv_graph",
                arguments,
                status="error",
                summary="Render request has invalid project config settings.",
                errors=config_errors,
                manual_review_needed=True,
                is_dry_run=dry_run,
                failure_stage="CONFIG",
                resolution_hint="Fix the generated render project_config settings.",
                artifact_status="failed",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
                geometry_diagnostics=render_helpers._geometry_stub("no figure"),
                layout_report=render_helpers._layout_report_from_geometry(render_helpers._geometry_stub("no figure")),
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
            return self._envelope(
                "graphhub.render_csv_graph",
                arguments,
                status="error",
                summary="Render data contract validation failed.",
                errors=contract_errors,
                manual_review_needed=True,
                is_dry_run=dry_run,
                failure_stage="CONTRACT",
                resolution_hint="Fix the CSV data contract, data_path, columns, or semantic_checks.",
                artifact_status="failed",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
                calculation_checks=calculation_checks,
                geometry_diagnostics=render_helpers._geometry_stub("no figure"),
                layout_report=render_helpers._layout_report_from_geometry(render_helpers._geometry_stub("no figure")),
            )
        if dry_run:
            calculation_warnings = self._calculation_warnings(calculation_checks)
            manual_review_needed = bool(calculation_checks.get("manual_review_needed"))
            return self._envelope(
                "graphhub.render_csv_graph",
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
            return self._envelope(
                "graphhub.render_csv_graph",
                arguments,
                status="error",
                summary="Render job already exists.",
                errors=[f"Render job already exists: {self._runtime_uri(job_root)}. Set overwrite=true to replace it."],
                manual_review_needed=True,
                is_dry_run=False,
                job_id=job_id,
                job_root=str(job_root),
                failure_stage="EXPORT",
                resolution_hint="Set overwrite=true to replace the existing MCP render job.",
                artifact_status="failed",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
                geometry_diagnostics=render_helpers._geometry_stub("no figure"),
                layout_report=render_helpers._layout_report_from_geometry(render_helpers._geometry_stub("no figure")),
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
                        "aggregate": aggregate,
                        "fit_line": fit_line,
                        "ci_band": ci_band,
                        "significance_markers": significance_markers,
                        "title": str(arguments.get("title") or "Graph Hub MCP render"),
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
            manifest = {
                "job_id": job_id,
                "job_root": str(job_root),
                "source_data_path": str(data_path),
                "copied_data_path": str(job_data_path),
                "config_path": str(config_path),
                "status_path": str(status_path),
                "latest_dir": str(latest_dir),
                "latest_alias": str(latest_dir),
                "figures": figures,
                "diagrams": [],
                "assemblies": [],
                "logs": [],
                "created_paths": created_paths,
                "modified_paths": [],
                "skipped_paths": [],
                "style_summary": {
                    "target_format": target_format,
                    "profile": profile,
                    "output_format": output_format,
                },
                "visual_preflight_status": preflight,
                "geometry_diagnostics": geometry_diagnostics,
                "layout_report": layout_report,
                "failure_stage": "",
                "resolution_hint": "",
                "artifact_status": artifact_status,
                "baseline_comparison": baseline_comparison,
                "manual_review_needed": manual_review_needed,
                "calculation_checks": calculation_checks,
                "provenance": provenance,
            }
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
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            status_path.write_text(
                json.dumps(status_payload, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            latest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(manifest_path, latest_dir / "manifest.json")
            shutil.copy2(status_path, latest_dir / "status.json")
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
            return self._envelope(
                "graphhub.render_csv_graph",
                arguments,
                status="error",
                summary="Render execution failed.",
                created_paths=created_paths,
                errors=[str(exc)],
                manual_review_needed=True,
                is_dry_run=False,
                job_id=job_id,
                job_root=str(job_root),
                manifest_path=str(manifest_path) if job_root.exists() else "",
                status_path=str(status_path) if job_root.exists() else "",
                latest_dir=str(latest_dir) if job_root.exists() else "",
                latest_alias=str(latest_dir) if job_root.exists() else "",
                failure_stage=failure_stage,
                resolution_hint=resolution_hint,
                artifact_status="failed",
                baseline_comparison=baseline_comparison,
                geometry_diagnostics=render_helpers._geometry_stub("render_execution_failed"),
                layout_report=render_helpers._layout_report_from_geometry(
                    render_helpers._geometry_stub("render_execution_failed"),
                    failure_stage=failure_stage,
                ),
            )
        return self._envelope(
            "graphhub.render_csv_graph",
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

    @staticmethod
    def _statistical_overlay_arg_errors(
        *,
        plot_type: str,
        fit_line: Any,
        ci_band: Any,
        significance_markers: Any,
    ) -> list[str]:
        errors: list[str] = []
        if not isinstance(fit_line, bool):
            errors.append("fit_line must be a boolean.")
        if not isinstance(ci_band, bool):
            errors.append("ci_band must be a boolean.")
        if significance_markers is None:
            significance_markers = ()
        if not isinstance(significance_markers, (list, tuple)):
            errors.append("significance_markers must be an array of objects.")
        else:
            for idx, marker in enumerate(significance_markers):
                if not isinstance(marker, dict):
                    errors.append(f"significance_markers[{idx}] must be an object.")
                    continue
                missing = [key for key in ("x1", "x2", "y") if key not in marker]
                if missing:
                    errors.append(f"significance_markers[{idx}] missing required field(s): {', '.join(missing)}.")
                    continue
                for key in ("x1", "x2", "y", "h"):
                    if key not in marker or marker.get(key) is None:
                        continue
                    try:
                        float(marker[key])
                    except (TypeError, ValueError):
                        errors.append(f"significance_markers[{idx}].{key} must be numeric.")
        has_overlays = bool(fit_line or ci_band or significance_markers)
        if has_overlays and plot_type not in _STATISTICAL_OVERLAY_PLOT_TYPES:
            errors.append(
                "statistical overlays are only supported for plot_type 'line', 'scatter', or 'xy'."
            )
        return errors

    @staticmethod
    def _bar_aggregate_arg_errors(*, plot_type: str, aggregate: str) -> list[str]:
        if not aggregate:
            return []
        if aggregate not in _BAR_AGGREGATE_METHODS:
            allowed = ", ".join(sorted(_BAR_AGGREGATE_METHODS))
            return [f"aggregate must be one of: {allowed}."]
        if plot_type != "bar":
            return ["aggregate is only supported for plot_type 'bar'."]
        return []

    def render_project_figure(self, arguments: dict[str, Any]) -> dict[str, Any]:
        dry_run = bool(arguments.get("dry_run", False))
        overwrite = bool(arguments.get("overwrite", False))
        job_id = self._render_job_id(arguments.get("job_id"))
        self._activate_runtime_root_for_runtime_access()
        job_root = self._mcp_project_jobs_root() / job_id
        try:
            project_path = self._resolve_project_render_path(arguments)
            loaded = self._load_project_config(project_path, allow_invalid=True)
            config = loaded["config"] if isinstance(loaded["config"], dict) else {}
            config_errors = validate_config(config) if isinstance(config, dict) else list(loaded["errors"])
            if config_errors:
                return self._project_render_error(
                    arguments,
                    dry_run=dry_run,
                    job_id=job_id,
                    job_root=job_root,
                    summary="Project config is not valid for rendering.",
                    errors=config_errors,
                    failure_stage="CONFIG",
                    resolution_hint="Fix project_config.yaml before rendering this project figure.",
                )
            figures = self._project_figure_entries(config)
            selected, selection_errors = self._select_project_figure(
                figures,
                figure_id=arguments.get("figure_id"),
                figure_output=arguments.get("figure_output"),
            )
            if selection_errors or selected is None:
                return self._project_render_error(
                    arguments,
                    dry_run=dry_run,
                    job_id=job_id,
                    job_root=job_root,
                    summary="Project figure selection is ambiguous or invalid.",
                    errors=selection_errors,
                    failure_stage="CONTRACT",
                    resolution_hint=f"Select one of: {self._figure_selector_summary(figures)}",
                )
            output_relpath = self._project_relative_path(selected.get("output"), "figures[].output").as_posix()
            style_summary = self._selected_figure_style_summary(config, selected, arguments)
            style_errors = self._render_style_errors(
                style_summary["target_format"],
                style_summary["output_format"],
                style_summary["profile"],
            )
            if style_errors:
                return self._project_render_error(
                    arguments,
                    dry_run=dry_run,
                    job_id=job_id,
                    job_root=job_root,
                    summary="Project figure style settings are invalid.",
                    errors=style_errors,
                    failure_stage="CONFIG",
                    resolution_hint="Use a supported target_format, output_format, and profile.",
                    selected_figure=self._public_selected_figure(selected),
                )
        except ValueError as exc:
            return self._project_render_error(
                arguments,
                dry_run=dry_run,
                job_id=job_id,
                job_root=job_root,
                summary="Project render request is invalid.",
                errors=[str(exc)],
                failure_stage="CONTRACT",
                resolution_hint="Provide a valid project_id or project_path and figure selector.",
            )
        config_relpath = str(loaded["config_relpath"] or "project_config.yaml")
        source_project_path = self._public_project_path(project_path)
        selected_public = self._public_selected_figure(selected)
        snapshot_project_path = job_root / "project"
        output_path = snapshot_project_path / output_relpath
        config_path = snapshot_project_path / config_relpath
        manifest_path = job_root / "manifest.json"
        status_path = job_root / "status.json"
        latest_dir = self.runtime_root / "_latest" / "mcp_project_render"
        project_id = self._stable_project_id_for_path(project_path)
        if dry_run:
            return self._envelope(
                "graphhub.render_project_figure",
                arguments,
                summary="Project figure render validated in dry-run mode; no files were created.",
                is_dry_run=True,
                job_id=job_id,
                project_id=project_id,
                source_project_path=source_project_path,
                job_root=str(job_root),
                snapshot_project_path=str(snapshot_project_path),
                selected_figure=selected_public,
                output_path=str(output_path),
                config_path=str(config_path),
                manifest_path=str(manifest_path),
                status_path=str(status_path),
                latest_dir=str(latest_dir),
                latest_alias=str(latest_dir),
                style_summary=style_summary,
                visual_preflight_status={"passed": None, "checks": [], "warnings": ["dry_run"]},
                geometry_diagnostics=render_helpers._geometry_stub("dry_run"),
                layout_report=render_helpers._layout_report_from_geometry(render_helpers._geometry_stub("dry_run")),
                artifact_status="validated",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
                provenance={},
                failure_stage="",
                resolution_hint="",
            )
        job_root = self._mcp_project_jobs_root() / job_id
        snapshot_project_path = job_root / "project"
        output_path = snapshot_project_path / output_relpath
        config_path = snapshot_project_path / config_relpath
        manifest_path = job_root / "manifest.json"
        status_path = job_root / "status.json"
        latest_dir = self.runtime_root / "_latest" / "mcp_project_render"
        if job_root.exists() and not overwrite:
            return self._project_render_error(
                arguments,
                dry_run=False,
                job_id=job_id,
                job_root=job_root,
                summary="Project render job already exists.",
                errors=[
                    f"Project render job already exists: {self._runtime_uri(job_root)}. "
                    "Set overwrite=true to replace it."
                ],
                failure_stage="EXPORT",
                resolution_hint="Set overwrite=true to replace the existing MCP project render job.",
                project_id=project_id,
                source_project_path=source_project_path,
                snapshot_project_path=str(snapshot_project_path),
                selected_figure=selected_public,
                output_path=str(output_path),
                config_path=str(config_path),
            )
        if job_root.exists() and overwrite:
            shutil.rmtree(job_root)
        created_paths: list[str] = []
        try:
            created_paths = self._copy_project_snapshot(
                source_project=project_path,
                snapshot_project=snapshot_project_path,
                config_relpath=config_relpath,
                selected_figure=selected,
            )
            self._run_project_figure_script(
                snapshot_project_path=snapshot_project_path,
                selected_figure=selected,
                style_summary=style_summary,
            )
            geometry_diagnostics = render_helpers._read_geometry_sidecar(job_root)
            geometry_warnings = render_helpers._geometry_warnings(geometry_diagnostics)
            layout_report = render_helpers._layout_report_from_geometry(geometry_diagnostics)
            if not output_path.is_file():
                raise render_helpers.ProjectRenderExportError(
                    f"Selected figure output was not created: {output_relpath}",
                    script_output=self._read_project_script_output(job_root),
                )
            figures_out = self._rendered_figure_artifacts(output_path)
            figure_metadata = self._project_figure_metadata(
                output_path,
                selected,
                project_path=snapshot_project_path,
                figures=figures,
            )
            figure_format_warnings = [
                *list(figure_metadata.get("canonical_check", {}).get("warnings", [])),
                *list(figure_metadata.get("family_check", {}).get("warnings", [])),
            ]
            for figure in figures_out:
                path_text = str(figure["path"])
                if path_text not in created_paths:
                    created_paths.append(path_text)
            preflight = self._visual_preflight_with_geometry_overlaps(
                output_path,
                style_summary["target_format"],
                geometry_diagnostics,
            )
            preflight_warnings = self._preflight_warnings(preflight)
            baseline_comparison = self._baseline_comparison(output_path, arguments.get("baseline_path"))
            baseline_warnings = self._baseline_warnings(baseline_comparison)
            manual_review_needed = (
                not bool(preflight.get("passed"))
                or bool(preflight_warnings)
                or (baseline_comparison["checked"] and not baseline_comparison["matched"])
                or geometry_diagnostics.get("passed") is False
                or bool(figure_format_warnings)
            )
            status = "warning" if manual_review_needed else "ok"
            artifact_status = self._artifact_status(preflight, baseline_comparison)
            provenance = self._mcp_project_render_provenance(
                job_id=job_id,
                project_path=project_path,
                snapshot_project_path=snapshot_project_path,
                config_path=config_path,
                output_path=output_path,
                selected_figure=selected,
                style_summary=style_summary,
            )
            created_paths.extend([str(manifest_path), str(status_path)])
            manifest = {
                "job_id": job_id,
                "project_id": project_id,
                "source_project_path": source_project_path,
                "job_root": str(job_root),
                "snapshot_project_path": str(snapshot_project_path),
                "config_path": str(config_path),
                "status_path": str(status_path),
                "latest_dir": str(latest_dir),
                "latest_alias": str(latest_dir),
                "selected_figure": selected_public,
                "figures": figures_out,
                "diagrams": [],
                "assemblies": [],
                "logs": [],
                "created_paths": created_paths,
                "modified_paths": [],
                "skipped_paths": [],
                "style_summary": style_summary,
                "visual_preflight_status": preflight,
                "geometry_diagnostics": geometry_diagnostics,
                "layout_report": layout_report,
                "figure_metadata": figure_metadata,
                "failure_stage": "",
                "resolution_hint": "",
                "artifact_status": artifact_status,
                "baseline_comparison": baseline_comparison,
                "manual_review_needed": manual_review_needed,
                "provenance": provenance,
            }
            status_payload = self._render_status_payload(
                job_id=job_id,
                status=status,
                summary=(
                    "Rendered project figure." if status == "ok" else "Rendered project figure with preflight warnings."
                ),
                manifest_path=manifest_path,
                output_path=output_path,
                artifact_status=artifact_status,
                manual_review_needed=manual_review_needed,
                failure_stage="",
                resolution_hint="",
            )
            status_payload["provenance"] = provenance
            status_payload["layout_report"] = layout_report
            status_payload["figure_metadata"] = figure_metadata
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            status_path.write_text(
                json.dumps(status_payload, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            latest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(manifest_path, latest_dir / "manifest.json")
            shutil.copy2(status_path, latest_dir / "status.json")
        except Exception as exc:
            if isinstance(exc, TimeoutError):
                failure_stage = "TIMEOUT"
            elif isinstance(exc, render_helpers.ProjectRenderExportError):
                failure_stage = "EXPORT"
            elif isinstance(exc, render_helpers.ProjectRenderScriptError):
                failure_stage = "PLOT"
            else:
                failure_stage = "PLOT"
            resolution_hint = (
                "Increase the render timeout or simplify the figure."
                if failure_stage == "TIMEOUT"
                else (
                    "Fix the selected figure script, declared inputs, and output path."
                    if failure_stage == "EXPORT"
                    else "Inspect the selected figure script error."
                )
            )
            baseline_comparison = self._baseline_comparison(None, arguments.get("baseline_path"))
            script_output = self._project_failure_script_output(exc, job_root)
            failure_geometry = (
                render_helpers._read_geometry_sidecar(job_root)
                if job_root.exists()
                else render_helpers._geometry_stub("render_execution_failed")
            )
            failure_layout_report = render_helpers._layout_report_from_geometry(
                failure_geometry,
                failure_stage=failure_stage,
                script_output=script_output,
            )
            if job_root.exists():
                created_paths = self._write_project_render_failure_artifacts(
                    job_id=job_id,
                    job_root=job_root,
                    snapshot_project_path=snapshot_project_path,
                    selected_figure=selected_public,
                    manifest_path=manifest_path,
                    status_path=status_path,
                    latest_dir=latest_dir,
                    created_paths=created_paths,
                    failure_stage=failure_stage,
                    resolution_hint=resolution_hint,
                    baseline_comparison=baseline_comparison,
                    script_output=script_output,
                    layout_report=failure_layout_report,
                )
            return self._envelope(
                "graphhub.render_project_figure",
                arguments,
                status="error",
                summary="Project figure render execution failed.",
                created_paths=created_paths,
                errors=self._exception_error_lines(exc),
                script_output=script_output,
                manual_review_needed=True,
                is_dry_run=False,
                job_id=job_id,
                project_id=project_id,
                source_project_path=source_project_path,
                job_root=str(job_root),
                snapshot_project_path=str(snapshot_project_path),
                selected_figure=selected_public,
                output_path=str(output_path),
                config_path=str(config_path),
                manifest_path=str(manifest_path) if job_root.exists() else "",
                status_path=str(status_path) if job_root.exists() else "",
                latest_dir=str(latest_dir) if job_root.exists() else "",
                latest_alias=str(latest_dir) if job_root.exists() else "",
                style_summary=style_summary,
                visual_preflight_status={"passed": False, "checks": [], "warnings": ["render_execution_failed"]},
                geometry_diagnostics=failure_geometry,
                layout_report=failure_layout_report,
                artifact_status="failed",
                baseline_comparison=baseline_comparison,
                provenance={},
                failure_stage=failure_stage,
                resolution_hint=resolution_hint,
            )
        return self._envelope(
            "graphhub.render_project_figure",
            arguments,
            status=status,
            summary=(
                "Rendered project figure." if status == "ok" else "Rendered project figure with preflight warnings."
            ),
            created_paths=created_paths,
            artifact_resources=[f"file://{figure['path']}" for figure in manifest["figures"]],
            warnings=preflight_warnings + baseline_warnings + geometry_warnings + figure_format_warnings,
            manual_review_needed=manual_review_needed,
            is_dry_run=False,
            job_id=job_id,
            project_id=project_id,
            source_project_path=source_project_path,
            job_root=str(job_root),
            snapshot_project_path=str(snapshot_project_path),
            selected_figure=selected_public,
            output_path=str(output_path),
            config_path=str(config_path),
            manifest_path=str(manifest_path),
            status_path=str(status_path),
            latest_dir=str(latest_dir),
            latest_alias=str(latest_dir),
            style_summary=style_summary,
            visual_preflight_status=preflight,
            geometry_diagnostics=geometry_diagnostics,
            layout_report=layout_report,
            figure_metadata=figure_metadata,
            artifact_status=artifact_status,
            baseline_comparison=baseline_comparison,
            provenance=provenance,
            failure_stage="",
            resolution_hint="",
        )
