"""Verified, bounded reads for project configuration files.

Callers parse the returned text directly.  They must not reopen the pathname
after this boundary has fixed and revalidated the source descriptor.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Final, Protocol

from .adapters.prefetch import NoopPrefetcher
from .project_paths import (
    ProjectPathError,
    normalize_project_relative_path,
    open_verified_project_input,
    project_path_has_symlink_component,
    resolve_project_input,
    resolve_project_root,
    revalidate_project_input,
    snapshot_project_input,
)

MAX_PROJECT_CONFIG_BYTES: Final = 1024 * 1024
PROJECT_CONFIG_CANDIDATES: Final = ("project_config.yaml", "scripts/project_config.yaml")


class ProjectConfigReadError(ValueError):
    """Path-redacted failure at the project-config read boundary."""


class _Prefetcher(Protocol):
    def ensure_local(self, paths: list[str]) -> None: ...


def find_verified_project_config(project_root: str | os.PathLike[str]) -> str | None:
    """Return the first safe config declaration without reading its bytes."""

    try:
        root = resolve_project_root(project_root)
    except (FileNotFoundError, OSError, ProjectPathError, RuntimeError) as exc:
        raise ProjectConfigReadError("Project root is unavailable or unsafe.") from exc
    for declaration in PROJECT_CONFIG_CANDIDATES:
        lexical = root.joinpath(*declaration.split("/"))
        if not os.path.lexists(lexical):
            continue
        _validate_config_path(root, declaration)
        return declaration
    return None


def read_verified_project_config(
    project_root: str | os.PathLike[str],
    declaration: str | os.PathLike[str],
    *,
    prefetcher: _Prefetcher | None = None,
    max_bytes: int = MAX_PROJECT_CONFIG_BYTES,
) -> str:
    """Read one UTF-8 config through the verified project-input descriptor.

    The selected prefetch adapter is invoked exactly once after an initial
    containment/reparse/hardlink check and before the filesystem snapshot.
    """

    if max_bytes <= 0:
        raise ValueError("Project config byte limit must be positive.")
    try:
        root = resolve_project_root(project_root)
        normalized = _relative_declaration(root, declaration)
        candidate = _validate_config_path(root, normalized)
        selected_prefetcher = prefetcher if prefetcher is not None else NoopPrefetcher()
        selected_prefetcher.ensure_local([str(candidate)])

        # Prefetch can materialize a cloud placeholder. Re-establish the entire
        # trust boundary before snapshotting whatever now occupies the path.
        _validate_config_path(root, normalized)
        snapshot = snapshot_project_input(root, normalized, purpose="project config")
        with open_verified_project_input(
            root,
            normalized,
            expected_snapshot=snapshot,
            purpose="project config",
        ) as handle:
            opened = os.fstat(handle.fileno())
            _validate_opened_file(opened, max_bytes=max_bytes)
            payload = handle.read(max_bytes + 1)
            closed = os.fstat(handle.fileno())
            if _identity(opened) != _identity(closed):
                raise ProjectConfigReadError("Project config changed while it was being read.")
        revalidate_project_input(
            root,
            normalized,
            expected_snapshot=snapshot,
            purpose="project config",
        )
        _validate_config_path(root, normalized)
    except ProjectConfigReadError:
        raise
    except (FileNotFoundError, OSError, ProjectPathError, RuntimeError) as exc:
        raise ProjectConfigReadError("Project config could not be read through the trusted project boundary.") from exc
    except Exception as exc:
        raise ProjectConfigReadError("Project config prefetch failed.") from exc

    if len(payload) > max_bytes:
        raise ProjectConfigReadError(f"Project config exceeds the {max_bytes}-byte limit.")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProjectConfigReadError("Project config must be valid UTF-8.") from exc


def _relative_declaration(root: Path, declaration: str | os.PathLike[str]) -> str:
    try:
        raw = os.fspath(declaration)
    except TypeError as exc:
        raise ProjectConfigReadError("Project config declaration must be a path string.") from exc
    path = Path(raw)
    if path.is_absolute():
        try:
            raw = path.absolute().relative_to(root.absolute()).as_posix()
        except ValueError as exc:
            raise ProjectConfigReadError("Project config must stay inside the project root.") from exc
    try:
        return normalize_project_relative_path(raw, purpose="project config")
    except ProjectPathError as exc:
        raise ProjectConfigReadError("Project config declaration is unsafe.") from exc


def _validate_config_path(root: Path, declaration: str) -> Path:
    try:
        if project_path_has_symlink_component(root, declaration, purpose="project config"):
            raise ProjectConfigReadError("Project config must not traverse a symlink, junction, or reparse point.")
        candidate = resolve_project_input(root, declaration, purpose="project config")
        item = candidate.stat()
    except ProjectConfigReadError:
        raise
    except (FileNotFoundError, OSError, ProjectPathError, RuntimeError) as exc:
        raise ProjectConfigReadError("Project config is unavailable or unsafe.") from exc
    if not stat.S_ISREG(item.st_mode):
        raise ProjectConfigReadError("Project config must be a regular file.")
    if item.st_nlink != 1:
        raise ProjectConfigReadError("Project config must not be hard-linked.")
    return candidate


def _validate_opened_file(item: os.stat_result, *, max_bytes: int) -> None:
    if not stat.S_ISREG(item.st_mode):
        raise ProjectConfigReadError("Project config must be a regular file.")
    if item.st_nlink != 1:
        raise ProjectConfigReadError("Project config must not be hard-linked.")
    if item.st_size > max_bytes:
        raise ProjectConfigReadError(f"Project config exceeds the {max_bytes}-byte limit.")


def _identity(item: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return item.st_dev, item.st_ino, item.st_mode, item.st_nlink, item.st_size, item.st_mtime_ns


__all__ = [
    "MAX_PROJECT_CONFIG_BYTES",
    "PROJECT_CONFIG_CANDIDATES",
    "ProjectConfigReadError",
    "find_verified_project_config",
    "read_verified_project_config",
]
