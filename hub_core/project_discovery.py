from __future__ import annotations

import hashlib
import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .adapters import select_adapters

DEFAULT_EXCLUDED_DIRS = {"__pycache__"}


@dataclass(frozen=True)
class DiscoveredProject:
    project_id: str
    name: str
    path: str
    config: str
    config_path: str
    role: str
    status: str
    valid: bool
    errors: tuple[str, ...]
    classification: str
    target_format: str

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "path": self.path,
            "config": self.config,
            "config_path": self.config_path,
            "role": self.role,
            "status": self.status,
            "valid": self.valid,
            "errors": list(self.errors),
            "classification": self.classification,
            "target_format": self.target_format,
        }


class ProjectDiscoveryService:
    def __init__(
        self,
        root_dir: str | os.PathLike,
        *,
        include_worktrees: bool = False,
        include_ephemeral: bool = False,
        include_quarantine: bool = False,
        conventions=None,
    ) -> None:
        self.root_dir = Path(root_dir).expanduser().resolve()
        self.include_worktrees = include_worktrees
        self.include_ephemeral = include_ephemeral
        self.include_quarantine = include_quarantine
        self.conventions = conventions if conventions is not None else select_adapters({}).conventions

    def discover(self, max_depth: int = 4) -> list[DiscoveredProject]:
        max_depth = max(1, int(max_depth or 1))
        discovered: dict[str, DiscoveredProject] = {}

        for current_root, dirs, _files in os.walk(self.root_dir, followlinks=True):
            current_path = Path(current_root)
            rel_path = self._relative_path(current_path)
            depth = 0 if not rel_path else len(Path(rel_path).parts)

            dirs[:] = self._filter_dirs(current_path, dirs)
            if depth >= max_depth:
                dirs[:] = []

            if current_path == self.root_dir:
                continue

            config_path = self._find_config_path(current_path)
            if not config_path:
                continue

            project = self._build_project(current_path, config_path)
            if project.classification == "ephemeral" and not self._include_ephemeral_path(project.path):
                continue
            discovered[project.path] = project
            if project.role == "master":
                for folder_entry in self._build_master_folder_entries(
                    current_path,
                    max_depth=max_depth,
                    master_depth=depth,
                ):
                    discovered.setdefault(folder_entry.path, folder_entry)
            if project.role != "master":
                dirs[:] = []

        return sorted(
            discovered.values(),
            key=lambda item: (
                item.classification == "ephemeral",
                item.classification == "quarantine",
                item.classification == "invalid",
                not item.valid,
                item.name.lower(),
                item.path,
            ),
        )

    def _filter_dirs(self, current_path: Path, dirs: list[str]) -> list[str]:
        result = []
        for dirname in dirs:
            if dirname in DEFAULT_EXCLUDED_DIRS:
                continue
            if dirname == ".git":
                continue
            if dirname == ".venv":
                continue
            child = current_path / dirname
            rel_child = self._relative_path(child)
            if self.conventions.is_worktree_path(rel_child) and not self.include_worktrees:
                continue
            if self.conventions.is_bridge_job_path(rel_child) and not self.include_ephemeral:
                continue
            result.append(dirname)
        return result

    def _build_project(self, project_path: Path, config_path: Path) -> DiscoveredProject:
        from .config_parser import _load_project_metadata

        rel_project = self._relative_path(project_path)
        rel_config = Path(os.path.relpath(config_path, project_path)).as_posix()
        metadata = _load_project_metadata(str(config_path), project_path.name)
        valid = bool(metadata["valid"])
        classification = self._classify(rel_project, rel_config, valid)
        target_format = self._read_target_format(config_path)

        return DiscoveredProject(
            project_id=self._stable_project_id(project_path),
            name=str(metadata["name"]),
            path=rel_project,
            config=rel_config,
            config_path=str(config_path),
            role=str(metadata["role"]),
            status=str(metadata["status"]),
            valid=valid,
            errors=tuple(metadata["errors"]),
            classification=classification,
            target_format=target_format,
        )

    def _build_master_folder_entries(
        self,
        master_path: Path,
        *,
        max_depth: int,
        master_depth: int,
    ) -> list[DiscoveredProject]:
        from .config_parser import folder_role_map, load_config, project_modules

        config, _config_path, _config_hash = load_config(str(master_path))
        if not isinstance(config, dict):
            return []
        declared_roles = folder_role_map(config)
        if not declared_roles:
            return []

        module_paths = {Path(path).as_posix().strip("/") for path in project_modules(config)}
        prefix_paths = self._folder_role_prefixes(set(declared_roles) | module_paths)
        entries: dict[str, DiscoveredProject] = {}

        for rel_folder, role in declared_roles.items():
            folder_path = master_path / Path(rel_folder)
            rel_project = self._relative_path(folder_path)
            if not folder_path.is_dir() or master_depth + len(Path(rel_folder).parts) > max_depth:
                continue
            entries[rel_project] = self._build_configless_folder_entry(
                folder_path,
                role=role,
                classification="folder_role",
            )

        for child in sorted(master_path.iterdir(), key=lambda path: path.name.lower()):
            if not child.is_dir():
                continue
            if child.name in DEFAULT_EXCLUDED_DIRS or child.name in {".git", ".venv"}:
                continue
            if self._find_config_path(child):
                continue
            rel_from_master = child.relative_to(master_path).as_posix()
            if rel_from_master in declared_roles or rel_from_master in prefix_paths:
                continue
            rel_project = self._relative_path(child)
            entries.setdefault(
                rel_project,
                self._build_configless_folder_entry(
                    child,
                    role="unclassified",
                    classification="unclassified",
                ),
            )

        return list(entries.values())

    def _build_configless_folder_entry(
        self,
        folder_path: Path,
        *,
        role: str,
        classification: str,
    ) -> DiscoveredProject:
        rel_project = self._relative_path(folder_path)
        return DiscoveredProject(
            project_id=self._stable_project_id(folder_path),
            name=folder_path.name,
            path=rel_project,
            config="",
            config_path="",
            role=role,
            status="active",
            valid=True,
            errors=(),
            classification=classification,
            target_format="",
        )

    @staticmethod
    def _folder_role_prefixes(paths: set[str]) -> set[str]:
        prefixes: set[str] = set()
        for raw_path in paths:
            parts = Path(raw_path).parts
            for index in range(1, len(parts)):
                prefixes.add(Path(*parts[:index]).as_posix())
        return prefixes

    def _classify(self, rel_project: str, rel_config: str, valid: bool) -> str:
        if self._is_ephemeral_path(rel_project):
            return "ephemeral"
        if self._is_quarantine_path(rel_project):
            return "quarantine"
        if not valid:
            return "invalid"
        if rel_config == "scripts/project_config.yaml":
            return "legacy"
        return "official"

    def _include_ephemeral_path(self, rel_project: str) -> bool:
        if self.conventions.is_worktree_path(rel_project):
            return self.include_worktrees
        if self.conventions.is_bridge_job_path(rel_project):
            return self.include_ephemeral
        return self.include_ephemeral

    def _is_ephemeral_path(self, rel_project: str) -> bool:
        return self.conventions.is_ephemeral_project_path(rel_project)

    def _is_quarantine_path(self, rel_project: str) -> bool:
        return self.conventions.is_quarantine_project_path(rel_project)

    def _relative_path(self, path: Path) -> str:
        try:
            rel = path.relative_to(self.root_dir)
        except ValueError:
            rel = path.resolve().relative_to(self.root_dir)
        return unicodedata.normalize("NFC", rel.as_posix())

    @staticmethod
    def _stable_project_id(project_path: str | os.PathLike) -> str:
        # Canonical, discovery-root-independent id: keyed on the resolved absolute
        # path so list_projects and render resolve the same project to the same id
        # regardless of which root each surface scans from.
        resolved = Path(project_path).resolve()
        normalized = unicodedata.normalize("NFC", resolved.as_posix())
        digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
        stem = "".join(ch if ch.isalnum() else "_" for ch in resolved.name).strip("_") or "project"
        return f"{stem}__{digest}"

    @staticmethod
    def _find_config_path(project_dir: Path) -> Path | None:
        from .config_parser import CONFIG_FILE_CANDIDATES

        for rel_path in CONFIG_FILE_CANDIDATES:
            candidate = project_dir / rel_path
            if candidate.exists():
                return candidate
        return None

    @staticmethod
    def _read_target_format(config_path: Path) -> str:
        from .config_parser import load_yaml_with_unique_keys

        try:
            with config_path.open("r", encoding="utf-8") as f:
                data = load_yaml_with_unique_keys(f.read()) or {}
        except Exception:
            return ""
        if not isinstance(data, dict):
            return ""
        visual_style = data.get("visual_style") or {}
        if not isinstance(visual_style, dict):
            return ""
        return str(visual_style.get("target_format") or "nature").strip().lower()


