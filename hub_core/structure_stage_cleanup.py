"""Ownership-safe cleanup helpers for structure-apply private stages."""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from typing import Any

from .structure_path_security import (
    DirectoryWitness,
    delete_file_by_identity,
    lease_directory_witness,
)

STRUCTURE_PRIVATE_STAGE_RETAINED = "FIGOPS_STRUCTURE_PRIVATE_STAGE_RETAINED"


def discard_private_stage(
    stage: Path,
    expected_identity: tuple[int, int] | None = None,
    parent_witness: DirectoryWitness | None = None,
) -> None:
    """Best-effort cleanup after publication may have consumed the stage."""

    try:
        lease = lease_directory_witness(parent_witness) if parent_witness is not None else nullcontext()
        with lease:
            if expected_identity is not None:
                delete_file_by_identity(stage, expected_identity)
    except (OSError, RuntimeError):
        return


def discard_owned_prepublication_stage(stage: Path) -> None:
    """Remove an exclusive-create stage while its private name is transaction-owned."""

    try:
        stage.unlink()
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"{STRUCTURE_PRIVATE_STAGE_RETAINED}: unpublished stage ownership became ambiguous"
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            f"{STRUCTURE_PRIVATE_STAGE_RETAINED}: unpublished stage could not be removed"
        ) from exc


def release_directory_leases(leases: list[Any]) -> None:
    """Release held witnesses in reverse acquisition order without masking failure."""

    for lease in reversed(leases):
        try:
            lease.__exit__(None, None, None)
        except (OSError, RuntimeError):
            pass
    leases.clear()
