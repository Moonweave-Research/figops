from __future__ import annotations

import glob
import os
from pathlib import Path, PureWindowsPath
from typing import Sequence


def _contained_file(project_root: Path, candidate: Path) -> Path:
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(project_root):
        raise ValueError(f"input path escapes project root: {candidate}")
    if not resolved.is_file():
        raise ValueError(f"input path is not a regular file: {candidate}")
    return resolved


def _normalized_declaration(raw: str) -> str:
    declaration = raw.strip()
    if not declaration:
        raise ValueError("input declaration must not be blank")
    windows_path = PureWindowsPath(declaration)
    if (
        Path(declaration).is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or bool(windows_path.root)
    ):
        raise ValueError(f"input declaration must be project-relative: {raw}")
    normalized = declaration.replace("\\", "/")
    if ".." in Path(normalized).parts:
        raise ValueError(f"input declaration must not traverse outside the project: {raw}")
    return normalized


def _expand_declaration(project_root: Path, declaration: str) -> list[Path]:
    candidate = project_root / Path(declaration)
    if glob.has_magic(declaration):
        raw_matches = [Path(match) for match in glob.glob(str(candidate), recursive=True)]
    elif candidate.is_dir():
        resolved_dir = candidate.resolve(strict=True)
        if not resolved_dir.is_relative_to(project_root):
            raise ValueError(f"input directory escapes project root: {declaration}")
        raw_matches = list(candidate.rglob("*"))
    elif candidate.exists():
        raw_matches = [candidate]
    else:
        raw_matches = []
    return [_contained_file(project_root, match) for match in raw_matches if match.is_file()]


def expand_project_input_files(
    project_dir: str | os.PathLike[str],
    declarations: Sequence[str],
    *,
    require_matches: bool,
) -> list[Path]:
    project_root = Path(project_dir).resolve(strict=True)
    if not project_root.is_dir():
        raise ValueError(f"project root is not a directory: {project_dir}")

    expanded: set[Path] = set()
    for raw in declarations:
        declaration = _normalized_declaration(raw)
        matches = _expand_declaration(project_root, declaration)
        if require_matches and not matches:
            raise FileNotFoundError(f"input declaration matched zero files: {raw}")
        expanded.update(matches)
    return sorted(expanded, key=lambda path: path.relative_to(project_root).as_posix())
