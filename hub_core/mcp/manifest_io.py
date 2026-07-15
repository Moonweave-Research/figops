"""Bounded, schema-minimal readers for persisted MCP JSON manifests."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

from hub_core.project_paths import (
    ProjectPathError,
    open_verified_project_input,
    project_path_has_symlink_component,
    revalidate_project_input,
    snapshot_project_input,
)

MCP_MAX_RUNTIME_MANIFEST_BYTES = 16 * 1024 * 1024


def read_json_object_file(path: str | Path, *, max_bytes: int = MCP_MAX_RUNTIME_MANIFEST_BYTES) -> dict[str, Any]:
    """Read a bounded UTF-8 JSON object without exposing file contents on failure."""
    if max_bytes <= 0:
        raise ValueError("Manifest byte limit must be positive.")
    manifest_path = Path(path)
    try:
        if not manifest_path.is_file():
            raise ValueError("Manifest must be a regular file.")
        if manifest_path.stat().st_size > max_bytes:
            raise ValueError(f"Manifest exceeds the {max_bytes}-byte limit.")
        with manifest_path.open("rb") as handle:
            payload = handle.read(max_bytes + 1)
    except OSError as exc:
        raise ValueError("Manifest could not be read safely.") from exc
    if len(payload) > max_bytes:
        raise ValueError(f"Manifest exceeds the {max_bytes}-byte limit.")
    return _parse_json_object(payload)


def read_verified_runtime_json_object(
    runtime_root: str | Path,
    candidate: str | Path,
    *,
    max_bytes: int = MCP_MAX_RUNTIME_MANIFEST_BYTES,
    expected_job_id: str | None = None,
) -> dict[str, Any]:
    """Parse exact manifest bytes through one reparse-free verified descriptor."""

    if max_bytes <= 0:
        raise ValueError("Manifest byte limit must be positive.")
    try:
        root = Path(runtime_root).expanduser().resolve(strict=True)
        raw_candidate = Path(candidate).expanduser().absolute()
    except (OSError, RuntimeError) as exc:
        raise ValueError("Runtime manifest root is unavailable.") from exc
    try:
        declaration = raw_candidate.relative_to(root.absolute()).as_posix()
    except ValueError as exc:
        raise ValueError("Runtime manifest must stay inside the runtime root.") from exc
    try:
        if project_path_has_symlink_component(root, declaration, purpose="runtime manifest"):
            raise ValueError("Runtime manifest must not include symlink or reparse-point components.")
        snapshot = snapshot_project_input(root, declaration, purpose="runtime manifest")
        with open_verified_project_input(
            root,
            declaration,
            expected_snapshot=snapshot,
            purpose="runtime manifest",
        ) as handle:
            opened = os.fstat(handle.fileno())
            if not stat.S_ISREG(opened.st_mode) or opened.st_size <= 0:
                raise ValueError("Manifest must be a non-empty regular file.")
            if opened.st_nlink != 1:
                raise ValueError("Manifest must not be hard-linked.")
            if opened.st_size > max_bytes:
                raise ValueError(f"Manifest exceeds the {max_bytes}-byte limit.")
            payload = handle.read(max_bytes + 1)
            closed = os.fstat(handle.fileno())
        if _stat_identity(opened) != _stat_identity(closed):
            raise ValueError("Runtime manifest changed while it was being read.")
        current = revalidate_project_input(
            root,
            declaration,
            expected_snapshot=snapshot,
            purpose="runtime manifest",
        )
        if project_path_has_symlink_component(root, declaration, purpose="runtime manifest"):
            raise ValueError("Runtime manifest acquired a symlink or reparse-point component.")
        if current.stat().st_nlink != 1:
            raise ValueError("Runtime manifest acquired a hard link.")
    except (FileNotFoundError, OSError, ProjectPathError, RuntimeError) as exc:
        raise ValueError("Manifest could not be read through the trusted runtime boundary.") from exc
    if len(payload) > max_bytes:
        raise ValueError(f"Manifest exceeds the {max_bytes}-byte limit.")
    parsed = _parse_json_object(payload)
    if expected_job_id is not None and parsed.get("job_id") != expected_job_id:
        raise ValueError("Manifest job_id does not match the requested render job.")
    return parsed


def _parse_json_object(payload: bytes) -> dict[str, Any]:
    try:
        decoded = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Manifest is not valid UTF-8.") from exc
    try:
        parsed = json.loads(
            decoded,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_nonfinite_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError("Manifest is not valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Manifest JSON value must be an object.")
    return parsed


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for key, value in pairs:
        if key in parsed:
            raise ValueError("Manifest JSON contains duplicate object keys.")
        parsed[key] = value
    return parsed


def _reject_nonfinite_constant(_value: str) -> None:
    raise ValueError("Manifest JSON contains a non-finite numeric constant.")


def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_mode, value.st_nlink, value.st_size, value.st_mtime_ns


def resolve_runtime_manifest_file(runtime_root: str | Path, candidate: str | Path) -> Path:
    """Resolve a discovered manifest only when every component stays non-symlinked in root."""
    root = Path(runtime_root).expanduser().resolve()
    raw_candidate = Path(candidate).expanduser()
    try:
        relative = raw_candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("Discovered manifest must stay under the runtime root.") from exc
    current = root
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            raise ValueError("Discovered manifest must not include symlinked path components.")
    try:
        resolved = raw_candidate.resolve(strict=True)
    except OSError as exc:
        raise ValueError("Discovered manifest is unavailable.") from exc
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError("Discovered manifest must be a regular file inside the runtime root.")
    return resolved
