"""Platform-native atomic namespace moves that never replace a destination."""

from __future__ import annotations

import ctypes
import errno
import os
import sys
from pathlib import Path

ATOMIC_NO_CLOBBER_UNAVAILABLE = "FIGOPS_ATOMIC_NO_CLOBBER_UNAVAILABLE"


class AtomicNoClobberUnavailable(RuntimeError):
    """The host cannot provide an atomic, consuming, no-replace move."""


def _unavailable(message: str, cause: BaseException | None = None) -> AtomicNoClobberUnavailable:
    error = AtomicNoClobberUnavailable(f"{ATOMIC_NO_CLOBBER_UNAVAILABLE}: {message}")
    if cause is not None:
        error.__cause__ = cause
    return error


def _raise_native_error(error_number: int, destination: Path) -> None:
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(error_number, os.strerror(error_number), str(destination))
    unsupported = {
        errno.ENOSYS,
        errno.EINVAL,
        getattr(errno, "ENOTSUP", errno.EINVAL),
        getattr(errno, "EOPNOTSUPP", errno.EINVAL),
    }
    if error_number in unsupported:
        raise _unavailable("the filesystem does not support a no-replace rename")
    native = OSError(error_number, os.strerror(error_number), str(destination))
    raise _unavailable("the atomic no-replace rename failed", native)


def _windows_move(source: Path, destination: Path) -> None:
    # CPython maps os.rename to MoveFileExW without MOVEFILE_REPLACE_EXISTING.
    # It consumes the source name on success and raises when destination exists.
    try:
        os.rename(source, destination)
    except FileExistsError:
        raise
    except PermissionError:
        raise
    except OSError as exc:
        raise _unavailable("Windows no-replace rename failed", exc) from exc


def _linux_move(source: Path, destination: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise _unavailable("Linux renameat2(RENAME_NOREPLACE) is unavailable")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        parent_fd = os.open(source.parent, flags)
    except OSError as exc:
        raise _unavailable("the publication directory could not be bound", exc) from exc
    try:
        result = renameat2(
            parent_fd,
            os.fsencode(source.name),
            parent_fd,
            os.fsencode(destination.name),
            1,  # RENAME_NOREPLACE
        )
        if result != 0:
            _raise_native_error(ctypes.get_errno(), destination)
    finally:
        os.close(parent_fd)


def _macos_move(source: Path, destination: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renamex_np = getattr(libc, "renamex_np", None)
    if renamex_np is None:
        raise _unavailable("macOS renamex_np(RENAME_EXCL) is unavailable")
    renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    renamex_np.restype = ctypes.c_int
    result = renamex_np(
        os.fsencode(source),
        os.fsencode(destination),
        0x00000004,  # RENAME_EXCL
    )
    if result != 0:
        _raise_native_error(ctypes.get_errno(), destination)


def atomic_no_clobber_move(
    source: str | os.PathLike[str],
    destination: str | os.PathLike[str],
) -> None:
    """Consume ``source`` into absent ``destination`` with one atomic operation.

    Both names must be siblings. Unsupported platforms and filesystems fail
    closed before any non-atomic fallback can publish bytes.
    """

    source_path = Path(source)
    destination_path = Path(destination)
    try:
        source_parent = source_path.parent.resolve(strict=True)
        destination_parent = destination_path.parent.resolve(strict=True)
    except OSError as exc:
        raise _unavailable("the publication directory is unavailable", exc) from exc
    if source_parent != destination_parent:
        raise _unavailable("source and destination must share one bound directory")
    source_path = source_parent / source_path.name
    destination_path = source_parent / destination_path.name

    if os.name == "nt":
        _windows_move(source_path, destination_path)
    elif sys.platform.startswith("linux"):
        _linux_move(source_path, destination_path)
    elif sys.platform == "darwin":
        _macos_move(source_path, destination_path)
    else:
        raise _unavailable(f"unsupported platform: {sys.platform}")
