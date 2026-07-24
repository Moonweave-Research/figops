"""Fail-closed transaction executor for reviewed structure plans."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

from .atomic_no_clobber import (
    ATOMIC_NO_CLOBBER_UNAVAILABLE,
    AtomicNoClobberUnavailable,
    atomic_no_clobber_move,
)
from .structure_apply_preflight import (
    materialize_parent_witness,
    prepare_structure_entries,
)
from .structure_path_security import (
    DirectoryWitness,
    assert_directory_witness,
    assert_opened_path,
    assert_project_root,
    capture_directory_witness,
    capture_project_root,
    delete_file_by_identity,
    hash_handle,
    lease_directory_witness,
    open_bound_source,
    source_identity,
)
from .structure_plan import PLAN_VERSION, validate_confirmation_token
from .structure_role_binding import config_mapping, validate_role_destination_bindings
from .structure_stage_cleanup import (
    discard_owned_prepublication_stage,
    discard_private_stage,
    release_directory_leases,
)

_config_mapping = config_mapping
_validate_role_destination_bindings = validate_role_destination_bindings
_discard_owned_prepublication_stage = discard_owned_prepublication_stage
_discard_private_stage = discard_private_stage
_release_directory_leases = release_directory_leases
STRUCTURE_MANUAL_CLEANUP_REQUIRED = "FIGOPS_STRUCTURE_MANUAL_CLEANUP_REQUIRED"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_parent(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _file_identity(path: Path) -> tuple[int, int]:
    """Return the stable identity used to avoid deleting a competing file."""

    metadata = path.stat(follow_symlinks=False)
    return metadata.st_dev, metadata.st_ino


def _publish_no_clobber(
    stage: Path,
    destination: Path,
    *,
    expected_stage_identity: tuple[int, int] | None = None,
    expected_hash: str | None = None,
) -> tuple[int, int]:
    """Atomically publish a sibling stage only when the destination is absent.

    The platform primitive consumes the private stage name on success. This
    avoids both an overwrite race and a writable hard-link alias.
    """

    if stage.parent.resolve() != destination.parent.resolve():
        raise RuntimeError("Structure staging must use the destination filesystem.")
    identity = _file_identity(stage)
    if expected_stage_identity is not None and identity != expected_stage_identity:
        raise RuntimeError("Private structure stage identity changed before publish.")
    try:
        atomic_no_clobber_move(stage, destination)
    except FileExistsError:
        _discard_owned_prepublication_stage(stage)
        raise FileExistsError(f"Destination appeared during apply: {destination.name}") from None
    except AtomicNoClobberUnavailable as exc:
        _discard_owned_prepublication_stage(stage)
        raise RuntimeError(
            f"{ATOMIC_NO_CLOBBER_UNAVAILABLE}: atomic no-clobber publish failed: {destination.name}"
        ) from exc
    except PermissionError:
        _discard_owned_prepublication_stage(stage)
        raise
    try:
        published_identity = _file_identity(destination)
    except OSError as exc:
        removed = _remove_if_identity(destination, identity, expected_hash)
        suffix = "" if removed else f"; {STRUCTURE_MANUAL_CLEANUP_REQUIRED}: cleanup withheld"
        raise RuntimeError(f"Published structure path changed during apply{suffix}.") from exc
    if published_identity != identity or os.path.lexists(stage):
        removed = _remove_if_identity(destination, identity, expected_hash)
        suffix = "" if removed else f"; {STRUCTURE_MANUAL_CLEANUP_REQUIRED}: cleanup withheld"
        raise RuntimeError(f"Structure parent or stage identity changed during publish{suffix}.")
    try:
        installed = destination.stat(follow_symlinks=False)
        installed_identity = (installed.st_dev, installed.st_ino)
        installed_hash = _sha256(destination)
    except OSError as exc:
        removed = _remove_if_identity(destination, identity, expected_hash)
        suffix = "" if removed else f"; {STRUCTURE_MANUAL_CLEANUP_REQUIRED}: cleanup withheld"
        raise RuntimeError(
            f"Published structure destination could not be verified{suffix}."
        ) from exc
    if (
        installed_identity != identity
        or installed.st_nlink != 1
        or (expected_hash is not None and installed_hash != expected_hash)
    ):
        removed = _remove_if_identity(destination, identity, expected_hash)
        suffix = "" if removed else f"; {STRUCTURE_MANUAL_CLEANUP_REQUIRED}: cleanup withheld"
        raise RuntimeError(
            f"Published structure destination retained an alias or changed after publish{suffix}."
        )
    _fsync_parent(destination)
    return identity


def _remove_if_owned(path: Path, expected_hash: str, identity: tuple[int, int]) -> bool:
    """Best-effort rollback that cannot unlink a replacement at the same path."""

    try:
        if not os.path.lexists(path):
            return True
        if (
            path.is_file()
            and not path.is_symlink()
            and _file_identity(path) == identity
            and _sha256(path) == expected_hash
        ):
            return delete_file_by_identity(path, identity, expected_hash)
    except OSError:
        return False
    return False


def _remove_if_identity(
    path: Path,
    identity: tuple[int, int],
    expected_hash: str | None = None,
) -> bool:
    """Remove only the exact namespace identity installed by this transaction."""

    if expected_hash is None:
        return False
    try:
        if not os.path.lexists(path):
            return True
        if path.is_file() and not path.is_symlink():
            return delete_file_by_identity(path, identity, expected_hash)
    except OSError:
        return False
    return False


def _stage_copy(
    source_handle,
    destination: Path,
    expected_hash: str,
    *,
    root: Path,
    parent_witness: DirectoryWitness,
) -> tuple[Path, tuple[int, int]]:
    stage = destination.with_name(f".{destination.name}.figops-{uuid.uuid4().hex}.tmp")
    descriptor = -1
    stage_identity: tuple[int, int] | None = None
    try:
        assert_directory_witness(parent_witness)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        descriptor = os.open(stage, flags, 0o600)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise RuntimeError("Structure stage is not a regular file.")
        stage_identity = (opened.st_dev, opened.st_ino)
        assert_opened_path(descriptor, stage, root)
        assert_directory_witness(parent_witness)
        with os.fdopen(descriptor, "wb", closefd=True) as writer:
            descriptor = -1
            shutil.copyfileobj(source_handle, writer, length=1024 * 1024)
            writer.flush()
            os.fsync(writer.fileno())
        assert_directory_witness(parent_witness)
        if _sha256(stage) != expected_hash:
            raise RuntimeError(f"Staged copy hash mismatch: {destination.name}")
        return stage, _file_identity(stage)
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        if stage_identity is not None:
            _discard_owned_prepublication_stage(stage)
        raise


def _stage_bytes(
    content: bytes,
    destination: Path,
    expected_hash: str,
    *,
    root: Path,
    parent_witness: DirectoryWitness,
) -> tuple[Path, tuple[int, int]]:
    stage = destination.with_name(f".{destination.name}.figops-{uuid.uuid4().hex}.tmp")
    descriptor = -1
    stage_identity: tuple[int, int] | None = None
    try:
        assert_directory_witness(parent_witness)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        descriptor = os.open(stage, flags, 0o600)
        opened = os.fstat(descriptor)
        stage_identity = (opened.st_dev, opened.st_ino)
        assert_opened_path(descriptor, stage, root)
        assert_directory_witness(parent_witness)
        with os.fdopen(descriptor, "wb", closefd=True) as writer:
            descriptor = -1
            writer.write(content)
            writer.flush()
            os.fsync(writer.fileno())
        assert_directory_witness(parent_witness)
        if _sha256(stage) != expected_hash:
            raise RuntimeError("Staged config hash mismatch.")
        return stage, _file_identity(stage)
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        if stage_identity is not None:
            _discard_owned_prepublication_stage(stage)
        raise


def _restore_guard_no_clobber(guard: Path, config_path: Path, expected_hash: str) -> None:
    """Restore a renamed config only into an absent name, preserving competitors."""

    if not guard.is_file() or guard.is_symlink() or _sha256(guard) != expected_hash:
        return
    guard_identity = _file_identity(guard)
    try:
        # A config guard contains the original (and potentially concurrently
        # modified) user file. Unlike an unpublished stage, it must never be
        # discarded when the public name is occupied or the native primitive
        # is unavailable.
        atomic_no_clobber_move(guard, config_path)
    except (FileExistsError, AtomicNoClobberUnavailable, OSError):
        return
    try:
        if _file_identity(config_path) != guard_identity or _sha256(config_path) != expected_hash:
            return
        _fsync_parent(config_path.parent)
    except OSError:
        return


def _publish_config_compare_and_swap_leased(
    *,
    config_path: Path,
    config_stage: Path,
    planned_hash: str,
    replacement_hash: str,
    root: Path,
    root_identity: tuple[int, int, int],
    parent_witness: DirectoryWitness,
) -> tuple[tuple[int, int], Path, tuple[int, int]]:
    """Replace the reviewed config without ever overwriting a competing name.

    Renaming the current name to a private guard first is the compare-and-swap
    point. If a third party won the race, its bytes are retained under the
    guard and restored only when the public name is absent. The new config is
    then installed with the same consuming atomic no-replace move used for
    copied artifacts.
    """

    assert_project_root(root, root_identity)
    assert_directory_witness(parent_witness)
    expected_identity = _file_identity(config_path)
    if _sha256(config_path) != planned_hash:
        raise RuntimeError("project_config.yaml changed before compare-and-swap.")
    guard = config_path.with_name(f".{config_path.name}.figops-{uuid.uuid4().hex}.cas")
    if os.path.lexists(guard):
        raise FileExistsError("Private config CAS guard already exists.")
    try:
        # On Windows os.rename is a no-clobber namespace operation. On POSIX
        # the cryptographically random absent guard makes collision infeasible;
        # it is verified immediately before any guarded bytes are discarded.
        try:
            atomic_no_clobber_move(config_path, guard)
        except PermissionError as exc:
            raise RuntimeError(
                "project_config.yaml is held by an open handle; compare-and-swap cannot proceed."
            ) from exc
        assert_directory_witness(parent_witness)
        if _file_identity(guard) != expected_identity or _sha256(guard) != planned_hash:
            _restore_guard_no_clobber(guard, config_path, _sha256(guard))
            raise RuntimeError("project_config.yaml changed at compare-and-swap.")
        try:
            replacement_identity = _publish_no_clobber(
                config_stage,
                config_path,
                expected_stage_identity=_file_identity(config_stage),
                expected_hash=replacement_hash,
            )
        except BaseException:
            _restore_guard_no_clobber(guard, config_path, planned_hash)
            raise
        if _sha256(config_path) != replacement_hash:
            _remove_if_owned(config_path, replacement_hash, replacement_identity)
            _restore_guard_no_clobber(guard, config_path, planned_hash)
            raise RuntimeError("Published project config failed verification.")
        assert_directory_witness(parent_witness)
        return replacement_identity, guard, expected_identity
    except BaseException:
        if guard.exists() and not guard.is_symlink() and not config_path.exists():
            _restore_guard_no_clobber(guard, config_path, planned_hash)
        raise


def _publish_config_compare_and_swap(
    *,
    config_path: Path,
    config_stage: Path,
    planned_hash: str,
    replacement_hash: str,
    root: Path,
    root_identity: tuple[int, int, int],
    parent_witness: DirectoryWitness,
) -> tuple[tuple[int, int], Path, tuple[int, int]]:
    with lease_directory_witness(parent_witness):
        return _publish_config_compare_and_swap_leased(
            config_path=config_path,
            config_stage=config_stage,
            planned_hash=planned_hash,
            replacement_hash=replacement_hash,
            root=root,
            root_identity=root_identity,
            parent_witness=parent_witness,
        )


def _finalize_config_guard(
    *,
    guard: Path,
    guard_identity: tuple[int, int],
    planned_hash: str,
    config_path: Path,
    replacement_identity: tuple[int, int],
    replacement_hash: str,
    parent_witness: DirectoryWitness,
) -> None:
    """Commit only if the guarded original and published replacement are stable.

    The guard is intentionally retained as the durable rollback backup. A
    writer that already holds the original inode can therefore never have its
    bytes discarded by transaction cleanup.
    """

    with lease_directory_witness(parent_witness):
        try:
            current_guard_identity = _file_identity(guard)
            current_guard_hash = _sha256(guard)
        except OSError as exc:
            raise RuntimeError("Private config CAS guard disappeared before commit.") from exc
        if current_guard_identity != guard_identity or current_guard_hash != planned_hash:
            _remove_if_identity(config_path, replacement_identity, replacement_hash)
            _restore_guard_no_clobber(guard, config_path, current_guard_hash)
            raise RuntimeError("project_config.yaml changed through an open handle during apply.")
        if _file_identity(config_path) != replacement_identity or _sha256(config_path) != replacement_hash:
            raise RuntimeError("Published project config changed before transaction commit.")


def _rollback_config_no_clobber_leased(
    *,
    config_path: Path,
    replacement_hash: str,
    replacement_identity: tuple[int, int],
    original_guard: Path | None,
) -> tuple[bool, tuple[Path, ...]]:
    """Restore the original config without overwriting a concurrent writer."""

    tomb = config_path.with_name(f".{config_path.name}.figops-{uuid.uuid4().hex}.rollback")
    try:
        atomic_no_clobber_move(config_path, tomb)
    except (AtomicNoClobberUnavailable, OSError):
        retained = (config_path,)
        if original_guard is not None and os.path.lexists(original_guard):
            retained += (original_guard,)
        return False, retained
    try:
        if _file_identity(tomb) != replacement_identity or _sha256(tomb) != replacement_hash:
            _restore_guard_no_clobber(tomb, config_path, _sha256(tomb))
            retained = (tomb,) if os.path.lexists(tomb) else (config_path,)
            return False, retained
        restore_source = original_guard
        if (
            restore_source is None
            or not restore_source.is_file()
            or restore_source.is_symlink()
        ):
            _restore_guard_no_clobber(tomb, config_path, replacement_hash)
            retained = tuple(
                path
                for path in (tomb, original_guard)
                if path is not None and os.path.lexists(path)
            )
            return False, retained or (config_path,)
        restore_hash = _sha256(restore_source)
        restore_identity = _file_identity(restore_source)
        try:
            # The guard is user-owned original data, not a disposable stage.
            # A failed no-replace operation must preserve its private name.
            atomic_no_clobber_move(restore_source, config_path)
        except (FileExistsError, AtomicNoClobberUnavailable, OSError):
            # A competing config won the public name, or native no-replace is
            # unavailable. Preserve the guard and report every retained
            # transaction path after restoring the replacement when possible.
            if not config_path.exists():
                _restore_guard_no_clobber(tomb, config_path, replacement_hash)
            retained = tuple(
                path for path in (tomb, restore_source) if os.path.lexists(path)
            )
            if not os.path.lexists(tomb) and os.path.lexists(config_path):
                retained += (config_path,)
            return False, retained
        try:
            restored = config_path.stat(follow_symlinks=False)
            if (
                (restored.st_dev, restored.st_ino) != restore_identity
                or not stat.S_ISREG(restored.st_mode)
                or _sha256(config_path) != restore_hash
            ):
                return False, tuple(
                    path for path in (tomb, config_path) if os.path.lexists(path)
                )
            _fsync_parent(config_path)
        except OSError:
            return False, tuple(
                path for path in (tomb, config_path) if os.path.lexists(path)
            )
        if not delete_file_by_identity(tomb, replacement_identity, replacement_hash):
            return False, (tomb,)
        return True, ()
    except BaseException:
        if tomb.exists() and not tomb.is_symlink() and not config_path.exists():
            _restore_guard_no_clobber(tomb, config_path, replacement_hash)
        raise


def _rollback_config_no_clobber(
    *,
    config_path: Path,
    replacement_hash: str,
    replacement_identity: tuple[int, int],
    original_guard: Path | None,
    parent_witness: DirectoryWitness,
) -> tuple[bool, tuple[Path, ...]]:
    with lease_directory_witness(parent_witness):
        return _rollback_config_no_clobber_leased(
            config_path=config_path,
            replacement_hash=replacement_hash,
            replacement_identity=replacement_identity,
            original_guard=original_guard,
        )


def apply_structure_plan(
    plan: Mapping[str, Any],
    *,
    confirmation_token: str,
    pre_apply_verifier: Callable[[Path, Mapping[str, Any]], None] | None = None,
    post_apply_verifier: Callable[[Path, Mapping[str, Any]], Mapping[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """Apply a reviewed plan without moving, linking, replacing, or deleting originals."""

    validate_confirmation_token(plan, confirmation_token)
    if plan.get("version") != PLAN_VERSION:
        raise ValueError(f"Unsupported structure plan version: {plan.get('version')!r}.")
    for field in ("hardcoded_unresolved_references", "unresolved_proposals"):
        if field not in plan:
            raise ValueError(f"Structure plan is missing the required {field} field for its version.")
        if not isinstance(plan[field], list):
            raise ValueError(f"Structure plan {field} must be a list.")
    if plan.get("operation") != "copy_only":
        raise ValueError("Only copy_only structure plans can be applied.")
    if plan.get("collisions"):
        raise FileExistsError("Structure plan contains destination collisions.")
    if plan.get("hardcoded_unresolved_references"):
        raise RuntimeError("Structure plan has unresolved hard-coded dependencies.")
    if plan.get("unresolved_proposals"):
        raise RuntimeError("Structure plan has unresolved normalization proposals.")
    root = Path(str(plan.get("project_root"))).absolute()
    try:
        root_identity = capture_project_root(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError("Planned project root is no longer a safe directory.") from exc
    planned_root_identity = plan.get("project_root_identity")
    if not isinstance(planned_root_identity, Mapping) or set(planned_root_identity) != {"device", "inode"}:
        raise ValueError("Structure plan is missing its reviewed project-root identity.")
    if {
        "device": root_identity[0],
        "inode": root_identity[1],
    } != dict(planned_root_identity):
        raise RuntimeError("Planned project root identity changed after review.")
    config_path = root / "project_config.yaml"
    planned_config_hash = plan.get("config_sha256")
    planned_config_identity = plan.get("config_identity")
    current_config_hash = _sha256(config_path) if config_path.is_file() and not config_path.is_symlink() else None
    if current_config_hash != planned_config_hash:
        raise RuntimeError("project_config.yaml changed after plan review.")
    if planned_config_hash is None:
        if planned_config_identity is not None:
            raise ValueError("Absent reviewed config must not carry a source identity.")
    else:
        if not isinstance(planned_config_identity, Mapping) or set(planned_config_identity) != {
            "device",
            "inode",
        }:
            raise ValueError("Reviewed project config identity is invalid.")
        if source_identity(config_path) != dict(planned_config_identity):
            raise RuntimeError("project_config.yaml identity changed after plan review.")
    config_update = plan.get("config_update")
    if bool(plan.get("config_diff")) != bool(config_update):
        raise ValueError("Typed config diff and reviewed config update payload do not agree.")
    if config_update is not None:
        if not isinstance(config_update, Mapping) or set(config_update) != {
            "path",
            "before_sha256",
            "after_sha256",
            "after_text",
            "size",
        }:
            raise ValueError("Reviewed config update payload is invalid.")
        if config_update["path"] != "project_config.yaml" or config_update["before_sha256"] != planned_config_hash:
            raise ValueError("Reviewed config update is not bound to project_config.yaml.")
        encoded_config = str(config_update["after_text"]).encode("utf-8")
        if (
            len(encoded_config) != config_update["size"]
            or hashlib.sha256(encoded_config).hexdigest() != config_update["after_sha256"]
        ):
            raise ValueError("Reviewed config update content/hash is invalid.")
    required = int(plan.get("total_bytes", 0)) + (int(config_update["size"]) * 2 if config_update else 0)
    if shutil.disk_usage(root).free < required:
        raise OSError("Insufficient free disk space for structure plan.")

    entries = list(plan.get("entries") or [])
    _validate_role_destination_bindings(
        root,
        entries,
        config_path=config_path,
        config_update=config_update,
        root_identity=root_identity,
        planned_hash=planned_config_hash if isinstance(planned_config_hash, str) else None,
    )
    # With no verifier, retain the historical eager parent preparation.  When
    # a verifier is supplied, destination-parent creation is deferred until
    # after the final authority gate so rejection cannot mutate the namespace.
    created: list[tuple[Path, str, tuple[int, int]]] = []
    config_replacement_identity: tuple[int, int] | None = None
    config_original_guard: Path | None = None
    config_original_guard_identity: tuple[int, int] | None = None
    config_parent_witness: DirectoryWitness | None = None
    held_directory_leases: list[Any] = []
    config_replaced = False
    try:
        prepared = prepare_structure_entries(
            entries,
            root=root,
            root_identity=root_identity,
            defer_parent_creation=pre_apply_verifier is not None,
        )

        # All reviewed-plan, root/config identity, source digest, destination
        # collision, and containment checks are complete at this point.  A
        # host authority callback is deliberately the final gate before any
        # staging or publication mutation begins.
        if pre_apply_verifier is not None:
            pre_apply_verifier(root, plan)

        for prepared_entry in prepared:
            entry = prepared_entry.entry
            destination = prepared_entry.destination
            parent_witness = materialize_parent_witness(
                prepared_entry,
                root=root,
                root_identity=root_identity,
            )
            with lease_directory_witness(parent_witness):
                assert_directory_witness(parent_witness)
                with open_bound_source(
                    root,
                    entry["source"],
                    root_identity=root_identity,
                    planned_identity=dict(entry["source_identity"]),
                ) as source_handle:
                    source_hash, source_size = hash_handle(source_handle)
                    if source_size != entry["size"] or source_hash != entry["sha256"]:
                        raise RuntimeError(f"Planned source changed during apply: {entry['source']}")
                    stage, stage_identity = _stage_copy(
                        source_handle,
                        destination,
                        entry["sha256"],
                        root=root,
                        parent_witness=parent_witness,
                    )
                try:
                    assert_directory_witness(parent_witness)
                    identity = _publish_no_clobber(
                        stage,
                        destination,
                        expected_stage_identity=stage_identity,
                        expected_hash=entry["sha256"],
                    )
                    assert_directory_witness(parent_witness)
                finally:
                    _discard_private_stage(stage, stage_identity, parent_witness)
                persistent_lease = lease_directory_witness(parent_witness)
                persistent_lease.__enter__()
                held_directory_leases.append(persistent_lease)
            created.append((destination, entry["sha256"], identity))
        if config_update is not None:
            if _sha256(config_path) != planned_config_hash:
                raise RuntimeError("project_config.yaml changed during structure apply.")
            config_parent_witness = capture_directory_witness(
                root,
                ".",
                root_identity=root_identity,
            )
            config_persistent_lease = lease_directory_witness(config_parent_witness)
            config_persistent_lease.__enter__()
            held_directory_leases.append(config_persistent_lease)
            with lease_directory_witness(config_parent_witness):
                config_stage, config_stage_identity = _stage_bytes(
                    str(config_update["after_text"]).encode("utf-8"),
                    config_path,
                    str(config_update["after_sha256"]),
                    root=root,
                    parent_witness=config_parent_witness,
                )
            try:
                (
                    config_replacement_identity,
                    config_original_guard,
                    config_original_guard_identity,
                ) = _publish_config_compare_and_swap(
                    config_path=config_path,
                    config_stage=config_stage,
                    planned_hash=str(planned_config_hash),
                    replacement_hash=str(config_update["after_sha256"]),
                    root=root,
                    root_identity=root_identity,
                    parent_witness=config_parent_witness,
                )
            finally:
                _discard_private_stage(config_stage, config_stage_identity, config_parent_witness)
            config_replaced = True
        verification = (
            dict(post_apply_verifier(root, plan) or {}) if post_apply_verifier else {"status": "not_requested"}
        )
        if (
            config_update is not None
            and config_original_guard is not None
            and config_original_guard_identity is not None
            and config_replacement_identity is not None
            and config_parent_witness is not None
        ):
            _finalize_config_guard(
                guard=config_original_guard,
                guard_identity=config_original_guard_identity,
                planned_hash=str(planned_config_hash),
                config_path=config_path,
                replacement_identity=config_replacement_identity,
                replacement_hash=str(config_update["after_sha256"]),
                parent_witness=config_parent_witness,
            )
        receipt = {
            "plan_digest": plan["digest"],
            "copies": [
                {
                    "source": entry["source"],
                    "destination": entry["destination"],
                    "role": entry["role"],
                    "sha256": entry["sha256"],
                    "size": entry["size"],
                }
                for entry in entries
            ],
            "config": {
                "before_sha256": planned_config_hash,
                "after_sha256": config_update["after_sha256"] if config_update else planned_config_hash,
                "backup": (
                    config_original_guard.relative_to(root).as_posix()
                    if config_original_guard
                    else None
                ),
            },
            "verification": verification,
            "originals_preserved": True,
        }
        result = {
            "status": "applied",
            "plan_digest": plan["digest"],
            "created_paths": [path.relative_to(root).as_posix() for path, _, _ in created],
            "originals_preserved": True,
            "rollback_journal": plan["rollback_journal"],
            "provenance_receipt": receipt,
        }
        _release_directory_leases(held_directory_leases)
        return result
    except BaseException as exc:
        cleanup_withheld: list[Path] = []
        if config_replaced and config_parent_witness is not None:
            if config_replacement_identity is not None:
                rolled_back, retained_paths = _rollback_config_no_clobber(
                    config_path=config_path,
                    replacement_hash=str(config_update["after_sha256"]),
                    replacement_identity=config_replacement_identity,
                    original_guard=config_original_guard,
                    parent_witness=config_parent_witness,
                )
                if not rolled_back:
                    cleanup_withheld.extend(retained_paths)
        try:
            for destination, expected_hash, identity in reversed(created):
                if not _remove_if_owned(destination, expected_hash, identity):
                    cleanup_withheld.append(destination)
        finally:
            _release_directory_leases(held_directory_leases)
        if cleanup_withheld:
            labels = ", ".join(
                sorted(
                    path.relative_to(root).as_posix()
                    if path.is_relative_to(root)
                    else path.name
                    for path in cleanup_withheld
                )
            )
            raise RuntimeError(
                f"{STRUCTURE_MANUAL_CLEANUP_REQUIRED}: automatic rollback was withheld for "
                f"ownership-ambiguous path(s): {labels}; preserve them for manual review"
            ) from exc
        raise


execute_structure_plan = apply_structure_plan
