from __future__ import annotations

import json
import multiprocessing
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from hub_core.mcp import render_orchestration as render_helpers
from hub_core.mcp.schemas import MCP_BATCH_MAX_PROJECTS
from hub_core.runtime_paths import runtime_root_lookup_candidates


class McpBatchToolsMixin:
    """Batch and artifact collection MCP tool handlers."""

    def _batch_check_error(
        self,
        arguments: dict[str, Any],
        *,
        summary: str,
        errors: list[str],
        is_dry_run: bool,
        batch_id: str,
        batch_root: str | Path,
        manifest_path: str | Path,
        resumed_from: str = "",
        **extra: Any,
    ) -> dict[str, Any]:
        return self._envelope(
            "figops.batch_check",
            arguments,
            status="error",
            summary=summary,
            errors=errors,
            manual_review_needed=True,
            is_dry_run=is_dry_run,
            batch_id=batch_id,
            batch_root=str(batch_root),
            manifest_path=str(manifest_path),
            checked_projects=[],
            skipped_projects=[],
            resumed_from=resumed_from,
            log_paths=[],
            **extra,
        )

    def collect_artifacts(self, arguments: dict[str, Any]) -> dict[str, Any]:
        job_id = self._render_job_id(arguments.get("job_id"))
        manifest_path = self._find_job_manifest_path(job_id)
        if not manifest_path.exists():
            return self._envelope(
                "figops.collect_artifacts",
                arguments,
                status="error",
                summary="Render job manifest was not found.",
                errors=[f"Manifest not found: {self._runtime_uri(manifest_path)}"],
                manual_review_needed=True,
                artifact_status="failed",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
            )
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return self._envelope(
                "figops.collect_artifacts",
                arguments,
                status="error",
                summary="Render job manifest could not be read.",
                errors=[str(exc)],
                manual_review_needed=True,
                artifact_status="failed",
                baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
            )

        preflight = manifest.get("visual_preflight_status") or {}
        layout_report = (
            manifest.get("layout_report")
            if isinstance(manifest.get("layout_report"), dict)
            else render_helpers._layout_report_from_geometry(
                manifest.get("geometry_diagnostics") or render_helpers._geometry_stub("no figure")
            )
        )
        figures = manifest.get("figures") if isinstance(manifest.get("figures"), list) else []
        figure_metadata = manifest.get("figure_metadata") if isinstance(manifest.get("figure_metadata"), dict) else {}
        figure_format_warnings = self._figure_metadata_warnings(figure_metadata)
        preflight_warnings = self._preflight_warnings(preflight)
        artifact_path = (
            Path(str(figures[0]["path"]))
            if figures and isinstance(figures[0], dict) and figures[0].get("path")
            else None
        )
        baseline_comparison = (
            self._baseline_comparison(artifact_path, arguments.get("baseline_path"))
            if arguments.get("baseline_path")
            else manifest.get("baseline_comparison") or self._baseline_comparison(None, None)
        )
        baseline_warnings = self._baseline_warnings(baseline_comparison)
        persisted_artifact_status = str(manifest.get("artifact_status") or "").strip()
        persisted_failure_stage = str(manifest.get("failure_stage") or "").strip()
        persisted_resolution_hint = str(manifest.get("resolution_hint") or "").strip()
        persisted_failed = persisted_artifact_status == "failed" or bool(persisted_failure_stage)
        manual_review_needed = (
            bool(manifest.get("manual_review_needed"))
            or bool(preflight_warnings)
            or bool(figure_format_warnings)
            or (baseline_comparison["checked"] and not baseline_comparison["matched"])
        )
        status = (
            "error"
            if persisted_failed
            else ("warning" if manual_review_needed or preflight.get("passed") is False else "ok")
        )
        artifact_status = (
            persisted_artifact_status if persisted_failed else self._artifact_status(preflight, baseline_comparison)
        )
        return self._envelope(
            "figops.collect_artifacts",
            arguments,
            status=status,
            summary=f"Collected artifacts for render job {job_id}.",
            artifact_resources=[f"file://{figure['path']}" for figure in figures if isinstance(figure, dict)],
            warnings=preflight_warnings + baseline_warnings + figure_format_warnings,
            script_output=manifest.get("script_output") if isinstance(manifest.get("script_output"), list) else [],
            created_paths=self._manifest_path_list(manifest, "created_paths"),
            modified_paths=self._manifest_path_list(manifest, "modified_paths"),
            skipped_paths=self._manifest_path_list(manifest, "skipped_paths"),
            manual_review_needed=manual_review_needed,
            job_id=job_id,
            figures=figures,
            diagrams=manifest.get("diagrams") or [],
            assemblies=manifest.get("assemblies") or [],
            logs=manifest.get("logs") or [],
            manifest_path=str(manifest_path),
            status_path=str(manifest.get("status_path", "")),
            latest_dir=str(manifest.get("latest_dir", "")),
            latest_alias=str(manifest.get("latest_alias", "")),
            failure_stage=persisted_failure_stage,
            resolution_hint=persisted_resolution_hint,
            provenance={
                "job_id": job_id,
                "manifest_path": str(manifest_path),
                "status_path": str(manifest.get("status_path", "")),
                "latest_dir": str(manifest.get("latest_dir", "")),
                "latest_alias": str(manifest.get("latest_alias", "")),
                "job_root": manifest.get("job_root", ""),
                **(manifest.get("provenance") if isinstance(manifest.get("provenance"), dict) else {}),
            },
            visual_preflight_status=preflight,
            layout_report=layout_report,
            figure_metadata=figure_metadata,
            artifact_status=artifact_status,
            baseline_comparison=baseline_comparison,
        )

    def batch_check(self, arguments: dict[str, Any]) -> dict[str, Any]:
        root = self._scan_root(arguments)
        max_depth = self._max_depth(arguments.get("max_depth", 4))
        max_projects = self._batch_max_projects(arguments.get("max_projects", 20))
        include_invalid = bool(arguments.get("include_invalid", False))
        include_legacy = bool(arguments.get("include_legacy", False))
        include_worktrees = bool(arguments.get("include_worktrees", False))
        include_ephemeral = bool(arguments.get("include_ephemeral", False))
        include_quarantine = bool(arguments.get("include_quarantine", False))
        dry_run = bool(arguments.get("dry_run", True))
        batch_id = self._render_job_id(arguments.get("batch_id") or f"batch-{uuid.uuid4().hex[:12]}")
        batch_root = self._mcp_jobs_root() / batch_id
        manifest_path = batch_root / "batch_manifest.json"
        resumed_from = ""
        previously_checked = set()

        if arguments.get("resume_manifest_path"):
            try:
                resume_path = self._resolve_allowed_data_path(
                    self._required_string(arguments, "resume_manifest_path"),
                    field_name="resume_manifest_path",
                )
            except ValueError as exc:
                return self._batch_check_error(
                    arguments,
                    summary="Batch resume manifest path is outside the allowed data roots.",
                    errors=[str(exc)],
                    is_dry_run=dry_run,
                    batch_id=batch_id,
                    batch_root=batch_root,
                    manifest_path=manifest_path,
                    failure_stage="CONTRACT",
                    resolution_hint="Point resume_manifest_path at a manifest under an allowed data root.",
                )
            resumed_from = str(resume_path)
            try:
                resume_manifest = json.loads(resume_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                return self._batch_check_error(
                    arguments,
                    summary="Batch resume manifest could not be read.",
                    errors=[str(exc)],
                    is_dry_run=dry_run,
                    batch_id=batch_id,
                    batch_root=batch_root,
                    manifest_path=manifest_path,
                    resumed_from=resumed_from,
                )
            resume_root = Path(str(resume_manifest.get("root") or "")).expanduser().resolve()
            if resume_root != root:
                return self._batch_check_error(
                    arguments,
                    summary="Batch resume manifest does not match the requested root.",
                    errors=["Resume manifest was created for a different root."],
                    is_dry_run=dry_run,
                    batch_id=batch_id,
                    batch_root=batch_root,
                    manifest_path=manifest_path,
                    resumed_from=resumed_from,
                )
            previously_checked = {
                str(project.get("project_id"))
                for project in resume_manifest.get("checked_projects", [])
                if isinstance(project, dict) and project.get("project_id")
            }

        started_at = time.monotonic()
        discovered, discovery_timed_out, discovery_warnings = self._discover_batch_projects(
            root,
            max_depth=max_depth,
            timeout_seconds=render_helpers.MCP_BATCH_TIMEOUT_SECONDS,
        )
        checked_projects: list[dict[str, Any]] = []
        skipped_projects: list[dict[str, Any]] = []
        warnings: list[str] = list(discovery_warnings)
        timed_out = discovery_timed_out

        for project in discovered:
            if time.monotonic() - started_at >= render_helpers.MCP_BATCH_TIMEOUT_SECONDS:
                timed_out = True
                warnings.append(f"Batch check timed out after {render_helpers.MCP_BATCH_TIMEOUT_SECONDS:.1f} seconds.")
                break

            skip_reason = self._batch_skip_reason(
                project,
                include_invalid=include_invalid,
                include_legacy=include_legacy,
                include_worktrees=include_worktrees,
                include_ephemeral=include_ephemeral,
                include_quarantine=include_quarantine,
                previously_checked=previously_checked,
            )
            if skip_reason:
                skipped_projects.append(self._batch_skipped_project(project, skip_reason))
                continue

            if len(checked_projects) >= max_projects:
                skipped_projects.append(self._batch_skipped_project(project, "max_projects_exceeded"))
                continue

            checked_projects.append(self._batch_checked_project(root, project))

        manifest = {
            "batch_id": batch_id,
            "batch_root": str(batch_root),
            "root": str(root),
            "max_depth": max_depth,
            "max_projects": max_projects,
            "checked_projects": checked_projects,
            "skipped_projects": skipped_projects,
            "resumed_from": resumed_from,
            "timed_out": timed_out,
            "warnings": warnings,
        }

        created_paths: list[str] = []
        log_paths: list[str] = []
        if not dry_run:
            self._activate_runtime_root_for_runtime_access()
            batch_root = self._mcp_jobs_root() / batch_id
            manifest_path = batch_root / "batch_manifest.json"
            manifest["batch_root"] = str(batch_root)
            batch_root.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            created_paths.append(str(manifest_path))
            log_paths.append(str(manifest_path))

        status = "warning" if timed_out else "ok"
        return self._envelope(
            "figops.batch_check",
            arguments,
            status=status,
            summary=(
                f"Batch checked {len(checked_projects)} project(s) with timeout."
                if timed_out
                else f"Batch checked {len(checked_projects)} project(s)."
            ),
            created_paths=created_paths,
            warnings=warnings,
            manual_review_needed=timed_out,
            is_dry_run=dry_run,
            batch_id=batch_id,
            batch_root=str(batch_root),
            manifest_path=str(manifest_path),
            checked_projects=checked_projects,
            skipped_projects=skipped_projects,
            resumed_from=resumed_from,
            log_paths=log_paths,
        )

    def _find_job_manifest_path(self, job_id: str) -> Path:
        candidate_roots = [self.runtime_root]
        if not self._runtime_root_explicit:
            candidate_roots.extend(Path(path) for path in runtime_root_lookup_candidates())

        seen = set()
        for root in candidate_roots:
            resolved_root = Path(root).expanduser().resolve()
            for jobs_dir_name in ("mcp_jobs", "mcp_project_jobs"):
                manifest_path = resolved_root / jobs_dir_name / job_id / "manifest.json"
                key = str(manifest_path)
                if key in seen:
                    continue
                seen.add(key)
                if manifest_path.exists():
                    return manifest_path
        return Path(candidate_roots[0]).expanduser().resolve() / "mcp_jobs" / job_id / "manifest.json"

    @staticmethod
    def _max_depth(value: Any) -> int:
        # RPC input is already range-validated against minimum:1/maximum:12 before
        # reaching the handler; this clamp only backstops non-RPC/internal callers
        # and default-fill, so the out-of-range branch is dead for tools/call.
        try:
            depth = int(value)
        except (TypeError, ValueError):
            depth = 4
        return min(12, max(1, depth))

    @staticmethod
    def _batch_max_projects(value: Any) -> int:
        try:
            count = int(value)
        except (TypeError, ValueError):
            count = 20
        return min(MCP_BATCH_MAX_PROJECTS, max(1, count))

    @staticmethod
    def _discover_batch_projects(
        root: Path,
        *,
        max_depth: int,
        timeout_seconds: float,
    ) -> tuple[list[Any], bool, list[str]]:
        with tempfile.TemporaryDirectory(prefix="figops_mcp_batch_worker_") as tmpdir:
            result_path = Path(tmpdir) / "result.json"
            process = multiprocessing.Process(
                target=render_helpers._batch_discovery_worker,
                args=(str(root), max_depth, str(result_path)),
                name="figops-mcp-batch-discovery",
            )
            process.start()
            process.join(max(0.0, timeout_seconds))
            if process.is_alive():
                process.terminate()
                process.join(5)
                if process.is_alive():
                    process.kill()
                    process.join(5)
                return [], True, [f"Batch discovery timed out after {timeout_seconds:.1f} seconds."]
            if process.exitcode not in (0, None):
                return [], True, [f"Batch discovery worker exited with code {process.exitcode}."]
            try:
                result = render_helpers._read_worker_result(result_path, "Batch discovery")
            except RuntimeError as exc:
                return [], True, [str(exc)]
            if result.get("status") != "ok":
                trace = result.get("traceback") if isinstance(result.get("traceback"), list) else []
                message = "\n".join(str(line) for line in trace[-render_helpers.SCRIPT_OUTPUT_TAIL_LINES:]) or str(
                    result.get("error") or "Batch discovery failed."
                )
                return [], True, [message]
            projects = result.get("projects")
            return (projects if isinstance(projects, list) else []), False, []

    @staticmethod
    def _batch_skip_reason(
        project: Any,
        *,
        include_invalid: bool,
        include_legacy: bool,
        include_worktrees: bool,
        include_ephemeral: bool,
        include_quarantine: bool,
        previously_checked: set[str],
    ) -> str:
        if project.project_id in previously_checked:
            return "already_checked"
        if project.classification == "ephemeral":
            if project.path.startswith(".worktrees/"):
                return "" if include_worktrees else "ephemeral_project"
            return "" if include_ephemeral else "ephemeral_project"
        if (
            project.classification == "legacy" or getattr(project, "status", "active") == "legacy"
        ) and not include_legacy:
            return "legacy_project"
        if project.classification == "quarantine" and not include_quarantine:
            return "quarantine_project"
        if not project.valid and not include_invalid:
            return "invalid_config"
        return ""

    def _batch_checked_project(self, root: Path, project: Any) -> dict[str, Any]:
        project_path = (root / project.path).resolve()
        validation = self.validate_project({"project_path": str(project_path)})
        errors = []
        for key in ("config_errors", "data_contract_errors", "style_errors"):
            value = validation.get(key)
            if isinstance(value, list):
                errors.extend(str(item) for item in value)
        return {
            "project_id": project.project_id,
            "project_root": project.path,
            "classification": project.classification,
            "project_status": getattr(project, "status", "active"),
            "target_format": project.target_format,
            "valid": bool(validation.get("valid")),
            "status": validation.get("status", "error"),
            "errors": errors,
        }

    @staticmethod
    def _batch_skipped_project(project: Any, reason: str) -> dict[str, Any]:
        return {
            "project_id": project.project_id,
            "project_root": project.path,
            "classification": project.classification,
            "project_status": getattr(project, "status", "active"),
            "target_format": project.target_format,
            "valid": bool(project.valid),
            "reason": reason,
            "errors": list(project.errors),
        }
