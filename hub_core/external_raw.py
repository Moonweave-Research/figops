"""Closed descriptor types for raw inputs governed outside a project tree.

Trust decisions are deliberately not made here.  The runtime integration layer
must resolve ``allowed_root`` against launcher-owned policy and verify observed
bytes against ``sha256`` before execution.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_URI_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*$")
_DESCRIPTOR_KEYS = frozenset({"id", "path", "uri", "allowed_root", "version", "sha256", "access_class"})


class ExternalRawError(ValueError):
    """An external-raw descriptor is malformed or ambiguous."""


_SENSITIVE_ACCESS_CLASSES = frozenset({"restricted", "sensitive", "confidential", "secret"})


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExternalRawError(f"external_raw.{field} must be a non-empty string")
    return value.strip()


def _normalize_path(value: object) -> str:
    text = _required_text(value, "path").replace("\\", "/")
    path = PurePosixPath(text)
    if path.is_absolute() or not path.parts or ".." in path.parts or ":" in path.parts[0]:
        raise ExternalRawError("external_raw.path must be relative to its trusted allowed root")
    normalized = path.as_posix()
    if normalized in {"", "."} or normalized != text:
        raise ExternalRawError("external_raw.path must be canonical")
    return normalized


def _normalize_uri(value: object) -> str:
    text = _required_text(value, "uri")
    parsed = urlsplit(text)
    if not parsed.scheme or not _URI_SCHEME.fullmatch(parsed.scheme):
        raise ExternalRawError("external_raw.uri must use a canonical lowercase URI scheme")
    if parsed.scheme == "file":
        raise ExternalRawError("external_raw.uri must not use file:; use path plus allowed_root")
    if parsed.username is not None or parsed.password is not None or parsed.fragment:
        raise ExternalRawError("external_raw.uri must not contain credentials or a fragment")
    if not parsed.netloc and not parsed.path:
        raise ExternalRawError("external_raw.uri must include a source location")
    normalized = urlunsplit(parsed)
    if normalized != text:
        raise ExternalRawError("external_raw.uri must be canonical")
    return normalized


@dataclass(frozen=True, slots=True)
class ExternalRawDescriptor:
    """Validated immutable identity for one externally governed input."""

    id: str
    locator_kind: str
    locator: str
    allowed_root: str
    version: str
    sha256: str
    access_class: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ExternalRawDescriptor":
        if not isinstance(value, Mapping):
            raise ExternalRawError("external_raw entries must be mappings")
        extra = set(value) - _DESCRIPTOR_KEYS
        if extra:
            raise ExternalRawError(f"external_raw contains unsupported fields: {', '.join(sorted(extra))}")
        descriptor_id = _required_text(value.get("id"), "id")
        if not _ID.fullmatch(descriptor_id):
            raise ExternalRawError("external_raw.id must use letters, digits, '.', '_', or '-'")
        present = [key for key in ("path", "uri") if key in value and value.get(key) is not None]
        if len(present) != 1:
            raise ExternalRawError("external_raw must define exactly one of path or uri")
        locator_kind = present[0]
        locator = (
            _normalize_path(value[locator_kind])
            if locator_kind == "path"
            else _normalize_uri(value[locator_kind])
        )
        allowed_root = _required_text(value.get("allowed_root"), "allowed_root")
        if not _ID.fullmatch(allowed_root):
            raise ExternalRawError("external_raw.allowed_root must be a stable root identifier")
        version = _required_text(value.get("version"), "version")
        digest = _required_text(value.get("sha256"), "sha256")
        if not _SHA256.fullmatch(digest):
            raise ExternalRawError("external_raw.sha256 must be 64 lowercase hexadecimal characters")
        access = value.get("access_class")
        if access is not None:
            access = _required_text(access, "access_class")
        return cls(descriptor_id, locator_kind, locator, allowed_root, version, digest, access)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            self.locator_kind: self.locator,
            "allowed_root": self.allowed_root,
            "version": self.version,
            "sha256": self.sha256,
        }
        if self.access_class is not None:
            result["access_class"] = self.access_class
        return result

    @property
    def is_sensitive(self) -> bool:
        return bool(self.access_class and self.access_class.lower() in _SENSITIVE_ACCESS_CLASSES)


@dataclass(frozen=True, slots=True)
class VerifiedExternalRawMaterialization:
    """Observed runtime copy; durable projection is metadata-only by design."""

    descriptor: ExternalRawDescriptor
    materialized_path: Path
    observed_sha256: str
    size_bytes: int

    def durable_metadata(self) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "artifact_id": self.descriptor.id,
            "allowed_root": self.descriptor.allowed_root,
            "version": self.descriptor.version,
            "sha256": self.observed_sha256,
            "access_class": self.descriptor.access_class or "standard",
            "content_included": False,
        }
        if not self.descriptor.is_sensitive:
            metadata["locator_kind"] = self.descriptor.locator_kind
            metadata["locator"] = self.descriptor.locator
        return metadata


def _hash_regular_file(path: Path) -> tuple[str, int]:
    if path.is_symlink() or not path.is_file():
        raise ExternalRawError("external raw materialization must be a non-symlink regular file")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def verify_external_raw_materialization(
    descriptor: ExternalRawDescriptor | Mapping[str, Any],
    materialized_path: str | os.PathLike[str],
    *,
    runtime_root: str | os.PathLike[str],
    allowed_roots: Mapping[str, str | os.PathLike[str]],
) -> VerifiedExternalRawMaterialization:
    """Verify launcher authority and exact post-prefetch bytes before execution."""

    item = (
        descriptor
        if isinstance(descriptor, ExternalRawDescriptor)
        else ExternalRawDescriptor.from_mapping(descriptor)
    )
    if item.allowed_root not in allowed_roots:
        raise ExternalRawError(f"external raw allowed root {item.allowed_root!r} is not launcher-approved")
    approved_root = Path(allowed_roots[item.allowed_root]).expanduser().resolve(strict=True)
    if not approved_root.is_dir():
        raise ExternalRawError("external raw allowed root must resolve to an existing directory")
    if item.locator_kind == "path":
        source = (approved_root / Path(item.locator)).resolve(strict=False)
        try:
            source.relative_to(approved_root)
        except ValueError as exc:
            raise ExternalRawError("external raw local locator escapes its approved root") from exc

    runtime = Path(runtime_root).expanduser().resolve(strict=True)
    if not runtime.is_dir():
        raise ExternalRawError("external raw runtime root must be an existing directory")
    raw_materialized = Path(materialized_path).expanduser().absolute()
    materialized = raw_materialized.resolve(strict=True)
    try:
        materialized.relative_to(runtime)
    except ValueError as exc:
        raise ExternalRawError("external raw materialization must stay below the runtime root") from exc
    observed, size = _hash_regular_file(raw_materialized)
    if observed != item.sha256:
        raise ExternalRawError(
            f"external raw materialized bytes do not match descriptor SHA-256 for {item.id!r}"
        )
    return VerifiedExternalRawMaterialization(item, materialized, observed, size)


def validate_external_raw_descriptors(value: object) -> tuple[ExternalRawDescriptor, ...]:
    """Validate descriptor shape and immutable identity, preserving order."""

    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ExternalRawError("external_raw must be a list of descriptors")
    descriptors: list[ExternalRawDescriptor] = []
    seen: set[str] = set()
    for index, item in enumerate(value, 1):
        try:
            descriptor = ExternalRawDescriptor.from_mapping(item)
        except ExternalRawError as exc:
            raise ExternalRawError(f"external_raw[{index}]: {exc}") from exc
        if descriptor.id in seen:
            raise ExternalRawError(f"external_raw[{index}]: duplicate id {descriptor.id!r}")
        seen.add(descriptor.id)
        descriptors.append(descriptor)
    return tuple(descriptors)


def external_raw_index(value: object) -> Mapping[str, ExternalRawDescriptor]:
    return MappingProxyType({descriptor.id: descriptor for descriptor in validate_external_raw_descriptors(value)})


__all__ = [
    "ExternalRawDescriptor",
    "ExternalRawError",
    "VerifiedExternalRawMaterialization",
    "external_raw_index",
    "validate_external_raw_descriptors",
    "verify_external_raw_materialization",
]
