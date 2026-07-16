"""Canonical filesystem identities for trust-boundary comparisons.

Containment compares resolved identities.  Code that executes or opens a path
must separately enforce its lexical symlink/reparse-point policy.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TypeAlias

PathLike: TypeAlias = str | os.PathLike[str]
_NATIVE_PATH_TYPE = type(Path.cwd())


def canonical_path(path: PathLike, *, strict: bool = False) -> Path:
    """Return one absolute filesystem identity for ``path``."""

    return _NATIVE_PATH_TYPE(path).expanduser().resolve(strict=strict)


def lexical_absolute_path(path: PathLike) -> Path:
    """Return an absolute path while preserving the caller's root spelling.

    This is for paths exposed in configuration, DTOs, environment variables,
    reports, and filesystem output selection.  Trust-boundary decisions must
    still use the canonical helpers above.
    """

    return _NATIVE_PATH_TYPE(path).expanduser().absolute()


def canonical_relative_to(path: PathLike, root: PathLike, *, strict: bool = False) -> Path:
    """Return ``path`` relative to ``root`` after resolving both identities."""

    return canonical_path(path, strict=strict).relative_to(canonical_path(root, strict=strict))


def canonical_is_relative_to(path: PathLike, root: PathLike, *, strict: bool = False) -> bool:
    """Return whether the resolved identity of ``path`` is below ``root``."""

    try:
        canonical_relative_to(path, root, strict=strict)
    except (OSError, RuntimeError, ValueError):
        return False
    return True


def canonical_paths_overlap(left: PathLike, right: PathLike) -> bool:
    """Return whether either resolved filesystem identity contains the other."""

    return canonical_is_relative_to(left, right) or canonical_is_relative_to(right, left)


def lexical_or_canonical_relative_to(path: PathLike, root: PathLike) -> Path:
    """Preserve lexical components when possible, tolerating root aliases only."""

    candidate = _NATIVE_PATH_TYPE(path).expanduser().absolute()
    boundary = _NATIVE_PATH_TYPE(root).expanduser().absolute()
    try:
        return candidate.relative_to(boundary)
    except ValueError:
        return canonical_relative_to(candidate, boundary)


def is_macos_system_alias(path: PathLike) -> bool:
    """Recognize only Apple's fixed root aliases, never project-owned symlinks."""

    if sys.platform != "darwin":
        return False
    candidate = _NATIVE_PATH_TYPE(path)
    target = {
        _NATIVE_PATH_TYPE("/var"): _NATIVE_PATH_TYPE("/private/var"),
        _NATIVE_PATH_TYPE("/tmp"): _NATIVE_PATH_TYPE("/private/tmp"),
        _NATIVE_PATH_TYPE("/etc"): _NATIVE_PATH_TYPE("/private/etc"),
    }.get(candidate)
    if target is None:
        return False
    try:
        return candidate.is_symlink() and canonical_path(candidate, strict=True) == target
    except (OSError, RuntimeError):
        return False


__all__ = [
    "canonical_is_relative_to",
    "canonical_path",
    "canonical_paths_overlap",
    "canonical_relative_to",
    "is_macos_system_alias",
    "lexical_absolute_path",
    "lexical_or_canonical_relative_to",
]
