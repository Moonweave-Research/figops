from __future__ import annotations

import shutil
from typing import Any

from hub_core.config_parser import master_execution_error, project_role, project_status, validate_config
from hub_core.mcp import render_orchestration as render_helpers
from hub_core.research_ops_enforcement import validate_research_ops_contract


class McpRenderProjectMixin:
    """Project-figure rendering MCP tool handlers."""

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
            if project_role(config) == "master":
                return self._project_render_error(
                    arguments,
                    dry_run=dry_run,
                    job_id=job_id,
                    job_root=job_root,
                    summary="Project render request targets a master project root.",
                    errors=[master_execution_error(config)],
                    failure_stage="CONFIG",
                    resolution_hint="Select a declared execution module and render from that module project.",
                )
            if project_status(config) == "legacy":
                return self._project_render_error(
                    arguments,
                    dry_run=dry_run,
                    job_id=job_id,
                    job_root=job_root,
                    summary="Project is marked legacy; rendering is disabled for retired projects.",
                    errors=["project is marked legacy; rendering is disabled for retired projects."],
                    failure_stage="CONFIG",
                    resolution_hint=(
                        "Keep the retired project inspectable with inspect_project/validate_project, "
                        "or set project.status to active before rendering."
                    ),
                )
            research_ops = validate_research_ops_contract(project_path, config)
            if research_ops["errors"]:
                return self._project_render_error(
                    arguments,
                    dry_run=dry_run,
                    job_id=job_id,
                    job_root=job_root,
                    summary="Project research-ops contract failed for rendering.",
                    errors=research_ops["errors"],
                    failure_stage="CONFIG",
                    resolution_hint="Fix declared research-ops contracts or set an explicit opt-out before rendering.",
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
            project_inputs = [
                self._figure_manifest_input(role="project_input", path=snapshot_project_path / input_rel)
                for input_rel in self._selected_figure_declared_inputs(selected)
            ]
            figure_manifests = self._write_figure_manifest_sidecars(
                figures=figures_out,
                context=render_helpers.FigureManifestContext(
                    job_id=job_id,
                    tool_name="graphhub.render_project_figure",
                    status=status,
                    artifact_status=artifact_status,
                    manual_review_needed=manual_review_needed,
                    style_summary=style_summary,
                    provenance=provenance,
                    config_path=config_path,
                    inputs=project_inputs,
                    warnings=preflight_warnings + baseline_warnings + geometry_warnings + figure_format_warnings,
                    selected_figure=selected_public,
                    figure_metadata=figure_metadata,
                ),
            )
            created_paths.extend(sidecar["path"] for sidecar in figure_manifests)
            created_paths.extend([str(manifest_path), str(status_path)])
            manifest = render_helpers._build_manifest(
                job_id=job_id,
                job_root=job_root,
                config_path=config_path,
                status_path=status_path,
                latest_dir=latest_dir,
                figures=figures_out,
                created_paths=created_paths,
                style_summary=style_summary,
                visual_preflight_status=preflight,
                geometry_diagnostics=geometry_diagnostics,
                layout_report=layout_report,
                artifact_status=artifact_status,
                baseline_comparison=baseline_comparison,
                manual_review_needed=manual_review_needed,
                provenance=provenance,
                project_id=project_id,
                source_project_path=source_project_path,
                snapshot_project_path=str(snapshot_project_path),
                selected_figure=selected_public,
                figure_metadata=figure_metadata,
                figure_manifests=figure_manifests,
            )
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
            render_helpers._write_manifest_and_status(manifest, manifest_path, status_payload, status_path, latest_dir)
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
