"""Allowed-root and verified-descriptor boundary for bounded data reads.

Blocking operations in this module are called only inside the hard-bounded
inspection worker. The MCP process passes named policy values; it never opens
the caller-controlled data path or serializes a callback/prefetcher object.
"""

from __future__ import annotations

import os
import stat
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, BinaryIO, Iterator, Sequence

DEFAULT_INSPECT_MAX_BYTES = 64 * 1024 * 1024
ABSOLUTE_INSPECT_MAX_BYTES = 256 * 1024 * 1024
SNAPSHOT_CHUNK_BYTES = 1024 * 1024
INSPECT_DEADLINE_SECONDS = 10.0
INSPECT_WORK_CUTOFF_SECONDS = 9.0
_REPARSE_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class AllowedDataError(ValueError):
    """A typed, path-redacted allowed-data boundary failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class AllowedDataSelection:
    root: Path
    candidate: Path
    display_name: str


@dataclass
class VerifiedAllowedData:
    handle: BinaryIO
    display_name: str
    suffix: str
    byte_size: int
    source_identity: tuple[int, int, int]
    prefetch_calls: int


def safe_data_name(raw_path: Any) -> str:
    try:
        name = Path(os.fspath(raw_path)).name
    except (TypeError, ValueError):
        return "<data-file>"
    if not name or name in {".", ".."}:
        return "<data-file>"
    return name[:512]


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _validate_raw_path_syntax(raw: str) -> None:
    portable = raw.replace("\\", "/")
    posix = PurePosixPath(portable)
    windows = PureWindowsPath(raw)
    if ".." in posix.parts or ".." in windows.parts:
        raise AllowedDataError("DATA_PATH_TRAVERSAL", "data_path must not contain path traversal.")
    host_path = Path(raw)
    if not host_path.is_absolute() and (posix.is_absolute() or windows.is_absolute() or windows.drive or windows.root):
        raise AllowedDataError("DATA_PATH_OUTSIDE_ALLOWED_ROOT", "Data path is outside allowed roots.")
    tail_parts = windows.parts[1:] if windows.drive else windows.parts
    if any(":" in part for part in tail_parts):
        raise AllowedDataError("DATA_PATH_STREAM", "data_path must not contain a stream designator.")


def _is_reparse_or_symlink(path: Path) -> bool:
    try:
        item = path.lstat()
    except OSError as exc:
        raise AllowedDataError("DATA_PATH_UNAVAILABLE", "Data path cannot be inspected safely.") from exc
    return path.is_symlink() or bool(getattr(item, "st_file_attributes", 0) & _REPARSE_ATTRIBUTE)


def _validate_root(raw_root: str | os.PathLike[str]) -> Path:
    try:
        lexical = Path(raw_root).expanduser()
    except (TypeError, ValueError) as exc:
        raise AllowedDataError("ALLOWED_ROOT_INVALID", "An allowed data root is invalid.") from exc
    if not lexical.is_absolute():
        raise AllowedDataError("ALLOWED_ROOT_INVALID", "Allowed data roots must be absolute directories.")
    try:
        root = lexical.resolve(strict=True)
        root_stat = root.stat()
    except (OSError, RuntimeError) as exc:
        raise AllowedDataError("ALLOWED_ROOT_INVALID", "An allowed data root is unavailable.") from exc
    if not stat.S_ISDIR(root_stat.st_mode):
        raise AllowedDataError("ALLOWED_ROOT_INVALID", "Allowed data roots must be directories.")
    return root


def _check_components(root: Path, candidate: Path) -> None:
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise AllowedDataError("DATA_PATH_OUTSIDE_ALLOWED_ROOT", "Data path is outside allowed roots.") from exc
    current = root
    for part in relative.parts:
        current = current / part
        if _is_reparse_or_symlink(current):
            raise AllowedDataError(
                "DATA_PATH_REPARSE_POINT",
                "Data path must not traverse a symlink, junction, or reparse point.",
            )


def select_allowed_data_path(
    raw_path: str | os.PathLike[str],
    *,
    allowed_roots: Sequence[str | os.PathLike[str]],
    relative_base: str | os.PathLike[str] | None = None,
    allow_internal_aliases: bool = False,
) -> AllowedDataSelection:
    """Select one contained regular file without widening configured trust."""

    if not allowed_roots:
        raise AllowedDataError("NO_ALLOWED_DATA_ROOTS", "No allowed data roots are configured.")
    try:
        raw = os.fspath(raw_path)
    except TypeError as exc:
        raise AllowedDataError("DATA_PATH_INVALID", "data_path must be a non-empty path string.") from exc
    if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
        raise AllowedDataError("DATA_PATH_INVALID", "data_path must be a non-empty path string.")
    _validate_raw_path_syntax(raw)
    roots = tuple(_validate_root(root) for root in allowed_roots)
    lexical = Path(raw).expanduser()
    if not lexical.is_absolute():
        if relative_base is None:
            raise AllowedDataError(
                "RELATIVE_DATA_PATH_WITHOUT_BASE",
                "Relative data_path requires an explicit trusted base.",
            )
        base = Path(relative_base).expanduser()
        if not base.is_absolute():
            raise AllowedDataError("RELATIVE_BASE_INVALID", "The relative data base must be absolute.")
        try:
            base = base.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise AllowedDataError("RELATIVE_BASE_INVALID", "The relative data base is unavailable.") from exc
        if not any(_is_relative_to(base, root) for root in roots):
            raise AllowedDataError("RELATIVE_BASE_OUTSIDE_ALLOWED_ROOT", "The relative data base is not allowed.")
        lexical = base / lexical
    try:
        resolved = lexical.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise AllowedDataError("DATA_PATH_UNAVAILABLE", "Data path does not exist or cannot be resolved.") from exc
    containing = tuple(root for root in roots if _is_relative_to(resolved, root))
    if not containing:
        raise AllowedDataError("DATA_PATH_OUTSIDE_ALLOWED_ROOT", "Data path is outside allowed roots.")
    root = max(containing, key=lambda item: len(item.parts))
    if not allow_internal_aliases:
        _check_components(root, lexical)
    # Alias-enabled read-only consumers receive the resolved candidate below,
    # so they never open through the caller-controlled symlink/junction
    # spelling. Containment is decided from the canonical target, while broken
    # aliases and external targets fail during strict resolution or the
    # allowed-root check above.
    _check_components(root, resolved)
    try:
        current = resolved.stat()
    except OSError as exc:
        raise AllowedDataError("DATA_PATH_UNAVAILABLE", "Data path cannot be inspected safely.") from exc
    if not stat.S_ISREG(current.st_mode):
        raise AllowedDataError("DATA_PATH_NOT_REGULAR", "Data path must name a regular file.")
    return AllowedDataSelection(root=root, candidate=resolved, display_name=safe_data_name(raw))


def resolve_inspect_max_bytes(raw_value: str | int | None = None, *, warnings: list[str] | None = None) -> int:
    if raw_value is None:
        raw_value = os.environ.get("GRAPH_HUB_MCP_INSPECT_MAX_BYTES")
    if raw_value is None or raw_value == "":
        return DEFAULT_INSPECT_MAX_BYTES
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = 0
    if value <= 0 or value > ABSOLUTE_INSPECT_MAX_BYTES:
        if warnings is not None:
            warnings.append(
                "GRAPH_HUB_MCP_INSPECT_MAX_BYTES is invalid; using the 64 MiB default inspection limit."
            )
        return DEFAULT_INSPECT_MAX_BYTES
    return value


def _deadline_check(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise AllowedDataError("INSPECTION_DEADLINE", "Data inspection exceeded its shared deadline.")


def _identity(path: Path) -> tuple[int, int, int]:
    try:
        item = path.stat()
    except OSError as exc:
        raise AllowedDataError("DATA_PATH_CHANGED", "Data path changed during verification.") from exc
    return item.st_dev, item.st_ino, item.st_mode


def _revalidate(selection: AllowedDataSelection, expected: tuple[int, int, int]) -> None:
    try:
        resolved = selection.candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise AllowedDataError("DATA_PATH_CHANGED", "Data path changed during verification.") from exc
    if resolved != selection.candidate or not _is_relative_to(resolved, selection.root):
        raise AllowedDataError("DATA_PATH_CHANGED", "Data path changed during verification.")
    _check_components(selection.root, selection.candidate)
    if _identity(resolved) != expected:
        raise AllowedDataError("DATA_PATH_CHANGED", "Data path changed during verification.")


def _prefetch_from_mode(mode: str):
    from hub_core.adapters.prefetch import GDrivePrefetcher, NoopPrefetcher

    if mode == "none":
        return None
    if mode == "noop":
        return NoopPrefetcher()
    if mode == "gdrive":
        return GDrivePrefetcher()
    raise AllowedDataError("PREFETCH_ADAPTER_UNSUPPORTED", "Data prefetch adapter is unavailable.")


@contextmanager
def open_verified_allowed_data(
    raw_path: str | os.PathLike[str],
    *,
    allowed_roots: Sequence[str | os.PathLike[str]],
    relative_base: str | os.PathLike[str] | None,
    prefetch_mode: str,
    max_bytes: int,
    deadline: float,
) -> Iterator[VerifiedAllowedData]:
    """Open one verified descriptor inside the hard-bounded worker."""

    selection = select_allowed_data_path(raw_path, allowed_roots=allowed_roots, relative_base=relative_base)
    _deadline_check(deadline)
    prefetcher = _prefetch_from_mode(prefetch_mode)
    prefetch_calls = 0
    if prefetcher is not None:
        try:
            prefetcher.ensure_local([str(selection.candidate)])
            prefetch_calls = 1
        except Exception as exc:
            raise AllowedDataError("DATA_PREFETCH_FAILED", "Data prefetch failed.") from exc
    _deadline_check(deadline)
    expected = _identity(selection.candidate)
    if not stat.S_ISREG(expected[2]):
        raise AllowedDataError("DATA_PATH_NOT_REGULAR", "Data path must name a regular file.")
    _revalidate(selection, expected)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(selection.candidate, flags)
    except OSError as exc:
        raise AllowedDataError("DATA_OPEN_FAILED", "Data path could not be opened safely.") from exc
    try:
        opened = os.fstat(descriptor)
        opened_identity = (opened.st_dev, opened.st_ino, opened.st_mode)
        if opened_identity != expected or not stat.S_ISREG(opened.st_mode):
            raise AllowedDataError("DATA_PATH_CHANGED", "Data path changed before it could be opened.")
        if opened.st_size <= 0:
            raise AllowedDataError("DATA_FILE_EMPTY", "Data file is empty.")
        if opened.st_size > max_bytes:
            raise AllowedDataError("DATA_SOURCE_BYTE_LIMIT", "Data file exceeds the inspection limit.")
        _revalidate(selection, expected)
        with os.fdopen(descriptor, "rb", closefd=True) as source:
            descriptor = -1
            yield VerifiedAllowedData(
                handle=source,
                display_name=selection.display_name,
                suffix=selection.candidate.suffix.lower(),
                byte_size=opened.st_size,
                source_identity=expected,
                prefetch_calls=prefetch_calls,
            )
        _revalidate(selection, expected)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


__all__ = [
    "ABSOLUTE_INSPECT_MAX_BYTES",
    "AllowedDataError",
    "AllowedDataSelection",
    "DEFAULT_INSPECT_MAX_BYTES",
    "INSPECT_DEADLINE_SECONDS",
    "INSPECT_WORK_CUTOFF_SECONDS",
    "SNAPSHOT_CHUNK_BYTES",
    "VerifiedAllowedData",
    "open_verified_allowed_data",
    "resolve_inspect_max_bytes",
    "safe_data_name",
    "select_allowed_data_path",
]
