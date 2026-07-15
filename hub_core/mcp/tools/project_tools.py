from __future__ import annotations

from pathlib import Path
from typing import Any

from hub_core.project_normalization import (
    apply_normalize_project,
    apply_scaffold_project,
    plan_normalize_project,
    plan_scaffold_project,
)


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
        move_policy = str(arguments.get("move_policy") or "copy").strip().lower()
        include_raw = bool(arguments.get("include_raw", False))
        overwrite = bool(arguments.get("overwrite", False))
        manifest = plan_normalize_project(project_path=project_path, move_policy=move_policy, include_raw=include_raw)
        public_manifest = self._public_manifest(manifest)
        planned_paths = self._manifest_destinations(public_manifest)
        project_root = Path(str(manifest["project_root"]))
        config_path = project_root / "project_config.yaml"
        validation = self._validation_summary(config_path)
        normalize_manifest_path = str(project_root / ".figops_normalization_manifest.json")
        if dry_run:
            return self._envelope(
                "figops.normalize_project_structure",
                arguments,
                summary=f"Planned normalization for {project_root.name}.",
                is_dry_run=True,
                project_root=str(project_root),
                planned_paths=planned_paths,
                manifest=public_manifest,
                manifest_path=normalize_manifest_path,
                config_path=str(config_path),
                style_summary=manifest["style_summary"],
                validation=validation,
            )
        try:
            applied = apply_normalize_project(manifest, hub_path=self.hub_path, overwrite=overwrite)
        except FileExistsError as exc:
            return self._envelope(
                "figops.normalize_project_structure",
                arguments,
                status="error",
                summary="Normalization destination already exists.",
                errors=[str(exc)],
                manual_review_needed=True,
                is_dry_run=False,
                project_root=str(project_root),
                planned_paths=planned_paths,
                manifest=public_manifest,
                manifest_path=normalize_manifest_path,
                config_path=str(config_path),
                style_summary=manifest["style_summary"],
                validation=validation,
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
            modified_paths=applied["modified_paths"],
            skipped_paths=applied["skipped_paths"],
            warnings=["Normalized project config did not pass validation."] if validation_failed else [],
            manual_review_needed=validation_failed,
            is_dry_run=False,
            project_root=str(project_root),
            planned_paths=planned_paths,
            manifest=applied["manifest"],
            manifest_path=normalize_manifest_path,
            config_path=str(config_path),
            style_summary=applied["manifest"]["style_summary"],
            validation=validation,
        )