def discover_projects_with_status(
    root_dir: str | os.PathLike,
    *,
    max_depth: int = 4,
    include_worktrees: bool = False,
    include_ephemeral: bool = False,
    include_quarantine: bool = False,
    conventions=None,
) -> list[dict]:
    service = ProjectDiscoveryService(
        root_dir,
        include_worktrees=include_worktrees,
        include_ephemeral=include_ephemeral,
        include_quarantine=include_quarantine,
        conventions=conventions,
    )
    return [project.to_dict() for project in service.discover(max_depth=max_depth)]


def get_discoverable_projects(
    root_dir: str | os.PathLike,
    *,
    max_depth: int = 4,
    include_worktrees: bool = False,
    include_ephemeral: bool = False,
    include_quarantine: bool = False,
    conventions=None,
) -> list[dict]:
    projects = []
    for project in discover_projects_with_status(
        root_dir,
        max_depth=max_depth,
        include_worktrees=include_worktrees,
        include_ephemeral=include_ephemeral,
        include_quarantine=include_quarantine,
        conventions=conventions,
    ):
        if not project["valid"]:
            continue
        if project.get("role") != "module" or not project.get("config_path"):
            continue
        if project.get("status") == "legacy":
            continue
        if project.get("classification") == "quarantine" and not include_quarantine:
            continue
        projects.append(
            {
                "project_id": project["project_id"],
                "name": project["name"],
                "path": project["path"],
                "config": project["config"],
                "role": project["role"],
                "status": project["status"],
                "classification": project["classification"],
                "target_format": project["target_format"],
            }
        )
    return projects
