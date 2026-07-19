"""Closed validation for the artifact section of an evidence envelope."""
from __future__ import annotations

import mimetypes
import re
from collections.abc import Mapping
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, NoReturn

_AVAILABILITY = {"available", "unavailable", "not_applicable", "unknown"}
_RASTER_ARTIFACT_MEDIA = {"image/png", "image/jpeg", "image/webp"}
_VECTOR_ARTIFACT_MEDIA = {"application/pdf", "image/svg+xml"}
_SUPPORTED_ARTIFACT_MEDIA = _RASTER_ARTIFACT_MEDIA | _VECTOR_ARTIFACT_MEDIA
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


class ArtifactSectionError(ValueError):
    """Internal structured error translated by the public contract module."""

    def __init__(self, code: str, path: str, detail: str) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"{path} {detail}")


def _fail(code: str, path: str, detail: str) -> NoReturn:
    raise ArtifactSectionError(code, path, detail)


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("TYPE_MAPPING", path, "must be a mapping")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        _fail("TYPE_LIST", path, "must be a list")
    return value


def _closed(item: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(item) - allowed)
    if unknown:
        _fail("UNKNOWN_FIELD", f"{path}.{unknown[0]}", "is not allowed")


def _nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("NONEMPTY_STRING", path, "must be a non-empty string")
    return value


