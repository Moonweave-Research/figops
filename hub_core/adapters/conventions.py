from __future__ import annotations

from pathlib import Path
from typing import Protocol


class Conventions(Protocol):
    def is_ephemeral_project_path(self, rel_path: str) -> bool: ...

    def is_quarantine_project_path(self, rel_path: str) -> bool: ...

    def is_worktree_path(self, rel_path: str) -> bool: ...

    def is_bridge_job_path(self, rel_path: str) -> bool: ...

    def default_target_format(self) -> str: ...

    def scaffold_directory_reason(self) -> str: ...

    def scaffold_file_reason(self) -> str: ...


class GenericConventions:
    def is_ephemeral_project_path(self, rel_path: str) -> bool:
        return False

    def is_quarantine_project_path(self, rel_path: str) -> bool:
        return is_quarantine_path(rel_path)

    def is_worktree_path(self, rel_path: str) -> bool:
        return False

    def is_bridge_job_path(self, rel_path: str) -> bool:
        return False

    def default_target_format(self) -> str:
        return "nature"

    def scaffold_directory_reason(self) -> str:
        return "scaffold directory"

    def scaffold_file_reason(self) -> str:
        return "scaffold file"


class SurfurConventions:
    _INTERNAL_TARGET_FORMAT = "_".join(("nature", "surfur"))

    def is_ephemeral_project_path(self, rel_path: str) -> bool:
        return self.is_worktree_path(rel_path) or self.is_bridge_job_path(rel_path)

    def is_quarantine_project_path(self, rel_path: str) -> bool:
        return is_quarantine_path(rel_path)

    def default_target_format(self) -> str:
        return self._INTERNAL_TARGET_FORMAT

    def scaffold_directory_reason(self) -> str:
        return "ResearchOS scaffold directory"

    def scaffold_file_reason(self) -> str:
        return "ResearchOS scaffold file"

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


def is_quarantine_path(rel_path: str) -> bool:
    for segment in Path(rel_path).parts:
        name = segment.strip()
        if name in {"_archive", "_quarantine", "_cross_validation"}:
            return True
        if name.startswith("legacy_") or name.endswith("_legacy"):
            return True
        if ".bak" in name:
            return True
    return False
