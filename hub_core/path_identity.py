"""Canonical filesystem identities for trust-boundary comparisons.

Containment compares resolved identities.  Code that executes or opens a path
must separately enforce its lexical symlink/reparse-point policy.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from typing import TypeAlias

PathLike: TypeAlias = str | os.PathLike[str]
_NATIVE_PATH_TYPE = type(Path.cwd())
_NATIVE_OS_NAME = os.name


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


def normalize_windows_final_path(value: str) -> str:
    """Normalize the Win32 final-path namespace to a regular DOS/UNC spelling."""

    if value.startswith("\\\\?\\UNC\\"):
        return "\\\\" + value[8:]
    if value.startswith("\\\\?\\"):
        return value[4:]
    return value


def final_regular_file_path(path: PathLike) -> Path:
    """Resolve an existing regular file through the opened object.

    On Windows, pathname resolution is not authoritative for every symlink and
    reparse-point spelling. Open the candidate read-only with non-exclusive
    sharing, then ask the kernel for the final path of that exact file object.
    POSIX retains strict canonical resolution.
    """

    if _NATIVE_OS_NAME != "nt":
        resolved = canonical_path(path, strict=True)
        if not stat.S_ISREG(resolved.stat().st_mode):
            raise OSError("Path is not a regular file.")
        return resolved
    return _windows_final_regular_file_path(path)


def _windows_final_regular_file_path(path: PathLike) -> Path:
    import ctypes
    import msvcrt

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
    ]
    create_file.restype = ctypes.c_void_p
    get_final_path = kernel32.GetFinalPathNameByHandleW
    get_final_path.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong]
    get_final_path.restype = ctypes.c_ulong
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = ctypes.c_int

    generic_read = 0x80000000
    share_read_write_delete = 0x00000001 | 0x00000002 | 0x00000004
    open_existing = 3
    file_attribute_normal = 0x00000080
    invalid_handle = ctypes.c_void_p(-1).value
    handle = create_file(
        str(lexical_absolute_path(path)),
        generic_read,
        share_read_write_delete,
        None,
        open_existing,
        file_attribute_normal,
        None,
    )
    if handle == invalid_handle:
        raise OSError(ctypes.get_last_error(), "Could not open path for final-path verification.")

    descriptor = -1
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        handle = invalid_handle
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise OSError("Path is not a regular file.")
        native_handle = msvcrt.get_osfhandle(descriptor)
        size = get_final_path(native_handle, None, 0, 0)
        if not size:
            raise OSError(ctypes.get_last_error(), "Could not resolve opened file handle.")
        buffer = ctypes.create_unicode_buffer(size + 1)
        written = get_final_path(native_handle, buffer, len(buffer), 0)
        if not written or written >= len(buffer):
            raise OSError(ctypes.get_last_error(), "Could not resolve opened file handle.")
        return _NATIVE_PATH_TYPE(normalize_windows_final_path(buffer.value))
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        elif handle != invalid_handle:
            close_handle(handle)


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
    "final_regular_file_path",
    "is_macos_system_alias",
    "lexical_absolute_path",
    "lexical_or_canonical_relative_to",
    "normalize_windows_final_path",
]
