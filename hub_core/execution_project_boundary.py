"""Fail-closed project-root selection for producer and write surfaces."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from .path_identity import canonical_path, canonical_relative_to, is_macos_system_alias

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

    root = canonical_path(research_root, strict=True)
    raw = Path(project_path).expanduser()
    lexical = raw if raw.is_absolute() else root / raw
    lexical = lexical.absolute()
    try:
        canonical_relative_to(lexical, root, strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ExecutionProjectPathError("execution project must stay under the research root.") from exc

    current = Path(lexical.anchor)
    for part in lexical.parts[1:]:
        current /= part
        if is_macos_system_alias(current):
            continue
        if _is_reparse_or_symlink(current):
            raise ExecutionProjectPathError(PROJECT_EXECUTION_REPARSE_ERROR)

    try:
        resolved = canonical_path(lexical, strict=True)
        canonical_relative_to(resolved, root, strict=True)
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
