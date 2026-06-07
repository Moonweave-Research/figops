from __future__ import annotations

import hashlib
import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_EXCLUDED_DIRS = {"__pycache__"}
EPHEMERAL_DIRS = {".worktrees"}


@dataclass(frozen=True)
class DiscoveredProject:
    project_id: str
    name: str
    path: str
    config: str
    config_path: str
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
    ) -> None:
        self.root_dir = Path(root_dir).expanduser().resolve()
        self.include_worktrees = include_worktrees
        self.include_ephemeral = include_ephemeral

    def discover(self, max_depth: int = 4) -> list[DiscoveredProject]:
        max_depth = max(1, int(max_depth or 1))
        discovered: list[DiscoveredProject] = []

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
            discovered.append(project)
            dirs[:] = []

        return sorted(
            discovered,
            key=lambda item: (
                item.classification == "ephemeral",
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
            if dirname == ".worktrees" and not self.include_worktrees:
                continue
            child = current_path / dirname
            rel_child = self._relative_path(child)
            if self._is_bridge_job_path(rel_child) and not self.include_ephemeral:
                continue
            result.append(dirname)
        return result

    def _build_project(self, project_path: Path, config_path: Path) -> DiscoveredProject:
        from .config_parser import _load_project_metadata

        rel_project = self._relative_path(project_path)
        rel_config = os.path.relpath(config_path, project_path)
        metadata = _load_project_metadata(str(config_path), project_path.name)
        valid = bool(metadata["valid"])
        classification = self._classify(rel_project, rel_config, valid)
        target_format = self._read_target_format(config_path)

        return DiscoveredProject(
            project_id=self._stable_project_id(rel_project),
            name=str(metadata["name"]),
            path=rel_project,
            config=rel_config,
            config_path=str(config_path),
            valid=valid,
            errors=tuple(metadata["errors"]),
            classification=classification,
            target_format=target_format,
        )

    def _classify(self, rel_project: str, rel_config: str, valid: bool) -> str:
        if self._is_ephemeral_path(rel_project):
            return "ephemeral"
        if not valid:
            return "invalid"
        if rel_config == "scripts/project_config.yaml":
            return "legacy"
        return "official"

    def _include_ephemeral_path(self, rel_project: str) -> bool:
        if rel_project.startswith(".worktrees/"):
            return self.include_worktrees
        if self._is_bridge_job_path(rel_project):
            return self.include_ephemeral
        return self.include_ephemeral

    def _is_ephemeral_path(self, rel_project: str) -> bool:
        return rel_project.startswith(".worktrees/") or self._is_bridge_job_path(rel_project)

    @staticmethod
    def _is_bridge_job_path(rel_path: str) -> bool:
        parts = Path(rel_path).parts
        return len(parts) >= 2 and parts[0] == "[Athena]" and parts[1] == "bridge_jobs"

    def _relative_path(self, path: Path) -> str:
        try:
            rel = path.relative_to(self.root_dir)
        except ValueError:
            rel = path.resolve().relative_to(self.root_dir)
        return unicodedata.normalize("NFC", rel.as_posix())

    @staticmethod
    def _stable_project_id(rel_project: str) -> str:
        normalized = unicodedata.normalize("NFC", rel_project)
        digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
        slug = normalized.replace("/", "__").replace(" ", "_")
        return f"{slug}::{digest}"

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
        import yaml

        try:
            with config_path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
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
) -> list[dict]:
    service = ProjectDiscoveryService(
        root_dir,
        include_worktrees=include_worktrees,
        include_ephemeral=include_ephemeral,
    )
    return [project.to_dict() for project in service.discover(max_depth=max_depth)]


def get_discoverable_projects(
    root_dir: str | os.PathLike,
    *,
    max_depth: int = 4,
    include_worktrees: bool = False,
    include_ephemeral: bool = False,
) -> list[dict]:
    projects = []
    for project in discover_projects_with_status(
        root_dir,
        max_depth=max_depth,
        include_worktrees=include_worktrees,
        include_ephemeral=include_ephemeral,
    ):
        if not project["valid"]:
            continue
        projects.append(
            {
                "project_id": project["project_id"],
                "name": project["name"],
                "path": project["path"],
                "config": project["config"],
                "classification": project["classification"],
                "target_format": project["target_format"],
            }
        )
    return projects
