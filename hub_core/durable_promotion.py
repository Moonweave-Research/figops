"""Verified promotion from disposable runtime storage to durable results."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .atomic_no_clobber import (
    ATOMIC_NO_CLOBBER_UNAVAILABLE,
    AtomicNoClobberUnavailable,
    atomic_no_clobber_move,
)
from .durable_receipt import DurableReceipt, canonical_serialize
from .runtime_boundary import RuntimeBoundaryError, paths_overlap, validate_runtime_location
from .structure_path_security import delete_file_by_identity

DURABLE_DESTINATION_EXISTS = "FIGOPS_DURABLE_DESTINATION_EXISTS"
DURABLE_MANUAL_CLEANUP_REQUIRED = "FIGOPS_DURABLE_MANUAL_CLEANUP_REQUIRED"
DURABLE_PRIVATE_STAGE_RETAINED = "FIGOPS_DURABLE_PRIVATE_STAGE_RETAINED"
DURABLE_VERIFY_BOUNDARY = "FIGOPS_DURABLE_VERIFY_BOUNDARY"
DURABLE_VERIFY_CHANGED = "FIGOPS_DURABLE_VERIFY_CHANGED"
DURABLE_VERIFY_FILE_TYPE = "FIGOPS_DURABLE_VERIFY_FILE_TYPE"


class DurablePromotionError(RuntimeError):
    """A runtime artifact could not be promoted without weakening integrity."""


def file_sha256(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _contained_regular_file(path: Path, root: Path, *, label: str) -> Path:
    raw = path.expanduser().absolute()
    resolved = raw.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise DurablePromotionError(f"{label} must stay below the validated runtime root") from exc
    if raw.is_symlink() or not resolved.is_file() or not stat.S_ISREG(resolved.stat().st_mode):
        raise DurablePromotionError(f"{label} must be a non-symlink regular file")
    return resolved


def _destination(path: str | os.PathLike[str], runtime_root: Path) -> Path:
    raw = Path(path).expanduser()
    if not raw.is_absolute():
        raise DurablePromotionError("durable destination must be absolute")
    raw.parent.mkdir(parents=True, exist_ok=True)
    parent = raw.parent.resolve(strict=True)
    destination = parent / raw.name
    if paths_overlap(runtime_root, destination):
        raise DurablePromotionError("durable destination must be outside the runtime root")
    if destination.is_symlink():
        raise DurablePromotionError("durable destination must not be a symlink")
    return destination


def _fsync_parent(parent: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(parent, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        # Directory fsync is not supported on every Windows/filesystem pairing.
        pass
    finally:
        os.close(descriptor)


def _stage_bytes(destination: Path, chunks: Any) -> tuple[Path, str]:
    staging = destination.with_name(f".{destination.name}.figops-stage-{secrets.token_hex(12)}")
    digest = hashlib.sha256()
    descriptor = os.open(staging, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    staging_identity: tuple[int, int] | None = None
    try:
        opened = os.fstat(descriptor)
        staging_identity = (opened.st_dev, opened.st_ino)
        with os.fdopen(descriptor, "wb", closefd=True) as output:
            descriptor = -1
            for chunk in chunks:
                if not isinstance(chunk, (bytes, bytearray)):
                    raise DurablePromotionError("promotion source yielded non-byte content")
                output.write(chunk)
                digest.update(chunk)
            output.flush()
            os.fsync(output.fileno())
        _fsync_parent(destination.parent)
        return staging, digest.hexdigest()
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        if staging_identity is not None:
            delete_file_by_identity(staging, staging_identity)
        raise


def _file_identity(path: Path) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    return metadata.st_dev, metadata.st_ino


def _atomic_install(staging: Path, destination: Path, expected_sha256: str) -> tuple[int, int]:
    """Atomically publish a complete sibling stage without clobbering a path."""

    if staging.parent.resolve() != destination.parent.resolve():
        raise DurablePromotionError("promotion staging must use the destination filesystem")
    identity = _file_identity(staging)
    try:
        atomic_no_clobber_move(staging, destination)
    except FileExistsError:
        raise DurablePromotionError(f"{DURABLE_DESTINATION_EXISTS}: durable destination already exists") from None
    except AtomicNoClobberUnavailable as exc:
        raise DurablePromotionError(f"{ATOMIC_NO_CLOBBER_UNAVAILABLE}: atomic no-clobber promotion failed") from exc
    try:
        installed = destination.stat(follow_symlinks=False)
        installed_identity = (installed.st_dev, installed.st_ino)
        installed_hash = file_sha256(destination)
    except OSError as exc:
        removed = _remove_installed(destination, identity, expected_sha256)
        suffix = "" if removed else f"; {DURABLE_MANUAL_CLEANUP_REQUIRED}: cleanup withheld"
        raise DurablePromotionError(
            f"promoted artifact could not be verified after atomic publication{suffix}"
        ) from exc
    if (
        os.path.lexists(staging)
        or installed_identity != identity
        or installed.st_nlink != 1
        or installed_hash != expected_sha256
    ):
        removed = _remove_installed(destination, identity, expected_sha256)
        suffix = "" if removed else f"; {DURABLE_MANUAL_CLEANUP_REQUIRED}: cleanup withheld"
        raise DurablePromotionError(
            f"atomic promotion retained an alias or changed after publication{suffix}"
        )
    _fsync_parent(destination.parent)
    return identity


def _discard_staging(
    staging: Path | None,
    identity: tuple[int, int] | None = None,
    expected_sha256: str | None = None,
) -> None:
    if staging is None or identity is None or expected_sha256 is None:
        return
    try:
        if staging.is_file() and not staging.is_symlink() and _file_identity(staging) == identity:
            if file_sha256(staging) == expected_sha256:
                delete_file_by_identity(staging, identity, expected_sha256)
    except OSError:
        return


def _remove_installed(path: Path, identity: tuple[int, int], expected_sha256: str) -> bool:
    """Remove only the exact verified file object installed by this process."""

    try:
        if not path.is_file() or path.is_symlink():
            return not os.path.lexists(path)
        if _file_identity(path) != identity:
            return False
        if file_sha256(path) != expected_sha256:
            return False
        if delete_file_by_identity(path, identity, expected_sha256):
            _fsync_parent(path.parent)
            return True
    except OSError:
        return False
    return False


def _cleanup_withheld_error(paths: Iterable[Path]) -> DurablePromotionError:
    labels = ", ".join(sorted(path.name for path in paths))
    return DurablePromotionError(
        f"{DURABLE_MANUAL_CLEANUP_REQUIRED}: automatic rollback was withheld for "
        f"ownership-ambiguous path(s): {labels}; preserve them for manual review"
    )


@dataclass(frozen=True, slots=True)
class PromotedArtifact:
    path: Path
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class _DurableFileRead:
    lexical_path: Path
    resolved_path: Path
    identity: tuple[int, int, int, int, int]
    payload: bytes
    sha256: str


def _reparse_or_symlink(path: Path) -> bool:
    metadata = path.lstat()
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return path.is_symlink() or bool(attributes & reparse_flag)


def _assert_no_reparse_components(path: Path, *, label: str) -> None:
    """Reject symlinks, junctions, and other reparse points before resolve()."""

    if not path.is_absolute():
        raise DurablePromotionError(f"{DURABLE_VERIFY_BOUNDARY}: {label} must be absolute")
    parts = path.parts
    current = Path(path.anchor)
    for part in parts[1:]:
        current /= part
        try:
            if _reparse_or_symlink(current):
                raise DurablePromotionError(
                    f"{DURABLE_VERIFY_BOUNDARY}: {label} must not traverse a symlink, junction, or reparse point"
                )
        except FileNotFoundError as exc:
            raise DurablePromotionError(
                f"{DURABLE_VERIFY_BOUNDARY}: {label} is missing or unavailable"
            ) from exc
        except OSError as exc:
            raise DurablePromotionError(
                f"{DURABLE_VERIFY_BOUNDARY}: {label} cannot be inspected safely"
            ) from exc


def _validated_durable_root(
    durable_root: str | os.PathLike[str], forbidden_roots: Iterable[str | os.PathLike[str]]
) -> tuple[Path, Path]:
    lexical = Path(durable_root).expanduser()
    if not lexical.is_absolute():
        raise DurablePromotionError(f"{DURABLE_VERIFY_BOUNDARY}: durable root must be absolute")
    lexical = Path(os.path.abspath(lexical))
    _assert_no_reparse_components(lexical, label="durable root")
    try:
        resolved = lexical.resolve(strict=True)
        metadata = resolved.stat()
    except (OSError, RuntimeError) as exc:
        raise DurablePromotionError(
            f"{DURABLE_VERIFY_BOUNDARY}: durable root is missing or unavailable"
        ) from exc
    if not stat.S_ISDIR(metadata.st_mode):
        raise DurablePromotionError(
            f"{DURABLE_VERIFY_FILE_TYPE}: durable root must be a real directory"
        )
    for forbidden in forbidden_roots:
        candidate = Path(forbidden).expanduser()
        if not candidate.is_absolute():
            raise DurablePromotionError(
                f"{DURABLE_VERIFY_BOUNDARY}: forbidden roots must be absolute"
            )
        if paths_overlap(resolved, candidate):
            raise DurablePromotionError(
                f"{DURABLE_VERIFY_BOUNDARY}: durable root overlaps a forbidden non-durable root"
            )
    return lexical, resolved


def _snapshot_durable_file(
    raw_path: str | os.PathLike[str],
    *,
    lexical_root: Path,
    resolved_root: Path,
    label: str,
) -> tuple[Path, Path, tuple[int, int, int, int, int]]:
    lexical = Path(raw_path).expanduser()
    if not lexical.is_absolute():
        raise DurablePromotionError(f"{DURABLE_VERIFY_BOUNDARY}: {label} must be absolute")
    lexical = Path(os.path.abspath(lexical))
    try:
        lexical.relative_to(lexical_root)
    except ValueError as exc:
        raise DurablePromotionError(
            f"{DURABLE_VERIFY_BOUNDARY}: {label} must stay below the declared durable root"
        ) from exc
    _assert_no_reparse_components(lexical, label=label)
    try:
        resolved = lexical.resolve(strict=True)
        resolved.relative_to(resolved_root)
        metadata = lexical.lstat()
    except ValueError as exc:
        raise DurablePromotionError(
            f"{DURABLE_VERIFY_BOUNDARY}: {label} resolves outside the declared durable root"
        ) from exc
    except (OSError, RuntimeError) as exc:
        raise DurablePromotionError(
            f"{DURABLE_VERIFY_BOUNDARY}: {label} is missing or unavailable"
        ) from exc
    if _reparse_or_symlink(lexical) or not stat.S_ISREG(metadata.st_mode):
        raise DurablePromotionError(
            f"{DURABLE_VERIFY_FILE_TYPE}: {label} must be a non-reparse regular file"
        )
    identity = (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
    )
    return lexical, resolved, identity


def _read_durable_file(
    raw_path: str | os.PathLike[str],
    *,
    lexical_root: Path,
    resolved_root: Path,
    label: str,
) -> _DurableFileRead:
    lexical, resolved, identity = _snapshot_durable_file(
        raw_path,
        lexical_root=lexical_root,
        resolved_root=resolved_root,
        label=label,
    )
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open(resolved, flags)
        opened = os.fstat(descriptor)
        opened_identity = (
            opened.st_dev,
            opened.st_ino,
            opened.st_mode,
            opened.st_size,
            opened.st_mtime_ns,
        )
        if opened_identity != identity or not stat.S_ISREG(opened.st_mode):
            raise DurablePromotionError(
                f"{DURABLE_VERIFY_CHANGED}: {label} changed before it could be opened"
            )
        with os.fdopen(descriptor, "rb", closefd=True) as handle:
            descriptor = -1
            payload = handle.read()
            closed = os.fstat(handle.fileno())
        closed_identity = (
            closed.st_dev,
            closed.st_ino,
            closed.st_mode,
            closed.st_size,
            closed.st_mtime_ns,
        )
        if closed_identity != identity:
            raise DurablePromotionError(
                f"{DURABLE_VERIFY_CHANGED}: {label} changed while it was being read"
            )
    except DurablePromotionError:
        raise
    except OSError as exc:
        raise DurablePromotionError(
            f"{DURABLE_VERIFY_CHANGED}: {label} could not be opened and read safely"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    read = _DurableFileRead(
        lexical_path=lexical,
        resolved_path=resolved,
        identity=identity,
        payload=payload,
        sha256=hashlib.sha256(payload).hexdigest(),
    )
    _revalidate_durable_read(read, lexical_root=lexical_root, resolved_root=resolved_root, label=label)
    return read


def _revalidate_durable_read(
    read: _DurableFileRead, *, lexical_root: Path, resolved_root: Path, label: str
) -> None:
    lexical, resolved, identity = _snapshot_durable_file(
        read.lexical_path,
        lexical_root=lexical_root,
        resolved_root=resolved_root,
        label=label,
    )
    if lexical != read.lexical_path or resolved != read.resolved_path or identity != read.identity:
        raise DurablePromotionError(
            f"{DURABLE_VERIFY_CHANGED}: {label} changed during durable verification"
        )


def promote_runtime_artifact(
    runtime_artifact: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    *,
    runtime_root: str | os.PathLike[str],
    expected_sha256: str,
) -> PromotedArtifact:
    """Copy, fsync, hash, and atomically install one runtime artifact."""

    promoted, _ = _promote_runtime_artifact_with_identity(
        runtime_artifact,
        destination,
        runtime_root=runtime_root,
        expected_sha256=expected_sha256,
    )
    return promoted


def _promote_runtime_artifact_with_identity(
    runtime_artifact: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    *,
    runtime_root: str | os.PathLike[str],
    expected_sha256: str,
) -> tuple[PromotedArtifact, tuple[int, int]]:
    """Internal promotion variant retaining the installed inode identity."""

    try:
        root = validate_runtime_location(runtime_root, durable_roots=(Path(destination).parent,))
    except RuntimeBoundaryError as exc:
        raise DurablePromotionError(str(exc)) from exc
    source = _contained_regular_file(Path(runtime_artifact), root, label="runtime artifact")
    target = _destination(destination, root)
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise DurablePromotionError("expected producer hash must be a lowercase SHA-256")
    try:
        int(expected_sha256, 16)
    except ValueError as exc:
        raise DurablePromotionError("expected producer hash must be a lowercase SHA-256") from exc
    if expected_sha256.lower() != expected_sha256:
        raise DurablePromotionError("expected producer hash must be a lowercase SHA-256")

    def chunks():
        with source.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                yield chunk

    staging, observed = _stage_bytes(target, chunks())
    staging_identity = _file_identity(staging)
    if observed != expected_sha256:
        _discard_staging(staging, staging_identity, observed)
        raise DurablePromotionError("runtime artifact hash does not match the producer declaration")
    identity: tuple[int, int] | None = None
    try:
        identity = _atomic_install(staging, target, expected_sha256)
        metadata = target.stat(follow_symlinks=False)
        if (metadata.st_dev, metadata.st_ino) != identity or file_sha256(target) != expected_sha256:
            if not _remove_installed(target, identity, expected_sha256):
                raise _cleanup_withheld_error((target,))
            raise DurablePromotionError("promoted artifact failed post-publish hash verification")
    except OSError as exc:
        if identity is not None and not _remove_installed(target, identity, expected_sha256):
            raise _cleanup_withheld_error((target,)) from exc
        raise DurablePromotionError("promoted artifact could not be verified after publication") from exc
    finally:
        _discard_staging(staging, staging_identity, observed)
    return PromotedArtifact(target, expected_sha256, metadata.st_size), identity


def _receipt_from_payload(payload: Mapping[str, Any]) -> DurableReceipt:
    try:
        return DurableReceipt.from_dict(payload)
    except (TypeError, ValueError) as exc:
        raise DurablePromotionError(f"invalid durable receipt: {exc}") from exc


def promote_result_with_receipt(
    runtime_artifact: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    receipt: DurableReceipt,
    receipt_destination: str | os.PathLike[str],
    *,
    runtime_root: str | os.PathLike[str],
) -> tuple[PromotedArtifact, PromotedArtifact]:
    """Promote a producer/claim-bound result and its normalized compact receipt."""

    if not isinstance(receipt, DurableReceipt):
        raise DurablePromotionError("receipt must be a normalized DurableReceipt")
    artifact_digest = receipt.durable_artifact["sha256"]
    promoted, promoted_identity = _promote_runtime_artifact_with_identity(
        runtime_artifact,
        destination,
        runtime_root=runtime_root,
        expected_sha256=artifact_digest,
    )
    receipt_target: Path | None = None
    staging: Path | None = None
    staging_identity: tuple[int, int] | None = None
    receipt_identity: tuple[int, int] | None = None
    digest: str | None = None
    payload = receipt.canonical_bytes()
    try:
        receipt_target = _destination(receipt_destination, Path(runtime_root).expanduser().resolve())
        staging, digest = _stage_bytes(receipt_target, (payload,))
        staging_identity = _file_identity(staging)
        receipt_identity = _atomic_install(staging, receipt_target, digest)
        if (
            _file_identity(receipt_target) != receipt_identity
            or file_sha256(receipt_target) != digest
            or _file_identity(promoted.path) != promoted_identity
            or file_sha256(promoted.path) != artifact_digest
        ):
            raise DurablePromotionError("promoted result changed during receipt publication")
    except BaseException as exc:
        cleanup_withheld: list[Path] = []
        if receipt_target is not None and receipt_identity is not None and digest is not None:
            if not _remove_installed(receipt_target, receipt_identity, digest):
                cleanup_withheld.append(receipt_target)
        if not _remove_installed(promoted.path, promoted_identity, artifact_digest):
            cleanup_withheld.append(promoted.path)
        if cleanup_withheld:
            raise _cleanup_withheld_error(cleanup_withheld) from exc
        raise
    finally:
        _discard_staging(staging, staging_identity, digest)
    assert receipt_target is not None and digest is not None
    return promoted, PromotedArtifact(receipt_target, digest, len(payload))


def verify_promoted_result(
    artifact_path: str | os.PathLike[str],
    receipt_path: str | os.PathLike[str],
    *,
    durable_root: str | os.PathLike[str],
    forbidden_roots: Iterable[str | os.PathLike[str]] = (),
) -> DurableReceipt:
    """Verify durable bytes and lineage below one reparse-free declared root.

    ``forbidden_roots`` names disposable runtime, snapshot, or temporary roots;
    it is boundary metadata only and is never read, so verification continues to
    work after those trees have been deleted.
    """

    lexical_root, resolved_root = _validated_durable_root(durable_root, forbidden_roots)
    receipt_read = _read_durable_file(
        receipt_path,
        lexical_root=lexical_root,
        resolved_root=resolved_root,
        label="durable receipt",
    )
    try:
        payload = json.loads(receipt_read.payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise DurablePromotionError("durable receipt is missing or unreadable") from exc
    if not isinstance(payload, Mapping):
        raise DurablePromotionError("durable receipt must be a JSON object")
    receipt = _receipt_from_payload(payload)
    if canonical_serialize(receipt) != canonical_serialize(payload):
        raise DurablePromotionError("durable receipt is not canonical or contains unsupported fields")
    artifact_read = _read_durable_file(
        artifact_path,
        lexical_root=lexical_root,
        resolved_root=resolved_root,
        label="durable artifact",
    )
    if artifact_read.sha256 != receipt.durable_artifact["sha256"]:
        raise DurablePromotionError("durable artifact hash does not match its receipt")
    # Detect a parent/file swap that occurred while the peer was being read.
    _revalidate_durable_read(
        receipt_read,
        lexical_root=lexical_root,
        resolved_root=resolved_root,
        label="durable receipt",
    )
    _revalidate_durable_read(
        artifact_read,
        lexical_root=lexical_root,
        resolved_root=resolved_root,
        label="durable artifact",
    )
    return receipt


__all__ = [
    "ATOMIC_NO_CLOBBER_UNAVAILABLE",
    "DURABLE_DESTINATION_EXISTS",
    "DURABLE_MANUAL_CLEANUP_REQUIRED",
    "DURABLE_PRIVATE_STAGE_RETAINED",
    "DURABLE_VERIFY_BOUNDARY",
    "DURABLE_VERIFY_CHANGED",
    "DURABLE_VERIFY_FILE_TYPE",
    "DurablePromotionError",
    "PromotedArtifact",
    "file_sha256",
    "promote_result_with_receipt",
    "promote_runtime_artifact",
    "verify_promoted_result",
]
