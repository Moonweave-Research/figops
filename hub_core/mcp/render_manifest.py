"""Trusted render-manifest persistence and preview membership helpers."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

from hub_core.project_paths import (
    open_verified_project_input,
    project_path_has_symlink_component,
    snapshot_project_input,
)

_PREVIEW_MEDIA_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
    ".svg": "image/svg+xml",
}


def write_manifest_and_status(
    manifest: dict[str, Any],
    manifest_path: Path,
    status_payload: dict[str, Any],
    status_path: Path,
    latest_dir: Path,
) -> None:
    ensure_no_symlinked_runtime_path(manifest_path)
    ensure_no_symlinked_runtime_path(status_path)
    ensure_no_symlinked_runtime_path(latest_dir)
    latest_dir.mkdir(parents=True, exist_ok=True)
    latest_manifest_path = latest_dir / "manifest.json"
    latest_status_path = latest_dir / "status.json"
    ensure_no_symlinked_runtime_path(latest_manifest_path)
    ensure_no_symlinked_runtime_path(latest_status_path)
    atomic_json_write(manifest_path, manifest)
    atomic_json_write(status_path, status_payload)
    atomic_json_write(latest_manifest_path, manifest)
    atomic_json_write(latest_status_path, status_payload)


def atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    ensure_no_symlinked_runtime_path(path)
    if path.exists() and path.is_symlink():
        raise RuntimeError(f"Runtime write target must not be a symlink: {path}")
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(temporary_path, flags | nofollow, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        ensure_no_symlinked_runtime_path(path)
        os.replace(temporary_path, path)
    except OSError:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def first_symlink_component(path: Path) -> Path | None:
    raw_path = Path(path)
    current = Path(raw_path.anchor) if raw_path.is_absolute() else Path()
    parts = raw_path.parts[1:] if raw_path.is_absolute() else raw_path.parts
    for part in parts:
        current = current / part
        if current.is_symlink():
            return current
    return None


def ensure_no_symlinked_runtime_path(path: Path) -> None:
    symlink = first_symlink_component(path)
    if symlink is not None:
        raise RuntimeError(f"Runtime write target must not include symlinked path components: {symlink}")


def build_manifest(
    *,
    job_id: str,
    job_root: Path,
    config_path: Path,
    status_path: Path,
    latest_dir: Path,
    figures: list[dict[str, Any]],
    created_paths: list[str],
    style_summary: dict[str, Any],
    visual_preflight_status: dict[str, Any],
    geometry_diagnostics: dict[str, Any],
    layout_report: dict[str, Any],
    artifact_status: str,
    baseline_comparison: dict[str, Any],
    manual_review_needed: bool,
    provenance: dict[str, Any],
    **extra: Any,
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "job_id": job_id,
        "job_root": str(job_root),
        "config_path": str(config_path),
        "status_path": str(status_path),
        "latest_dir": str(latest_dir),
        "latest_alias": str(latest_dir),
        "figures": figures,
        "diagrams": [],
        "assemblies": [],
        "logs": [],
        "created_paths": created_paths,
        "modified_paths": [],
        "skipped_paths": [],
        "style_summary": style_summary,
        "visual_preflight_status": visual_preflight_status,
        "geometry_diagnostics": geometry_diagnostics,
        "layout_report": layout_report,
        "failure_stage": "",
        "resolution_hint": "",
        "artifact_status": artifact_status,
        "baseline_comparison": baseline_comparison,
        "manual_review_needed": manual_review_needed,
        "provenance": provenance,
    }
    manifest.update(extra)
    return manifest


def build_preview_artifacts(
    *,
    job_root: Path,
    output_path: Path,
    figures: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    root = job_root.absolute()
    requested_primary = output_path.absolute()
    inspected: list[tuple[Path, dict[str, Any]]] = []
    for index, figure in enumerate(figures):
        raw_path = figure.get("path") if isinstance(figure, dict) else None
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise RuntimeError(f"Rendered figure {index} has no artifact path.")
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = root / candidate
        try:
            declaration = candidate.absolute().relative_to(root).as_posix()
        except ValueError as exc:
            raise RuntimeError("Rendered preview artifact escapes the job root.") from exc
        if project_path_has_symlink_component(root, declaration, purpose="render preview artifact"):
            raise RuntimeError("Rendered preview artifact contains a symlink or reparse-point component.")
        snapshot = snapshot_project_input(root, declaration, purpose="render preview artifact")
        media_type = _PREVIEW_MEDIA_BY_SUFFIX.get(snapshot.path.suffix.lower())
        if media_type is None:
            raise RuntimeError("Rendered preview artifact has an unsupported media type.")
        with open_verified_project_input(
            root,
            declaration,
            expected_snapshot=snapshot,
            purpose="render preview artifact",
        ) as stream:
            opened = os.fstat(stream.fileno())
            if opened.st_size <= 0:
                raise RuntimeError("Rendered preview artifact is empty.")
            head = stream.read(4096)
            if preview_media_type_from_header(head) != media_type:
                raise RuntimeError("Rendered preview artifact header does not match its file extension.")
            digest = hashlib.sha256()
            digest.update(head)
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
            closed = os.fstat(stream.fileno())
            if render_stat_identity(opened) != render_stat_identity(closed):
                raise RuntimeError("Rendered preview artifact changed while it was being sealed.")
        inspected.append(
            (
                snapshot.path.absolute(),
                {
                    "relative_path": declaration,
                    "media_type": media_type,
                    "byte_size": opened.st_size,
                    "sha256": digest.hexdigest(),
                },
            )
        )
    primary_indexes = [index for index, (path, _) in enumerate(inspected) if path == requested_primary]
    if len(primary_indexes) != 1:
        raise RuntimeError("Rendered primary output is not represented exactly once in final figure artifacts.")
    primary_index = primary_indexes[0]
    ordered = [inspected[primary_index], *(item for index, item in enumerate(inspected) if index != primary_index)]
    role_counts: dict[str, int] = {}
    result: list[dict[str, Any]] = []
    for index, (_, entry) in enumerate(ordered):
        if index == 0:
            role = "primary"
        else:
            stem = f"companion:{Path(entry['relative_path']).suffix.lower().lstrip('.')}"
            count = role_counts.get(stem, 0)
            role_counts[stem] = count + 1
            role = stem if count == 0 else f"{stem}:{count + 1}"
        result.append({"logical_role": role, **entry})
    return result


def preview_resource_references(job_id: str, preview_artifacts: list[dict[str, Any]]) -> dict[str, list[str]]:
    artifact_resources: list[str] = []
    preview_resources: list[str] = []
    for index, entry in enumerate(preview_artifacts):
        role = quote(str(entry["logical_role"]), safe="")
        artifact_resources.append(f"figops://jobs/{quote(job_id, safe='')}/artifacts/{role}/{index}")
        preview_resources.append(f"figops://jobs/{quote(job_id, safe='')}/previews/{role}/{index}")
    return {"artifact_resources": artifact_resources, "preview_resources": preview_resources}


def preview_media_type_from_header(head: bytes) -> str:
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(head) >= 12 and head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if b"<svg" in head.lstrip(b"\xef\xbb\xbf\x00\t\r\n ")[:1024].lower():
        return "image/svg+xml"
    return ""


def render_stat_identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns
