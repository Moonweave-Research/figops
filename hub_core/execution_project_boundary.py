"""Fail-closed project-root selection for producer and write surfaces."""

from __future__ import annotations

import os
import stat
from pathlib import Path

PROJECT_EXECUTION_REPARSE_ERROR = (
    "execution project must not resolve through a symlink, junction, or reparse point."
)


class ExecutionProjectPathError(ValueError):
    """Raised when a runnable project root is outside its trusted lexical boundary."""


def _is_reparse_or_symlink(path: Path) -> bool:
    try:
        item = path.lstat()
    except OSError as exc:
        raise ExecutionProjectPathError("execution project path is unavailable.") from exc
    attributes = getattr(item, "st_file_attributes", 0)
    return path.is_symlink() or bool(
        attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def resolve_execution_project_path(
    research_root: str | os.PathLike[str],
    project_path: str | os.PathLike[str],
) -> Path:
    """Resolve one real directory below ``research_root`` without aliases."""

    root = Path(research_root).expanduser().resolve(strict=True)
    raw = Path(project_path).expanduser()
    lexical = raw if raw.is_absolute() else root / raw
    lexical = lexical.absolute()
    try:
        relative = lexical.relative_to(root)
    except ValueError as exc:
        raise ExecutionProjectPathError("execution project must stay under the research root.") from exc

    current = root
    for part in relative.parts:
        current = current / part
        if _is_reparse_or_symlink(current):
            raise ExecutionProjectPathError(PROJECT_EXECUTION_REPARSE_ERROR)

    try:
        resolved = lexical.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ExecutionProjectPathError("execution project must stay under the research root.") from exc
    if not resolved.is_dir():
        raise ExecutionProjectPathError("execution project must be a directory.")
    return resolved


__all__ = [
    "ExecutionProjectPathError",
    "PROJECT_EXECUTION_REPARSE_ERROR",
    "resolve_execution_project_path",
]
