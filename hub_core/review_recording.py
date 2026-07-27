"""Storage-only recording of validated human-review receipts.

This module deliberately does not issue or verify reviewer authority and does
not know about runtime renders or promotion.  It accepts an already validated
receipt, serializes it canonically, and publishes those bytes once below a
caller-owned evidence root.
"""

from __future__ import annotations

import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .atomic_no_clobber import AtomicNoClobberUnavailable, atomic_no_clobber_move
from .human_review_receipt import (
    HumanReviewReceiptError,
    canonical_human_review_receipt_bytes,
    parse_human_review_receipt_bytes,
    validate_human_review_receipt,
)
from .structure_path_security import (
    capture_directory_witness,
    capture_project_root,
    lease_directory_witness,
)


class ReviewRecordingError(RuntimeError):
    """Raised when a review receipt cannot be recorded safely."""


class ReviewRecordingAuthorizationError(ReviewRecordingError):
    """Raised when the caller has not explicitly enabled this write."""


class ReviewRecordExistsError(ReviewRecordingError):
    """Raised when the append-only destination already exists."""


@dataclass(frozen=True, slots=True)
class ReviewRecordingResult:
    """Small, immutable, runtime-independent publication result."""

    relative_path: str
    receipt_id: str
    canonical_sha256: str
    size_bytes: int

    @property
    def record_relative_path(self) -> str:
        """Compatibility spelling for callers that call this a record path."""

        return self.relative_path


_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def record_human_review_receipt(
    receipt_or_bytes: Mapping[str, Any] | bytes | bytearray | memoryview,
    *,
    evidence_root: str | os.PathLike[str],
    relative_path: str | os.PathLike[str],
    write_authorized: bool,
) -> ReviewRecordingResult:
    """Publish one canonical human-review receipt below ``evidence_root``.

    ``write_authorized`` is an explicit caller-side write gate.  A mapping is
    schema-validated; byte input must already be the exact canonical encoding
    emitted by :func:`canonical_human_review_receipt_bytes`.  No existing
    destination is replaced, including in a concurrent publication race.
    """

    if write_authorized is not True:
        raise ReviewRecordingAuthorizationError("review recording writes are disabled")

    receipt, canonical_bytes = _validated_canonical_receipt(receipt_or_bytes)
    relative = _canonical_relative_path(relative_path)
    root = _prepare_evidence_root(evidence_root)
    # The path-security helpers deliberately raise their own low-level
    # ``RuntimeError``/``ValueError``/``OSError`` failures when a witnessed
    # directory changes, becomes unsafe, or cannot be leased.  Keep those
    # checks fail-closed, but expose one public error type to callers of this
    # storage API while preserving the helper's diagnostic message.
    try:
        root_identity = capture_project_root(root)
        parent_relative = PurePosixPath(relative).parent.as_posix()
        witness = capture_directory_witness(
            root,
            parent_relative,
            root_identity=root_identity,
            create=True,
        )
        destination = root.joinpath(*PurePosixPath(relative).parts)

        with lease_directory_witness(witness):
            _reject_existing_destination(destination)
            _append_no_clobber(destination, canonical_bytes)
    except ReviewRecordingError:
        raise
    except (RuntimeError, ValueError, OSError) as exc:
        raise ReviewRecordingError(str(exc)) from exc

    # Keep the returned DTO independent of the absolute evidence-root path.
    return ReviewRecordingResult(
        relative_path=relative,
        receipt_id=receipt["receipt_id"],
        canonical_sha256=receipt["integrity"]["canonical_sha256"],
        size_bytes=len(canonical_bytes),
    )


def _validated_canonical_receipt(
    receipt_or_bytes: Mapping[str, Any] | bytes | bytearray | memoryview,
) -> tuple[dict[str, Any], bytes]:
    try:
        if isinstance(receipt_or_bytes, (bytes, bytearray, memoryview)):
            raw = bytes(receipt_or_bytes)
            receipt = parse_human_review_receipt_bytes(raw)
            canonical = canonical_human_review_receipt_bytes(receipt)
            if raw != canonical:
                raise ReviewRecordingError("human review receipt bytes must be canonical")
        elif isinstance(receipt_or_bytes, Mapping):
            receipt = validate_human_review_receipt(receipt_or_bytes)
            canonical = canonical_human_review_receipt_bytes(receipt)
        else:
            raise ReviewRecordingError("human review receipt must be a mapping or canonical bytes")
    except ReviewRecordingError:
        raise
    except (HumanReviewReceiptError, TypeError, ValueError, AttributeError) as exc:
        raise ReviewRecordingError(f"malformed human review receipt: {exc}") from exc
    return receipt, canonical


