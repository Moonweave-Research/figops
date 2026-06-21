from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import yaml

from hub_core.config_parser import (
    ALLOWED_OUTPUT_FORMATS,
    ALLOWED_TARGET_FORMATS,
    ConfigMigrationError,
    find_config_path,
    folder_role_map,
    migrate_config,
    normalize_project_defaults,
    project_modules,
    project_role,
    validate_config,
)
from hub_core.mcp.schemas import describe_graphhub_surface
from hub_core.project_discovery import ProjectDiscoveryService
from themes.style_packs import list_style_packs
from themes.style_profiles import DEFAULT_PROFILE, PROFILE_ALIASES, list_profiles


class McpReadToolsMixin:
    """Read-only Graph Hub MCP tool handlers."""

    def health(self, arguments: dict[str, Any]) -> dict[str, Any]:
        root = self._scan_root(arguments)
        max_depth = self._max_depth(arguments.get("max_depth", 4))
        warnings: list[str] = list(self.security_warnings)
        discovery = {"project_count": 0, "valid_count": 0, "invalid_count": 0, "root": self._display_path(root)}
        if root.exists():
            projects = ProjectDiscoveryService(root).discover(max_depth=max_depth)
            discovery["project_count"] = len(projects)
            discovery["valid_count"] = sum(1 for project in projects if project.valid)
            discovery["invalid_count"] = sum(1 for project in projects if not project.valid)
        else:
            warnings.append(f"Discovery root does not exist: {self._display_path(root)}")

        status = "warning" if warnings else "ok"
        summary = (
            "Graph Hub MCP surface is available with discovery warnings."
            if warnings
            else "Graph Hub MCP surface is available."
        )
        return self._envelope(
            "graphhub.health",
            arguments,
            status=status,
            summary=summary,
            warnings=warnings,
            hub_path=str(self.hub_path),
            version=self._read_version(),
            python_executable=sys.executable,
            runtime_root=str(self.runtime_root),
            style_format_count=len(ALLOWED_TARGET_FORMATS),
            discovery_status=discovery,
            write_tools_enabled=self.write_tools_enabled,
        )

    def list_styles(self, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = arguments or {}
        return self._envelope(
            "graphhub.list_styles",
            arguments,
            summary=f"{len(ALLOWED_TARGET_FORMATS)} target formats and {len(list_profiles())} profiles available.",
            target_formats=sorted(ALLOWED_TARGET_FORMATS),
            output_formats=sorted(ALLOWED_OUTPUT_FORMATS),
            profiles=list_profiles(),
            profile_aliases=dict(sorted(PROFILE_ALIASES.items())),
            style_packs=list_style_packs(),
            default_target_format="nature",
            default_profile=DEFAULT_PROFILE,
        )

    def describe(self, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = arguments or {}
        surface = describe_graphhub_surface()
        return self._envelope(
            "graphhub.describe",
            arguments,
            summary=(
                f"Described {len(surface['tools'])} tools, {len(surface['plot_types'])} plot type(s), "
                f"{len(surface['semantic_checks'])} semantic check(s), "
                f"and {len(surface['domain_helpers'])} domain helper(s)."
            ),
            **surface,
        )

    def list_projects(self, arguments: dict[str, Any]) -> dict[str, Any]:
        root = self._scan_root(arguments)
        include_invalid = bool(arguments.get("include_invalid", True))
        include_worktrees = bool(arguments.get("include_worktrees", False))
        include_ephemeral = bool(arguments.get("include_ephemeral", False))
        max_depth = self._max_depth(arguments.get("max_depth", 4))

        projects = ProjectDiscoveryService(
            root,
            include_worktrees=include_worktrees,
            include_ephemeral=include_ephemeral,
        ).discover(max_depth=max_depth)
        if not include_invalid:
            projects = [project for project in projects if project.valid]

        serialized = [self._serialize_project(project) for project in projects]
        invalid_count = sum(1 for project in projects if not project.valid)
        return self._envelope(
            "graphhub.list_projects",
            arguments,
            status="warning" if invalid_count else "ok",
            summary=f"Discovered {len(serialized)} project config(s).",
            warnings=[f"{invalid_count} invalid project config(s) found."] if invalid_count else [],
            projects=serialized,
        )

    def inspect_project(self, arguments: dict[str, Any]) -> dict[str, Any]:
        project_path = self._resolve_project_path(arguments)
        loaded = self._load_project_config(project_path)
        if loaded["errors"]:
            return self._envelope(
                "graphhub.inspect_project",
                arguments,
                status="error",
                summary="Project config could not be inspected.",
                errors=loaded["errors"],
                manual_review_needed=True,
            )

        config = loaded["config"]
        project = config.get("project") if isinstance(config.get("project"), dict) else {}
        visual_style = config.get("visual_style") if isinstance(config.get("visual_style"), dict) else {}
        analysis_steps = self._list_section(config.get("pipeline", {}), "analysis")
        figures = self._list_section(config, "figures")
        diagrams = self._list_section(config, "diagrams")
        csv_checks = self._list_section(config.get("data_contract", {}), "csv_checks")
        figure_outputs = self._outputs(figures)
        diagram_outputs = self._outputs(diagrams)

        return self._envelope(
            "graphhub.inspect_project",
            arguments,
            summary=f"Inspected project config at {loaded['config_relpath']}.",
            project_metadata={
                "name": project.get("name") or project_path.name,
                "role": project_role(config),
                "project_root": self._display_path(project_path),
                "config_path": loaded["config_relpath"],
            },
            folder_structure_status={
                "has_project_config": True,
                "has_hub_scripts": (project_path / "hub_scripts").is_dir(),
                "has_results": (project_path / "results").is_dir(),
                "uses_legacy_config_path": loaded["config_relpath"] == "scripts/project_config.yaml",
            },
            data_contract_summary={
                "csv_check_count": len(csv_checks),
                "paths": [
                    str(check.get("path")) for check in csv_checks if isinstance(check, dict) and check.get("path")
                ],
            },
            pipeline_steps={"analysis": len(analysis_steps)},
            figure_outputs=figure_outputs,
            diagram_outputs=diagram_outputs,
            missing_inputs=self._missing_inputs(project_path, analysis_steps),
            missing_outputs=self._missing_paths(project_path, figure_outputs + diagram_outputs),
            style_summary={
                "target_format": str(visual_style.get("target_format") or "nature").lower(),
                "font_scale": visual_style.get("font_scale", 1.0),
                "profile": visual_style.get("profile", DEFAULT_PROFILE),
            },
            folder_role_summary=self._folder_role_summary(project_path, config),
            experimental_conditions_summary=self._experimental_conditions_summary(config),
            normalization_needed=loaded["config_relpath"] == "scripts/project_config.yaml",
        )

    def validate_project(self, arguments: dict[str, Any]) -> dict[str, Any]:
        project_path = self._resolve_project_path(arguments)
        loaded = self._load_project_config(project_path, allow_invalid=True)
        config_errors = list(loaded["errors"])
        config = loaded["config"] if isinstance(loaded["config"], dict) else {}
        if isinstance(config, dict):
            config_errors = validate_config(config)

        data_contract_errors = [error for error in config_errors if error.startswith("data_contract.")]
        style_errors = [
            error
            for error in config_errors
            if error.startswith("Invalid visual_style") or error.startswith("visual_style.")
        ]
        lockfile_status = self._lockfile_status(project_path, config, strict=bool(arguments.get("strict_lock", False)))
        valid = not config_errors and lockfile_status["valid"]
        if valid:
            next_action = "ready_for_render"
        elif style_errors:
            next_action = "fix_style_contract"
        elif data_contract_errors:
            next_action = "fix_data_contract"
        else:
            next_action = "fix_project_config"

        render_environment_warnings = self._project_context_render_warnings(project_path)
        warnings = [] if valid else ["Project validation reported warnings or errors."]
        warnings.extend(render_environment_warnings)
        status = "warning" if warnings else "ok"
        if valid and render_environment_warnings:
            summary = "Project config is valid with render environment warnings."
        elif valid:
            summary = "Project config is valid."
        else:
            summary = "Project config needs changes before rendering."

        return self._envelope(
            "graphhub.validate_project",
            arguments,
            status=status,
            summary=summary,
            warnings=warnings,
            valid=valid,
            config_errors=config_errors,
            data_contract_errors=data_contract_errors,
            lockfile_status=lockfile_status,
            style_errors=style_errors,
            recommended_next_action=next_action,
        )

    def _serialize_project(self, project: Any) -> dict[str, Any]:
        if not project.config_path:
            return {
                "project_id": project.project_id,
                "project_root": project.path,
                "config_path": "",
                "role": project.role,
                "status": self._project_status(project),
                "errors": list(project.errors),
                "declared_figures": 0,
                "declared_diagrams": 0,
                "target_format": "",
            }
        if Path(project.config_path).is_symlink():
            return {
                "project_id": project.project_id,
                "project_root": project.path,
                "config_path": project.config,
                "status": "invalid",
                "errors": ["Project config is a symlink and is not exposed through MCP resources."],
                "role": "module",
                "declared_figures": 0,
                "declared_diagrams": 0,
                "target_format": "",
            }
        config_data = self._load_project_config(
            Path(project.config_path).parent,
            config_path=Path(project.config_path),
            allow_invalid=True,
        )
        config = config_data["config"] if isinstance(config_data["config"], dict) else {}
        figures = self._list_section(config, "figures")
        diagrams = self._list_section(config, "diagrams")
        return {
            "project_id": project.project_id,
            "project_root": project.path,
            "config_path": project.config,
            "role": project.role,
            "status": self._project_status(project),
            "errors": list(project.errors),
            "declared_figures": len(figures),
            "declared_diagrams": len(diagrams),
            "target_format": project.target_format,
        }

    @staticmethod
    def _project_status(project: Any) -> str:
        if not project.valid:
            return "invalid"
        if getattr(project, "role", "module") == "master":
            return "master"
        if project.classification in {"folder_role", "unclassified"}:
            return project.classification
        if project.classification in {"legacy", "ephemeral"}:
            return project.classification
        return "valid"

    @staticmethod
    def _folder_role_summary(project_path: Path, config: dict[str, Any]) -> dict[str, Any]:
        if project_role(config) != "master":
            return {"declared": {}, "modules": [], "unclassified": [], "note": ""}
        declared = folder_role_map(config)
        modules = project_modules(config)
        unclassified: list[str] = []
        if declared:
            declared_or_prefix = set(declared) | set(modules)
            prefixes: set[str] = set()
            for raw_path in declared_or_prefix:
                parts = Path(raw_path).parts
                for index in range(1, len(parts)):
                    prefixes.add(Path(*parts[:index]).as_posix())
            try:
                children = sorted(project_path.iterdir(), key=lambda path: path.name.lower())
            except OSError:
                children = []
            for child in children:
                if not child.is_dir() or find_config_path(str(child)):
                    continue
                rel_child = child.relative_to(project_path).as_posix()
                if rel_child not in declared and rel_child not in prefixes:
                    unclassified.append(rel_child)
        return {
            "declared": declared,
            "modules": modules,
            "unclassified": unclassified,
            "note": (
                "Only module project configs are runnable; non-module and unclassified folders are excluded "
                "from the re-run surface."
                if declared
                else "No folder_roles declared; T1.1 master/module discovery behavior applies."
            ),
        }

    @staticmethod
    def _experimental_conditions_summary(config: dict[str, Any]) -> dict[str, Any]:
        experimental_conditions = config.get("experimental_conditions")
        if not isinstance(experimental_conditions, dict):
            return {"condition_count": 0, "condition_ids": []}
        conditions = experimental_conditions.get("conditions", [])
        if not isinstance(conditions, list):
            return {"condition_count": 0, "condition_ids": []}
        condition_ids = [
            condition["id"].strip()
            for condition in conditions
            if isinstance(condition, dict) and isinstance(condition.get("id"), str) and condition["id"].strip()
        ]
        return {"condition_count": len(condition_ids), "condition_ids": condition_ids}

    @staticmethod
    def _validation_summary(config_path: Path) -> dict[str, Any]:
        if not config_path.exists():
            return {"checked": False, "valid": None, "errors": []}
        try:
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            config = migrate_config(config)
            config = normalize_project_defaults(config)
        except (OSError, yaml.YAMLError) as exc:
            return {"checked": True, "valid": False, "errors": [str(exc)]}
        except ConfigMigrationError as exc:
            return {"checked": True, "valid": False, "errors": [str(exc)]}
        errors = validate_config(config)
        return {"checked": True, "valid": not errors, "errors": errors}

    @staticmethod
    def _load_project_config(
        project_path: Path,
        *,
        config_path: Path | None = None,
        allow_invalid: bool = False,
    ) -> dict[str, Any]:
        discovered_config_path = find_config_path(str(project_path))
        config_path = config_path or (Path(discovered_config_path) if discovered_config_path else None)
        if config_path is None:
            return {
                "config": None,
                "config_path": None,
                "config_relpath": "",
                "errors": [f"project_config.yaml not found in {project_path}"],
            }
        try:
            raw_text = config_path.read_text(encoding="utf-8")
            config = yaml.safe_load(raw_text)
            config = migrate_config(config)
            config = normalize_project_defaults(config)
        except yaml.YAMLError as exc:
            return {
                "config": None,
                "config_path": str(config_path),
                "config_relpath": "",
                "errors": [f"Invalid YAML: {exc}"],
            }
        except ConfigMigrationError as exc:
            return {
                "config": None,
                "config_path": str(config_path),
                "config_relpath": os.path.relpath(config_path, project_path),
                "errors": [str(exc)],
            }
        except OSError as exc:
            return {
                "config": None,
                "config_path": str(config_path),
                "config_relpath": "",
                "errors": [f"Failed to read config: {exc}"],
            }

        errors = validate_config(config)
        if errors and not allow_invalid:
            return {
                "config": config,
                "config_path": str(config_path),
                "config_relpath": os.path.relpath(config_path, project_path),
                "errors": errors,
            }
        return {
            "config": config,
            "config_path": str(config_path),
            "config_relpath": os.path.relpath(config_path, project_path),
            "errors": errors if allow_invalid else [],
        }

    @staticmethod
    def _list_section(config: Any, section_name: str) -> list[dict[str, Any]]:
        if not isinstance(config, dict):
            return []
        section = config.get(section_name, [])
        if isinstance(section, list):
            return [item for item in section if isinstance(item, dict)]
        return []

    @staticmethod
    def _outputs(items: list[dict[str, Any]]) -> list[str]:
        return [str(item["output"]) for item in items if isinstance(item.get("output"), str) and item["output"].strip()]

    @staticmethod
    def _missing_paths(project_path: Path, paths: list[str]) -> list[str]:
        return [path for path in paths if not (project_path / path).exists()]

    @staticmethod
    def _missing_inputs(project_path: Path, analysis_steps: list[dict[str, Any]]) -> list[str]:
        missing: list[str] = []
        for step in analysis_steps:
            inputs = step.get("inputs") or []
            if not isinstance(inputs, list):
                continue
            for path in inputs:
                if isinstance(path, str) and path.strip() and not (project_path / path).exists():
                    missing.append(path)
        return missing