def _sha256(value: Any, path: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        _fail("SHA256_INVALID", path, "must be a 64-character hexadecimal SHA-256")


def validate_artifacts(value: Any) -> tuple[str | None, bool]:
    """Validate artifact integrity metadata without applying policy."""
    artifacts = _mapping(value, "evidence.artifacts")
    _closed(artifacts, {"status", "reason", "entries"}, "evidence.artifacts")
    status = artifacts.get("status")
    if status is None:
        _fail("ARTIFACT_STATUS_REQUIRED", "evidence.artifacts.status", "is required")
    if status not in {"passed", "warning", "failed", "skipped", "unavailable"}:
        _fail("ARTIFACT_STATUS_INVALID", "evidence.artifacts.status", "has an invalid value")
    if status in {"skipped", "unavailable"}:
        _nonempty_string(artifacts.get("reason"), "evidence.artifacts.reason")
    entries = _list(artifacts.get("entries", []), "evidence.artifacts.entries")
    if status in {"passed", "warning"} and not entries:
        _fail(
            "ARTIFACT_REQUIRED",
            "evidence.artifacts.entries",
            "requires at least one entry when artifact production completed",
        )
    if status in {"failed", "skipped", "unavailable"} and entries:
        _fail(
            "ARTIFACT_ENTRY_CONFLICT",
            "evidence.artifacts.entries",
            "must be empty when artifact production did not complete",
        )
    roles: set[str] = set()
    allowed = {
        "logical_role", "relative_path", "media_type", "byte_size", "sha256",
        "width", "height", "header_valid", "dimensions_valid",
        "dimension_availability", "dimension_reason", "availability", "reason",
    }
    for index, raw in enumerate(entries):
        path = f"evidence.artifacts.entries[{index}]"
        item = _mapping(raw, path)
        _closed(item, allowed, path)
        role = _nonempty_string(item.get("logical_role"), f"{path}.logical_role")
        if role in roles:
            _fail("ARTIFACT_ROLE_DUPLICATE", f"{path}.logical_role", "must be unique")
        roles.add(role)
        availability = item.get("availability", "available")
        if availability not in _AVAILABILITY:
            _fail("AVAILABILITY_INVALID", f"{path}.availability", "has an invalid value")
        if availability == "available":
            relative_path = _nonempty_string(item.get("relative_path"), f"{path}.relative_path")
            windows_path = PureWindowsPath(relative_path)
            portable_path = PurePosixPath(relative_path.replace("\\", "/"))
            if (
                windows_path.is_absolute()
                or bool(windows_path.drive)
                or portable_path.is_absolute()
                or ".." in portable_path.parts
            ):
                _fail(
                    "ARTIFACT_PATH_INVALID",
                    f"{path}.relative_path",
                    "must be a safe relative path without traversal",
                )
            media_type = _nonempty_string(item.get("media_type"), f"{path}.media_type").lower()
            if not re.fullmatch(
                r"[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*", media_type
            ):
                _fail(
                    "ARTIFACT_MEDIA_TYPE_INVALID",
                    f"{path}.media_type",
                    "must be a valid MIME type",
                )
            if media_type not in _SUPPORTED_ARTIFACT_MEDIA:
                _fail(
                    "ARTIFACT_MEDIA_TYPE_INVALID",
                    f"{path}.media_type",
                    "is outside the supported render artifact media allowlist",
                )
            guessed_type, _ = mimetypes.guess_type(relative_path, strict=False)
            if guessed_type is None or guessed_type.lower() != media_type:
                _fail(
                    "ARTIFACT_MEDIA_TYPE_INVALID",
                    f"{path}.media_type",
                    "does not match the declared file extension",
                )
            byte_size = item.get("byte_size")
            if isinstance(byte_size, bool) or not isinstance(byte_size, int) or byte_size <= 0:
                _fail("ARTIFACT_SIZE_INVALID", f"{path}.byte_size", "must be a positive integer")
            _sha256(item.get("sha256"), f"{path}.sha256")
            if item.get("header_valid") is not True:
                _fail("ARTIFACT_VALIDATION_REQUIRED", f"{path}.header_valid", "must be true")
            dimension_availability = item.get("dimension_availability", "available")
            if dimension_availability not in _AVAILABILITY:
                _fail(
                    "AVAILABILITY_INVALID",
                    f"{path}.dimension_availability",
                    "has an invalid value",
                )
            if media_type in _RASTER_ARTIFACT_MEDIA and dimension_availability != "available":
                _fail(
                    "ARTIFACT_DIMENSION_CONFLICT",
                    f"{path}.dimension_availability",
                    "must be available for a verified raster artifact",
                )
            if media_type in _VECTOR_ARTIFACT_MEDIA and dimension_availability == "available":
                _fail(
                    "ARTIFACT_DIMENSION_CONFLICT",
                    f"{path}.dimension_availability",
                    "must not claim policy-neutral pixel dimensions for a vector artifact",
                )
            if dimension_availability == "available":
                for field in ("width", "height"):
                    dimension = item.get(field)
                    if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension <= 0:
                        _fail(
                            "ARTIFACT_DIMENSION_INVALID",
                            f"{path}.{field}",
                            "must be a positive integer",
                        )
                if item.get("dimensions_valid") is not True:
                    _fail("ARTIFACT_VALIDATION_REQUIRED", f"{path}.dimensions_valid", "must be true")
                if "dimension_reason" in item:
                    _fail(
                        "ARTIFACT_DIMENSION_CONFLICT",
                        f"{path}.dimension_reason",
                        "is forbidden when dimensions are available",
                    )
            else:
                _nonempty_string(item.get("dimension_reason"), f"{path}.dimension_reason")
                claimed_dimensions = {"width", "height", "dimensions_valid"}.intersection(item)
                if claimed_dimensions:
                    field = sorted(claimed_dimensions)[0]
                    _fail(
                        "ARTIFACT_DIMENSION_CONFLICT",
                        f"{path}.{field}",
                        "is forbidden when dimensions are unavailable",
                    )
        else:
            _nonempty_string(item.get("reason"), f"{path}.reason")
            forbidden = {
                "relative_path", "media_type", "byte_size", "sha256", "width", "height",
                "header_valid", "dimensions_valid", "dimension_availability", "dimension_reason",
            }
            claimed = forbidden.intersection(item)
            if claimed:
                field = sorted(claimed)[0]
                _fail(
                    "ARTIFACT_INTEGRITY_CONFLICT",
                    f"{path}.{field}",
                    "is forbidden when the artifact is unavailable",
                )
    return status, bool(entries)
