from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from hub_core.adapters import select_adapters
from hub_core.artifact_policy_measurement import resolve_render_policy_context
from hub_core.attempt_provenance import build_attempt_provenance, update_attempt_provenance
from hub_core.config_parser import (
    master_execution_error,
    project_role,
    project_status,
    validate_config,
    workflow_intent_report,
)
from hub_core.data_contract import validate_data_contract, validate_data_contract_preflight
from hub_core.external_raw_execution import (
    is_external_raw_declaration,
    materialize_external_raw_inputs,
)
from hub_core.mcp import render_orchestration as render_helpers
from hub_core.mcp import render_project_integrity_context as integrity_context
from hub_core.mcp.errors import PROJECT_DECLARATION_PATH_INVALID, has_unsafe_declared_path
from hub_core.project_paths import ProjectPathError, resolve_project_input, resolve_project_output
from hub_core.provenance_inputs import expand_project_input_files, resolved_research_ops_evidence
from hub_core.render_evidence import build_render_evidence
from hub_core.research_ops_enforcement import validate_research_ops_contract
from hub_core.result_promotion import promote_eligible_project_result


class McpRenderProjectMixin:
    """Project-figure rendering MCP tool handlers."""

    def render_project_figure(self, arguments: dict[str, Any]) -> dict[str, Any]:
        arguments = dict(arguments)
        guarded = self._authorize_write_tool("figops.render_project_figure", arguments)
        if guarded is not None:
            return guarded
        dry_run = bool(arguments.get("dry_run", False))
        overwrite = bool(arguments.get("overwrite", False))
        job_id = self._render_job_id(arguments.get("job_id"))
        selector_kind = "project_id" if arguments.get("project_id") else "project_path"
        attempt = build_attempt_provenance(
            surface="mcp",
            step="plot",
            selector_kind=selector_kind,
            hub_path=self.hub_path,
        )
        arguments["_mcp_attempt_provenance"] = attempt
        self._activate_runtime_root_for_runtime_access()
        job_root = self._mcp_project_jobs_root() / job_id
        project_resolved = False
        safe_output_path = False
        try:
            try:
                project_path = self._resolve_project_render_path(arguments)
            except (OSError, RuntimeError):
                return self._project_render_error(
                    arguments,
                    dry_run=dry_run,
                    job_id=job_id,
                    job_root=job_root,
                    summary="Project render request is invalid.",
                    errors=[
                        "project_path must stay under the research root "
                        "and resolve to an available project directory."
                    ],
                    failure_stage="CONTRACT",
                    resolution_hint="Provide a valid project_id or project_path and figure selector.",
                    persist_failure=False,
                )
            project_resolved = True
            loaded = self._load_project_config(project_path, allow_invalid=True)
            loaded_config = loaded["config"]
            config = loaded_config if isinstance(loaded_config, dict) else {}
            config_errors = (
                validate_config(config)
                if isinstance(loaded_config, dict)
                else list(loaded["errors"])
            )
            config_source_path = project_path / str(loaded["config_relpath"] or "project_config.yaml")
            update_attempt_provenance(
                attempt,
                config_path=config_source_path,
                config_status="invalid" if config_errors else "valid",
            )
            if config_errors:
                config_read_boundary_failure = loaded.get("failure_kind") == "config_read"
                unsafe_declared_path = (
                    config_read_boundary_failure or has_unsafe_declared_path(config_errors)
                )
                return self._project_render_error(
                    arguments,
                    dry_run=dry_run,
                    job_id=job_id,
                    job_root=job_root,
                    summary="Project config is not valid for rendering.",
                    errors=config_errors,
                    failure_stage="CONTRACT" if unsafe_declared_path else "CONFIG",
                    resolution_hint="Fix project_config.yaml before rendering this project figure.",
                    persist_failure=not unsafe_declared_path,
                    error_category="validation" if unsafe_declared_path else None,
                    error_code=PROJECT_DECLARATION_PATH_INVALID if unsafe_declared_path else None,
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
                    persist_failure=True,
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
                    persist_failure=True,
                )
            workflow_intent = integrity_context.resolve_project_render_workflow_intent(
                config,
                workflow_intent_report_fn=workflow_intent_report,
            )
            research_ops = validate_research_ops_contract(project_path, config)
            research_ops_policy = resolved_research_ops_evidence(config)
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
                    persist_failure=True,
                    raw_integrity_status=research_ops["raw_integrity_status"],
                    canonical_docs_registry=research_ops["canonical_docs_registry"],
                    research_ops_policy=research_ops_policy,
                )
            adapters = select_adapters(config)
            try:
                preflight_valid = validate_data_contract_preflight(
                    project_path,
                    config,
                    # Full validation below performs the single guarded prefetch/read.
                    require_existing=False,
                    prefetcher=adapters.prefetcher,
                    raise_path_contract_errors=True,
                )
            except ProjectPathError:
                return self._project_render_error(
                    arguments,
                    dry_run=dry_run,
                    job_id=job_id,
                    job_root=job_root,
                    summary="Project data contract declares an unsafe input path.",
                    errors=["Data contract preflight failed for project render."],
                    failure_stage="CONTRACT",
                    resolution_hint="Use only project-local data_contract inputs.",
                    persist_failure=False,
                    error_category="validation",
                    error_code=PROJECT_DECLARATION_PATH_INVALID,
                )
            if not preflight_valid:
                return self._project_render_error(
                    arguments,
                    dry_run=dry_run,
                    job_id=job_id,
                    job_root=job_root,
                    summary="Project data contract failed before rendering.",
                    errors=["Data contract preflight failed for project render."],
                    failure_stage="VALIDATE",
                    resolution_hint="Fix declared data_contract inputs before rendering this project figure.",
                    persist_failure=True,
                )
            if not validate_data_contract(
                project_path,
                config,
                prefetcher=adapters.prefetcher,
                write_sidecar=False,
            ):
                contract_paths = [
                    check.get("path")
                    for check in config.get("data_contract", {}).get("csv_checks", [])
                    if isinstance(check, dict) and isinstance(check.get("path"), str)
                ]
                input_unavailable = False
                for contract_path in contract_paths:
                    try:
                        resolve_project_input(
                            project_path,
                            contract_path,
                            purpose="data_contract.csv_checks[].path",
                        )
                    except (FileNotFoundError, ValueError):
                        input_unavailable = True
                        break
                return self._project_render_error(
                    arguments,
                    dry_run=dry_run,
                    job_id=job_id,
                    job_root=job_root,
                    summary="Project data contract failed before rendering.",
                    # Preserve the public failure distinction while the guarded
                    # full validator owns the single prefetch/read operation.
                    errors=[
                        "Data contract preflight failed for project render."
                        if input_unavailable
                        else "Data contract validation failed for project render."
                    ],
                    failure_stage="VALIDATE",
                    resolution_hint="Fix declared data_contract checks before rendering this project figure.",
                    persist_failure=True,
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
                    persist_failure=True,
                )
            output_relpath = self._project_relative_path(selected.get("output"), "figures[].output").as_posix()
            script_relpath = str(selected.get("script") or "").split("::", 1)[0]
            script_path = resolve_project_input(
                project_path,
                script_relpath,
                purpose="figures[].script",
            )
            script_suffix = script_path.suffix.lower()
            if script_suffix not in {".py", ".r"}:
                return self._project_render_error(
                    arguments,
                    dry_run=dry_run,
                    job_id=job_id,
                    job_root=job_root,
                    summary="Project figure script runtime is unsupported.",
                    errors=["Configured figure scripts must be project-local .py or .R files."],
                    failure_stage="CONTRACT",
                    resolution_hint="Declare a project-local Python or R figure script.",
                    persist_failure=False,
                    runtime_availability={"status": "unavailable", "reason": "SCRIPT_RUNTIME_UNSUPPORTED"},
                )
            if script_suffix == ".r" and shutil.which("Rscript") is None:
                return self._project_render_error(
                    arguments,
                    dry_run=dry_run,
                    job_id=job_id,
                    job_root=job_root,
                    summary="The declared R figure runtime is unavailable.",
                    errors=["Rscript is unavailable; the .R figure script was not executed."],
                    failure_stage="EXECUTE",
                    resolution_hint="Install a trusted Rscript runtime or render a declared .py figure.",
                    persist_failure=False,
                    runtime_availability={"status": "unavailable", "reason": "RSCRIPT_UNAVAILABLE"},
                )
            resolve_project_output(
                project_path,
                output_relpath,
                purpose="figures[].output",
            )
            safe_output_path = True
            style_summary = self._selected_figure_style_summary(config, selected, arguments)
            policy_context = integrity_context.resolve_project_render_policy_context(
                arguments,
                target_format=style_summary["target_format"],
                resolve_render_policy_context_fn=resolve_render_policy_context,
            )
            validation_target, render_policy = integrity_context.apply_project_render_policy_context(
                style_summary,
                policy_context,
            )
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
                    style_summary=style_summary,
                    persist_failure=True,
                )
        except (OSError, ValueError) as exc:
            error = (
                str(exc)
                if isinstance(exc, ValueError)
                else (
                    "Configured project render paths must stay inside the project "
                    "and resolve to available files."
                )
            )
            return self._project_render_error(
                arguments,
                dry_run=dry_run,
                job_id=job_id,
                job_root=job_root,
                summary="Project render request is invalid.",
                errors=[error],
                failure_stage="CONTRACT",
                resolution_hint="Provide a valid project_id or project_path and figure selector.",
                persist_failure=project_resolved and safe_output_path,
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
                "figops.render_project_figure",
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
                provenance={"attempt": attempt},
                policy_context=policy_context,
                workflow_intent=workflow_intent,
                failure_stage="",
                resolution_hint="",
            )
        claim_inventory = self._project_claim_inventory(project_path, selected)
        claim_warnings = [f"Claim inventory: {message}" for message in claim_inventory["errors"]]
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
            symlink = render_helpers._first_symlink_component(job_root)
            if symlink is not None:
                return self._project_render_error(
                    arguments,
                    dry_run=False,
                    job_id=job_id,
                    job_root=job_root,
                    summary="Project render job path is not safe to overwrite.",
                    errors=[f"Runtime job path includes a symlinked component: {symlink}"],
                    failure_stage="EXPORT",
                    resolution_hint="Choose a new job_id or remove the symlinked runtime path manually.",
                    project_id=project_id,
                    source_project_path=source_project_path,
                    snapshot_project_path=str(snapshot_project_path),
                    selected_figure=selected_public,
                    output_path=str(output_path),
                    config_path=str(config_path),
                )
            shutil.rmtree(job_root)
        unsafe_path = (
            render_helpers._first_symlink_component(job_root)
            or render_helpers._first_symlink_component(latest_dir)
        )
        if unsafe_path is not None:
            return self._project_render_error(
                arguments,
                dry_run=False,
                job_id=job_id,
                job_root=job_root,
                summary="Project render runtime path is not safe to write.",
                errors=[f"Runtime write path includes a symlinked component: {unsafe_path}"],
                failure_stage="EXPORT",
                resolution_hint="Choose a different job_id/runtime root or remove the symlinked runtime path manually.",
                project_id=project_id,
                source_project_path=source_project_path,
                snapshot_project_path=str(snapshot_project_path),
                selected_figure=selected_public,
                output_path=str(output_path),
                config_path=str(config_path),
            )
        created_paths: list[str] = []
        try:
            created_paths = self._copy_project_snapshot(
                source_project=project_path,
                snapshot_project=snapshot_project_path,
                config_relpath=config_relpath,
                selected_figure=selected,
                claim_inventory=claim_inventory,
            )
            output_path = resolve_project_output(
                snapshot_project_path,
                output_relpath,
                purpose="figures[].output",
            )
            input_declarations = self._selected_figure_declared_inputs(selected)
            project_input_declarations = [
                item for item in input_declarations if not is_external_raw_declaration(item)
            ]
            execution_input_paths = expand_project_input_files(
                snapshot_project_path,
                project_input_declarations,
                require_matches=True,
            )
            external_inputs = materialize_external_raw_inputs(
                # Authority/boundary checks bind to the durable source project.
                # The snapshot is itself disposable runtime state and must not
                # be treated as a durable project root overlapping runtime.
                project_root=project_path,
                config=config,
                declarations=input_declarations,
                prefetcher=adapters.prefetcher,
                allowed_roots=self.allowed_data_roots,
                runtime_root=self.runtime_root,
            )
            execution_input_paths.extend(item.path for item in external_inputs)
            pre_execution_hashes = self._mcp_project_pre_execution_hashes(
                snapshot_project_path=snapshot_project_path,
                config_path=config_path,
                config=config,
                selected_figure=selected,
            )
            self._run_project_figure_script(
                snapshot_project_path=snapshot_project_path,
                selected_figure=selected,
                style_summary=style_summary,
                input_paths=execution_input_paths,
            )
            geometry_diagnostics = render_helpers._read_geometry_sidecar(job_root)
            geometry_warnings = render_helpers._geometry_warnings(geometry_diagnostics)
            layout_report = render_helpers._layout_report_from_geometry(geometry_diagnostics)
            try:
                output_path = resolve_project_output(
                    snapshot_project_path,
                    output_relpath,
                    must_exist=True,
                    purpose="figures[].output",
                )
            except (FileNotFoundError, ValueError) as exc:
                raise render_helpers.ProjectRenderExportError(
                    f"Selected figure output was not created safely: {output_relpath}: {exc}",
                    script_output=self._read_project_script_output(job_root),
                ) from exc
            figures_out = self._rendered_figure_artifacts(output_path)
            preview_artifacts = render_helpers._build_preview_artifacts(
                job_root=job_root,
                output_path=output_path,
                figures=figures_out,
            )
            preview_references = render_helpers._preview_resource_references(job_id, preview_artifacts)
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
            preflight = (
                self._visual_preflight_with_geometry_overlaps(
                    output_path,
                    validation_target,
                    geometry_diagnostics,
                )
                if validation_target
                else {
                    "passed": True,
                    "checks": [],
                    "warnings": ["publication validation target not selected"],
                    "target": None,
                }
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
                or bool(claim_inventory["manual_review_needed"])
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
                pre_execution_hashes=pre_execution_hashes,
            )
            provenance["attempt"] = attempt
            created_paths.extend([str(manifest_path), str(status_path)])
            manifest = render_helpers._build_manifest(
                job_id=job_id,
                job_root=job_root,
                config_path=config_path,
                status_path=status_path,
                latest_dir=latest_dir,
                figures=figures_out,
                created_paths=self._public_runtime_paths(created_paths),
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
                raw_integrity_status=research_ops["raw_integrity_status"],
                canonical_docs_registry=research_ops["canonical_docs_registry"],
                research_ops_policy=research_ops_policy,
                data_contract={"schema_version": "data_contract_summary/1", "passed": True},
                preview_artifacts=preview_artifacts,
                policy_context=policy_context,
                workflow_intent=workflow_intent,
            )
            manifest["claim_inventory"] = claim_inventory
            manifest["publication_status"] = (
                "verified" if claim_inventory["status"] == "verified" else "unverified"
            )
            manifest["evidence"] = build_render_evidence(
                manifest,
                job_root=job_root,
                producer_kind="mcp-project-script-render",
                producer_version=self._read_version(),
                baseline_reference_sha256=(
                    self._file_sha256(Path(baseline_comparison["baseline_path"]))
                    if baseline_comparison.get("checked")
                    and isinstance(baseline_comparison.get("baseline_path"), str)
                    and Path(baseline_comparison["baseline_path"]).is_file()
                    else None
                ),
                render_policy=render_policy,
                policy_context=policy_context,
                validation_target=validation_target or None,
            )
            policy_projections = manifest["evidence"]["policy_projections"]
            promotion_decision = integrity_context.decide_project_render_promotion_eligibility(
                claim_inventory=claim_inventory,
                policy_projections=policy_projections,
                validation_target=validation_target,
                workflow_intent=workflow_intent,
                manual_review_needed=manual_review_needed,
            )
            manual_review_needed = bool(promotion_decision["manual_review_needed"])
            status = "warning" if manual_review_needed else "ok"
            manifest["manual_review_needed"] = manual_review_needed
            manifest["promotion_eligible"] = bool(promotion_decision["promotion_eligible"])
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
            status_payload["claim_inventory"] = claim_inventory
            status_payload["publication_status"] = manifest["publication_status"]
            status_payload["promotion_eligible"] = manifest["promotion_eligible"]
            status_payload["policy_context"] = policy_context
            status_payload["workflow_intent"] = workflow_intent
            render_helpers._write_manifest_and_status(manifest, manifest_path, status_payload, status_path, latest_dir)
            promoted = None
            if manifest["promotion_eligible"]:
                try:
                    promoted = promote_eligible_project_result(
                        project_root=project_path,
                        config=config,
                        runtime_root=self.runtime_root,
                        runtime_artifact=output_path,
                        output_relpath=output_relpath,
                        manifest=manifest,
                        manifest_path=manifest_path,
                        figure_id=str(selected.get("id") or "figure"),
                        selected_figure=selected,
                    )
                except Exception as exc:
                    raise render_helpers.ProjectRenderExportError(
                        f"Eligible result promotion failed: {exc}",
                        script_output=self._read_project_script_output(job_root),
                    ) from exc
            if promoted is not None:
                created_paths.extend(str(item.path) for item in promoted)
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
                    provenance={"attempt": attempt},
                    style_summary=style_summary,
                    script_output=script_output,
                    layout_report=failure_layout_report,
                )
            return self._envelope(
                "figops.render_project_figure",
                arguments,
                status="error",
                summary="Project figure render execution failed.",
                created_paths=self._public_runtime_paths(created_paths),
                errors=self._exception_error_lines(exc),
                script_output=script_output,
                manual_review_needed=True,
                is_dry_run=False,
                job_id=job_id,
                project_id=project_id,
                source_project_path=source_project_path,
                job_root=self._public_runtime_path(job_root),
                snapshot_project_path=self._public_runtime_path(snapshot_project_path),
                selected_figure=selected_public,
                output_path=self._public_runtime_path(output_path),
                config_path=self._public_runtime_path(config_path),
                manifest_path=self._public_runtime_path(manifest_path) if job_root.exists() else "",
                status_path=self._public_runtime_path(status_path) if job_root.exists() else "",
                latest_dir=self._public_runtime_path(latest_dir) if job_root.exists() else "",
                latest_alias=self._public_runtime_path(latest_dir) if job_root.exists() else "",
                style_summary=style_summary,
                visual_preflight_status={"passed": False, "checks": [], "warnings": ["render_execution_failed"]},
                geometry_diagnostics=failure_geometry,
                layout_report=failure_layout_report,
                artifact_status="failed",
                baseline_comparison=baseline_comparison,
                provenance={"attempt": attempt},
                failure_stage=failure_stage,
                resolution_hint=resolution_hint,
            )
        return self._envelope(
            "figops.render_project_figure",
            arguments,
            status=status,
            summary=(
                "Rendered project figure." if status == "ok" else "Rendered project figure with preflight warnings."
            ),
            created_paths=created_paths,
            artifact_resources=preview_references["artifact_resources"],
            preview_resources=preview_references["preview_resources"],
            warnings=(
                preflight_warnings
                + baseline_warnings
                + geometry_warnings
                + figure_format_warnings
                + claim_warnings
            ),
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
            evidence=manifest["evidence"],
            policy_context=policy_context,
            workflow_intent=workflow_intent,
            claim_inventory=claim_inventory,
            publication_status=manifest["publication_status"],
            promotion_eligible=manifest["promotion_eligible"],
            failure_stage="",
            resolution_hint="",
        )
