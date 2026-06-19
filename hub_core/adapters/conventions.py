from __future__ import annotations

from pathlib import Path
from typing import Protocol


class Conventions(Protocol):
    def is_ephemeral_project_path(self, rel_path: str) -> bool: ...

    def is_worktree_path(self, rel_path: str) -> bool: ...

    def is_bridge_job_path(self, rel_path: str) -> bool: ...

    def default_target_format(self) -> str: ...


class GenericConventions:
    def is_ephemeral_project_path(self, rel_path: str) -> bool:
        return False

    def is_worktree_path(self, rel_path: str) -> bool:
        return False

    def is_bridge_job_path(self, rel_path: str) -> bool:
        return False

    def default_target_format(self) -> str:
        return "nature"


class SurfurConventions:
    def is_ephemeral_project_path(self, rel_path: str) -> bool:
        return self.is_worktree_path(rel_path) or self.is_bridge_job_path(rel_path)

    def default_target_format(self) -> str:
        return "nature_surfur"

    @staticmethod
    def is_worktree_path(rel_path: str) -> bool:
        return ".worktrees" in Path(rel_path).parts

    @staticmethod
    def is_bridge_job_path(rel_path: str) -> bool:
        parts = Path(rel_path).parts
        return any(
            part == "[Athena]" and index + 1 < len(parts) and parts[index + 1] == "bridge_jobs"
            for index, part in enumerate(parts)
        )