def _canonical_relative_path(value: str | os.PathLike[str]) -> str:
    try:
        text = os.fspath(value)
    except TypeError as exc:
        raise ReviewRecordingError("review record destination must be a relative path") from exc
    if not isinstance(text, str) or not text:
        raise ReviewRecordingError("review record destination must be a non-empty relative path")
    relative = PurePosixPath(text)
    if (
        relative.is_absolute()
        or relative.as_posix() != text
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or any(":" in part for part in relative.parts)
        or "\\" in text
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in text)
    ):
        raise ReviewRecordingError("review record destination must be canonical and evidence-root relative")
    return relative.as_posix()


def _is_reparse_or_symlink(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    return path.is_symlink() or bool(getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT)


def _prepare_evidence_root(value: str | os.PathLike[str]) -> Path:
    try:
        root = Path(value).expanduser()
    except (TypeError, ValueError) as exc:
        raise ReviewRecordingError("evidence root must be an absolute directory") from exc
    if not root.is_absolute() or any(part in {".", ".."} for part in root.parts):
        raise ReviewRecordingError("evidence root must be an absolute directory")

    # Bind/create every component without following a symlink or reparse point.
    current = Path(root.anchor)
    for part in root.parts[1:]:
        current /= part
        try:
            exists = os.path.lexists(current)
        except OSError as exc:
            raise ReviewRecordingError("evidence root is unavailable") from exc
        if exists:
            if _is_reparse_or_symlink(current):
                raise ReviewRecordingError("evidence root must not traverse a symlink or reparse point")
            try:
                if not current.is_dir():
                    raise ReviewRecordingError("evidence root must be a directory")
            except OSError as exc:
                raise ReviewRecordingError("evidence root is unavailable") from exc
            continue
        try:
            current.mkdir()
        except FileExistsError:
            pass
        except OSError as exc:
            raise ReviewRecordingError("evidence root is not writable") from exc
        if _is_reparse_or_symlink(current) or not current.is_dir():
            raise ReviewRecordingError("evidence root must not traverse a symlink or reparse point")
    try:
        if _is_reparse_or_symlink(root) or not root.is_dir():
            raise ReviewRecordingError("evidence root must be a non-symlink directory")
    except OSError as exc:
        raise ReviewRecordingError("evidence root is unavailable") from exc
    return root


def _reject_existing_destination(destination: Path) -> None:
    try:
        if not os.path.lexists(destination):
            return
    except OSError as exc:
        raise ReviewRecordingError("review record destination is unavailable") from exc
    if _is_reparse_or_symlink(destination):
        raise ReviewRecordingError("review record destination must not be a symlink or reparse point")
    raise ReviewRecordExistsError("review record destination already exists")


def _append_no_clobber(destination: Path, payload: bytes) -> None:
    stage = destination.parent / f".{destination.name}.{os.getpid()}.{secrets.token_hex(12)}.tmp"
    descriptor = -1
    try:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
        descriptor = os.open(stage, flags, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            atomic_no_clobber_move(stage, destination)
        except FileExistsError as exc:
            raise ReviewRecordExistsError("review record destination already exists") from exc
        except AtomicNoClobberUnavailable as exc:
            raise ReviewRecordingError("review record publication is unavailable") from exc
        except PermissionError as exc:
            raise ReviewRecordingError("review record publication was denied") from exc
        except OSError as exc:
            raise ReviewRecordingError("review record publication failed") from exc
    except ReviewRecordingError:
        raise
    except FileExistsError as exc:
        # A pre-existing private stage name is not a publication race; retrying
        # with a fresh random name is unnecessary and could hide tampering.
        raise ReviewRecordingError("review record staging path already exists") from exc
    except OSError as exc:
        raise ReviewRecordingError("review record staging failed") from exc
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            if os.path.lexists(stage):
                stage.unlink()
        except OSError:
            pass


__all__ = [
    "ReviewRecordExistsError",
    "ReviewRecordingAuthorizationError",
    "ReviewRecordingError",
    "ReviewRecordingResult",
    "record_human_review_receipt",
]
