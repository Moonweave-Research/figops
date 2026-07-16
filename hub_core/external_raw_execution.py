"""Fail-closed execution bridge for ``external_raw:<id>`` declarations.

Project configuration declares identity but never grants filesystem authority.
Callers must supply launcher-validated allowed roots.  External bytes are
materialized below the disposable FigOps runtime and only their opaque identity
and digest enter cache/provenance records.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .external_raw import (
    ExternalRawDescriptor,
    ExternalRawError,
    VerifiedExternalRawMaterialization,
    external_raw_index,
    verify_external_raw_materialization,
)
from .runtime_boundary import activate_runtime_root, runtime_project_id, safe_runtime_segment
from .runtime_paths import resolve_runtime_root

EXTERNAL_RAW_PREFIX = "external_raw:"
_ROOT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True, slots=True)
class ResolvedExternalRawInput:
    declaration: str
    path: Path
    verified: VerifiedExternalRawMaterialization

    def signature(self) -> dict[str, Any]:
        descriptor = self.verified.descriptor
        return _descriptor_signature(self.declaration, descriptor)

    def provenance_metadata(self) -> dict[str, Any]:
        return self.verified.durable_metadata()


def is_external_raw_declaration(value: object) -> bool:
    return isinstance(value, str) and value.startswith(EXTERNAL_RAW_PREFIX)


def _descriptor_id(declaration: str) -> str:
    if not is_external_raw_declaration(declaration):
        raise ExternalRawError("external raw declaration must start with 'external_raw:'")
    descriptor_id = declaration[len(EXTERNAL_RAW_PREFIX) :]
    if not descriptor_id:
        raise ExternalRawError("external raw declaration must include an id")
    return descriptor_id


def _locator_identity(descriptor: ExternalRawDescriptor) -> str:
    payload = f"{descriptor.locator_kind}\0{descriptor.locator}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _descriptor_signature(declaration: str, descriptor: ExternalRawDescriptor) -> dict[str, Any]:
    return {
        "declaration": declaration,
        "artifact_id": descriptor.id,
        "allowed_root": descriptor.allowed_root,
        "version": descriptor.version,
        "sha256": descriptor.sha256,
        "locator_kind": descriptor.locator_kind,
        "locator_identity_sha256": _locator_identity(descriptor),
        "access_class": descriptor.access_class or "standard",
        "content_included": False,
    }


def external_raw_signatures(config: Mapping[str, Any], declarations: Sequence[str]) -> list[dict[str, Any]]:
    """Return stable, content-free signatures for declared external inputs."""

    descriptors = external_raw_index(config.get("external_raw"))
    signatures: list[dict[str, Any]] = []
    for declaration in declarations:
        if not is_external_raw_declaration(declaration):
            continue
        descriptor_id = _descriptor_id(declaration)
        descriptor = descriptors.get(descriptor_id)
        if descriptor is None:
            raise ExternalRawError(f"external raw input {descriptor_id!r} has no descriptor")
        signatures.append(_descriptor_signature(declaration, descriptor))
    return signatures


def bind_launcher_allowed_roots(
    roots: Mapping[str, str | os.PathLike[str]] | Sequence[str | os.PathLike[str]] | None,
) -> dict[str, Path]:
    """Normalize launcher authority without consulting project configuration.

    MCP supplies an already validated sequence.  Its stable identifier is the
    final directory name; duplicate names are ambiguous and therefore refused.
    Other trusted launchers may supply an explicit identifier-to-path mapping.
    """

    if roots is None:
        return {}
    items = roots.items() if isinstance(roots, Mapping) else ((Path(root).name, root) for root in roots)
    bound: dict[str, Path] = {}
    for raw_id, raw_path in items:
        root_id = str(raw_id).strip()
        if not _ROOT_ID.fullmatch(root_id):
            raise ExternalRawError(
                "launcher external raw root id must use letters, digits, '.', '_', or '-'"
            )
        path = Path(raw_path).expanduser().resolve(strict=True)
        if not path.is_dir():
            raise ExternalRawError(f"launcher external raw root {root_id!r} is not a directory")
        if root_id in bound and bound[root_id] != path:
            raise ExternalRawError(f"launcher external raw root id {root_id!r} is ambiguous")
        bound[root_id] = path
    return bound


def parse_cli_external_raw_roots(specs: Sequence[str] | None) -> dict[str, Path]:
    """Parse repeatable launcher-owned ``ID=ABSOLUTE_PATH`` CLI grants."""

    raw_mapping: dict[str, Path] = {}
    for spec in specs or ():
        if not isinstance(spec, str) or "=" not in spec:
            raise ExternalRawError("--external-raw-root must use ID=ABSOLUTE_PATH")
        root_id, raw_path = spec.split("=", 1)
        root_id = root_id.strip()
        candidate = Path(raw_path.strip()).expanduser()
        if not candidate.is_absolute():
            raise ExternalRawError("--external-raw-root path must be absolute")
        if root_id in raw_mapping:
            raise ExternalRawError(f"duplicate --external-raw-root id {root_id!r}")
        raw_mapping[root_id] = candidate
    return bind_launcher_allowed_roots(raw_mapping)


def _approved_source(
    descriptor: ExternalRawDescriptor,
    allowed_roots: Mapping[str, Path],
    *,
    project_root: Path,
) -> Path:
    approved_root = allowed_roots.get(descriptor.allowed_root)
    if approved_root is None:
        raise ExternalRawError(
            f"external raw allowed root {descriptor.allowed_root!r} is not launcher-approved"
        )
    if descriptor.locator_kind != "path":
        raise ExternalRawError(
            f"external raw URI {descriptor.id!r} requires an enabled materialization adapter"
        )
    lexical = approved_root.joinpath(*descriptor.locator.split("/"))
    if lexical.is_symlink():
        raise ExternalRawError(f"external raw source {descriptor.id!r} must not be a symlink")
    try:
        source = lexical.resolve(strict=True)
        source.relative_to(approved_root)
    except (FileNotFoundError, ValueError) as exc:
        raise ExternalRawError(
            f"external raw source {descriptor.id!r} is unavailable or outside its approved root"
        ) from exc
    if not source.is_file():
        raise ExternalRawError(f"external raw source {descriptor.id!r} must be a regular file")
    try:
        source.relative_to(project_root)
    except ValueError:
        pass
    else:
        raise ExternalRawError(f"external raw source {descriptor.id!r} must remain outside the project")
    return source


def _copy_verified_source_bytes(
    source: Path,
    destination: Path,
    expected_sha256: str,
    descriptor_id: str,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.stage")
    digest = hashlib.sha256()
    source_lstat_before = source.lstat()
    if stat.S_ISLNK(source_lstat_before.st_mode):
        raise ExternalRawError(f"external raw source {descriptor_id!r} must not be a symlink")
    source_stat_before = source.stat()
    if not stat.S_ISREG(source_stat_before.st_mode):
        raise ExternalRawError(f"external raw source {descriptor_id!r} must be a regular file")
    try:
        read_flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        source_descriptor = os.open(source, read_flags)
        with os.fdopen(source_descriptor, "rb") as input_handle, stage.open("xb") as output_handle:
            for chunk in iter(lambda: input_handle.read(1024 * 1024), b""):
                digest.update(chunk)
                output_handle.write(chunk)
            output_handle.flush()
            os.fsync(output_handle.fileno())
        source_lstat_after = source.lstat()
        if stat.S_ISLNK(source_lstat_after.st_mode):
            raise ExternalRawError(f"external raw source {descriptor_id!r} changed during materialization")
        source_stat_after = source.stat()
        if (
            source_stat_before.st_dev,
            source_stat_before.st_ino,
            source_stat_before.st_size,
            source_stat_before.st_mtime_ns,
        ) != (
            source_stat_after.st_dev,
            source_stat_after.st_ino,
            source_stat_after.st_size,
            source_stat_after.st_mtime_ns,
        ):
            raise ExternalRawError(f"external raw source {descriptor_id!r} changed during materialization")
        if digest.hexdigest() != expected_sha256:
            raise ExternalRawError(
                f"external raw source bytes do not match descriptor SHA-256 for {descriptor_id!r}"
            )
        os.replace(stage, destination)
    finally:
        try:
            stage.unlink()
        except FileNotFoundError:
            pass


def _copy_verified_source(source: Path, destination: Path, expected_sha256: str, descriptor_id: str) -> None:
    try:
        _copy_verified_source_bytes(source, destination, expected_sha256, descriptor_id)
    except ExternalRawError:
        raise
    except OSError as exc:
        raise ExternalRawError(
            f"external raw source {descriptor_id!r} could not be materialized safely"
        ) from exc


def _runtime_child(runtime: Path, *parts: str) -> Path:
    candidate = runtime.joinpath(*parts)
    try:
        candidate.resolve(strict=False).relative_to(runtime)
    except ValueError as exc:
        raise ExternalRawError("external raw materialization path escaped the runtime root") from exc
    current = runtime
    for part in parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise ExternalRawError("external raw materialization path contains a symlink")
    return candidate


def materialize_external_raw_inputs(
    *,
    project_root: str | os.PathLike[str],
    config: Mapping[str, Any],
    declarations: Sequence[str],
    prefetcher: Any,
    allowed_roots: Mapping[str, str | os.PathLike[str]] | Sequence[str | os.PathLike[str]] | None,
    runtime_root: str | os.PathLike[str] | None = None,
) -> list[ResolvedExternalRawInput]:
    """Materialize and verify external declarations immediately before use."""

    external_declarations = [item for item in declarations if is_external_raw_declaration(item)]
    if not external_declarations:
        return []
    descriptors = external_raw_index(config.get("external_raw"))
    authority = bind_launcher_allowed_roots(allowed_roots)
    project = Path(project_root).resolve(strict=True)
    if runtime_root is None:
        runtime = Path(resolve_runtime_root(project_root=project, config=dict(config))).resolve(strict=True)
    else:
        runtime = activate_runtime_root(
            runtime_root,
            project_root=project,
            config=dict(config),
        )
    materialization_root = _runtime_child(
        runtime,
        "external_raw",
        runtime_project_id(project_root),
    )
    materialization_root.mkdir(parents=True, exist_ok=True)
    resolved: list[ResolvedExternalRawInput] = []
    for declaration in external_declarations:
        descriptor_id = _descriptor_id(declaration)
        descriptor = descriptors.get(descriptor_id)
        if descriptor is None:
            raise ExternalRawError(f"external raw input {descriptor_id!r} has no descriptor")
        if descriptor.locator_kind == "uri":
            materializer = getattr(prefetcher, "materialize_external_raw", None)
            if not callable(materializer):
                raise ExternalRawError(
                    f"external raw URI {descriptor.id!r} requires an enabled materialization adapter"
                )
            destination_dir = _runtime_child(
                runtime,
                "external_raw",
                runtime_project_id(project_root),
                safe_runtime_segment(descriptor.id, fallback="raw"),
            )
            destination_dir.mkdir(parents=True, exist_ok=True)
            raw_path = materializer(descriptor, destination_dir)
            if raw_path is None:
                raise ExternalRawError(
                    f"external raw URI adapter did not materialize {descriptor.id!r}"
                )
            materialized_path = Path(raw_path)
        else:
            source = _approved_source(descriptor, authority, project_root=project)
            prefetcher.ensure_local([str(source)])
            # Re-resolve after prefetch so a path replacement cannot inherit authority.
            source = _approved_source(descriptor, authority, project_root=project)
            suffix = Path(descriptor.locator).suffix
            filename = f"{safe_runtime_segment(descriptor.id, fallback='raw')}-{descriptor.sha256[:16]}{suffix}"
            materialized_path = _runtime_child(
                runtime,
                "external_raw",
                runtime_project_id(project_root),
                filename,
            )
            _copy_verified_source(source, materialized_path, descriptor.sha256, descriptor.id)
        verified = verify_external_raw_materialization(
            descriptor,
            materialized_path,
            runtime_root=runtime,
            allowed_roots=authority,
        )
        resolved.append(ResolvedExternalRawInput(declaration, verified.materialized_path, verified))
    return resolved


__all__ = [
    "EXTERNAL_RAW_PREFIX",
    "ResolvedExternalRawInput",
    "bind_launcher_allowed_roots",
    "external_raw_signatures",
    "is_external_raw_declaration",
    "materialize_external_raw_inputs",
    "parse_cli_external_raw_roots",
]
