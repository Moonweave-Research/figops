"""Project-relative path declarations and runtime containment checks.

This module is intentionally separate from MCP allowed-data-root handling.
Project configuration paths are always relative to one project root; an
operator-configured MCP data root must never widen this contract.
"""

from __future__ import annotations

import os
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

_WINDOWS_RESERVED_DEVICES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class ProjectPathError(ValueError):
    """Raised when a declared project path is unsafe or has the wrong type."""


@dataclass(frozen=True)
class ProjectInputSnapshot:
    """Resolved path plus filesystem identity captured immediately before use."""

    path: Path
    device: int
    inode: int
    mode: int


def _display(raw: Any) -> str:
    return repr(os.fspath(raw) if isinstance(raw, os.PathLike) else raw)


def normalize_project_relative_path(
    declared_path: str | os.PathLike[str],
    *,
    purpose: str = "project path",
) -> str:
    """Validate and normalize a project-relative declaration.

    Both POSIX and Windows path grammars are checked regardless of the host OS
    so that a configuration cannot become unsafe when moved between systems.
    The returned spelling always uses ``/`` separators.
    """

    try:
        raw = os.fspath(declared_path)
    except TypeError as exc:
        raise ProjectPathError(f"{purpose} must be a non-empty project-relative path.") from exc
    if not isinstance(raw, str) or not raw.strip():
        raise ProjectPathError(f"{purpose} must be a non-empty project-relative path.")
    if "\x00" in raw:
        raise ProjectPathError(f"{purpose} must not contain a NUL byte.")

    declaration = raw.strip()
    windows = PureWindowsPath(declaration)
    posix = PurePosixPath(declaration.replace("\\", "/"))
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or bool(windows.root)
        or declaration.startswith(("//", "\\\\"))
    ):
        raise ProjectPathError(
            f"{purpose} must be a project-relative path; absolute, drive-qualified, "
            "and UNC paths are not allowed."
        )

    normalized = declaration.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if ".." in parts:
        raise ProjectPathError(f"{purpose} must not contain path traversal '..'.")
    # A colon can address an NTFS alternate data stream even when it is not a
    # drive prefix. Reject it cross-platform so portable configs remain safe.
    if any(":" in part for part in parts):
        raise ProjectPathError(f"{purpose} must not contain a Windows drive or stream designator.")
    for part in parts:
        windows_stem = part.rstrip(" .").split(".", 1)[0].upper()
        if windows_stem in _WINDOWS_RESERVED_DEVICES:
            raise ProjectPathError(f"{purpose} must not contain a reserved Windows device name.")

    collapsed = PurePosixPath(normalized).as_posix()
    if collapsed in {"", "."}:
        raise ProjectPathError(f"{purpose} must name a path below the project root.")
    return collapsed


def resolve_project_root(project_root: str | os.PathLike[str]) -> Path:
    """Resolve an existing project root to a real directory."""

    try:
        root = Path(project_root).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ProjectPathError(f"project root does not exist or cannot be resolved: {_display(project_root)}.") from exc
    if not root.is_dir():
        raise ProjectPathError(f"project root must be a directory: {_display(project_root)}.")
    return root


def _contained_candidate(
    project_root: str | os.PathLike[str],
    declared_path: str | os.PathLike[str],
    *,
    must_exist: bool,
    regular_file: bool,
    purpose: str,
) -> Path:
    root = resolve_project_root(project_root)
    normalized = normalize_project_relative_path(declared_path, purpose=purpose)
    candidate = root.joinpath(*PurePosixPath(normalized).parts)
    try:
        resolved = candidate.resolve(strict=must_exist)
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise FileNotFoundError(f"{purpose} does not exist: {_display(declared_path)}.") from exc
    except (OSError, RuntimeError) as exc:
        raise ProjectPathError(f"{purpose} cannot be resolved safely: {_display(declared_path)}.") from exc

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ProjectPathError(f"{purpose} escapes the project root: {_display(declared_path)}.") from exc

    if resolved.exists() and regular_file:
        try:
            mode = resolved.stat().st_mode
        except OSError as exc:
            raise ProjectPathError(f"{purpose} cannot be inspected safely: {_display(declared_path)}.") from exc
        if not stat.S_ISREG(mode):
            raise ProjectPathError(f"{purpose} must be a regular file: {_display(declared_path)}.")
    return resolved


def resolve_project_input(
    project_root: str | os.PathLike[str],
    declared_path: str | os.PathLike[str],
    *,
    must_exist: bool = True,
    regular_file: bool = True,
    purpose: str = "project input",
) -> Path:
    """Resolve a contained project input and optionally require a regular file."""

    return _contained_candidate(
        project_root,
        declared_path,
        must_exist=must_exist,
        regular_file=regular_file,
        purpose=purpose,
    )


