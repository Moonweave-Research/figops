"""Fail-closed artifact integrity evidence for completed render manifests.

This module verifies bytes at the job boundary.  It deliberately reports only
facts; publication policy and visual-quality judgments belong to readiness
projections and human review.
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from .project_paths import open_verified_project_input, snapshot_project_input

_READ_CHUNK: Final = 1024 * 1024
_RASTER_MEDIA: Final = {"image/png", "image/jpeg", "image/webp"}
_SUPPORTED_MEDIA: Final = _RASTER_MEDIA | {"application/pdf", "image/svg+xml"}
_MAX_ARTIFACT_BYTES: Final = 256 * 1024 * 1024
_MAX_RASTER_PIXELS: Final = 100_000_000


def inspect_manifest_artifacts(manifest: Mapping[str, Any], manifest_path: str | Path) -> dict[str, Any]:
    """Return deterministic, path-safe integrity facts for declared figures."""

    root = Path(manifest_path).resolve(strict=True).parent
    figures = manifest.get("figures")
    if not isinstance(figures, list):
        return _failed("ARTIFACT_DECLARATION_INVALID", "manifest figures must be a list")

    entries: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for index, raw in enumerate(figures):
        if not isinstance(raw, Mapping) or not isinstance(raw.get("path"), str):
            errors.append(_error("ARTIFACT_DECLARATION_INVALID", f"figures[{index}] has no path"))
            continue
        try:
            entry = _inspect_one(root, raw["path"], logical_role=f"figure:{index}")
        except OSError:
            errors.append(_error("ARTIFACT_IO_FAILED", f"figures[{index}] could not be read safely"))
            continue
        except ValueError as exc:
            errors.append(_error("ARTIFACT_INTEGRITY_FAILED", str(exc)))
            continue
        entries.append(entry)

    declared_status = str(manifest.get("artifact_status") or "").strip().lower()
    failure_stage = str(manifest.get("failure_stage") or "").strip()
    if declared_status == "failed" or failure_stage:
        errors.append(
            _error(
                "ARTIFACT_PRODUCER_FAILED",
                f"producer reported artifact_status={declared_status!r}, failure_stage={failure_stage!r}",
            )
        )
    elif not entries:
        errors.append(_error("ARTIFACT_MISSING", "no completed artifact entry was declared"))

    output_sha = _find_hash(manifest.get("provenance"), "output_sha256")
    if entries and output_sha and output_sha not in {entry["sha256"] for entry in entries}:
        errors.append(
            _error(
                "ARTIFACT_OUTPUT_HASH_MISMATCH",
                "provenance output_sha256 does not match the primary artifact bytes",
            )
        )

    return {
        "schema_version": "artifact_integrity/1",
        "status": "failed" if errors else "passed",
        "entries": entries,
        "errors": errors,
    }


def _inspect_one(root: Path, raw_path: str, *, logical_role: str) -> dict[str, Any]:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        declaration = candidate.absolute().relative_to(root.absolute()).as_posix()
    except ValueError as exc:
        raise ValueError("artifact path escapes the render job root") from exc
    if _has_reparse_component(root, candidate):
        raise ValueError("artifact path must not contain symlink or reparse-point components")
    snapshot = snapshot_project_input(root, declaration, purpose="render artifact")
    with open_verified_project_input(
        root,
        declaration,
        expected_snapshot=snapshot,
        purpose="render artifact",
    ) as stream:
        opened = os.fstat(stream.fileno())
        resolved = snapshot.path
        size = opened.st_size
        if size <= 0:
            raise ValueError("artifact is empty")
        if size > _MAX_ARTIFACT_BYTES:
            raise ValueError("artifact exceeds the integrity verification byte limit")
        media_type = _media_type(stream, resolved)
        width, height = _dimensions(stream, media_type)
        digest = _sha256_stream(stream)
        closed = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
            closed.st_dev,
            closed.st_ino,
            closed.st_size,
            closed.st_mtime_ns,
        ):
            raise ValueError("artifact changed during integrity verification")
    return {
        "logical_role": logical_role,
        "relative_path": resolved.relative_to(root).as_posix(),
        "media_type": media_type,
        "byte_size": size,
        "width": width,
        "height": height,
        "header_valid": True,
        "dimensions_valid": width > 0 and height > 0,
        "sha256": digest,
    }


def _media_type(stream: Any, path: Path) -> str:
    stream.seek(0)
    head = stream.read(512)
    suffix_type = (mimetypes.guess_type(path.name, strict=False)[0] or "").lower()
    detected = ""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = "image/png"
    elif head.startswith(b"\xff\xd8\xff"):
        detected = "image/jpeg"
    elif head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        detected = "image/webp"
    elif head.startswith(b"%PDF-"):
        detected = "application/pdf"
    elif b"<svg" in head.lstrip(b"\xef\xbb\xbf\x00\t\r\n ")[:256].lower():
        detected = "image/svg+xml"
    if detected not in _SUPPORTED_MEDIA or suffix_type != detected:
        raise ValueError("artifact media header does not match its declared file extension")
    return detected


def _dimensions(stream: Any, media_type: str) -> tuple[int, int]:
    if media_type in _RASTER_MEDIA:
        try:
            from PIL import Image

            stream.seek(0)
            with Image.open(stream) as image:
                width, height = int(image.width), int(image.height)
                if width <= 0 or height <= 0 or width * height > _MAX_RASTER_PIXELS:
                    raise ValueError("raster dimensions exceed the integrity limit")
                image.verify()
            return width, height
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("raster structure or dimensions could not be verified") from exc
    # PDF/SVG dimension validation belongs to WP4's bounded rasterizer.  Never
    # invent dimensions merely because the source header is recognizable.
    raise ValueError("vector artifact dimensions are unavailable without bounded preview validation")


def _has_reparse_component(root: Path, candidate: Path) -> bool:
    """Check every existing path component before resolving its target."""

    try:
        relative = candidate.absolute().relative_to(root.absolute())
    except ValueError:
        return False
    current = root.absolute()
    for part in relative.parts:
        current = current / part
        try:
            stat = current.lstat()
        except FileNotFoundError:
            continue
        attributes = getattr(stat, "st_file_attributes", 0)
        reparse_flag = getattr(os.stat_result, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if current.is_symlink() or bool(attributes & reparse_flag):
            return True
    return False


def _sha256_stream(stream: Any) -> str:
    digest = hashlib.sha256()
    stream.seek(0)
    for chunk in iter(lambda: stream.read(_READ_CHUNK), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _find_hash(value: Any, key: str) -> str:
    if not isinstance(value, Mapping):
        return ""
    direct = value.get(key)
    if isinstance(direct, str) and len(direct) == 64:
        return direct.lower()
    for child in value.values():
        found = _find_hash(child, key)
        if found:
            return found
    return ""


def _error(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _failed(code: str, message: str) -> dict[str, Any]:
    return {
        "schema_version": "artifact_integrity/1",
        "status": "failed",
        "entries": [],
        "errors": [_error(code, message)],
    }
