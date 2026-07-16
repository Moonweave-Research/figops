"""Reparse-aware filesystem witnesses for reviewed structure changes.

The structure transaction is deliberately pathname based because Python does
not expose portable ``*at`` operations on Windows.  These helpers narrow that
surface by binding every operation to the original project directory identity,
rejecting reparse components, and verifying opened descriptors before bytes are
read or written.  Callers must re-run the witness immediately around each
namespace mutation.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Iterator

_REPARSE_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


@dataclass(frozen=True, slots=True)
class DirectoryWitness:
    root: Path
    root_identity: tuple[int, int, int]
    relative: str
    components: tuple[tuple[str, tuple[int, int, int]], ...]


def path_identity(path: Path) -> tuple[int, int, int]:
    item = path.lstat()
    return item.st_dev, item.st_ino, item.st_mode


def source_identity(path: Path) -> dict[str, int]:
    item = path.stat(follow_symlinks=False)
    return {"device": int(item.st_dev), "inode": int(item.st_ino)}


def _is_reparse(path: Path, item: os.stat_result | None = None) -> bool:
    current = item if item is not None else path.lstat()
    return path.is_symlink() or bool(getattr(current, "st_file_attributes", 0) & _REPARSE_ATTRIBUTE)


def capture_project_root(root: Path) -> tuple[int, int, int]:
    if not root.is_absolute():
        raise ValueError("Planned project root must be absolute.")
    item = root.lstat()
    if _is_reparse(root, item) or not stat.S_ISDIR(item.st_mode):
        raise ValueError("Planned project root is no longer a safe directory.")
    resolved = root.resolve(strict=True)
    if os.path.normcase(str(resolved)) != os.path.normcase(str(root)):
        raise ValueError("Planned project root must not resolve through a reparse point.")
    return item.st_dev, item.st_ino, item.st_mode


def assert_project_root(root: Path, expected: tuple[int, int, int]) -> None:
    try:
        current = capture_project_root(root)
    except OSError as exc:
        raise RuntimeError("Planned project root changed during structure apply.") from exc
    if current != expected:
        raise RuntimeError("Planned project root changed during structure apply.")


def _canonical_relative(value: str) -> str:
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or relative.as_posix() != value
        or ".." in relative.parts
        or any(":" in part for part in relative.parts)
        or "\\" in value
    ):
        raise ValueError("Structure path is not canonical and project-relative.")
    return value


def capture_directory_witness(
    root: Path,
    relative: str,
    *,
    root_identity: tuple[int, int, int],
    create: bool = False,
) -> DirectoryWitness:
    """Capture every directory identity and reject symlinks/junctions.

    Missing components are created one at a time only for destination parents;
    after each creation the root and complete prefix are revalidated.
    """

    relative = _canonical_relative(relative)
    assert_project_root(root, root_identity)
    current = root
    components: list[tuple[str, tuple[int, int, int]]] = []
    prefix: list[str] = []
    for part in PurePosixPath(relative).parts:
        prefix.append(part)
        current /= part
        if not os.path.lexists(current):
            if not create:
                raise FileNotFoundError(f"Structure directory is missing: {'/'.join(prefix)}")
            prefix_witness = DirectoryWitness(
                root,
                root_identity,
                "/".join(prefix[:-1]),
                tuple(components),
            )
            with lease_directory_witness(prefix_witness):
                try:
                    current.mkdir()
                except FileExistsError:
                    pass
        item = current.lstat()
        if _is_reparse(current, item) or not stat.S_ISDIR(item.st_mode):
            raise RuntimeError(f"Structure path traverses an unsafe directory: {'/'.join(prefix)}")
        components.append(("/".join(prefix), (item.st_dev, item.st_ino, item.st_mode)))
        assert_project_root(root, root_identity)
    witness = DirectoryWitness(root, root_identity, relative, tuple(components))
    assert_directory_witness(witness)
    return witness


def assert_directory_witness(witness: DirectoryWitness) -> None:
    assert_project_root(witness.root, witness.root_identity)
    for relative, expected in witness.components:
        path = witness.root.joinpath(*PurePosixPath(relative).parts)
        try:
            item = path.lstat()
        except OSError as exc:
            raise RuntimeError("Structure directory changed during apply.") from exc
        if _is_reparse(path, item) or not stat.S_ISDIR(item.st_mode):
            raise RuntimeError("Structure directory changed to a symlink, junction, or reparse point.")
        if (item.st_dev, item.st_ino, item.st_mode) != expected:
            raise RuntimeError("Structure directory identity changed during apply.")
    assert_project_root(witness.root, witness.root_identity)


@contextmanager
def lease_directory_witness(witness: DirectoryWitness) -> Iterator[None]:
    """Hold Windows directory handles without delete sharing during an operation.

    Excluding ``FILE_SHARE_DELETE`` prevents a witnessed directory from being
    renamed, removed, or replaced by a junction while file bytes are copied or
    a namespace entry is published. POSIX callers retain the identity checks;
    its directory descriptors do not provide the same mandatory rename lease.
    """

    assert_directory_witness(witness)
    if os.name != "nt":
        yield
        assert_directory_witness(witness)
        return

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
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = ctypes.c_int
    share_read_write = 0x00000001 | 0x00000002
    generic_read = 0x80000000
    open_existing = 3
    backup_semantics = 0x02000000
    open_reparse_point = 0x00200000
    invalid = ctypes.c_void_p(-1).value
    paths = [witness.root]
    paths.extend(witness.root.joinpath(*PurePosixPath(relative).parts) for relative, _ in witness.components)
    handles: list[int] = []
    try:
        for path in paths:
            handle = create_file(
                str(path),
                generic_read,
                share_read_write,
                None,
                open_existing,
                backup_semantics | open_reparse_point,
                None,
            )
            if handle == invalid:
                raise OSError(ctypes.get_last_error(), "Could not lease structure directory.")
            handles.append(handle)
        assert_directory_witness(witness)
        yield
        assert_directory_witness(witness)
    finally:
        for handle in reversed(handles):
            close_handle(handle)


def _final_path_for_descriptor(descriptor: int) -> Path | None:
    if os.name == "nt":
        import msvcrt

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        get_final_path = kernel32.GetFinalPathNameByHandleW
        get_final_path.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong]
        get_final_path.restype = ctypes.c_ulong
        handle = msvcrt.get_osfhandle(descriptor)
        size = get_final_path(handle, None, 0, 0)
        if not size:
            raise OSError(ctypes.get_last_error(), "Could not resolve opened structure file handle.")
        buffer = ctypes.create_unicode_buffer(size + 1)
        written = get_final_path(handle, buffer, len(buffer), 0)
        if not written or written >= len(buffer):
            raise OSError(ctypes.get_last_error(), "Could not resolve opened structure file handle.")
        value = buffer.value
        if value.startswith("\\\\?\\UNC\\"):
            value = "\\\\" + value[8:]
        elif value.startswith("\\\\?\\"):
            value = value[4:]
        return Path(value)
    proc_path = Path(f"/proc/self/fd/{descriptor}")
    if proc_path.exists():
        return Path(os.readlink(proc_path))
    return None


def assert_opened_path(descriptor: int, expected: Path, root: Path) -> None:
    final = _final_path_for_descriptor(descriptor)
    if final is None:
        return
    final_absolute = final.absolute()
    expected_absolute = expected.absolute()
    if os.path.normcase(str(final_absolute)) != os.path.normcase(str(expected_absolute)):
        raise RuntimeError("Opened structure path changed or escaped the project root.")
    try:
        final_absolute.relative_to(root)
    except ValueError as exc:
        raise RuntimeError("Opened structure path escaped the project root.") from exc


@contextmanager
def open_bound_source(
    root: Path,
    relative: str,
    *,
    root_identity: tuple[int, int, int],
    planned_identity: dict[str, int],
) -> Iterator[BinaryIO]:
    parent = PurePosixPath(relative).parent.as_posix()
    witness = capture_directory_witness(root, parent, root_identity=root_identity)
    source = root.joinpath(*PurePosixPath(relative).parts)
    if _is_reparse(source):
        raise RuntimeError(f"Planned source is missing or unsafe: {relative}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    with lease_directory_witness(witness):
        descriptor = os.open(source, flags)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode):
                raise RuntimeError(f"Planned source is missing or unsafe: {relative}")
            actual_identity = {"device": int(opened.st_dev), "inode": int(opened.st_ino)}
            if actual_identity != planned_identity:
                raise RuntimeError(f"Planned source identity changed after review: {relative}")
            assert_opened_path(descriptor, source, root)
            assert_directory_witness(witness)
            with os.fdopen(descriptor, "rb", closefd=True) as handle:
                descriptor = -1
                yield handle
            assert_directory_witness(witness)
        finally:
            if descriptor >= 0:
                os.close(descriptor)


def hash_handle(handle: BinaryIO) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
        size += len(chunk)
    handle.seek(0)
    return digest.hexdigest(), size


def delete_file_by_identity(
    path: Path,
    expected: tuple[int, int],
    expected_sha256: str | None = None,
) -> bool:
    """Delete the exact verified Windows file object, never a replacement.

    Python has no portable handle-bound unlink. Non-Windows callers therefore
    fail closed instead of performing a rename/check/unlink sequence whose
    private pathname can still be replaced between verification and deletion.
    Windows opens one non-write-shared handle, verifies file ID and optional
    content hash through that handle, and applies delete disposition to that
    same file object. A pathname swap can therefore never redirect deletion.
    """

    if os.name != "nt":
        return False
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
    set_info = kernel32.SetFileInformationByHandle
    set_info.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong]
    set_info.restype = ctypes.c_int
    delete_access = 0x00010000
    read_attributes = 0x00000080
    generic_read = 0x80000000
    share_read_delete = 0x00000001 | 0x00000004
    open_existing = 3
    open_reparse_point = 0x00200000
    handle = create_file(
        str(path),
        delete_access | read_attributes | generic_read,
        share_read_delete,
        None,
        open_existing,
        open_reparse_point,
        None,
    )
    if handle == ctypes.c_void_p(-1).value:
        return False
    descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != expected or not stat.S_ISREG(opened.st_mode):
            return False
        if expected_sha256 is not None:
            digest = hashlib.sha256()
            os.lseek(descriptor, 0, os.SEEK_SET)
            for chunk in iter(lambda: os.read(descriptor, 1024 * 1024), b""):
                digest.update(chunk)
            if digest.hexdigest() != expected_sha256:
                return False
        disposition = ctypes.c_int(1)
        return bool(
            set_info(
                msvcrt.get_osfhandle(descriptor),
                4,
                ctypes.byref(disposition),
                ctypes.sizeof(disposition),
            )
        )
    finally:
        os.close(descriptor)
