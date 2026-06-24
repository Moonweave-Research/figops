from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import yaml

from hub_core.canonical_docs import canonical_docs_registry
from hub_core.config_parser import (
    ALLOWED_OUTPUT_FORMATS,
    ALLOWED_TARGET_FORMATS,
    ConfigMigrationError,
    find_config_path,
    folder_role_map,
    load_yaml_with_unique_keys,
    migrate_config,
    normalize_project_defaults,
    project_modules,
    project_role,
    project_status,
    validate_config,
)
from hub_core.config_placeholders import placeholder_report
from hub_core.mcp.schemas import describe_figops_surface
from hub_core.naming_lint import empty_naming_lint, lint_project_naming
from hub_core.project_discovery import ProjectDiscoveryService
from hub_core.raw_integrity import raw_integrity_config, verify_raw_integrity
from hub_core.research_ops_enforcement import validate_research_ops_contract
from themes.style_packs import list_style_packs
from themes.style_profiles import DEFAULT_PROFILE, PROFILE_ALIASES, list_profiles


class McpReadToolsMixin:
    """Read-only FigOps MCP tool handlers."""

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
            "FigOps MCP surface is available with discovery warnings."
            if warnings
            else "FigOps MCP surface is available."
        )
        return self._envelope(
            "figops.health",
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
            "figops.list_styles",
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
        surface = describe_figops_surface()
        return self._envelope(
            "figops.describe",
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
        include_quarantine = bool(arguments.get("include_quarantine", False))
        max_depth = self._max_depth(arguments.get("max_depth", 4))

        projects = ProjectDiscoveryService(
            root,
            include_worktrees=include_worktrees,
            include_ephemeral=include_ephemeral,
            include_quarantine=include_quarantine,
        ).discover(max_depth=max_depth)
        if not include_invalid:
            projects = [project for project in projects if project.valid]

        serialized = [self._serialize_project(project) for project in projects]
        invalid_count = sum(1 for project in projects if not project.valid)
        return self._envelope(
            "figops.list_projects",
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
                "figops.inspect_project",
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
        naming_lint = self._naming_lint(project_path, enabled=bool(arguments.get("include_naming_lint", False)))
        canonical_registry = canonical_docs_registry(project_path, config)
        placeholders = placeholder_report(config)

        return self._envelope(
            "figops.inspect_project",
            arguments,
            summary=f"Inspected project config at {loaded['config_relpath']}.",
            project_metadata={
                "name": project.get("name") or project_path.name,
                "role": project_role(config),
                "status": project_status(config),
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
            figure_traceability_matrix=self._traceability_matrix(figures),
            missing_inputs=self._missing_inputs(project_path, analysis_steps),
            missing_outputs=self._missing_paths(project_path, figure_outputs + diagram_outputs),
            style_summary={
                "target_format": str(visual_style.get("target_format") or "nature").lower(),
                "font_scale": visual_style.get("font_scale", 1.0),
                "profile": visual_style.get("profile", DEFAULT_PROFILE),
            },
            folder_role_summary=self._folder_role_summary(project_path, config),
            experimental_conditions_summary=self._experimental_conditions_summary(config),
            sample_registry_summary=self._sample_registry_summary(config),
            raw_integrity_status=self._raw_integrity_status(project_path, config),
            naming_lint=naming_lint,
            canonical_docs_registry=canonical_registry,
            placeholder_report=placeholders,
            normalization_needed=loaded["config_relpath"] == "scripts/project_config.yaml",
        )

    def validate_project(self, arguments: dict[str, Any]) -> dict[str, Any]:
        project_path = self._resolve_project_path(arguments)
        loaded = self._load_project_config(project_path, allow_invalid=True)
        config_errors = list(loaded["errors"])
        config = loaded["config"] if isinstance(loaded["config"], dict) else {}
        if isinstance(config, dict):
            config_errors = validate_config(config)
        lifecycle_status = project_status(config)
        if lifecycle_status == "legacy":
            research_ops = {
                "errors": [],
                "warnings": [],
                "raw_integrity_status": self._legacy_raw_integrity_status(config),
                "canonical_docs_registry": canonical_docs_registry(project_path, config),
                "placeholder_report": placeholder_report(config),
            }
        else:
            research_ops = validate_research_ops_contract(project_path, config)
        config_errors.extend(research_ops["errors"])
        raw_integrity_status = research_ops["raw_integrity_status"]
        canonical_registry = research_ops["canonical_docs_registry"]
        placeholders = research_ops["placeholder_report"]

        data_contract_errors = [error for error in config_errors if error.startswith("data_contract.")]
        style_errors = [
            error
            for error in config_errors
            if error.startswith("Invalid visual_style") or error.startswith("visual_style.")
        ]
        lockfile_status = self._lockfile_status(project_path, config, strict=bool(arguments.get("strict_lock", False)))
        valid = not config_errors and lockfile_status["valid"]
        if valid and lifecycle_status == "legacy":
            next_action = "legacy_render_disabled"
        elif valid:
            next_action = "ready_for_render"
        elif style_errors:
            next_action = "fix_style_contract"
        elif data_contract_errors:
            next_action = "fix_data_contract"
        else:
            next_action = "fix_project_config"

        render_environment_warnings = self._project_context_render_warnings(project_path)
        naming_lint = self._naming_lint(project_path, enabled=bool(arguments.get("include_naming_lint", False)))
        warnings = [] if valid else ["Project validation reported warnings or errors."]
        warnings.extend(research_ops["warnings"])
        warnings.extend(naming_lint["warnings"])
        warnings.extend(render_environment_warnings)
        if valid and lifecycle_status == "legacy":
            warnings.append("Project is marked legacy; rendering is disabled for retired projects.")
        status = "warning" if warnings else "ok"
        if valid and warnings:
            summary = "Project config is valid with advisory warnings."
        elif valid:
            summary = "Project config is valid."
        else:
            summary = "Project config needs changes before rendering."

        return self._envelope(
            "figops.validate_project",
            arguments,
            status=status,
            summary=summary,
            warnings=warnings,
            valid=valid,
            config_errors=config_errors,
            data_contract_errors=data_contract_errors,
            lockfile_status=lockfile_status,
            style_errors=style_errors,
            raw_integrity_status=raw_integrity_status,
            naming_lint=naming_lint,
            canonical_docs_registry=canonical_registry,
            placeholder_report=placeholders,
            project_status=lifecycle_status,
            recommended_next_action=next_action,
        )

    def _serialize_project(self, project: Any) -> dict[str, Any]:
        base = {
            "project_id": project.project_id,
            "project_root": project.path,
            "role": project.role,
            "classification": project.classification,
            "errors": list(project.errors),
            "declared_figures": 0,
            "declared_diagrams": 0,
        }
        if not project.config_path:
            base.update(
                config_path="",
                status=self._project_status(project),
                project_status=getattr(project, "status", "active"),
                target_format="",
            )
            return base
        if Path(project.config_path).is_symlink():
            base.update(
                config_path=project.config,
                status="invalid",
                project_status="active",
                classification="invalid",
                errors=["Project config is a symlink and is not exposed through MCP resources."],
                target_format="",
            )
            return base
        config_data = self._load_project_config(
            Path(project.config_path).parent,
            config_path=Path(project.config_path),
            allow_invalid=True,
        )
        config = config_data["config"] if isinstance(config_data["config"], dict) else {}
        figures = self._list_section(config, "figures")
        diagrams = self._list_section(config, "diagrams")
        base.update(
            config_path=project.config,
            status=self._project_status(project),
            project_status=project_status(config),
            classification=project.classification,
            errors=list(project.errors),
            declared_figures=len(figures),
            declared_diagrams=len(diagrams),
            target_format=project.target_format,
        )
        return base

    @staticmethod
    def _project_status(project: Any) -> str:
        if not project.valid:
            return "invalid"
        if getattr(project, "status", "active") == "legacy":
            return "legacy"
        if getattr(project, "role", "module") == "master":
            return "master"
        if project.classification in {"folder_role", "unclassified"}:
            return project.classification
        if project.classification in {"legacy", "ephemeral"}:
            return project.classification
        if project.classification == "quarantine":
            return project.classification
        return "valid"

    @staticmethod
    def _legacy_raw_integrity_status(config: dict[str, Any]) -> dict[str, Any]:
        configured = raw_integrity_config(config) is not None
        return {
            "configured": configured,
            "sealed": False,
            "ok": True,
            "manifest_path": "",
            "mode": "legacy_exempt" if configured else "",
            "sealed_at": "",
            "modified": [],
            "added": [],
            "removed": [],
            "errors": [],
        }

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
    def _sample_registry_summary(config: dict[str, Any]) -> dict[str, Any]:
        sample_registry = config.get("sample_registry", [])
        if not isinstance(sample_registry, list):
            return {"sample_count": 0, "sample_ids": []}
        sample_ids = [
            sample["sample_id"].strip()
            for sample in sample_registry
            if isinstance(sample, dict) and isinstance(sample.get("sample_id"), str) and sample["sample_id"].strip()
        ]
        return {"sample_count": len(sample_ids), "sample_ids": sample_ids}

    @staticmethod
    def _raw_integrity_status(project_path: Path, config: dict[str, Any]) -> dict[str, Any]:
        if raw_integrity_config(config) is None:
            return {
                "configured": False,
                "sealed": False,
                "ok": True,
                "manifest_path": "",
                "mode": "",
                "sealed_at": "",
                "modified": [],
                "added": [],
                "removed": [],
                "errors": [],
            }
        return verify_raw_integrity(project_path, config)

    def _naming_lint(self, project_path: Path, *, enabled: bool) -> dict[str, Any]:
        if not enabled:
            return empty_naming_lint()
        try:
            lint_path = project_path.resolve().relative_to(self.research_root)
        except ValueError:
            lint_path = project_path.name
        return lint_project_naming(lint_path)

    @staticmethod
    def _traceability_matrix(figures: list[dict[str, Any]]) -> list[dict[str, Any]]:
        matrix = []
        for index, figure in enumerate(figures, 1):
            figure_id = figure.get("id")
            inputs = figure.get("inputs", [])
            samples = figure.get("samples", [])
            conditions = figure.get("conditions", [])
            matrix.append(
                {
                    "id": figure_id if isinstance(figure_id, str) and figure_id.strip() else f"Figure{index}",
                    "claim": figure.get("claim") if isinstance(figure.get("claim"), str) else "",
                    "script": figure.get("script") if isinstance(figure.get("script"), str) else "",
                    "inputs": inputs if isinstance(inputs, list) else [],
                    "samples": samples if isinstance(samples, list) else [],
                    "conditions": conditions if isinstance(conditions, list) else [],
                    "output": figure.get("output") if isinstance(figure.get("output"), str) else "",
                }
            )
        return matrix

    @staticmethod
    def _validation_summary(config_path: Path) -> dict[str, Any]:
        if not config_path.exists():
            return {"checked": False, "valid": None, "errors": []}
        try:
            config = load_yaml_with_unique_keys(config_path.read_text(encoding="utf-8"))
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
            config = load_yaml_with_unique_keys(raw_text)
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