def resolve_project_output(
    project_root: str | os.PathLike[str],
    declared_path: str | os.PathLike[str],
    *,
    must_exist: bool = False,
    purpose: str = "project output",
) -> Path:
    """Resolve a contained project output, including a not-yet-created target."""

    return _contained_candidate(
        project_root,
        declared_path,
        must_exist=must_exist,
        regular_file=must_exist,
        purpose=purpose,
    )


def revalidate_project_input(
    project_root: str | os.PathLike[str],
    declared_path: str | os.PathLike[str],
    *,
    expected_path: str | os.PathLike[str] | None = None,
    expected_snapshot: ProjectInputSnapshot | None = None,
    purpose: str = "project input",
) -> Path:
    """Re-resolve an input immediately before use and detect boundary changes."""

    resolved = resolve_project_input(project_root, declared_path, purpose=purpose)
    if expected_snapshot is not None:
        expected_path = expected_snapshot.path
    if expected_path is not None:
        try:
            expected = Path(expected_path).resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ProjectPathError(f"{purpose} changed after validation: {_display(declared_path)}.") from exc
        if resolved != expected:
            raise ProjectPathError(f"{purpose} changed after validation: {_display(declared_path)}.")
    if expected_snapshot is not None:
        try:
            current = resolved.stat()
        except OSError as exc:
            raise ProjectPathError(f"{purpose} changed after validation: {_display(declared_path)}.") from exc
        if (current.st_dev, current.st_ino, current.st_mode) != (
            expected_snapshot.device,
            expected_snapshot.inode,
            expected_snapshot.mode,
        ):
            raise ProjectPathError(f"{purpose} changed after validation: {_display(declared_path)}.")
    return resolved


def snapshot_project_input(
    project_root: str | os.PathLike[str],
    declared_path: str | os.PathLike[str],
    *,
    purpose: str = "project input",
) -> ProjectInputSnapshot:
    """Capture a contained regular file's identity for immediate revalidation."""

    resolved = resolve_project_input(project_root, declared_path, purpose=purpose)
    try:
        current = resolved.stat()
    except OSError as exc:
        raise ProjectPathError(f"{purpose} cannot be inspected safely: {_display(declared_path)}.") from exc
    return ProjectInputSnapshot(
        path=resolved,
        device=current.st_dev,
        inode=current.st_ino,
        mode=current.st_mode,
    )


def project_path_has_symlink_component(
    project_root: str | os.PathLike[str],
    declared_path: str | os.PathLike[str],
    *,
    purpose: str = "project path",
) -> bool:
    """Return whether a safe lexical declaration traverses a symlink component."""

    root = resolve_project_root(project_root)
    normalized = normalize_project_relative_path(declared_path, purpose=purpose)
    current = root
    for part in PurePosixPath(normalized).parts:
        current = current / part
        try:
            attributes = getattr(current.lstat(), "st_file_attributes", 0)
        except FileNotFoundError:
            attributes = 0
        if current.is_symlink() or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            return True
    return False


@contextmanager
def open_verified_project_input(
    project_root: str | os.PathLike[str],
    declared_path: str | os.PathLike[str],
    *,
    expected_snapshot: ProjectInputSnapshot,
    purpose: str = "project input",
):
    """Open one verified descriptor and keep pathname swaps out of the read path.

    The pathname is revalidated before and after ``os.open``. The descriptor's
    identity must equal the caller's post-prefetch snapshot, so swapping a
    parent directory between validation and open fails closed. Consumers must
    parse this binary handle rather than reopen ``handle.name``.
    """

    resolved = revalidate_project_input(
        project_root,
        declared_path,
        expected_snapshot=expected_snapshot,
        purpose=purpose,
    )
    flags = os.O_RDONLY
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(resolved, flags)
    except OSError as exc:
        raise ProjectPathError(f"{purpose} could not be opened safely: {_display(declared_path)}.") from exc
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_mode) != (
            expected_snapshot.device,
            expected_snapshot.inode,
            expected_snapshot.mode,
        ):
            raise ProjectPathError(f"{purpose} changed before it could be opened: {_display(declared_path)}.")
        revalidate_project_input(
            project_root,
            declared_path,
            expected_snapshot=expected_snapshot,
            purpose=purpose,
        )
        with os.fdopen(descriptor, "rb", closefd=True) as handle:
            descriptor = -1
            yield handle
    finally:
        if descriptor >= 0:
            os.close(descriptor)
