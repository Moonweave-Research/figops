from __future__ import annotations

from pathlib import Path
from typing import Any

from hub_core.project_normalization import (
    NORMALIZATION_CONFIRMATION_REQUIRED,
    NORMALIZATION_OVERWRITE_DISABLED,
    NORMALIZATION_PLAN_REJECTED,
    NORMALIZATION_POLICY_DEPRECATED,
    NORMALIZATION_REVIEW_REQUIRED,
    apply_normalize_project,
    apply_scaffold_project,
    plan_normalize_project,
    plan_scaffold_project,
)
from hub_core.structure_plan import confirmation_token as structure_confirmation_token


class McpProjectToolsMixin:
    """Project scaffold and normalization MCP tool handlers."""

    def scaffold_project(self, arguments: dict[str, Any]) -> dict[str, Any]:
        guarded = self._authorize_write_tool("figops.scaffold_project", arguments)
        if guarded is not None:
            return guarded
        project_name = self._required_string(arguments, "project_name")
        project_root = self._resolve_under_root(arguments.get("project_root"), field_name="project_root")
        target_format = str(arguments.get("target_format") or "nature").strip().lower()
        template = str(arguments.get("template") or "standard").strip().lower()
        dry_run = bool(arguments.get("dry_run", True))
        overwrite = bool(arguments.get("overwrite", False))
        manifest = plan_scaffold_project(
            project_root=project_root,
            hub_path=self.hub_path,
            project_name=project_name,
            target_format=target_format,
            template=template,
        )
        public_manifest = self._public_manifest(manifest)
        planned_paths = self._manifest_destinations(public_manifest)
        config_path = Path(str(manifest["project_root"])) / "project_config.yaml"
        style_summary = self._manifest_style_summary(manifest)
        validation = self._validation_summary(config_path)
        scaffold_manifest_path = str(Path(str(manifest["project_root"])) / ".figops_scaffold_manifest.json")
        if dry_run:
            return self._envelope(
                "figops.scaffold_project",
                arguments,
                summary=f"Planned scaffold for project {project_name}.",
                is_dry_run=True,
                project_root=str(manifest["project_root"]),
                project_name=project_name,
                planned_paths=planned_paths,
                manifest=public_manifest,
                manifest_path=scaffold_manifest_path,
                config_path=str(config_path),
                style_summary=style_summary,
                validation=validation,
            )
        try:
            applied = apply_scaffold_project(manifest, overwrite=overwrite)
        except FileExistsError as exc:
            return self._envelope(
                "figops.scaffold_project",
                arguments,
                status="error",
                summary="Scaffold destination already exists.",
                errors=[str(exc)],
                manual_review_needed=True,
                is_dry_run=False,
                project_root=str(manifest["project_root"]),
                project_name=project_name,
                planned_paths=planned_paths,
                manifest=public_manifest,
                manifest_path=scaffold_manifest_path,
                config_path=str(config_path),
                style_summary=style_summary,
                validation=validation,
            )
        validation = self._validation_summary(config_path)
        return self._envelope(
            "figops.scaffold_project",
            arguments,
            summary=f"Created scaffold for project {project_name}.",
            created_paths=applied["created_paths"],
            modified_paths=applied["modified_paths"],
            skipped_paths=applied["skipped_paths"],
            is_dry_run=False,
            project_root=str(manifest["project_root"]),
            project_name=project_name,
            planned_paths=planned_paths,
            manifest=applied["manifest"],
            manifest_path=scaffold_manifest_path,
            config_path=str(config_path),
            style_summary=style_summary,
            validation=validation,
        )

    def normalize_project_structure(self, arguments: dict[str, Any]) -> dict[str, Any]:
        guarded = self._authorize_write_tool("figops.normalize_project_structure", arguments)
        if guarded is not None:
            return guarded
        project_path = self._resolve_under_root(arguments.get("project_path"), field_name="project_path")
        dry_run = bool(arguments.get("dry_run", True))
        move_policy = str(arguments.get("move_policy") or "adopt").strip().lower()
        include_raw = bool(arguments.get("include_raw", False))
        overwrite = bool(arguments.get("overwrite", False))
        approved_mappings = arguments.get("approved_mappings")
        config_diff = arguments.get("config_diff")
        unresolved_references = arguments.get("hardcoded_unresolved_references")

        if move_policy in {"move", "symlink"}:
            return self._envelope(
                "figops.normalize_project_structure",
                arguments,
                status="error",
                summary="Legacy normalization policy is disabled.",
                errors=[f"move_policy={move_policy!r} is deprecated and disabled; use reviewed copy-only migration."],
                manual_review_needed=True,
                is_dry_run=dry_run,
                error_category="disabled",
                error_code=NORMALIZATION_POLICY_DEPRECATED,
                project_root=str(project_path),
            )
        if overwrite:
            return self._envelope(
                "figops.normalize_project_structure",
                arguments,
                status="error",
                summary="Normalization overwrite is disabled.",
                errors=["overwrite=true is disabled; reviewed migrations never replace existing paths."],
                manual_review_needed=True,
                is_dry_run=dry_run,
                error_category="disabled",
                error_code=NORMALIZATION_OVERWRITE_DISABLED,
                project_root=str(project_path),
            )
        if move_policy not in {"adopt", "copy"}:
            return self._envelope(
                "figops.normalize_project_structure",
                arguments,
                status="error",
                summary="Normalization policy is invalid.",
                errors=["move_policy must be one of: adopt, copy."],
                manual_review_needed=True,
                is_dry_run=dry_run,
                error_category="validation",
                error_code=NORMALIZATION_PLAN_REJECTED,
                project_root=str(project_path),
            )

        if approved_mappings is not None and not isinstance(approved_mappings, list):
            raise ValueError("approved_mappings must be an array of reviewed mappings.")
        if config_diff is not None and not isinstance(config_diff, list):
            raise ValueError("config_diff must be an array of typed compare-and-swap edits.")
        if unresolved_references is not None and not isinstance(unresolved_references, list):
            raise ValueError("hardcoded_unresolved_references must be an array.")

        planning_policy = move_policy
        if move_policy == "copy" and approved_mappings is None:
            planning_policy = "adopt"
        manifest = plan_normalize_project(
            project_path=project_path,
            move_policy=planning_policy,
            include_raw=include_raw,
            approved_mappings=approved_mappings,
            config_diff=config_diff,
            hardcoded_unresolved_references=unresolved_references,
        )
        public_manifest = self._public_manifest(manifest)
        proposed_mappings = list(public_manifest.get("proposed_mappings") or [])
        planned_paths = self._manifest_destinations(public_manifest)
        if not planned_paths:
            planned_paths = [str(item["destination"]) for item in proposed_mappings]
        project_root = Path(str(manifest["project_root"]))
        config_path = project_root / "project_config.yaml"
        validation = self._validation_summary(config_path)
        token = structure_confirmation_token(manifest)
        common = {
            "project_root": str(project_root),
            "planned_paths": planned_paths,
            "manifest": public_manifest,
            "manifest_path": "",
            "config_path": str(config_path),
            "style_summary": manifest["style_summary"],
            "validation": validation,
            "proposed_mappings": proposed_mappings,
            "unresolved_proposals": list(public_manifest.get("unresolved_proposals") or []),
            "plan_digest": manifest["digest"],
            "confirmation_token": token,
        }
        if dry_run and move_policy == "adopt":
            return self._envelope(
                "figops.normalize_project_structure",
                arguments,
                summary=f"Proposed normalization mappings for {project_root.name}; no mappings are approved.",
                is_dry_run=True,
                manual_review_needed=bool(proposed_mappings or common["unresolved_proposals"]),
                **common,
            )
        if move_policy == "adopt" or approved_mappings is None or (not dry_run and not approved_mappings):
            return self._envelope(
                "figops.normalize_project_structure",
                arguments,
                status="error",
                summary="Normalization requires reviewed mappings.",
                errors=["Autodiscovery cannot be applied; submit explicit approved_mappings in copy mode."],
                manual_review_needed=True,
                is_dry_run=dry_run,
                error_category="validation",
                error_code=NORMALIZATION_REVIEW_REQUIRED,
                **common,
            )
        if dry_run:
            return self._envelope(
                "figops.normalize_project_structure",
                arguments,
                summary=f"Built reviewed copy-only plan for {project_root.name}.",
                is_dry_run=True,
                **common,
            )
        supplied_token = arguments.get("confirmation_token")
        if not isinstance(supplied_token, str) or not supplied_token:
            return self._envelope(
                "figops.normalize_project_structure",
                arguments,
                status="error",
                summary="Normalization confirmation is required.",
                errors=["Apply requires the confirmation_token returned for the reviewed copy-only plan."],
                manual_review_needed=True,
                is_dry_run=False,
                error_category="validation",
                error_code=NORMALIZATION_CONFIRMATION_REQUIRED,
                **common,
            )
        try:
            self._resolve_execution_project_path(arguments.get("project_path"))
        except ValueError as exc:
            return self._envelope(
                "figops.normalize_project_structure",
                arguments,
                status="error",
                summary="Reviewed normalization plan was rejected.",
                errors=[str(exc)],
                manual_review_needed=True,
                is_dry_run=False,
                error_category="validation",
                error_code=NORMALIZATION_PLAN_REJECTED,
                **common,
            )
        try:
            applied = apply_normalize_project(
                manifest,
                hub_path=self.hub_path,
                confirmation_token=supplied_token,
            )
        except (FileExistsError, OSError, PermissionError, RuntimeError, ValueError) as exc:
            return self._envelope(
                "figops.normalize_project_structure",
                arguments,
                status="error",
                summary="Reviewed normalization plan was rejected.",
                errors=[str(exc)],
                manual_review_needed=True,
                is_dry_run=False,
                error_category="validation",
                error_code=NORMALIZATION_PLAN_REJECTED,
                **common,
            )
        validation = self._validation_summary(config_path)
        validation_failed = validation.get("checked") is True and validation.get("valid") is False
        return self._envelope(
            "figops.normalize_project_structure",
            arguments,
            status="warning" if validation_failed else "ok",
            summary=(
                f"Applied normalization for {project_root.name}, but project validation still needs changes."
                if validation_failed
                else f"Applied normalization for {project_root.name}."
            ),
            created_paths=applied["created_paths"],
            modified_paths=[],
            skipped_paths=[],
            warnings=["Normalized project config did not pass validation."] if validation_failed else [],
            manual_review_needed=validation_failed,
            is_dry_run=False,
            project_root=str(project_root),
            planned_paths=planned_paths,
            manifest=public_manifest,
            manifest_path="",
            config_path=str(config_path),
            style_summary=manifest["style_summary"],
            validation=validation,
            proposed_mappings=proposed_mappings,
            unresolved_proposals=common["unresolved_proposals"],
            plan_digest=applied["plan_digest"],
            confirmation_token=token,
            originals_preserved=applied["originals_preserved"],
            rollback_journal=applied["rollback_journal"],
            provenance_receipt=applied["provenance_receipt"],
        )
