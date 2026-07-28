"""Runtime-independent persistence for a validated promotion-gate receipt.

The promotion gate is evaluated without side effects.  The admission
transaction freezes its validated gate receipt below the project's evidence
role before invoking native durable result promotion, then removes that exact
receipt if promotion rejects a raced destination.  It intentionally shares
the append-only/no-clobber path discipline with human review recording while
remaining independent of the durable promotion primitive.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .atomic_no_clobber import AtomicNoClobberUnavailable
from .promotion_gate_receipt import (
    canonical_promotion_gate_receipt_bytes,
    validate_promotion_gate_receipt,
)
from .review_recording import (
    ReviewRecordExistsError,
    _append_no_clobber,
    _canonical_relative_path,
    _prepare_evidence_root,
    _reject_existing_destination,
)
from .structure_path_security import (
    capture_directory_witness,
    capture_project_root,
    delete_file_by_identity,
    lease_directory_witness,
)


class PromotionGateRecordingError(RuntimeError):
    """A validated promotion-gate receipt could not be frozen safely."""


class PromotionGateRecordExistsError(PromotionGateRecordingError):
    """The append-only promotion-gate destination already exists."""


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate keys while decoding persisted receipt JSON."""

    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_non_finite_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r}")


@dataclass(frozen=True, slots=True)
class PromotionGateRecordingResult:
    """Runtime-independent identity of a frozen promotion-gate receipt."""

    relative_path: str
    receipt_id: str
    canonical_sha256: str
    size_bytes: int
    # Private ownership witness used only for a failed-promotion rollback. It
    # is excluded from repr/equality so the public result remains runtime
    # independent while the transaction retains exact inode ownership.
    _created_identity: tuple[int, int] | None = field(default=None, repr=False, compare=False)


def record_promotion_gate_receipt(
    receipt: Mapping[str, Any],
    *,
    evidence_root: str | os.PathLike[str],
    relative_path: str | os.PathLike[str],
) -> PromotionGateRecordingResult:
    """Freeze one canonical gate receipt below ``evidence_root``.

    This function is append-only.  It validates the closed gate DTO before
    touching the destination and never replaces a competing inode.
    """

    try:
        normalized = validate_promotion_gate_receipt(receipt)
        payload = canonical_promotion_gate_receipt_bytes(normalized)
        relative = _canonical_relative_path(relative_path)
        root = _prepare_evidence_root(evidence_root)
        root_identity = capture_project_root(root)
        parent_relative = PurePosixPath(relative).parent.as_posix()
        witness = capture_directory_witness(root, parent_relative, root_identity=root_identity, create=True)
        destination = root.joinpath(*PurePosixPath(relative).parts)
        with lease_directory_witness(witness):
            _reject_existing_destination(destination)
            _append_no_clobber(destination, payload)
            metadata = destination.stat(follow_symlinks=False)
            created_identity = (metadata.st_dev, metadata.st_ino)
    except PromotionGateRecordingError:
        raise
    except ReviewRecordExistsError as exc:
        raise PromotionGateRecordExistsError(str(exc)) from exc
    except (TypeError, ValueError, RuntimeError, OSError, AtomicNoClobberUnavailable) as exc:
        raise PromotionGateRecordingError(str(exc)) from exc
    return PromotionGateRecordingResult(
        relative_path=relative,
        receipt_id=normalized["receipt_id"],
        canonical_sha256=normalized["integrity"]["canonical_sha256"],
        size_bytes=len(payload),
        _created_identity=created_identity,
    )


def discard_promotion_gate_receipt(
    result: PromotionGateRecordingResult,
    *,
    evidence_root: str | os.PathLike[str],
) -> None:
    """Remove only the exact gate receipt created by this transaction.

    This is used when native durable promotion rejects a raced destination
    after the gate receipt was frozen.  A replacement inode is never removed.
    """

    if result._created_identity is None:
        raise PromotionGateRecordingError("promotion gate receipt ownership witness is unavailable")
    try:
        root = Path(evidence_root).expanduser()
    except (TypeError, ValueError) as exc:
        raise PromotionGateRecordingError("promotion gate evidence root is unavailable") from exc
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise PromotionGateRecordingError("promotion gate evidence root changed before rollback")
    relative = _canonical_relative_path(result.relative_path)
    parent_relative = PurePosixPath(relative).parent.as_posix()
    try:
        root_identity = capture_project_root(root)
        witness = capture_directory_witness(root, parent_relative, root_identity=root_identity, create=False)
        destination = root.joinpath(*PurePosixPath(relative).parts)
        with lease_directory_witness(witness):
            metadata = destination.lstat()
            if destination.is_symlink() or not destination.is_file():
                raise PromotionGateRecordingError("promotion gate receipt destination changed before rollback")
            current = (metadata.st_dev, metadata.st_ino)
            if current != result._created_identity:
                raise PromotionGateRecordingError("promotion gate receipt ownership changed before rollback")
            current_bytes = destination.read_bytes()
            try:
                parsed = json.loads(
                    current_bytes.decode("utf-8"),
                    object_pairs_hook=_reject_duplicate_json_keys,
                    parse_constant=_reject_non_finite_json_constant,
                )
                if not isinstance(parsed, Mapping):
                    raise ValueError("receipt JSON root must be an object")
                validated = validate_promotion_gate_receipt(parsed)
                canonical_bytes = canonical_promotion_gate_receipt_bytes(validated)
            except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
                raise PromotionGateRecordingError(
                    "promotion gate receipt ownership changed before rollback"
                ) from exc
            if (
                canonical_bytes != current_bytes
                or validated["integrity"]["canonical_sha256"] != result.canonical_sha256
            ):
                raise PromotionGateRecordingError("promotion gate receipt ownership changed before rollback")
            full_bytes_sha256 = hashlib.sha256(current_bytes).hexdigest()
            if not delete_file_by_identity(destination, result._created_identity, full_bytes_sha256):
                raise PromotionGateRecordingError(
                    "promotion gate receipt rollback ownership is ambiguous; receipt retained for review"
                )
    except FileNotFoundError:
        return
    except PromotionGateRecordingError:
        raise
    except OSError as exc:
        raise PromotionGateRecordingError("promotion gate receipt rollback failed") from exc


__all__ = [
    "PromotionGateRecordExistsError",
    "PromotionGateRecordingError",
    "PromotionGateRecordingResult",
    "discard_promotion_gate_receipt",
    "record_promotion_gate_receipt",
]
